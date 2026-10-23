from datetime import date

import pytest

import jobs.add_company as add_company
import jobs.refresh as refresh
from data.db import connect
from data.sources.edgar import FilingRef
from jobs.add_company import add_companies, format_outcome, normalize_ticker
from jobs.refresh import AlreadyRunning, LOCK_KEY
from test_refresh import FakeEdgar, FakeLLM, FakeNews, FakePrices, make_deps

A, B = "ZZADD", "ZZADE"


class CountingNews(FakeNews):
    def __init__(self):
        self.calls = []

    def get_news(self, symbol, company_name, days=7):
        self.calls.append(symbol)
        return super().get_news(symbol, company_name, days)


class ForeignFilerEdgar(FakeEdgar):
    """Like TSM or ASML: no 10-K or 10-Q at the SEC, but a 20-F."""

    def list_filings(self, cik, forms, limit):
        if "20-F" in forms:
            return [FilingRef("0-ZZR-20F", cik, "20-F", date(2026, 4, 16), date(2025, 12, 31), "https://x/f.htm")]
        return []

    def company_facts(self, cik):  # the international accounting vocabulary: no US-GAAP figures at all
        row = {"start": "2024-01-01", "end": "2024-12-31", "val": 1, "accn": "x", "form": "20-F", "filed": "2025-04-17"}
        return {"facts": {"ifrs-full": {"Revenue": {"units": {"TWD": [row]}}}}}


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setattr(add_company, "ADD_JOB", "test_add_company")
    with connect() as c:
        yield c
        c.rollback()
        c.execute("DELETE FROM job_runs WHERE job = 'test_add_company'")
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzr-ZZAD%'")
        for table in ("filings", "financial_facts", "prices_daily", "instruments"):
            c.execute(f"DELETE FROM {table} WHERE symbol = ANY(%s)", ([A, B],))
        c.commit()


def count(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def lines(outcome):
    return {step: (status, text) for step, status, text in outcome.lines}


def test_a_new_company_gets_every_step_and_a_clean_report(conn):
    nightly_before = count(conn, "SELECT count(*) FROM job_runs WHERE job = 'nightly_refresh'")
    report, (out,) = add_companies(conn, make_deps(), [A])
    assert out.complete and out.verdict == "ADDED" and out.name == f"{A} Co"
    assert [lines(out)[s][0] for s in refresh.STEPS] == ["OK"] * 6
    assert count(conn, "SELECT count(*) FROM financial_facts WHERE symbol = %s", A) == 1
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 3
    assert count(conn, "SELECT count(*) FROM filings WHERE symbol = %s", A) == 1
    assert "1 of 1 filings searchable" in lines(out)["index"][1]
    assert "2 headlines labeled" in lines(out)["sentiment"][1]
    # logged under its own name, so the nightly history and status are untouched
    assert count(conn, "SELECT count(*) FROM job_runs WHERE id = %s AND job = 'test_add_company'", report.run_id) == 1
    assert count(conn, "SELECT count(*) FROM job_runs WHERE job = 'nightly_refresh'") == nightly_before
    assert "=> ADDED" in format_outcome(out)


def test_an_unknown_ticker_stores_nothing_and_does_not_try_the_other_steps(conn):
    news = CountingNews()
    _, (out,) = add_companies(conn, make_deps(price_source=FakePrices(fail=[A]), news_source=news), [A])
    assert not out.stored and not out.complete and out.verdict == "NOT ADDED"
    assert lines(out)["prices"][0] == "FAILED" and "price feed down" in lines(out)["prices"][1]
    assert [lines(out)[s][0] for s in refresh.STEPS[1:]] == ["--"] * 5
    assert news.calls == [] and count(conn, "SELECT count(*) FROM instruments WHERE symbol = %s", A) == 0


def test_a_foreign_filer_is_added_but_reported_as_having_no_filings(conn):
    _, (out,) = add_companies(conn, make_deps(edgar_factory=ForeignFilerEdgar), [A])
    assert out.stored and not out.complete and out.verdict == "ADDED, WITH GAPS"
    status, text = lines(out)["filings"]
    assert status == "NONE" and "20-F" in text and "only 10-K and 10-Q" in text
    assert "no filings stored" in out.gaps
    assert lines(out)["prices"][0] == "OK" and lines(out)["sentiment"][0] == "OK"  # the rest still works
    status, text = lines(out)["fundamentals"]
    assert status == "NONE" and "no US-GAAP figures" in text and "no fundamentals stored" in out.gaps


def test_no_filings_for_other_reasons_does_not_claim_a_foreign_filer(conn):
    class Nothing(FakeEdgar):
        def list_filings(self, cik, forms, limit):
            return []

    _, (out,) = add_companies(conn, make_deps(edgar_factory=Nothing), [A])
    status, text = lines(out)["filings"]
    assert status == "NONE" and "20-F" not in text and "no 10-K or 10-Q on file" in text


def test_a_failing_step_is_a_visible_gap_and_the_rest_still_run(conn):
    class BrokenNews(FakeNews):
        def get_news(self, symbol, company_name, days=7):
            raise RuntimeError("feed changed")

    _, (out,) = add_companies(conn, make_deps(news_source=BrokenNews()), [A])
    assert out.stored and not out.complete and "news failed" in out.gaps
    assert lines(out)["news"] == ("FAILED", "RuntimeError: feed changed")
    assert lines(out)["filings"][0] == "OK"


def test_missing_ollama_and_sec_contact_are_reported_as_skipped(conn):
    _, (out,) = add_companies(conn, make_deps(llm=FakeLLM(up=False), edgar_factory=lambda: None), [A])
    assert out.stored and lines(out)["sentiment"][0] == "SKIPPED" and "Ollama" in lines(out)["sentiment"][1]
    assert lines(out)["filings"][0] == "SKIPPED" and "SEC_USER_AGENT" in lines(out)["filings"][1]
    assert not out.complete


class SkippingLLM(FakeLLM):
    """Labels only the first headline of each batch, like the local model sometimes does."""

    def generate(self, system, user, json_schema=None):
        import json
        lines = user.split("Headlines:\n")[1].splitlines()[:1]
        return json.dumps({"results": [{"id": int(line.split(".")[0]), "sentiment": "positive"} for line in lines]})


class NothingLLM(FakeLLM):
    def generate(self, system, user, json_schema=None):
        return "not json"


def test_a_few_unlabeled_headlines_are_a_note_but_none_labeled_is_a_gap(conn):
    _, (some,) = add_companies(conn, make_deps(llm=SkippingLLM()), [A])
    assert "1 headlines labeled, 1 unlabeled" in lines(some)["sentiment"][1] and some.complete
    conn.execute("DELETE FROM news_sentiment WHERE symbol = %s", (A,))
    conn.commit()
    _, (none,) = add_companies(conn, make_deps(llm=NothingLLM()), [A])
    assert "no headlines were labeled" in none.gaps and not none.complete


def test_a_company_with_no_headlines_says_so(conn):
    class Quiet(FakeNews):
        def get_news(self, symbol, company_name, days=7):
            return []

    _, (out,) = add_companies(conn, make_deps(news_source=Quiet()), [A])
    assert "no headlines found" in lines(out)["news"][1] and out.complete


def test_adding_a_tracked_company_again_refreshes_it_and_switches_it_back_on(conn):
    add_companies(conn, make_deps(), [A])
    conn.execute("UPDATE instruments SET active = false WHERE symbol = %s", (A,))
    conn.commit()
    _, (out,) = add_companies(conn, make_deps(), [A])
    assert out.already_tracked and out.turned_back_on and out.complete and out.verdict == "UPDATED"
    assert count(conn, "SELECT active FROM instruments WHERE symbol = %s", A) is True
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", A) == 3  # upserted, not doubled
    text = format_outcome(out)
    assert "already tracked" in text and "switched back on" in text


def test_two_tickers_are_reported_separately(conn):
    _, outs = add_companies(conn, make_deps(price_source=FakePrices(fail=[B])), [A, B])
    assert [(o.symbol, o.stored) for o in outs] == [(A, True), (B, False)]
    assert outs[0].complete and outs[0].verdict == "ADDED"
    assert outs[1].verdict == "NOT ADDED" and lines(outs[1])["prices"][0] == "FAILED"


def test_it_refuses_to_run_while_another_refresh_holds_the_lock(conn):
    with connect() as other:
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        with pytest.raises(AlreadyRunning):
            add_companies(conn, make_deps(), [A])
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    conn.rollback()
    assert count(conn, "SELECT count(*) FROM instruments WHERE symbol = %s", A) == 0


@pytest.mark.parametrize("raw,expected", [("amd", "AMD"), (" TSM ", "TSM"), ("brk.b", "BRK-B"), ("BRK-B", "BRK-B")])
def test_tickers_are_tidied(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "^GSPC", "A B", "0700.HK", "AAPL;DROP", "TOOLONGTICKER"])
def test_odd_tickers_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_ticker(raw)


