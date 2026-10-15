"""A figure the user typed, repeated by an answer that declines or restates the question, is not "unverified".

"Will Microsoft hit $600 by December?" was answered correctly ("the sources do not provide information about future stock
prices, including whether Microsoft will hit $600"), and the numbers check flagged "600" as a figure missing from the
sources, so a correct answer carried a warning. A warning on a correct answer teaches the reader to ignore warnings.

The exemption is deliberately narrow, because this check is the only code-level guard on figures: the number must be one
the question itself contains, and every sentence of the answer that uses it must decline (not, no, cannot...) without
making a prediction of its own. "Microsoft will not hit $600" and "Microsoft is at $600" are still flagged.
"""
from datetime import date

import pytest

from ai.copilot import answer_question, unverified_numbers
from ai.search import SearchResult
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM, store
from test_fundamentals import company

SRC = SearchResult(1, "0-ZO", "ZZMS", "10-K", date(2026, 1, 1), None, "https://x", "Item 1",
                   "Latest close 541.15 on 2026-10-12. Revenue increased 18%.", 1.0)
Q = "Will Microsoft hit $600 by December?"


def flagged(answer, question=Q):
    return unverified_numbers(answer, [1], [SRC], question)


@pytest.mark.parametrize("answer", [
    "The sources do not provide information about future stock prices, including whether Microsoft will hit $600 by December [1].",
    "I can't say whether Microsoft will reach $600 [1].",
    "I cannot say if Microsoft will hit $600 by December [1].",
    "The sources do not mention $600 [1].",
    "Nothing in the sources says anything about $600 [1]. The latest close is 541.15 [1].",
])
def test_the_users_own_number_in_a_declining_sentence_is_not_flagged(answer):
    assert flagged(answer) == [], answer


@pytest.mark.parametrize("answer", [
    "Microsoft will not hit $600 by December [1].",                    # a prediction of its own
    "Microsoft is at $600 [1].",                                       # a claim
    "The latest close is 541.15, far below $600 [1].",                 # a claim built on the number
    "The sources do not provide a forecast. Microsoft hit $600 [1].",  # declines once, then asserts
    "Microsoft will hit $600 [1].",
    "I can't say whether Microsoft will hit $600 [1]. Microsoft is at $600 [1].",  # declines once, then uses it in a claim
    "Microsoft won't hit $600 by December [1].",                       # "won't" is a prediction, not a decline
    "Microsoft wouldn't reach $600 [1].",
])
def test_the_number_is_still_flagged_when_the_answer_uses_it_to_say_something(answer):
    assert flagged(answer) == ["600"], answer


def test_a_number_the_user_did_not_type_is_still_flagged_even_in_a_declining_sentence():
    assert flagged("The sources do not say whether Microsoft will hit $700 [1].") == ["700"]


def test_without_the_question_nothing_changes():
    answer = "The sources do not say whether Microsoft will hit $600 [1]."
    assert unverified_numbers(answer, [1], [SRC]) == ["600"]
    assert unverified_numbers(answer, [1], [SRC], "") == ["600"]


def test_other_figures_in_the_same_answer_are_still_checked():
    answer = "I can't say whether Microsoft will hit $600 [1]. Revenue grew 19% [1]."
    assert flagged(answer) == ["19"]


# ---- through the whole copilot, with a fake model ----

A = "ZZFC"
TODAY = date(2026, 10, 12)


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


def test_a_correct_decline_has_no_warning_and_no_retry(conn):
    store(conn, company())
    declining = "The sources do not provide information about future prices, including whether ZZFC will hit $600 by December [1]."
    llm = ScriptedLLM(declining)
    ans = ask(conn, "Will ZZFC stock hit $600 by December?", llm)
    assert ans.unverified_numbers == [] and len(llm.calls) == 1  # it used to be flagged, which also cost a second model call


def test_an_assertion_with_the_number_is_still_warned_about_and_retried(conn):
    store(conn, company())
    llm = ScriptedLLM("ZZFC will hit $600 by December [1].")
    ans = ask(conn, "Will ZZFC stock hit $600 by December?", llm)
    assert ans.unverified_numbers == ["600"] and len(llm.calls) == 2
