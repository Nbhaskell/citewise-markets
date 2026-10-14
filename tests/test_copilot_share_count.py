"""Share-count questions ("How many shares does Apple have?").

The price rules read "shares does" as a price verb, so these were answered from price data, which has no share count.
The stored shares-outstanding figure is the answer. Questions about what a company or person did with shares
(repurchased, issued, owns, can I buy) are filings questions, and still go there.
"""
from datetime import date

import pytest

from ai.copilot import answer_question
from ai.market import detect_intent
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM, store
from test_fundamentals import company

A = "ZZFC"
TODAY = date(2026, 10, 12)


@pytest.mark.parametrize("question", [
    "How many shares does Apple have?",
    "How many shares does Apple have outstanding?",
    "How many shares of Tesla are there?",
    "How many shares are there in Tesla?",
    "How many Nvidia shares are out there?",             # a company word between "many" and "shares"
    "How many of Apple's shares are outstanding?",
    "How many shares outstanding does Apple have?",     # worked before; must keep working
    "What's Apple's share count?",                       # same
])
def test_a_share_count_question_goes_to_the_stored_figure(question):
    got = detect_intent(question)
    assert got.fundamentals == frozenset({"shares"}) and not got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "How many shares did Microsoft repurchase last year?",
    "How many shares does Elon Musk own in Tesla?",
    "How many shares did Apple issue to employees?",
    "How many shares can I buy of Tesla for $1000?",
    "How many shares of Nvidia were sold by insiders?",
    "How many Tesla shares did Elon Musk sell?",
    "How many employees hold Apple shares?",
])
def test_questions_about_what_was_done_with_shares_go_to_the_filings(question):
    got = detect_intent(question)
    assert got.fundamentals == frozenset() and not got.prices and got.filings, question


@pytest.mark.parametrize("question", [
    "What is Apple's stock price?",
    "How has Apple stock done this month?",
    "Apple shares rose today, why?",
    "Are Tesla shares up this week?",
    "Is Nvidia's share price down?",
])
def test_price_questions_about_shares_are_still_price_questions(question):
    assert detect_intent(question).prices, question


def test_a_share_count_and_a_price_can_be_asked_together():
    got = detect_intent("How many shares does Apple have, and how has the stock done this month?")
    assert got.fundamentals == frozenset({"shares"}) and got.prices


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


def test_the_copilot_answers_from_the_figures_not_from_prices(conn):
    store(conn, company())
    llm, emb = ScriptedLLM("The share count is given in the source [1]."), FakeEmbedder()
    ans = answer_question(conn, emb, llm, "How many shares does ZZFC have?", expand=False, today=TODAY)
    assert [e.kind for e in ans.retrieved] == ["fundamentals"] and emb.queries == []
    assert "Latest close" not in llm.calls[0][1]  # no price source was given to the model
