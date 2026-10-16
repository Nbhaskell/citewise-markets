"""The period a price question names, through the price source and the whole copilot (see test_price_windows.py for the
period parsing itself).

Three answers used to pass while not being about the period asked: "since July" was priced over the past month, "the end
of last week" got the newest close, and "today" got a two-day-old close. The source now says what it is not, and the
answer carries a caution written in code, so it does not depend on what the model chooses to say.
"""
from datetime import date, timedelta

import pytest

from ai.copilot import answer_question
from ai.market import parse_window, price_evidence
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM

A = "ZZPP"
TODAY = date(2026, 10, 15)
NEWEST = date(2026, 10, 13)          # two days old: the problem the 3pm task was meant to fix


@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Periodco Holdings')", (A,))
        first = NEWEST - timedelta(days=299)
        for i in range(300):  # one bar a day, close = 100 + i
            c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, %s, 'fake')",
                      (A, first + timedelta(days=i), 100 + i))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM prices_daily WHERE symbol = %s", (A,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (A,))
        c.commit()


def test_since_a_month_is_priced_from_that_months_first_day(conn):
    ev = price_evidence(conn, A, parse_window("How did ZZPP do since July?", TODAY), TODAY)
    assert "Window: since July 1, from 2026-07-01 to 2026-10-13" in ev.text
    # 2026-10-13 is bar 299 (close 399); 2026-07-01 is 104 days earlier (close 295): +104.00, 35.25%
    assert "Close on 2026-07-01: 295.00." in ev.text and "+104.00 (+35.25%), a rise." in ev.text
    assert "asked about" not in ev.text


def test_a_numbered_window_is_priced_over_that_many_days(conn):
    ev = price_evidence(conn, A, parse_window("ZZPP over the last four weeks", TODAY), TODAY)
    assert "Window: past 4 weeks, from 2026-09-15 to 2026-10-13" in ev.text


def test_an_unmatched_period_is_named_in_the_source(conn):
    ev = price_evidence(conn, A, parse_window("What was ZZPP's closing price at the end of last week?", TODAY), TODAY)
    assert "asked about “the end of last week”" in ev.text and "do not isolate" in ev.text
    assert "past week, from 2026-10-06 to 2026-10-13" in ev.text


def test_today_with_an_older_newest_close_is_named_in_the_source(conn):
    ev = price_evidence(conn, A, parse_window("How did ZZPP stock finish today?", TODAY), TODAY)
    assert "asked about today (2026-10-15), but the newest stored close is from 2026-10-13" in ev.text


def test_today_with_todays_close_has_no_such_note(conn):
    conn.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, 500, 'fake')", (A, TODAY))
    ev = price_evidence(conn, A, parse_window("How did ZZPP stock finish today?", TODAY), TODAY)
    assert "asked about today" not in ev.text


# ---- through the whole copilot, with a fake model ----

def _ask(conn, question):
    llm = ScriptedLLM("The change is given in the source [1].")
    return answer_question(conn, FakeEmbedder(), llm, question, expand=False, today=TODAY), llm


def test_the_copilot_attaches_the_caution_for_an_unmatched_period(conn):
    ans, llm = _ask(conn, "What was ZZPP's closing price at the end of last week?")
    assert [e.kind for e in ans.retrieved] == ["price"]
    assert any("the end of last week" in c and "up to the close on 2026-10-13" in c for c in ans.cautions), ans.cautions
    assert "do not isolate" in llm.calls[0][1]      # the model was told too


def test_the_copilot_attaches_a_caution_for_today_when_the_close_is_old(conn):
    ans, _ = _ask(conn, "How did ZZPP stock finish today?")
    assert any("asked about today" in c and "2026-10-13" in c for c in ans.cautions), ans.cautions


def test_a_question_with_a_matched_period_gets_no_period_caution(conn):
    ans, _ = _ask(conn, "How did ZZPP stock do over the last four weeks?")
    assert not [c for c in ans.cautions if "You asked about" in c], ans.cautions
