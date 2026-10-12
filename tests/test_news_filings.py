from datetime import date, datetime, timezone

import pytest

from data.db import connect
from data.ingest_filings import ingest_filings
from data.ingest_news import ingest_news
from data.sources.base import NewsItem
from data.sources.edgar import EdgarClient, FilingRef, html_to_text
from data.sources.google_news import parse_feed

SYMBOL = "ZZNEWS"

FEED = b"""<?xml version="1.0"?><rss><channel>
<item><title>Big news - Example Wire</title><link>https://news.example/a</link><guid>g1</guid>
<pubDate>Thu, 08 Oct 2026 16:29:00 GMT</pubDate><source url="https://x">Example Wire</source></item>
<item><title>No date here</title><link>https://news.example/b</link><guid>g2</guid></item>
</channel></rss>"""


def test_parse_feed_strips_publisher_and_skips_bad_items():
    items = parse_feed(FEED, "aapl")
    assert len(items) == 1
    assert items[0].title == "Big news"
    assert items[0].publisher == "Example Wire"
    assert items[0].symbol == "AAPL"
    assert items[0].published_at == datetime(2026, 10, 8, 16, 29, tzinfo=timezone.utc)


def test_html_to_text_drops_hidden_xbrl_header_and_scripts():
    html = (
        "<html><body><ix:header>HIDDEN FACTS</ix:header><script>var x=1</script>"
        "<p>Item&nbsp;1.   Business</p><p>We make things.</p></body></html>"
    )
    text = html_to_text(html)
    assert "HIDDEN" not in text and "var x" not in text
    assert "Item 1. Business" in text and "We make things." in text


def test_list_filings_limits_per_form_and_builds_urls(monkeypatch):
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "10-K", "10-Q", "10-Q"],
                "accessionNumber": ["0-1", "0000320193-26-000010", "0000320193-25-000099", "0-4", "0-5"],
                "filingDate": ["2026-10-01", "2026-08-01", "2025-11-01", "2026-05-01", "2026-02-01"],
                "reportDate": ["", "2026-06-27", "2025-09-27", "2026-03-28", "2025-12-27"],
                "primaryDocument": ["a.htm", "q.htm", "k.htm", "q2.htm", "q3.htm"],
            }
        }
    }

    class Resp:
        def json(self):
            return submissions

    client = EdgarClient("Test test@test.invalid")
    monkeypatch.setattr(client, "_get", lambda url: Resp())
    refs = client.list_filings("0000320193", ["10-K", "10-Q"], limit_per_form=2)
    assert [r.accession_number for r in refs] == ["0000320193-26-000010", "0000320193-25-000099", "0-4"]
    assert refs[0].url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/q.htm"
    assert refs[0].period_of_report == date(2026, 6, 27)


@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'News Test Co')", (SYMBOL,))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zz%'")
        c.execute("DELETE FROM filings WHERE symbol = %s", (SYMBOL,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYMBOL,))
        c.commit()


class FakeNews:
    name = "fake"

    def get_news(self, symbol, company_name, days=7):
        assert company_name == "News Test Co"
        ts = datetime(2026, 10, 1, tzinfo=timezone.utc)
        return [NewsItem(f"fake:zz{i}", "fake", symbol, f"Headline {i}", "Wire", "https://x", ts) for i in (1, 2)]


def test_ingest_news_dedupes_on_rerun(conn):
    assert ingest_news(conn, FakeNews(), SYMBOL, 7) == 2
    assert ingest_news(conn, FakeNews(), SYMBOL, 7) == 0
    n = conn.execute("SELECT count(*) FROM news_article_symbols WHERE symbol = %s", (SYMBOL,)).fetchone()[0]
    assert n == 2


def test_ingest_news_rejects_unknown_symbol(conn):
    with pytest.raises(ValueError, match="not in instruments"):
        ingest_news(conn, FakeNews(), "NOPE", 7)


class FakeEdgar:
    def __init__(self):
        self.fetched = 0

    def cik_for_ticker(self, symbol):
        return "0000000001"

    def list_filings(self, cik, forms, limit):
        return [FilingRef("0-ZZ1", cik, "10-K", date(2026, 1, 2), date(2025, 12, 31), "https://x/k.htm")]

    def fetch_text(self, ref):
        self.fetched += 1
        return "Item 1. Business"


def test_ingest_filings_skips_already_stored(conn):
    edgar = FakeEdgar()
    assert ingest_filings(conn, edgar, SYMBOL, ["10-K"], 1) == 1
    assert ingest_filings(conn, edgar, SYMBOL, ["10-K"], 1) == 0
    assert edgar.fetched == 1
    assert conn.execute("SELECT cik FROM instruments WHERE symbol = %s", (SYMBOL,)).fetchone()[0] == "0000000001"


def test_google_news_query_excludes_spam_sites(monkeypatch):
    import data.sources.google_news as gn

    seen = {}

    class Resp:
        content = b"<rss><channel></channel></rss>"

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        return Resp()

    monkeypatch.setattr(gn.requests, "get", fake_get)
    gn.GoogleNewsSource().get_news("AAPL", "Apple Inc.", days=3)
    assert "-site%3Amarketbeat.com" in seen["url"] and "when%3A3d" in seen["url"]
