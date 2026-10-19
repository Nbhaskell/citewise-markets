"""The period a price question names, and what the app says when it cannot match it (DECISIONS: "Second held-out round").

"since July" was answered over the past month, "over the last few weeks" was not read as a period at all, "the end of last
week" got the newest close as if it were that day's, and "today" got a two-day-old close. Passing answers hid all four,
because the checks looked for figures and sources, not for the period asked. Now `parse_window` reads more periods, and a
period it cannot match is named in the price source and carried to the answer as a caution, in code.
"""
from datetime import date

import pytest

from ai.market import Window, parse_window, period_cautions

NOW = date(2026, 10, 15)


@pytest.mark.parametrize("question,label,days", [
    ("How has Apple done over the last four weeks?", "past 4 weeks", 28),
    ("Tesla in the last 10 days", "past 10 days", 10),
    ("Nvidia over the past two months", "past 2 months", 61),
    ("Amazon in the past nine months", "past 9 months", 274),
    ("Microsoft over the last 3 years", "past 3 years", 1098),
    # the forms that were already right keep their labels and lengths
    ("Tesla in the past three months", "past 3 months", 92),
    ("Nvidia over the last 90 days", "past 3 months", 92),
    ("Nvidia over the last 12 months", "past year", 366),
    ("Apple over the last two weeks", "past 2 weeks", 14),
    ("Apple over the last 7 days", "past week", 7),
    ("Nvidia over the last 5 years", "past 5 years", 1830),
])
def test_a_number_of_days_weeks_months_or_years_is_read(question, label, days):
    w = parse_window(question, NOW)
    assert (w.label, w.days, w.explicit) == (label, days, True)


@pytest.mark.parametrize("question,n,unit", [
    ("Has Amazon been kind to holders over the last few weeks?", 3, "weeks"),
    ("Tesla over the past couple of weeks", 2, "weeks"),
    ("AMD over the last several months", 4, "months"),
])
def test_a_rough_amount_is_read_as_a_number_and_the_label_says_so(question, n, unit):
    w = parse_window(question, NOW)
    assert w.explicit and w.label.startswith(f"past {n} {unit} (reading '") and w.label.endswith(f"as {n})")


@pytest.mark.parametrize("question,since,label", [
    ("How did Apple shares do since July?", date(2026, 7, 1), "since July 1"),
    ("Tesla since the start of September", date(2026, 9, 1), "since September 1"),
    ("Nvidia since October", date(2026, 10, 1), "since October 1"),
    ("Amazon since December", date(2025, 12, 1), "since December 1"),   # a month still to come this year means last year's
])
def test_since_a_month_starts_on_its_first_day(question, since, label):
    w = parse_window(question, NOW)
    assert (w.since, w.label, w.days, w.explicit) == (since, label, (NOW - since).days, True)


def test_since_january_is_still_year_to_date():
    w = parse_window("Nvidia stock since January", NOW)
    assert (w.label, w.days, w.since) == ("year to date", None, None)


@pytest.mark.parametrize("question,phrase", [
    ("What was Microsoft's closing price at the end of last week?", "the end of last week"),
    ("What was Apple's price on October 3rd?", "on October 3rd"),
    ("How did Amazon do during July?", "during July"),
    ("What did Nvidia do in Q2?", "Q2"),
    ("How did Alphabet do in 2025?", "in 2025"),
])
def test_a_period_that_cannot_be_matched_is_named(question, phrase):
    assert parse_window(question, NOW).unmet == phrase


@pytest.mark.parametrize("question", [
    "Nvidia stock last month", "Nvidia stock this week", "How has Apple done over the last four weeks?",
    "Nvidia since July", "What is Apple's stock price?", "Nvidia over the past year",
])
def test_a_period_that_is_matched_is_not_flagged(question):
    assert parse_window(question, NOW).unmet is None


def test_today_and_yesterday_are_remembered_for_the_freshness_check():
    assert parse_window("How did Tesla's stock finish today?", NOW).asked_day == "today"
    assert parse_window("What did Tesla close at yesterday?", NOW).asked_day == "yesterday"
    assert parse_window("How is Tesla's stock?", NOW).asked_day is None


# ---- the caution that goes with the answer ----

class _Ev:
    def __init__(self, kind, as_of):
        self.kind, self.as_of, self.starts = kind, as_of, None


def test_no_caution_for_a_matched_period():
    assert period_cautions(parse_window("Nvidia over the last four weeks", NOW), [_Ev("price", date(2026, 10, 15))], NOW) == []


def test_an_unmatched_period_carries_a_caution_naming_the_window_used():
    w = parse_window("What was Microsoft's closing price at the end of last week?", NOW)
    [caution] = period_cautions(w, [_Ev("price", date(2026, 10, 13))], NOW)
    assert "the end of last week" in caution and "past week" in caution and "2026-10-13" in caution


def test_today_with_an_older_newest_close_carries_a_caution():
    w = parse_window("How did Tesla's stock finish today?", NOW)
    [caution] = period_cautions(w, [_Ev("price", date(2026, 10, 13))], NOW)
    assert "today" in caution and "2026-10-13" in caution
    assert period_cautions(w, [_Ev("price", NOW)], NOW) == []                      # the newest close is today's


def test_the_oldest_newest_close_is_the_one_named():
    w = parse_window("How did the stocks finish today?", NOW)
    [caution] = period_cautions(w, [_Ev("price", date(2026, 10, 14)), _Ev("price", date(2026, 10, 13))], NOW)
    assert "2026-10-13" in caution


def test_no_caution_without_a_price_or_headline_source():
    w = parse_window("What was Microsoft's closing price at the end of last week?", NOW)
    assert period_cautions(w, [], NOW) == []


def test_a_headline_source_alone_gets_the_headlines_version_not_the_price_one():
    # Changed in fix (2): an unmatched period on a news question used to pass without a word (see test_unread_periods.py).
    w = parse_window("What was Microsoft's closing price at the end of last week?", NOW)
    [caution] = period_cautions(w, [_Ev("headline", NOW)], NOW)
    assert "stored headlines" in caution and "daily prices" not in caution


def test_a_window_without_the_new_fields_still_builds():
    assert Window("past month", 31, True).since is None
