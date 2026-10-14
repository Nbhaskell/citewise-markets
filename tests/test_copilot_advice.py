"""Questions that ask for a buy, sell, or hold call.

The model refused such questions in its own words only some of the time: "Should I buy/sell" 10 of 10, but "Is it a good
time to buy Nvidia?" 3 of 10 (often "cannot be answered with certainty", which implies it could be), "Is Amazon a good
investment?" 3 of 10, "Should I hold Microsoft?" 4 of 10. So the refusal is attached to the answer in code, whatever the
model wrote, the same way the data cautions are.
"""
from datetime import date

import pytest

from ai.copilot import ADVICE_CAUTION, answer_question
from ai.market import asks_for_advice, detect_intent
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM, gains_company, store
from test_fundamentals import company

A = "ZZFC"
TODAY = date(2026, 10, 12)


@pytest.mark.parametrize("question", [
    "Should I buy Apple stock?",
    "Should I sell my Tesla shares?",
    "Should I hold Microsoft through the end of the year?",
    "Should I invest in Nvidia?",
    "Should I keep my Amazon shares?",
    "Based on its P/E, should I buy Alphabet?",
    "Is it a good time to buy Nvidia?",
    "Is now a bad time to sell Tesla?",
    "Is Amazon a good investment right now?",
    "Is Tesla a good buy?",
    "Is Microsoft a safe investment?",
    "Is Apple stock worth buying?",
    "Is Nvidia worth investing in?",
    "Buy or sell Tesla?",
    "Buy, sell, or hold Apple?",
    "Would you buy Nvidia here?",
    "Do you recommend Microsoft?",
    "What stock should I buy?",
    # wordings that all slipped past the first, phrase-based version (it recognized none of these)
    "Would it be smart to sell my Nvidia position now?",
    "I'm thinking about buying more Apple. Good idea?",
    "Is Alphabet stock a smart pick for the long run?",
    "Tell me whether to dump my Tesla shares.",
    "Is it wise to add to my Microsoft holding?",
    "Can I safely invest in Amazon right now?",
    "Is Microsoft overvalued enough that I should sell?",
    # a second round, found when the first rule scored 3 of 6 on fresh wordings
    "Do you think I should get out of Tesla before earnings?",
    "What would you do with Apple stock, keep it or sell it?",
    "Is Amazon undervalued enough to load up on?",
    "Any reason not to buy Microsoft today?",
    "Which is the better buy, Apple or Microsoft?",
    "Is Nvidia the right stock to put my savings into?",
])
def test_requests_for_a_buy_sell_or_hold_call_are_recognized(question):
    assert asks_for_advice(question) and detect_intent(question).advice, question


@pytest.mark.parametrize("question", [
    "Why did insiders sell Tesla shares?",
    "Did Apple buy back shares last year?",
    "How much did Microsoft pay to buy Activision?",
    "What is Tesla's best selling model?",
    "What are Nvidia's biggest risks?",
    "How has Nvidia stock done this month?",
    "What is Apple's P/E ratio?",
    "What does the 10-K say about share repurchases?",
    "Will Tesla stock go up next month?",           # a prediction, handled by its own rule, not a buy/sell call
    "What is a good P/E ratio for a software company?",
    "Is there any reason Tesla's margins fell?",        # "reason" alone is not a cue; there is no trading word either
    "Is Apple's cash enough to cover its debt?",         # "enough to" with no trading word
    "How much cash does Apple hold?",                    # a trading word ("hold") but no decision cue
    "What is the net worth of Tesla's founder?",
    "Is the dividend worth mentioning in the 10-K?",
])
def test_ordinary_questions_are_not_mistaken_for_advice_requests(question):
    assert not asks_for_advice(question) and not detect_intent(question).advice, question


# ---- through the whole copilot, with a fake model ----

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


def ask(conn, question, llm):
    return answer_question(conn, FakeEmbedder(), llm, question, expand=False, today=TODAY)


def test_the_refusal_is_attached_even_when_the_model_does_not_refuse(conn):
    store(conn, company())
    # the model's sentence says "cannot be answered with certainty" and never says it won't advise
    llm = ScriptedLLM("Whether it is a good time to buy cannot be answered with certainty. The P/E ratio is 10.0 [1].")
    ans = ask(conn, "Is it a good time to buy ZZFC? What is its P/E ratio?", llm)
    assert ADVICE_CAUTION in ans.cautions and not ans.refused


def test_an_ordinary_question_gets_no_advice_caution(conn):
    store(conn, company())
    ans = ask(conn, "What is ZZFC's P/E ratio?", ScriptedLLM("The P/E ratio is 10.0 [1]."))
    assert ADVICE_CAUTION not in ans.cautions


def test_it_sits_alongside_the_data_cautions(conn):
    store(conn, gains_company())
    ans = ask(conn, "Based on its P/E, should I buy ZZFC?", ScriptedLLM("The P/E ratio is 3.3 [1]."))
    assert ADVICE_CAUTION in ans.cautions
    assert any(c.startswith("Caution for ZZFC:") for c in ans.cautions)


def test_the_caution_says_what_it_is_for():
    assert "buy, sell, or hold" in ADVICE_CAUTION and "recommendation" in ADVICE_CAUTION
