"""Two ways a filings-only answer used to say "the stock price is not available" when prices are stored.

"Tell me Apple's price to free cash flow" is a ratio the app doesn't compute and wasn't on the list of nine, so it went to
the filings, found no price, and the answer said "the sources do not include Apple's stock price" (held-out round, item
5). First, more ratio names are recognized, so the copilot declines them in code (see test_copilot_unstored_figures.py).
Second, whatever else lands on the filings route, an answer that says a price is missing, for a company whose prices are
stored, carries a caution saying that the stored prices exist and were not used.
"""
from datetime import date

import pytest

from ai.copilot import false_price_claim
from ai.copilot import answer_question
from ai.market import MarketEvidence, detect_intent
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM, store
from test_fundamentals import company

A = "ZZFC"
TODAY = date(2026, 10, 12)


@pytest.mark.parametrize("question,names", [
    ("Tell me Apple's price to free cash flow.", {"price-to-free-cash-flow ratio"}),
    ("What's Nvidia's P/FCF?", {"price-to-free-cash-flow ratio"}),
    ("What is Microsoft's price-to-cash-flow?", {"price-to-cash-flow ratio"}),
    ("What is Amazon's free cash flow yield?", {"free cash flow yield"}),
    ("What's Tesla's earnings yield?", {"earnings yield"}),
    ("What is Apple's EV/sales?", {"EV/sales"}),
    ("What's Microsoft's current ratio?", {"current ratio"}),
    ("What is Nvidia's quick ratio?", {"quick ratio"}),
    ("What's Amazon's ROIC?", {"return on invested capital"}),
    ("What is Apple's return on invested capital?", {"return on invested capital"}),
    ("What is Tesla's interest coverage ratio?", {"interest coverage ratio"}),
])
def test_more_ratios_the_app_does_not_compute_are_recognized(question, names):
    got = detect_intent(question)
    assert set(got.unstored) == names and got.unstored_only and not got.market, question


@pytest.mark.parametrize("question", [
    "How much free cash flow did Apple generate last year?",        # a stated amount; the filings answer it
    "What does Microsoft's 10-K say about cash flow?",
    "What is Nvidia's operating cash flow?",
    "What was Amazon's price to ship a Prime order?",
    "Is Tesla's current price too high?",                           # "current" and "price", but no ratio
    "What is the current state of Apple's capital spending?",       # "capital" without "return on"
    "How are Microsoft's earnings, and what is the yield on its bonds?",
])
def test_questions_that_only_share_words_with_those_ratios_are_not_caught(question):
    assert detect_intent(question).unstored == (), question


# ---- the caution on a filings-only answer ----

@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Funco Holdings')", (A,))
        c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, 24, 'fake')", (A, TODAY))
        c.commit()
        yield c
        c.rollback()
        for table in ("financial_facts", "prices_daily"):
            c.execute(f"DELETE FROM {table} WHERE symbol = %s", (A,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (A,))
        c.commit()


PRICE_EV = MarketEvidence("price", A, "ZZFC price data", "Latest close: 24.00", None, TODAY, change=1.0, change_pct=4.0)


@pytest.mark.parametrize("text", [
    "The sources provided do not include Funco's stock price, so the ratio can't be worked out [1].",
    "Funco's stock price is not provided in the sources.",
    "There is no share price in the passages, only free cash flow.",
    "The sources lack the current price of Funco.",
    "Price data is not available in the sources.",
])
def test_an_answer_saying_the_price_is_missing_gets_a_caution_when_prices_are_stored(conn, text):
    caution = false_price_claim(conn, text, [A], [])
    assert caution and A in caution and "store daily closing prices" in caution


@pytest.mark.parametrize("text", [
    "Funco's free cash flow was 12 million [1].",
    "The 10-K describes the risk factors for Funco [1].",
    "Funco's stock price was 24.00 at the latest close [1].",
    "The sources do not discuss dividends [1].",
])
def test_an_answer_that_does_not_deny_the_price_gets_nothing(conn, text):
    assert false_price_claim(conn, text, [A], []) is None


def test_no_caution_when_the_answer_had_a_price_source(conn):
    assert false_price_claim(conn, "The stock price is not in the filings.", [A], [PRICE_EV]) is None


def test_no_caution_when_no_prices_are_stored_for_the_company(conn):
    conn.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZNP', 'No Prices Inc')")
    try:
        assert false_price_claim(conn, "The stock price is not available.", ["ZZNP"], []) is None
        assert false_price_claim(conn, "The stock price is not available.", [A, "ZZNP"], []) is None  # one lacks them
    finally:
        conn.rollback()


def test_no_caution_without_a_company(conn):
    assert false_price_claim(conn, "The stock price is not available.", [], []) is None


def test_the_caution_reaches_the_answer(conn):
    store(conn, company())
    llm = ScriptedLLM("The sources provided do not include ZZFC's stock price, so the ratio cannot be worked out [1].")
    # a figures question: its only source is the financial figures, never a price source, so this is the same situation
    ans = answer_question(conn, FakeEmbedder(), llm, "What is ZZFC's net income?", expand=False, today=TODAY)
    assert not ans.refused and any(e.kind == "fundamentals" for e in ans.retrieved)
    assert any("store daily closing prices" in c for c in ans.cautions)
