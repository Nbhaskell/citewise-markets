"""Removing a company: `python -m jobs.remove_company TICKER` and the web app's Remove button.

"Remove" means stop tracking, not delete: the company is switched off (`instruments.active = false`) and everything stored
about it stays, so adding it again picks up where it left off. Uses the real dev database with ZZRMV (the one removed) and
ZZRMK (the one that must be left alone), and cleans up after itself.
"""
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from ai.copilot import answer_question, company_mentions
from ai.index_filings import vector_literal
from ai.search import search_filings
from api import queries
from api.app import app
from api.deps import get_chat_model, get_embedder, get_sentiment_model
from data.changes import build_changes
from data.db import connect
from jobs import remove_company as rc
from jobs.refresh import LOCK_KEY, AlreadyRunning
from test_copilot import FakeEmbedder, FakeLLM, vec

GO, KEEP = "ZZRMV", "ZZRMK"  # the company that is removed, and the one that stays
SYMS = [GO, KEEP]
LOCAL = {"Origin": "http://localhost:5173", "Content-Type": "application/json"}


@pytest.fixture
def conn():
    with connect() as c:
        for sym, name in ((GO, "Removia Corp."), (KEEP, "Keepsake Corp.")):
            c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, %s)", (sym, name))
            for day in (1, 2):
                c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, %s, 'test')",
                          (sym, date(2026, 1, day), 10 + day))
            c.execute("INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                      "VALUES (%s, %s, '1', '10-K', %s, 'https://x', 't')", (f"0-{sym}-K", sym, date(2026, 1, 1)))
            c.execute("INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
                      "VALUES (%s, 0, 'Item 1A', %s, %s::vector, 'fake')",
                      (f"0-{sym}-K", f"{sym} supply risk", vector_literal(vec(0))))
            c.execute("INSERT INTO news_articles (id, source, title, url, published_at) VALUES (%s, 'test', %s, 'https://x', %s)",
                      (f"zzrm-{sym}", f"{sym} headline", datetime(2026, 1, 2, tzinfo=timezone.utc)))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"zzrm-{sym}", sym))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM news_articles WHERE id LIKE 'zzrm-%'")
        for table in ("filings", "prices_daily", "financial_facts", "instruments"):
            c.execute(f"DELETE FROM {table} WHERE symbol = ANY(%s)", (SYMS,))
        c.commit()


def active(conn, symbol):
    return conn.execute("SELECT active FROM instruments WHERE symbol = %s", (symbol,)).fetchone()[0]


def count(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def hold_lock():
    """Another process holding the database lock, as the nightly refresh does. Returns the connection holding it."""
    other = connect()
    assert other.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]
    other.commit()
    return other


def release_lock(other):
    other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    other.commit()
    other.close()


# --- the command -------------------------------------------------------------

def test_removing_switches_the_company_off_and_keeps_everything_stored(conn):
    result = rc.remove_company(conn, GO)
    assert result.symbol == GO and result.name == "Removia Corp."
    assert active(conn, GO) is False
    assert result.kept == {"prices": 2, "filings": 1, "headlines": 1, "figures": 0}
    # nothing was deleted
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", GO) == 2
    assert count(conn, "SELECT count(*) FROM filings WHERE symbol = %s", GO) == 1
    assert count(conn, "SELECT count(*) FROM filing_chunks WHERE accession_number = %s", f"0-{GO}-K") == 1
    assert count(conn, "SELECT count(*) FROM news_article_symbols WHERE symbol = %s", GO) == 1


def test_removing_one_company_leaves_the_others_alone(conn):
    rc.remove_company(conn, GO)
    assert active(conn, KEEP) is True


def test_a_lowercase_ticker_is_read_like_the_add_command(conn):
    assert rc.remove_company(conn, GO.lower()).symbol == GO


def test_an_unknown_company_is_refused_and_says_so(conn):
    with pytest.raises(rc.NotTracked) as err:
        rc.remove_company(conn, "ZZNONE")
    assert "ZZNONE" in str(err.value) and "isn't a tracked company" in str(err.value)


def test_removing_twice_says_it_is_already_removed(conn):
    rc.remove_company(conn, GO)
    with pytest.raises(rc.NotTracked) as err:
        rc.remove_company(conn, GO)
    assert "already" in str(err.value)
    assert count(conn, "SELECT count(*) FROM prices_daily WHERE symbol = %s", GO) == 2


