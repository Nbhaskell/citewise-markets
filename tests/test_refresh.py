import json
from datetime import date, datetime, timedelta, timezone

import pytest

import jobs.refresh as refresh
from jobs.refresh import AlreadyRunning, Deps, LOCK_KEY, active_symbols, choose_period, run_refresh, summarize
from jobs.status import print_status
from data.db import connect
from data.sources.base import Instrument, NewsItem, PriceBar
from data.sources.edgar import FilingRef

A, B = "ZZREF", "ZZREG"
TODAY = date(2026, 10, 12)


class FakePrices:
    name = "fake"

    def __init__(self, fail=()):
        self.fail, self.periods = set(fail), []

    def get_instrument(self, symbol):
        if symbol in self.fail:
            raise RuntimeError("price feed down")
        return Instrument(symbol=symbol, name=f"{symbol} Co")

    def get_daily_bars(self, symbol, period="5y"):
        self.periods.append((symbol, period))
        return [PriceBar(symbol, TODAY - timedelta(days=d), 1, 1, 1, 1 + d, 1, 10) for d in (5, 4, 3)]


class FakeNews:
    name = "fake"

    def get_news(self, symbol, company_name, days=7):
        ts = datetime(2026, 10, 10, tzinfo=timezone.utc)
        return [NewsItem(f"fake:zzr-{symbol}-{i}", "fake", symbol, f"{symbol} beats {i}", "Wire", "https://x", ts) for i in (1, 2)]


class FakeEdgar:
    def cik_for_ticker(self, symbol):
        return "0000000009"

    def list_filings(self, cik, forms, limit):
        return [FilingRef(f"0-ZZR-{cik}", cik, "10-K", date(2026, 1, 2), date(2025, 12, 31), "https://x/k.htm")]

    def fetch_text(self, ref):
        return "\n".join(f"Item 1.\nrow {i} " + "z" * 80 for i in range(30))

    def company_facts(self, cik):
        row = {"start": "2025-01-01", "end": "2025-12-31", "val": 1000, "accn": "0-ZZR-FACT", "form": "10-K", "filed": "2026-01-30"}
        return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [row]}}}}}


class FakeEmbedder:
    name = "fake-emb"
    dim = 384

    def embed_documents(self, texts):
        return [[1.0] + [0.0] * 383 for _ in texts]


class FakeLLM:
    name = "fake-llm"

    def __init__(self, up=True):
        self.up = up

    def available(self):
        return self.up

    def generate(self, system, user, json_schema=None):
        lines = user.split("Headlines:\n")[1].splitlines()
        return json.dumps({"results": [{"id": int(l.split(".")[0]), "sentiment": "positive"} for l in lines]})


def make_deps(**kw):
    base = dict(price_source=FakePrices(), news_source=FakeNews(), edgar_factory=FakeEdgar,
                embedder_factory=FakeEmbedder, embedder_name="fake-emb", llm=FakeLLM())
    base.update(kw)
    return Deps(**base)


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setattr(refresh, "JOB_NAME", "test_refresh")
    with connect() as c:
        yield c
        c.rollback()
        c.execute("DELETE FROM job_runs WHERE job = 'test_refresh'")
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzr-%'")
        c.execute("DELETE FROM filings WHERE symbol = ANY(%s)", ([A, B],))
        c.execute("DELETE FROM financial_facts WHERE symbol = ANY(%s)", ([A, B],))
        c.execute("DELETE FROM prices_daily WHERE symbol = ANY(%s)", ([A, B],))
        c.execute("DELETE FROM instruments WHERE symbol = ANY(%s)", ([A, B],))
        c.commit()


