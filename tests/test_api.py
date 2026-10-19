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
        c.execute("DELETE FROM financial_facts WHERE symbol = %s", (SYM,))  # leftovers from an interrupted run
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYM,))
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
        # Reported figures (a calendar-year company): last twelve months = full year 2025 + first half 2026 - first half 2025
        facts = []
        for concept, unit, scale, fy, h1_now, h1_before in [
            ("Revenues", "USD", 1e9, 100, 60, 40), ("NetIncomeLoss", "USD", 1e9, 40, 24, 16),
            ("EarningsPerShareDiluted", "USD/shares", 1, 4.0, 2.4, 1.6), ("OperatingIncomeLoss", "USD", 1e9, 25, 15, 10),
            ("GrossProfit", "USD", 1e9, 50, 30, 20),
        ]:
            facts += [(concept, unit, "taxonomy", "2025-01-01", "2025-12-31", fy * scale, "0-ZZAPI-FY", "10-K", "2026-02-05"),
                      (concept, unit, "taxonomy", "2025-01-01", "2025-06-30", h1_before * scale, "0-ZZAPI-H125", "10-Q", "2025-07-30"),
                      (concept, unit, "taxonomy", "2026-01-01", "2026-06-30", h1_now * scale, "0-ZZAPI-H126", "10-Q", "2026-07-30")]
        facts += [("WeightedAverageNumberOfDilutedSharesOutstanding", "shares", "taxonomy", "2026-01-01", "2026-06-30", 10e9, "0-ZZAPI-H126", "10-Q", "2026-07-30"),
                  ("EntityCommonStockSharesOutstanding", "shares", "dei", None, "2026-07-20", 10.1e9, "0-ZZAPI-H126", "10-Q", "2026-07-30")]
        for concept, unit, taxonomy, start, end, value, accn, form, filed in facts:
            c.execute(
                "INSERT INTO financial_facts (symbol, taxonomy, concept, unit, period_start, period_end, value, accession_number, form, filed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (SYM, "us-gaap" if taxonomy == "taxonomy" else taxonomy, concept, unit, start, end, value, accn, form, filed))
        c.commit()
    yield
    with connect() as c:
        c.execute("DELETE FROM financial_facts WHERE symbol = %s", (SYM,))
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
    # last 7 days: positive, negative, irrelevant; the 60-day-old story and unscored one don't count, and the neutral
    # "Zeta quote page" is shown in the news list but left out of the totals
    assert z["sentiment"] == {"days": 7, "positive": 1, "neutral": 0, "negative": 1, "irrelevant": 1, "score": 0.0}


def test_fundamentals_are_computed_from_the_reported_figures(client):
    d = client.get(f"/api/stocks/{SYM.lower()}/fundamentals").json()
    assert d["symbol"] == SYM and d["available"] is True and d["unavailable_reason"] is None
    assert d["period_end"] == "2026-06-30"
    assert d["revenue"]["value"] == pytest.approx(120e9) and d["net_income"]["value"] == pytest.approx(48e9)
    assert d["diluted_eps"]["value"] == pytest.approx(4.8) and d["operating_income"]["value"] == pytest.approx(30e9)
    assert d["revenue"]["growth"] == pytest.approx(0.5) and "6 months to 2026-06-30" in d["revenue"]["growth_label"]
    assert "the last full year (ended 2025-12-31)" in d["revenue"]["how"]
    assert d["revenue"]["sources"] == ["10-K filed 2026-02-05 (the year ended 2025-12-31)",
                                       "10-Q filed 2026-07-30 (6 months to 2026-06-30)",
                                       "10-Q filed 2025-07-30 (the same 6 months a year earlier)"]
    assert (d["gross_margin"], d["operating_margin"], d["net_margin"]) == (pytest.approx(0.5), pytest.approx(0.25), pytest.approx(0.4))
    assert d["price"] == 499 and d["price_date"] == str(LATEST)
    assert d["shares"]["value"] == pytest.approx(10.1e9) and "cover page" in d["shares"]["source"]
    assert d["market_value"] == pytest.approx(10.1e9 * 499) and d["pe"] == pytest.approx(499 / 4.8) and d["pe_note"] is None


def test_fundamentals_carry_their_cautions(client):
    d = client.get(f"/api/stocks/{SYM}/fundamentals").json()
    # net income (48B) is 1.6 times operating income (30B), so the response must say so
    assert any("1.6 times operating income" in c and "may flatter" in c for c in d["cautions"])


def test_a_company_without_figures_is_available_false_with_a_reason(client):
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZAPN', 'No Figures Co') ON CONFLICT DO NOTHING")
        c.commit()
    try:
        d = client.get("/api/stocks/ZZAPN/fundamentals")
        assert d.status_code == 200
        body = d.json()
        assert body["available"] is False and "foreign filer" in body["unavailable_reason"]
        assert body["revenue"] is None and body["pe"] is None and body["market_value"] is None and body["cautions"] == []
    finally:
        with connect() as c:
            c.execute("DELETE FROM instruments WHERE symbol = 'ZZAPN'")
            c.commit()


def test_fundamentals_for_an_unknown_company_is_404_and_a_bad_symbol_422(client):
    assert client.get("/api/stocks/NOPE/fundamentals").status_code == 404
    assert client.get("/api/stocks/bad!symbol/fundamentals").status_code == 422


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


def test_copilot_answers_a_pe_question_from_the_figures_and_carries_the_caution(client, llm):
    llm.reply = "Zeta Co's P/E ratio is 104.0 [1]."  # the model says nothing about the caution; the response still has it
    body = client.post("/api/copilot", json={"question": "What is the ZZAPI P/E ratio?"}).json()
    assert body["companies"] == [SYM] and body["evidence_kinds"] == ["fundamentals"] and body["searches"] == []
    assert body["grounded"] and not body["refused"] and body["unverified_numbers"] == []
    src = body["sources"][0]
    assert src["kind"] == "fundamentals" and src["url"] is None and src["form"] is None and src["as_of"] == "2026-06-30"
    assert "P/E ratio: 104.0" in src["excerpt"] and "financial figures" in src["title"]
    # net income (48B) is 1.6 times operating income (30B): the warning rides with the answer
    assert any(c.startswith(f"Caution for {SYM}:") and "1.6 times operating income" in c and "may flatter" in c
               for c in body["cautions"])


def test_copilot_a_revenue_answer_does_not_carry_the_earnings_caution(client, llm):
    llm.reply = "Revenue over the last 12 months was $120.0 billion [1]."
    body = client.post("/api/copilot", json={"question": "What was the ZZAPI revenue over the last twelve months?"}).json()
    assert body["evidence_kinds"] == ["fundamentals"] and body["unverified_numbers"] == []
    assert not any("operating income" in c for c in body["cautions"])


def test_copilot_reports_headlines_as_sources_with_their_links(client, llm):
    llm.reply = "There was a headline about a deal [1]."
    body = client.post("/api/copilot", json={"question": "Any news on ZZAPI?"}).json()
    assert body["evidence_kinds"] == ["headline"]
    first = body["sources"][0]
    assert first["kind"] == "headline" and first["url"].startswith("http") and "automatic label" in first["title"]


def test_copilot_says_nothing_about_the_router_when_the_keywords_decided(client, llm, monkeypatch):
    monkeypatch.setenv("COPILOT_ROUTER", "model")
    llm.reply = "Zeta Co closed at 499.00 on 2026-10-09 [1]."
    body = client.post("/api/copilot", json={"question": "What is the ZZAPI stock price?"}).json()
    assert body["evidence_kinds"] == ["price"] and body["model_route"] == []         # present, and empty


def test_copilot_reports_what_the_model_chose_when_the_router_routed_it(client, llm, monkeypatch):
    import json as _json

    from ai.router import ROUTER_SYSTEM

    class RoutingLLM(type(llm)):
        def generate(self, system, user, json_schema=None):
            if system == ROUTER_SYSTEM:
                return _json.dumps({"category": "research", "price": True, "news": False, "sentiment": False, "figures": [],
                                    "filings": False, "advice": False})
            return super().generate(system, user, json_schema)

    routed = RoutingLLM(reply="Zeta Co closed at 499.00 on 2026-10-09 [1].")
    app.dependency_overrides[get_chat_model] = lambda: routed
    monkeypatch.setenv("COPILOT_ROUTER", "model")
    body = client.post("/api/copilot", json={"question": "Has ZZAPI pulled back from its high this year?"}).json()
    assert body["model_route"] == ["price"] and body["evidence_kinds"] == ["price"] and not body["refused"]
    monkeypatch.setenv("COPILOT_ROUTER", "off")
    body = client.post("/api/copilot", json={"question": "Has ZZAPI pulled back from its high this year?"}).json()
    assert body["model_route"] == []                                                   # the same question with the router off


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


# ---- the question log (DECISIONS: "Question log"): every answer is appended to a local file, and the log never changes the response ----


def log_lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.fixture
def qlog(tmp_path, monkeypatch):
    path = tmp_path / "copilot_questions.jsonl"
    monkeypatch.setenv("COPILOT_LOG", "on")
    monkeypatch.setenv("COPILOT_LOG_FILE", str(path))
    return path


def test_copilot_an_answer_is_logged_with_the_question_and_the_answer(client, llm, qlog):
    llm.reply = "Zeta Co closed at 499.00 on 2026-10-09 [1]."
    body = client.post("/api/copilot", json={"question": "What is the ZZAPI stock price?"}).json()
    [rec] = log_lines(qlog)
    assert rec["question"] == "What is the ZZAPI stock price?" and rec["answer"] == body["answer"]
    assert rec["companies"] == ["ZZAPI"] and rec["evidence_kinds"] == ["price"] and rec["refused"] is False and rec["follow_up"] is False


def test_copilot_a_refusal_is_logged_too(client, llm, qlog):
    client.post("/api/copilot", json={"question": "How is the S&P 500 doing today?"})
    [rec] = log_lines(qlog)
    assert rec["refused"] is True and rec["evidence_kinds"] == []


def test_copilot_a_follow_up_is_marked_in_the_log(client, llm, qlog):
    llm.reply = "Zeta Co closed at 499.00 on 2026-10-09 [1]."
    history = [{"question": "What is the ZZAPI stock price?", "answer": "It closed at 499.00.", "companies": ["ZZAPI"]}]
    client.post("/api/copilot", json={"question": "And its news?", "history": history})
    assert log_lines(qlog)[0]["follow_up"] is True


def test_copilot_two_questions_make_two_lines(client, llm, qlog):
    client.post("/api/copilot", json={"question": "What is the ZZAPI stock price?"})
    client.post("/api/copilot", json={"question": "Any news on ZZAPI?"})
    assert [r["question"] for r in log_lines(qlog)] == ["What is the ZZAPI stock price?", "Any news on ZZAPI?"]


def test_copilot_nothing_is_logged_when_it_is_switched_off(client, llm, qlog, monkeypatch):
    monkeypatch.setenv("COPILOT_LOG", "off")
    client.post("/api/copilot", json={"question": "What is the ZZAPI stock price?"})
    assert not qlog.exists()


@pytest.mark.parametrize("payload,status", [
    ({"question": "What is the ZZAPI stock price?", "symbols": ["NOPE"]}, 404),        # not a tracked company
    ({"question": "What is the ZZAPI stock price?", "symbols": ["bad symbol!"]}, 422),
    ({"question": ""}, 422),
])
def test_copilot_a_request_that_gets_no_answer_is_not_logged(client, llm, qlog, payload, status):
    assert client.post("/api/copilot", json=payload).status_code == status
    assert not qlog.exists()


def test_copilot_a_model_that_is_down_is_not_logged(client, llm, qlog):
    llm.up = False
    assert client.post("/api/copilot", json={"question": "What is the ZZAPI stock price?"}).status_code == 503
    assert not qlog.exists()


def test_copilot_the_response_is_the_same_when_the_log_cannot_be_written(client, llm, tmp_path, monkeypatch):
    llm.reply = "Zeta Co closed at 499.00 on 2026-10-09 [1]."
    q = {"question": "What is the ZZAPI stock price?"}
    monkeypatch.setenv("COPILOT_LOG", "off")
    expected = client.post("/api/copilot", json=q).json()
    monkeypatch.setenv("COPILOT_LOG", "on")
    monkeypatch.setenv("COPILOT_LOG_FILE", str(tmp_path))                  # a folder: the write fails
    response = client.post("/api/copilot", json=q)
    assert response.status_code == 200 and response.json() == expected