def test_it_is_refused_while_another_update_holds_the_lock(conn):
    other = hold_lock()
    try:
        with pytest.raises(AlreadyRunning):
            rc.remove_company(conn, GO)
        assert active(conn, GO) is True
    finally:
        release_lock(other)


def test_it_gives_the_lock_back(conn):
    rc.remove_company(conn, GO)
    other = hold_lock()  # would fail if the removal had kept the lock
    release_lock(other)


def test_the_report_says_what_was_kept_and_how_to_undo_it(conn):
    text = rc.format_removal(rc.remove_company(conn, GO))
    assert f"{GO} - Removia Corp." in text and "2 daily prices" in text and "1 filings" in text and "1 headlines" in text
    assert f"python -m jobs.add_company {GO}" in text and "nothing was deleted" in text.lower()


def test_main_removes_and_returns_zero(conn, capsys):
    assert rc.main([GO]) == 0
    assert active(conn, GO) is False
    assert "no longer tracked" in capsys.readouterr().out.lower()


def test_main_returns_one_for_an_untracked_company(conn, capsys):
    assert rc.main(["ZZNONE"]) == 1
    assert "isn't a tracked company" in capsys.readouterr().out


def test_main_returns_three_when_another_update_is_running(conn, capsys):
    other = hold_lock()
    try:
        assert rc.main([GO]) == 3
        assert active(conn, GO) is True
    finally:
        release_lock(other)


def test_main_rejects_something_that_is_not_a_ticker(capsys):
    with pytest.raises(SystemExit):
        rc.main(["not a ticker!"])


# --- a removed company disappears from everything that lists or finds companies -----------------------------------

def test_a_removed_company_is_no_longer_found_by_the_copilot(conn):
    assert set(company_mentions(conn, "Removia and ZZRMK, Keepsake")) == {GO, KEEP}
    rc.remove_company(conn, GO)
    assert set(company_mentions(conn, "Removia and ZZRMV and ZZRMK, Keepsake")) == {KEEP}


def test_filing_search_skips_a_removed_company_even_when_asked_for_it_by_name(conn):
    emb = FakeEmbedder(vec(0))
    assert {r.symbol for r in search_filings(conn, emb, "supply risk", limit=20)} >= {GO, KEEP}
    rc.remove_company(conn, GO)
    assert GO not in {r.symbol for r in search_filings(conn, emb, "supply risk", limit=20)}
    assert search_filings(conn, emb, "supply risk", symbols=[GO], limit=20) == []


def test_asking_the_copilot_about_a_removed_company_says_it_is_not_tracked(conn):
    rc.remove_company(conn, GO)
    for question in ("What are Removia's biggest risks?", "How is ZZRMV stock doing?", "what is the price of removia"):
        llm = FakeLLM("should never be used [1]")
        ans = answer_question(conn, FakeEmbedder(vec(0)), llm, question, limit=3, expand=False)
        assert ans.refused and llm.calls == [], question
        assert "isn't one of the companies tracked here" in ans.text, question
        assert "Add a company" in ans.text, question
        listed = ans.text.split(" tracks (")[1].split(")")[0].split(", ")
        assert GO not in listed and KEEP in listed, question  # the list of tracked companies no longer names it
    still = answer_question(conn, FakeEmbedder(vec(0)), FakeLLM("Risk [1]."), "What are Keepsake's risks?", limit=3, expand=False)
    assert not still.refused and still.symbols == [KEEP]


def test_the_dashboard_queries_skip_a_removed_company(conn):
    assert GO in {r["symbol"] for r in queries.stock_rows(conn)} and GO in queries.tracked_symbols(conn)
    rc.remove_company(conn, GO)
    assert GO not in {r["symbol"] for r in queries.stock_rows(conn)}
    assert GO not in queries.tracked_symbols(conn) and KEEP in queries.tracked_symbols(conn)


def test_what_changed_skips_a_removed_company_even_when_named(conn):
    def filing_symbols():
        out = build_changes(conn, "m", 30, lambda n: {}, symbols=[GO, KEEP], since=date(2025, 12, 1))
        return {f["symbol"] for f in out["filings"]}

    assert filing_symbols() == {GO, KEEP}  # the control: both show while both are tracked
    rc.remove_company(conn, GO)
    assert filing_symbols() == {KEEP}