def count(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def by_step(report, step):
    return [r for r in report.results if r.step == step]


def test_full_run_fills_every_table_and_logs_the_run(conn):
    report = run_refresh(conn, make_deps(), [A], today=TODAY)
    assert report.status == "success" and [r.status for r in report.results] == ["ok"] * 6
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 3
    assert count(conn, "SELECT count(*) FROM news_article_symbols WHERE symbol = %s", A) == 2
    assert count(conn, "SELECT count(*) FROM filings WHERE symbol = %s", A) == 1
    assert count(conn, "SELECT count(*) FROM filing_chunks c JOIN filings f USING (accession_number) WHERE f.symbol = %s", A) > 1
    assert count(conn, "SELECT count(*) FROM news_sentiment WHERE symbol = %s AND model = 'fake-llm'", A) == 2
    status, finished, details = conn.execute("SELECT status, finished_at, details FROM job_runs WHERE id = %s", (report.run_id,)).fetchone()
    assert status == "success" and finished is not None and len(details) == 6


def test_second_run_finds_nothing_new_and_only_asks_for_recent_prices(conn):
    prices = FakePrices()
    run_refresh(conn, make_deps(price_source=prices), [A], today=TODAY)
    second = run_refresh(conn, make_deps(price_source=prices), [A], today=TODAY)
    assert second.status == "success"
    assert [(r.step, r.count) for r in second.results if r.step in ("news", "filings", "index", "sentiment")] == [
        ("news", 0), ("filings", 0), ("index", 0), ("sentiment", 0)]
    assert prices.periods == [(A, "5y"), (A, "1mo")]  # first run: no history; second: short gap


def test_one_failing_company_does_not_stop_the_others(conn):
    report = run_refresh(conn, make_deps(price_source=FakePrices(fail=[B])), [A, B], today=TODAY)
    assert report.status == "partial"
    assert [r.status for r in by_step(report, "prices")] == ["ok", "error"]
    assert "price feed down" in by_step(report, "prices")[1].detail
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 3
    assert count(conn, "SELECT count(*) FROM news_article_symbols WHERE symbol = %s", A) == 2
    assert count(conn, "SELECT count(*) FROM job_runs WHERE id = %s AND status = 'partial'", report.run_id) == 1


def test_a_never_stored_ticker_whose_prices_fail_is_left_out_of_the_later_steps(conn):
    report = run_refresh(conn, make_deps(price_source=FakePrices(fail=[B])), [A, B], today=TODAY)
    assert {(r.step, r.symbol) for r in report.results if r.symbol == B} == {("prices", B)}  # no "not in instruments" noise
    assert ("news", A) in {(r.step, r.symbol) for r in report.results}


def test_a_stored_company_whose_prices_fail_still_gets_the_other_steps(conn):
    run_refresh(conn, make_deps(), [A], today=TODAY)
    report = run_refresh(conn, make_deps(price_source=FakePrices(fail=[A])), [A], today=TODAY)
    assert [(r.step, r.status) for r in report.results if r.symbol == A] == [
        ("prices", "error"), ("news", "ok"), ("filings", "ok"), ("fundamentals", "ok"), ("sentiment", "ok")]


def test_the_job_name_can_be_chosen_for_a_run(conn):
    report = run_refresh(conn, make_deps(), [A], steps=("prices",), today=TODAY, job="test_refresh_other")
    try:
        assert count(conn, "SELECT job FROM job_runs WHERE id = %s", report.run_id) == "test_refresh_other"
    finally:
        conn.execute("DELETE FROM job_runs WHERE job = 'test_refresh_other'")
        conn.commit()


def test_everything_failing_is_reported_as_failed(conn):
    report = run_refresh(conn, make_deps(price_source=FakePrices(fail=[A])), [A], steps=("prices",), today=TODAY)
    assert report.status == "failed" and report.results[0].status == "error"


def test_model_steps_are_skipped_not_failed_when_ollama_is_down(conn):
    report = run_refresh(conn, make_deps(llm=FakeLLM(up=False)), [A], today=TODAY)
    sentiment = by_step(report, "sentiment")
    assert report.status == "partial" and [r.status for r in sentiment] == ["skipped"]
    assert "Ollama" in sentiment[0].detail
    assert count(conn, "SELECT count(*) FROM news_sentiment WHERE symbol = %s", A) == 0
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 3  # the rest still ran


def test_filings_are_skipped_without_an_sec_contact(conn):
    report = run_refresh(conn, make_deps(edgar_factory=lambda: None), [A], today=TODAY)
    assert [r.status for r in by_step(report, "filings")] == ["skipped"]
    assert "SEC_USER_AGENT" in by_step(report, "filings")[0].detail and report.status == "partial"


def test_embedding_model_failing_to_load_skips_indexing(conn):
    def broken():
        raise RuntimeError("no model files")

    report = run_refresh(conn, make_deps(embedder_factory=broken), [A], today=TODAY)
    assert [r.status for r in by_step(report, "index")] == ["skipped"]


def test_only_the_requested_steps_run(conn):
    conn.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Only News Co')", (A,))
    conn.commit()
    report = run_refresh(conn, make_deps(), [A], steps=("news",), today=TODAY)
    assert [r.step for r in report.results] == ["news"] and report.status == "success"
    assert count(conn, "SELECT count(*) FROM news_article_symbols WHERE symbol = %s", A) == 2
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 0
    assert count(conn, "SELECT count(*) FROM filings WHERE symbol = %s", A) == 0


def test_a_second_run_cannot_start_while_one_is_in_progress(conn):
    with connect() as other:
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        with pytest.raises(AlreadyRunning):
            run_refresh(conn, make_deps(), [A], steps=("prices",), today=TODAY)
        assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 0  # nothing ran
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    conn.rollback()
    assert run_refresh(conn, make_deps(), [A], steps=("prices",), today=TODAY).status == "success"  # lock was released


def test_lock_is_released_after_a_run_even_if_it_fails(conn):
    run_refresh(conn, make_deps(price_source=FakePrices(fail=[A])), [A], steps=("prices",), today=TODAY)
    with connect() as other:
        assert other.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0] is True
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def test_active_symbols_skips_inactive_companies(conn):
    conn.execute("INSERT INTO instruments (symbol, name, active) VALUES (%s, 'x', true), (%s, 'y', false)", (A, B))
    conn.commit()
    symbols = active_symbols(conn)
    assert A in symbols and B not in symbols