# ---- the command ----

@pytest.fixture
def cli(conn, monkeypatch):
    monkeypatch.setattr(add_company, "setup_logging", lambda: None)  # don't write to the real logs/refresh.log
    return conn


def test_main_exits_0_and_prints_the_report_when_all_went_well(cli, monkeypatch, capsys):
    monkeypatch.setattr(add_company, "default_deps", make_deps)
    assert add_company.main(["zzadd"]) == 0
    out = capsys.readouterr().out
    assert "ZZADD - ZZADD Co" in out and "=> ADDED" in out and "GAPS" not in out


def test_main_exits_1_when_there_are_gaps(cli, monkeypatch, capsys):
    monkeypatch.setattr(add_company, "default_deps", lambda: make_deps(edgar_factory=ForeignFilerEdgar))
    assert add_company.main([A]) == 1
    assert "ADDED, WITH GAPS" in capsys.readouterr().out


def test_main_exits_3_when_a_refresh_is_running(cli, monkeypatch, capsys):
    monkeypatch.setattr(add_company, "default_deps", make_deps)
    with connect() as other:
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        assert add_company.main([A]) == 3
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    assert "ADDED" not in capsys.readouterr().out


def test_main_exits_2_when_the_database_is_down(monkeypatch):
    def down():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(add_company, "setup_logging", lambda: None)
    monkeypatch.setattr(add_company, "connect", down)
    assert add_company.main(["AMD"]) == 2


def test_main_exits_4_when_it_crashes(cli, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(add_company, "default_deps", make_deps)
    monkeypatch.setattr(add_company, "add_companies", boom)
    assert add_company.main([A]) == 4


def test_main_rejects_a_bad_ticker_before_touching_the_database(monkeypatch):
    def never():
        raise AssertionError("should not connect")

    monkeypatch.setattr(add_company, "connect", never)
    with pytest.raises(SystemExit) as exc:
        add_company.main(["^GSPC"])
    assert exc.value.code == 2
