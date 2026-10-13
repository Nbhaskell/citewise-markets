import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from ai.index_filings import vector_literal
from api.app import app
from api.deps import get_chat_model, get_embedder, get_sentiment_model
from data.db import connect

SYM = "ZZAPI"
LATEST = date(2026, 10, 9)
MODEL = "fake-llm"


def vec(i):
    v = [0.0] * 384
    v[i] = 1.0
    return v


class FakeEmbedder:
    name = "fake-emb"
    dim = 384

    def embed_query(self, text):
        return vec(0)


class FakeLLM:
    name = MODEL

    def __init__(self, up=True, reply="Zeta has supply risk [1]."):
        self.up, self.reply, self.calls = up, reply, 0

    def available(self):
        return self.up

    def generate(self, system, user, json_schema=None):
        self.calls += 1
        return self.reply


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(llm):
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_chat_model] = lambda: llm
    app.dependency_overrides[get_sentiment_model] = lambda: MODEL
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module", autouse=True)
def seeded():
    now = datetime.now(timezone.utc)
    with connect() as c:
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYM,))  # leftovers from an interrupted run
        c.execute(
            "INSERT INTO instruments (symbol, name, sector, industry, exchange) "
            "VALUES (%s, 'Zeta API Co', 'Tech', 'Software', 'NMS')", (SYM,))
        for k in range(400):  # 400 days of prices ending LATEST; close rises by 1 a day, last two are 500 and 499
            d = LATEST - timedelta(days=399 - k)
            close = 100 + k
            c.execute(
                "INSERT INTO prices_daily (symbol, ts, open, high, low, close, adj_close, volume, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 1000, 'fake')",
                (SYM, d, close, close + 2, close - 2, close, close))
        for key, title, label, days_ago in [("a", "Zeta wins big deal", "positive", 1), ("b", "Zeta faces probe", "negative", 2),
                                           ("c", "Zeta quote page", "neutral", 3), ("d", "Unrelated other firm", "irrelevant", 4),
                                           ("e", "Zeta unscored story", None, 5), ("f", "Old Zeta story", "positive", 60)]:
            c.execute(
                "INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                "VALUES (%s, 'fake', %s, 'Wire', 'https://x', %s)", (f"fake:zzapi-{key}", title, now - timedelta(days=days_ago)))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"fake:zzapi-{key}", SYM))
            if label:
                c.execute("INSERT INTO news_sentiment (article_id, symbol, label, model) VALUES (%s, %s, %s, %s)",
                          (f"fake:zzapi-{key}", SYM, label, MODEL))
        for acc, form, filed in [("0-ZZAPI-K", "10-K", date(2026, 2, 1)), ("0-ZZAPI-Q", "10-Q", date(2026, 8, 1))]:
            c.execute(
                "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, period_of_report, url, text) "
                "VALUES (%s, %s, '1', %s, %s, %s, 'https://sec.example/f', 't')", (acc, SYM, form, filed, filed))
        c.execute(
            "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
            "VALUES ('0-ZZAPI-K', 0, 'Part I, Item 1A', 'Supply chain risk text for Zeta.', %s::vector, 'fake-emb')",
            (vector_literal(vec(0)),))
        c.commit()
    yield
    with connect() as c:
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzapi-%'")
        c.execute("DELETE FROM filings WHERE symbol = %s", (SYM,))
        c.execute("DELETE FROM prices_daily WHERE symbol = %s", (SYM,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYM,))
        c.commit()


def test_health_reports_database_and_model(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "database": True, "ai_model": MODEL, "ai_model_available": True}


def test_health_shows_when_the_model_is_down(client, llm):
    llm.up = False
    assert client.get("/health").json()["ai_model_available"] is False


def test_stock_list_has_price_change_and_sentiment(client):
    stocks = {s["symbol"]: s for s in client.get("/api/stocks").json()}
    z = stocks[SYM]
    assert z["name"] == "Zeta API Co" and z["last_price"] == 499 and z["as_of"] == str(LATEST)
    assert z["change"] == 1 and z["change_pct"] == pytest.approx(1 / 498 * 100, abs=1e-3)
    # last 7 days: positive, negative, neutral, irrelevant; the 60-day-old story and unscored one don't count
    assert z["sentiment"] == {"days": 7, "positive": 1, "neutral": 1, "negative": 1, "irrelevant": 1, "score": 0.0}


def test_stock_detail_adds_52_week_range(client):
    d = client.get(f"/api/stocks/{SYM.lower()}").json()
    assert d["symbol"] == SYM and d["exchange"] == "NMS" and d["currency"] == "USD" and d["volume"] == 1000
    # closes are 100..499 over 400 days; the 365-day window starts at the 35th bar (close 134, low 132)
    assert d["high_52w"] == 501 and d["low_52w"] == 132
    assert d["sentiment"]["positive"] == 1 and d["last_price"] == 499


def test_unknown_company_is_404_and_bad_symbol_is_422(client):
    assert client.get("/api/stocks/NOPE").status_code == 404
    assert "not a tracked company" in client.get("/api/stocks/NOPE").json()["detail"]
    assert client.get("/api/stocks/bad$sym").status_code == 422
    assert client.get("/api/stocks/NOPE/prices").status_code == 404


@pytest.mark.parametrize("rng,expected_points", [("1M", 32), ("3M", 93), ("1Y", 367), ("MAX", 400)])
def test_price_ranges_end_at_the_latest_bar(client, rng, expected_points):
    body = client.get(f"/api/stocks/{SYM}/prices", params={"range": rng}).json()
    assert body["range"] == rng and len(body["points"]) == expected_points
    assert body["points"][-1] == {"date": str(LATEST), "open": 499, "high": 501, "low": 497, "close": 499, "volume": 1000}
    assert [p["date"] for p in body["points"]] == sorted(p["date"] for p in body["points"])


def test_price_range_is_validated(client):
    assert client.get(f"/api/stocks/{SYM}/prices", params={"range": "7Y"}).status_code == 422
    assert len(client.get(f"/api/stocks/{SYM}/prices").json()["points"]) == 367  # default 1Y


def test_news_hides_irrelevant_and_old_items_by_default(client):
    items = client.get(f"/api/stocks/{SYM}/news").json()
    assert [i["title"] for i in items] == ["Zeta wins big deal", "Zeta faces probe", "Zeta quote page", "Zeta unscored story"]
    assert items[0]["sentiment"] == "positive" and items[-1]["sentiment"] is None
    everything = client.get(f"/api/stocks/{SYM}/news", params={"include_irrelevant": True, "days": 90}).json()
    assert len(everything) == 6
    assert len(client.get(f"/api/stocks/{SYM}/news", params={"limit": 2}).json()) == 2
    assert client.get(f"/api/stocks/{SYM}/news", params={"limit": 500}).status_code == 422


def test_news_feed_spans_companies_and_filters(client):
    default = client.get("/api/news", params={"symbol": SYM}).json()  # dashboard default: last 3 days
    assert [i["title"] for i in default] == ["Zeta wins big deal", "Zeta faces probe"]
    feed = client.get("/api/news", params={"symbol": SYM.lower(), "days": 7}).json()
    assert [(i["symbol"], i["title"]) for i in feed] == [
        (SYM, "Zeta wins big deal"), (SYM, "Zeta faces probe"), (SYM, "Zeta quote page"), (SYM, "Zeta unscored story")]
    assert feed[0]["sentiment"] == "positive" and feed[0]["publisher"] == "Wire"
    only = client.get("/api/news", params={"symbol": SYM, "days": 7, "sentiment": ["positive", "negative"]}).json()
    assert [i["title"] for i in only] == ["Zeta wins big deal", "Zeta faces probe"]
    assert len(client.get("/api/news", params={"symbol": SYM, "days": 90, "include_irrelevant": True}).json()) == 6
    assert len(client.get("/api/news", params={"symbol": SYM, "limit": 1}).json()) == 1
    several = client.get("/api/news", params={"symbol": [SYM, "NOPE"], "days": 7}).json()  # repeatable filter
    assert {i["symbol"] for i in several} == {SYM}  # a ticker with no headlines just matches nothing
    everyone = client.get("/api/news", params={"limit": 100}).json()  # no filter: every active company
    assert len(everyone) <= 100 and all(i["symbol"] for i in everyone)
    assert [i["published_at"] for i in everyone] == sorted((i["published_at"] for i in everyone), reverse=True)


@pytest.fixture
def duplicated_news():
    """ZZDUP has one story carried by three outlets (one adding " - Wire" to the title), a second story carried
    twice, and a third once. ZZAPI shares the first story, which is allowed to appear once for each company."""
    now = datetime.now(timezone.utc)
    rows = [  # (key, symbol, title, publisher, hours_ago)
        ("a1", "ZZDUP", "Dup Co lands a big deal", "Yahoo", 1),
        ("a2", "ZZDUP", "Dup Co lands a big deal", "TradingView", 2),
        ("a3", "ZZDUP", "dup co lands  a big deal - Wire", "Wire", 3),
        ("b1", "ZZDUP", "Dup Co faces a probe", "Yahoo", 4),
        ("b2", "ZZDUP", "Dup Co faces a probe", "Wire", 5),
        ("c1", "ZZDUP", "Dup Co opens a plant", "Wire", 6),
        ("a4", SYM, "Dup Co lands a big deal", "Yahoo", 7),
    ]
    with connect() as c:
        c.execute("DELETE FROM instruments WHERE symbol = 'ZZDUP'")
        c.execute("INSERT INTO instruments (symbol, name, sector, industry, exchange) "
                  "VALUES ('ZZDUP', 'Dup Co', 'Tech', 'Software', 'NMS')")
        for key, sym, title, publisher, hours in rows:
            aid = f"fake:zzapi-dup-{key}"
            c.execute("INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                      "VALUES (%s, 'fake', %s, %s, %s, %s)", (aid, title, publisher, f"https://x/{key}", now - timedelta(hours=hours)))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (aid, sym))
        c.commit()
    yield
    with connect() as c:
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzapi-dup-%'")
        c.execute("DELETE FROM instruments WHERE symbol = 'ZZDUP'")
        c.commit()


def test_company_news_shows_each_story_once_keeping_the_newest_copy(client, duplicated_news):
    items = client.get("/api/stocks/ZZDUP/news").json()
    assert [(i["title"], i["publisher"]) for i in items] == [
        ("Dup Co lands a big deal", "Yahoo"), ("Dup Co faces a probe", "Yahoo"), ("Dup Co opens a plant", "Wire")]
    # repeats must not use up the limit: asking for 2 gives 2 different stories, not 2 copies of the first
    two = client.get("/api/stocks/ZZDUP/news", params={"limit": 2}).json()
    assert [i["title"] for i in two] == ["Dup Co lands a big deal", "Dup Co faces a probe"]


def test_news_feed_shows_each_story_once_per_company(client, duplicated_news):
    feed = client.get("/api/news", params={"symbol": ["ZZDUP", SYM], "days": 7, "limit": 20}).json()
    assert [(i["symbol"], i["title"]) for i in feed if i["title"].startswith("Dup Co")] == [
        ("ZZDUP", "Dup Co lands a big deal"), ("ZZDUP", "Dup Co faces a probe"),
        ("ZZDUP", "Dup Co opens a plant"), (SYM, "Dup Co lands a big deal")]  # the other company keeps its own copy
    assert len(client.get("/api/news", params={"symbol": "ZZDUP", "limit": 2}).json()) == 2


def test_news_feed_validates_input(client):
    assert client.get("/api/news", params={"sentiment": "great"}).status_code == 422
    assert client.get("/api/news", params={"symbol": "bad$"}).status_code == 422
    assert client.get("/api/news", params={"limit": 0}).status_code == 422
    assert client.get("/api/news", params={"days": 365}).status_code == 422


def test_filings_list_says_which_are_searchable(client):
    filings = client.get(f"/api/stocks/{SYM}/filings").json()
    assert [(f["form"], f["searchable"]) for f in filings] == [("10-Q", False), ("10-K", True)]


def test_filing_search_returns_passages_with_sources(client):
    hits = client.get("/api/filings/search", params={"q": "supply chain risk", "symbol": SYM}).json()
    assert len(hits) == 1 and hits[0]["section"] == "Part I, Item 1A" and hits[0]["score"] == pytest.approx(1.0, abs=1e-3)
    assert hits[0]["url"] == "https://sec.example/f" and "Supply chain" in hits[0]["text"]
    assert client.get("/api/filings/search", params={"q": "x", "symbol": SYM}).status_code == 422  # too short
    assert client.get("/api/filings/search", params={"q": "risk", "form": "S-1"}).status_code == 422
    assert client.get("/api/filings/search", params={"q": "risk", "symbol": "bad$"}).status_code == 422
    assert client.get("/api/filings/search", params={"q": "risk", "symbol": SYM, "form": "10-Q"}).json() == []


def test_copilot_answers_with_numbered_sources(client, llm):
    r = client.post("/api/copilot", json={"question": "What is Zeta's supply risk?", "symbols": [SYM.lower()]})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Zeta has supply risk [1]." and body["grounded"] and not body["refused"]
    assert body["companies"] == [SYM] and body["unverified_numbers"] == []
    assert body["sources"][0]["number"] == 1 and body["sources"][0]["form"] == "10-K"
    assert "not financial advice" in body["disclaimer"]


def test_copilot_answers_a_price_question_from_stored_prices(client, llm):
    llm.reply = "Zeta Co closed at 499.00 on 2026-10-09 [1]."
    body = client.post("/api/copilot", json={"question": "What is the ZZAPI stock price?"}).json()
    assert body["companies"] == [SYM] and body["evidence_kinds"] == ["price"] and body["searches"] == []
    assert body["grounded"] and not body["refused"] and body["unverified_numbers"] == [] and body["cautions"] == []
    src = body["sources"][0]
    assert src["kind"] == "price" and src["number"] == 1 and src["url"] is None and src["form"] is None
    assert src["as_of"] == str(LATEST) and "as of 2026-10-09" in src["title"] and "Latest close: 499.00" in src["excerpt"]


def test_copilot_reports_headlines_as_sources_with_their_links(client, llm):
    llm.reply = "There was a headline about a deal [1]."
    body = client.post("/api/copilot", json={"question": "Any news on ZZAPI?"}).json()
    assert body["evidence_kinds"] == ["headline"]
    first = body["sources"][0]
    assert first["kind"] == "headline" and first["url"].startswith("http") and "automatic label" in first["title"]


def test_copilot_a_wrong_way_price_move_is_reported_not_hidden(client, llm):
    llm.reply = "The stock fell 31.00 over the past month [1]."  # it rose 31.00
    body = client.post("/api/copilot", json={"question": "How did the ZZAPI stock do this month?"}).json()
    assert any("stored change is" in b for b in body["unverified_numbers"])


def test_copilot_a_market_question_without_a_company_is_refused(client, llm):
    body = client.post("/api/copilot", json={"question": "How is the S&P 500 doing today?"}).json()
    assert body["refused"] and body["evidence_kinds"] == [] and body["sources"] == [] and llm.calls == 0


def test_copilot_flags_numbers_missing_from_sources(client, llm):
    llm.reply = "Zeta lost 999 million dollars [1]."
    body = client.post("/api/copilot", json={"question": "What did Zeta lose?", "symbols": [SYM]}).json()
    assert body["unverified_numbers"] == ["999"]


def test_copilot_input_and_availability_errors(client, llm):
    assert client.post("/api/copilot", json={"question": "hi"}).status_code == 422
    assert client.post("/api/copilot", json={"question": "x" * 501}).status_code == 422
    assert client.post("/api/copilot", json={"question": "valid question", "limit": 50}).status_code == 422
    assert client.post("/api/copilot", json={"question": "valid question", "symbols": ["NOPE"]}).status_code == 404
    assert client.post("/api/copilot", json={"question": "valid question", "symbols": ["bad$"]}).status_code == 422
    llm.up = False
    r = client.post("/api/copilot", json={"question": "What is Zeta's supply risk?", "symbols": [SYM]})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"] and llm.calls == 0


def test_status_lists_runs_and_freshness(client):
    body = client.get("/api/status").json()
    z = next(c for c in body["companies"] if c["symbol"] == SYM)
    assert z["last_price_date"] == str(LATEST) and z["filings_total"] == 2 and z["unscored_headlines"] >= 0
    assert isinstance(body["runs"], list)


def test_cors_allows_the_local_web_app_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_docs_describe_the_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/stocks", "/api/stocks/{symbol}/prices", "/api/copilot", "/api/filings/search"} <= set(paths)