@pytest.mark.parametrize("last,expected", [
    (None, "5y"), (date(2026, 10, 10), "1mo"), (date(2026, 9, 17), "1mo"), (date(2026, 9, 16), "3mo"),
    (date(2026, 7, 20), "3mo"), (date(2026, 5, 1), "6mo"), (date(2025, 12, 1), "1y"), (date(2024, 1, 1), "5y"),
])
def test_choose_period_covers_the_gap(last, expected):
    assert choose_period(last, TODAY) == expected


def test_summary_and_status_report_are_readable(conn, capsys):
    report = run_refresh(conn, make_deps(llm=FakeLLM(up=False)), [A], today=TODAY)
    text = summarize(report)
    assert "PARTIAL" in text and "prices       3 bars refreshed" in text
    assert "1 problem(s)" in text and "skipped" in text and "Ollama" in text
    print_status(conn, "fake-emb", "fake-llm")
    out = capsys.readouterr().out
    assert "Recent runs" in out and "Data freshness:" in out and A in out


# ---- desktop alerts ----

class Alerts:
    """Stands in for the desktop notification and remembers what it was asked to show."""

    def __init__(self):
        self.shown = []

    def __call__(self, title, body):
        self.shown.append((title, body))


@pytest.fixture
def quiet_main(monkeypatch):
    monkeypatch.setattr(refresh, "setup_logging", lambda: None)  # don't write to the real logs/refresh.log


def test_alert_message_names_the_steps_that_had_problems(conn):
    report = run_refresh(conn, make_deps(price_source=FakePrices(fail=[B]), llm=FakeLLM(up=False)), [A, B], today=TODAY)
    title, body = refresh.alert_message(report)
    assert title == "Nightly refresh: PARTIAL"
    assert "prices: 1 failed" in body and "sentiment: skipped - the local AI model isn't reachable" in body
    assert "index:" not in body  # a step with no problems stays out of it
    only_models = run_refresh(conn, make_deps(llm=FakeLLM(up=False)), [A], steps=("index", "sentiment"), today=TODAY)
    assert refresh.alert_message(only_models)[1].startswith("sentiment: skipped - ")


def test_a_clean_run_shows_no_alert(conn, monkeypatch, quiet_main):
    monkeypatch.setattr(refresh, "default_deps", make_deps)
    alerts = Alerts()
    assert refresh.main(["--symbols", A], notify=alerts) == 0
    assert alerts.shown == []


def test_a_run_with_problems_shows_one_alert(conn, monkeypatch, quiet_main):
    monkeypatch.setattr(refresh, "default_deps", lambda: make_deps(llm=FakeLLM(up=False)))
    alerts = Alerts()
    assert refresh.main(["--symbols", A], notify=alerts) == 1
    assert len(alerts.shown) == 1 and alerts.shown[0][0] == "Nightly refresh: PARTIAL"


def test_no_alert_flag_silences_alerts(conn, monkeypatch, quiet_main):
    monkeypatch.setattr(refresh, "default_deps", lambda: make_deps(llm=FakeLLM(up=False)))
    alerts = Alerts()
    assert refresh.main(["--symbols", A, "--no-alert"], notify=alerts) == 1
    assert alerts.shown == []


def test_an_unreachable_database_shows_an_alert(monkeypatch, quiet_main):
    def down():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(refresh, "connect", down)
    alerts = Alerts()
    assert refresh.main([], notify=alerts) == 2
    assert len(alerts.shown) == 1 and "Docker" in alerts.shown[0][1]


def test_a_crash_shows_an_alert_and_exit_code_4(conn, monkeypatch, quiet_main):
    def boom(*args, **kwargs):
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(refresh, "default_deps", make_deps)
    monkeypatch.setattr(refresh, "run_refresh", boom)
    alerts = Alerts()
    assert refresh.main(["--symbols", A], notify=alerts) == 4
    assert len(alerts.shown) == 1 and "something unexpected" in alerts.shown[0][1]


def test_another_run_in_progress_is_not_an_alert(conn, monkeypatch, quiet_main):
    monkeypatch.setattr(refresh, "default_deps", make_deps)
    alerts = Alerts()
    with connect() as other:
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        assert refresh.main(["--symbols", A], notify=alerts) == 3
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    assert alerts.shown == []


def test_a_notification_that_fails_never_raises(monkeypatch):
    import jobs.notify as notify

    def broken(*args, **kwargs):
        raise OSError("powershell not found")

    monkeypatch.setattr(notify.subprocess, "run", broken)
    assert notify.send_notification("t", "b") is False


def test_database_connections_give_up_instead_of_hanging(monkeypatch):
    import data.db as db

    seen = {}
    monkeypatch.setattr(db.psycopg, "connect", lambda url, **kw: seen.update(kw))
    db.connect()
    assert 0 < seen["connect_timeout"] <= 30
