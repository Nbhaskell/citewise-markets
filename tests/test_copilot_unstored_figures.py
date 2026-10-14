"""Questions for a ratio the app does not compute (dividend yield, price-to-book, ...).

Those used to go to the filings only, so the model saw no price and said "the stock price is not provided" even though
prices are stored. Now the copilot says plainly that it doesn't calculate the ratio and lists what it does have, in code,
before the model is asked. If the ratio is mixed into a question the app can answer, the answer carries a note instead.
"""
from datetime import date

import pytest

from ai.copilot import NO_COMPANY, answer_question
from ai.market import detect_intent
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM, store
from test_fundamentals import company

A = "ZZFC"
TODAY = date(2026, 10, 12)


# ---- which questions are about a ratio the app doesn't compute ----

@pytest.mark.parametrize("question,names", [
    ("What is Microsoft's dividend yield?", {"dividend yield"}),
    ("What's the dividend yield on Apple?", {"dividend yield"}),
    ("What is Nvidia's price-to-book ratio?", {"price-to-book ratio"}),
    ("What is Nvidia's price to book?", {"price-to-book ratio"}),
    ("What's Apple's P/B ratio?", {"price-to-book ratio"}),
    ("What is Tesla's price-to-sales ratio?", {"price-to-sales ratio"}),
    ("What's Amazon's P/S?", {"price-to-sales ratio"}),
    ("What is Alphabet's PEG ratio?", {"PEG ratio"}),
    ("What is Apple's EV/EBITDA?", {"EV/EBITDA"}),
    ("What is Microsoft's enterprise value?", {"enterprise value"}),
    ("What is Nvidia's return on equity?", {"return on equity"}),
    ("What's Tesla's ROE?", {"return on equity"}),
    ("What is Apple's return on assets?", {"return on assets"}),
    ("What is Amazon's debt-to-equity ratio?", {"debt-to-equity ratio"}),
    ("What are Apple's P/B and dividend yield?", {"price-to-book ratio", "dividend yield"}),
])
def test_ratios_the_app_does_not_compute_are_recognized(question, names):
    got = detect_intent(question)
    assert set(got.unstored) == names, question
    assert got.unstored_only and not got.market, question


@pytest.mark.parametrize("question", [
    "How much did Microsoft pay in dividends last year?",        # a stated amount; the filings answer it
    "What does Apple's 10-K say about dividends?",
    "What is Nvidia's P/E ratio?",
    "What is Apple's market value?",
    "What are Tesla's profit margins?",
    "How has Nvidia stock done this month?",
    "What are Nvidia's biggest risks?",
    "Is the stock price of Microsoft pegged to anything?",         # "pegged" is not "PEG"
])
def test_other_questions_are_not_caught(question):
    got = detect_intent(question)
    assert got.unstored == () and not got.unstored_only, question


def test_a_ratio_mixed_into_an_answerable_question_is_noted_but_does_not_stop_it():
    pe = detect_intent("What is Apple's P/E ratio and dividend yield?")
    assert pe.unstored == ("dividend yield",) and not pe.unstored_only and pe.fundamentals == frozenset({"pe"})
    risks = detect_intent("What is Apple's dividend yield, and what are its biggest risks?")
    assert risks.unstored == ("dividend yield",) and not risks.unstored_only and risks.filings
    price = detect_intent("How has Nvidia stock done this month, and what is its price-to-book?")
    assert price.unstored == ("price-to-book ratio",) and not price.unstored_only and price.prices


def test_the_words_for_the_ratio_do_not_change_how_the_rest_is_routed():
    # "price-to-book" must not read as a price question, and "P/S" must not hide the P/E
    got = detect_intent("What is Nvidia's price-to-book ratio?")
    assert not got.prices and got.fundamentals == frozenset()
    assert detect_intent("What is Apple's P/E and P/S?").fundamentals == frozenset({"pe"})


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


def ask(conn, question, llm, emb=None):
    return answer_question(conn, emb or FakeEmbedder(), llm, question, expand=False, today=TODAY)


def test_a_ratio_the_app_does_not_compute_is_declined_before_the_model_is_asked(conn):
    store(conn, company())
    llm, emb = ScriptedLLM("should not be asked"), FakeEmbedder()
    ans = ask(conn, "What is ZZFC's dividend yield?", llm, emb)
    assert ans.refused and llm.calls == [] and emb.queries == [] and ans.symbols == [A]
    assert "dividend yield" in ans.text and "don't calculate" in ans.text
    # it says what it does have, and never claims the stock price is unavailable (it is stored)
    assert "P/E ratio" in ans.text and "stored prices" in ans.text and "not provided" not in ans.text


def test_two_ratios_are_both_named(conn):
    ans = ask(conn, "What are ZZFC's price-to-book and dividend yield?", ScriptedLLM("x"))
    assert "price-to-book ratio and dividend yield" in ans.text or "dividend yield and price-to-book ratio" in ans.text


def test_the_decline_does_not_need_a_company(conn):
    llm = ScriptedLLM("should not be asked")
    ans = ask(conn, "What is a good dividend yield?", llm)
    assert ans.refused and llm.calls == [] and "dividend yield" in ans.text and ans.text != NO_COMPANY


def test_a_ratio_mixed_into_a_pe_question_gets_the_answer_and_a_note(conn):
    store(conn, company())
    llm = ScriptedLLM("The P/E ratio is 10.0 [1]. Dividend yield isn't one of the sources.")
    ans = ask(conn, "What is ZZFC's P/E ratio and its dividend yield?", llm)
    assert not ans.refused and ans.grounded and len(llm.calls) == 1
    assert len(ans.cautions) == 1 and "dividend yield" in ans.cautions[0] and "doesn't calculate" in ans.cautions[0]


def test_an_ordinary_question_gets_no_note(conn):
    store(conn, company())
    ans = ask(conn, "What is ZZFC's P/E ratio?", ScriptedLLM("The P/E ratio is 10.0 [1]."))
    assert ans.cautions == []