# --- the web app's endpoint -------------------------------------------------------------------------------------

@pytest.fixture
def client():
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder(vec(0))
    app.dependency_overrides[get_chat_model] = lambda: FakeLLM("x")
    app.dependency_overrides[get_sentiment_model] = lambda: "m"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_endpoint_removes_the_company_and_reports_what_was_kept(conn, client):
    r = client.post("/api/remove-company", json={"ticker": GO.lower()}, headers=LOCAL)
    assert r.status_code == 200
    assert r.json() == {"symbol": GO, "name": "Removia Corp.",
                        "kept": {"prices": 2, "filings": 1, "headlines": 1, "figures": 0},
                        "message": r.json()["message"]}
    assert GO in r.json()["message"] and "Not tracked" in r.json()["message"]
    assert active(conn, GO) is False and active(conn, KEEP) is True
    assert GO not in {s["symbol"] for s in client.get("/api/stocks").json()}
    assert client.get(f"/api/stocks/{GO}").status_code == 404
    assert client.get(f"/api/stocks/{GO}/prices").status_code == 404


def test_the_endpoint_needs_the_local_web_apps_origin_and_json(conn, client):
    assert client.post("/api/remove-company", json={"ticker": GO}).status_code == 403
    assert client.post("/api/remove-company", json={"ticker": GO}, headers={**LOCAL, "Origin": "http://evil.example"}).status_code == 403
    r = client.post("/api/remove-company", content='{"ticker": "%s"}' % GO, headers={**LOCAL, "Content-Type": "text/plain"})
    assert r.status_code == 415
    assert active(conn, GO) is True  # none of the refused requests changed anything


def test_the_endpoint_says_404_for_an_untracked_company_and_409_when_busy(conn, client):
    r = client.post("/api/remove-company", json={"ticker": "ZZNONE"}, headers=LOCAL)
    assert r.status_code == 404 and "isn't a tracked company" in r.json()["detail"]
    other = hold_lock()
    try:
        r = client.post("/api/remove-company", json={"ticker": GO}, headers=LOCAL)
        assert r.status_code == 409 and "Another update is running" in r.json()["detail"]
        assert active(conn, GO) is True
    finally:
        release_lock(other)


def test_the_endpoint_rejects_something_that_is_not_a_ticker(conn, client):
    assert client.post("/api/remove-company", json={"ticker": "no way!"}, headers=LOCAL).status_code == 422


def test_the_add_box_sees_a_removed_company_as_not_tracked(conn, client):
    from api.deps import get_instrument_source
    from data.sources.base import Instrument

    class Source:
        def get_instrument(self, symbol):
            return Instrument(symbol=symbol, name="Removia Corp.", exchange="NMS")

    app.dependency_overrides[get_instrument_source] = lambda: Source()
    assert client.get(f"/api/add-company/lookup?ticker={GO}").json()["tracked"] is True
    rc.remove_company(conn, GO)
    assert client.get(f"/api/add-company/lookup?ticker={GO}").json()["tracked"] is False


# --- the "Not tracked" list the dashboard shows, so a removed company can be switched back on -------------------

def test_the_removed_list_shows_only_removed_companies_in_order(conn, client):
    def listed():
        return [c for c in client.get("/api/removed-companies").json() if c["symbol"] in SYMS]

    assert listed() == []  # nothing removed yet: both are tracked
    rc.remove_company(conn, KEEP)
    rc.remove_company(conn, GO)
    # removed in the opposite order on purpose: the list is sorted by ticker (ZZRMK before ZZRMV), not by when it was removed
    assert listed() == [{"symbol": KEEP, "name": "Keepsake Corp."}, {"symbol": GO, "name": "Removia Corp."}]
    assert [c["symbol"] for c in queries.removed_companies(conn) if c["symbol"] in SYMS] == [KEEP, GO]


def test_a_company_switched_back_on_leaves_the_removed_list(conn, client):
    rc.remove_company(conn, GO)
    assert GO in {c["symbol"] for c in client.get("/api/removed-companies").json()}
    conn.execute("UPDATE instruments SET active = true WHERE symbol = %s", (GO,))  # what a finished add does
    conn.commit()
    assert GO not in {c["symbol"] for c in client.get("/api/removed-companies").json()}
    assert GO in {s["symbol"] for s in client.get("/api/stocks").json()}
