"""An answer written from filings alone that says the data is not there (DECISIONS: "Fresh held-out round", cause 1).

When a question never reaches the price or news data, the model sees only filing text and reads its own gap as the app's:
"the sources do not include AMD's stock prices", "there are no recent news stories about Amazon". Both were false (prices
and headlines are stored). The price caution (test_copilot_price_claim.py) missed the plural "prices" and "no price data";
there was no caution at all for a false "no news". Each wording below was added one at a time. The negative cases matter as
much: a caution on an answer that does not deny the data is noise, and one on a company with nothing stored is false.
"""
from datetime import date

import pytest

from ai.copilot import answer_question, false_news_claim, false_price_claim
from ai.market import MarketEvidence
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM, store
from test_fundamentals import company

A = "ZZFC"
TODAY = date(2026, 10, 12)


@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Funco Holdings')", (A,))
        c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, 24, 'fake')", (A, TODAY))
        # (id, hours ago): three recent stories and one old one
        for id_, hours in (("a", 5), ("b", 30), ("c", 24 * 12), ("old", 24 * 80)):
            c.execute("INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                      "VALUES (%s, 'fake', %s, 'Wire', %s, now() - make_interval(hours => %s))",
                      (f"fake:zzfc-{id_}", f"Funco story {id_}", f"https://x/{id_}", hours))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"fake:zzfc-{id_}", A))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzfc-%'")
        for table in ("financial_facts", "prices_daily"):
            c.execute(f"DELETE FROM {table} WHERE symbol = %s", (A,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (A,))
        c.commit()


PRICE_EV = MarketEvidence("price", A, "ZZFC price data", "Latest close: 24.00", None, TODAY, change=1.0, change_pct=4.0)
NEWS_EV = MarketEvidence("headline", A, "ZZFC headline", "Funco wins a contract", "https://x", TODAY)
SENT_EV = MarketEvidence("sentiment", A, "ZZFC sentiment", "3 positive", None, TODAY)


# ---- the price claim: wordings the first version missed ----

@pytest.mark.parametrize("text", [
    "The sources do not include information about Funco stock prices since August [1].",      # plural
    "No price data is available for periods after that date [1].",                          # "no" before "price data"
    "There is no price information for Funco in the filings.",
    "The sources do not provide Funco's price movements for that stretch.",
    "Funco's closing prices are not in the passages [1].",
    "The sources don't give Funco's stock price [1].",                                        # a contraction
])
def test_more_ways_of_saying_the_price_is_missing_get_the_caution(conn, text):
    caution = false_price_claim(conn, text, [A], [])
    assert caution and A in caution and "store daily closing prices" in caution, text


@pytest.mark.parametrize("text", [
    "The filing includes price information for the offering of its notes [1].",
    "Funco's price data is shown for the last month [1].",
    "The 10-K does not mention a price target [1].",
    "Funco does not discuss dividends or buybacks [1].",
])
def test_price_wording_that_does_not_deny_the_data_gets_no_caution(conn, text):
    assert false_price_claim(conn, text, [A], []) is None, text


# ---- the news claim ----

@pytest.mark.parametrize("text", [
    "There are no recent news stories provided in the sources about Funco [1].",
    "The sources do not include any news headlines about Funco.",
    "No headlines are available for Funco in the passages [1].",
    "The available sources are SEC filings and do not include news articles or headlines.",
    "I cannot find any recent news about Funco in the provided sources.",
    "Funco's recent news is not available in the sources.",
])
def test_an_answer_saying_there_is_no_news_gets_a_caution_when_headlines_are_stored(conn, text):
    caution = false_news_claim(conn, text, [A], [])
    assert caution and A in caution and "stores headlines" in caution and "last 30 days" in caution, text


def test_the_news_caution_counts_the_recent_stories_and_gives_the_newest_date(conn):
    caution = false_news_claim(conn, "There are no recent news stories about Funco.", [A], [])
    newest = conn.execute("SELECT (max(published_at) AT TIME ZONE 'UTC')::date FROM news_articles WHERE id LIKE 'fake:zzfc-%'").fetchone()[0]
    assert f"{A} (3 in the last 30 days, the newest on {newest})" in caution  # the 80-day-old story is not counted


@pytest.mark.parametrize("text", [
    "Funco launched a new product line in the third quarter [1].",
    "The 10-K describes Funco's supply risks [1].",
    "Funco's headline revenue grew 12% [1].",                         # "headline" as an adjective
    "The articles of incorporation do not limit its activities [1].", # not news articles
    "The sources do not discuss dividends [1].",
    "None of the filings mention a recall [1].",
])
def test_an_answer_that_does_not_deny_the_news_gets_nothing(conn, text):
    assert false_news_claim(conn, text, [A], []) is None, text


@pytest.mark.parametrize("evidence", [[NEWS_EV], [SENT_EV], [PRICE_EV, NEWS_EV]])
def test_no_news_caution_when_the_answer_had_a_news_source(conn, evidence):
    assert false_news_claim(conn, "There are no news stories about Funco.", [A], evidence) is None


def test_a_price_source_alone_does_not_stop_the_news_caution(conn):
    assert false_news_claim(conn, "There are no news stories about Funco.", [A], [PRICE_EV])


def test_no_news_caution_when_the_question_asked_for_news(conn):
    # The news route ran and found nothing in its window: "no news this week" is then true, not a gap in what was used.
    assert false_news_claim(conn, "There are no news stories about Funco.", [A], [], asked_for_news=True) is None


def test_no_news_caution_when_nothing_recent_is_stored(conn):
    conn.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZNN', 'No News Inc')")
    conn.execute("INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                 "VALUES ('fake:zzfc-zznn', 'fake', 'Old', 'Wire', 'https://x/o', now() - interval '90 days')")
    conn.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES ('fake:zzfc-zznn', 'ZZNN')")
    try:
        text = "There are no news stories about the company."
        assert false_news_claim(conn, text, ["ZZNN"], []) is None            # only a 90-day-old story
        assert false_news_claim(conn, text, [A, "ZZNN"], []) is None         # one of the two lacks recent news
    finally:
        conn.rollback()


def test_no_news_caution_without_a_company(conn):
    assert false_news_claim(conn, "There are no news stories.", [], []) is None


# ---- it reaches the answer ----

def test_the_news_caution_reaches_the_answer_to_a_figures_question(conn):
    store(conn, company())
    llm = ScriptedLLM("There are no recent news stories about ZZFC in the sources, but its net income is in the figures [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "What is ZZFC's net income?", expand=False, today=TODAY)
    assert not ans.refused and any(e.kind == "fundamentals" for e in ans.retrieved)
    assert any("stores headlines" in c for c in ans.cautions)


def test_no_news_caution_when_the_question_asked_for_news_and_the_window_had_none(conn):
    # Only a 12-day-old story is left, so the news route (7 days) finds nothing and "no news this week" is true.
    conn.execute("DELETE FROM news_articles WHERE id IN ('fake:zzfc-a', 'fake:zzfc-b')")
    store(conn, company())
    llm = ScriptedLLM("There are no recent news stories about ZZFC this week; its net income is in the figures [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "What is ZZFC's net income, and is there any news this week?",
                          expand=False, today=TODAY)
    assert not ans.refused and not any(e.kind == "headline" for e in ans.retrieved)
    assert not any("stores headlines" in c for c in ans.cautions)
