"""Periods the question names that the parser used to default to "the past month" without a word (DECISIONS: "Fresh held-out
round", fix 2).

"Is Amazon's share price higher than when the year opened?" was compared with a year ago; "Compare how AMD and Nvidia traded over
the past ninety days" used one month and called it ninety days, because the number table stopped at thirty. Both passed the
evaluation rules, which only check that a price was quoted. Now: the wordings that can be read exactly are read ("ninety",
"8 quarters", "since 2024", "since Monday", "a year and a half"), and a period that still cannot be read is flagged in code
(`Window.unmet`, which becomes a caution on the answer) instead of falling to the default silently. The negative cases matter as much:
a question with no period must stay silent, and so must the ones that were always read ("last month", "this week", "since July").
Every wording here is new (none is an evaluation case). Today in these tests is Friday 2026-10-16.
"""
from datetime import date

import pytest

from ai.market import MarketEvidence, Window, detect_intent, news_days, parse_window, period_cautions, price_evidence

TODAY = date(2026, 10, 16)


def read(question):
    return parse_window(question, TODAY)


# ---- "when the year opened" is year to date ----

@pytest.mark.parametrize("question", [
    "Is Amazon's share price higher than when the year opened?",
    "Is Tesla up on where it was when the year began?",
    "Are Nvidia shares ahead of when 2026 kicked off?",
    "Has Apple stock fallen below when the year started?",
    "Compared with when the year opened, is Alphabet's stock price lower?",
    "Has Meta stock moved versus when 2026 began?",
    "Is Amazon stock doing better relative to when the year started?",
])
def test_when_the_year_opened_is_the_year_to_date_window(question):
    w = read(question)
    assert (w.label, w.days, w.explicit) == ("year to date", None, True), question
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "What did Apple say about its plans when the year began?",       # no comparison and no stock
    "Was Tesla's headcount larger when the year ended?",             # "ended" is not an opening
    "Was Tesla's headcount larger than when the year began?",        # a comparison, but not about the stock
    "Is Amazon's revenue higher than when the year started?",        # the stored figures, not prices
    "Compared with when the year began, was Tesla's headcount larger?",
])
def test_other_when_the_year_phrases_are_not_year_to_date(question):
    assert read(question).label != "year to date", question
    assert not detect_intent(question).prices, question


# ---- number words and digits beyond thirty ----

@pytest.mark.parametrize("question,label,days", [
    ("How has Tesla stock done over the past ninety days?", "past 3 months", 92),            # the old label for 90 days
    ("How has Tesla stock done over the past sixty days?", "past 60 days", 60),
    ("How has Tesla stock done over the last forty-five days?", "past 45 days", 45),
    ("How has Tesla stock done over the last forty days?", "past 40 days", 40),
    ("How has Tesla stock done over the last twenty-one days?", "past 21 days", 21),
    ("How has Tesla stock done over the last two hundred days?", "past 200 days", 200),
    ("How has Tesla stock done over the last hundred days?", "past 100 days", 100),
    ("How has Tesla stock done over the past one hundred and twenty days?", "past 120 days", 120),
    ("How has Tesla stock done over the past eighteen months?", "past 18 months", 549),
    ("How has Tesla stock done over the past nineteen weeks?", "past 19 weeks", 133),
    ("How has Tesla stock done over the past 365 days?", "past 365 days", 365),
    ("Is Nvidia stock higher than seventy days ago?", "past 70 days", 70),
])
def test_number_words_beyond_thirty_are_read(question, label, days):
    w = read(question)
    assert (w.label, w.days, w.explicit) == (label, days, True), question


@pytest.mark.parametrize("question,label,days", [
    ("How has Tesla stock done over the past 7 days?", "past week", 7),                      # the canonical labels stay
    ("How has Tesla stock done over the last twelve months?", "past year", 366),
    ("How has Tesla stock done over the last twenty days?", "past 20 days", 20),
    ("How has Tesla stock done over the last few weeks?", "past 3 weeks (reading 'few' as 3)", 21),
])
def test_what_was_read_before_is_read_the_same(question, label, days):
    w = read(question)
    assert (w.label, w.days) == (label, days), question


# ---- quarters, trading days and sessions, a decade, "and a half" ----

@pytest.mark.parametrize("question,label,days", [
    ("How has Tesla stock done over the last 8 quarters?", "past 8 quarters", 732),
    ("How has Tesla stock done over the last two quarters?", "past 2 quarters", 183),
    ("How has Tesla stock done over the past quarter?", "past 3 months", 92),                # unchanged: the plain word
    ("How has Tesla stock done over the last 10 trading days?", "past 10 trading days (about 14 calendar days)", 14),
    ("How has Tesla stock done over the last 5 sessions?", "past 5 trading days (about 7 calendar days)", 7),
    ("How has Tesla stock done over the last 3 trading days?", "past 3 trading days (about 5 calendar days)", 5),   # 4.2, rounded up
    ("How has Tesla stock done over the past decade?", "past 10 years", 3660),
    ("How has Tesla stock done over a year and a half?", "past 1.5 years", 549),
    ("How has Tesla stock done over two and a half years?", "past 2.5 years", 915),
    ("What has Amazon stock done in the past year and a half?", "past 1.5 years", 549),
    ("What has Amazon stock done in the last month and a half?", "past 1.5 months", 46),
    ("How has Tesla stock done over six and a half months?", "past 6.5 months", 198),
])
def test_quarters_sessions_a_decade_and_a_half_are_read_with_their_reading_stated(question, label, days):
    w = read(question)
    assert (w.label, w.days, w.explicit) == (label, days, True), question


# ---- since a year, since a weekday ----

@pytest.mark.parametrize("question,since", [
    ("How has Tesla stock done since 2024?", date(2024, 1, 1)),
    ("How has Tesla stock done since the start of 2025?", date(2025, 1, 1)),
    ("Is Nvidia stock above where it was since the beginning of 2022?", date(2022, 1, 1)),
    ("Where has Apple stock gone since 2019?", date(2019, 1, 1)),
])
def test_since_a_past_year_starts_on_january_first(question, since):
    w = read(question)
    assert (w.since, w.days, w.explicit, w.unmet) == (since, (TODAY - since).days, True, None), question
    assert w.label == f"since January 1, {since.year}"


def test_since_this_year_is_year_to_date():
    assert read("How has Tesla stock done since 2026?").label == "year to date"
    assert read("How has Tesla stock done since the start of 2026?").label == "year to date"


@pytest.mark.parametrize("question,since", [
    ("How has Tesla stock done since Monday?", date(2026, 10, 12)),
    ("How has Tesla stock done since Thursday?", date(2026, 10, 15)),
    ("How has Tesla stock done since Saturday?", date(2026, 10, 10)),
    ("How has Tesla stock done since Friday?", date(2026, 10, 9)),   # today is a Friday: the one a week ago
])
def test_since_a_weekday_starts_on_the_most_recent_one_before_today(question, since):
    w = read(question)
    assert (w.since, w.days, w.explicit, w.unmet) == (since, (TODAY - since).days, True, None), question
    assert str(since) in w.label


def test_since_last_friday_is_still_flagged_not_read():
    w = read("How has Tesla stock done since last Friday?")
    assert w.unmet == "last Friday" and not w.explicit


# ---- a period that still cannot be read is flagged, never defaulted silently ----

@pytest.mark.parametrize("question,phrase", [
    ("How has Tesla stock done since earnings?", "since earnings"),
    ("How has Tesla stock done since the election?", "since the election"),
    ("How has Tesla stock done since the IPO?", "since the IPO"),
    ("How has Tesla stock done since early August?", "early August"),
    ("How has Tesla stock done since late August?", "late August"),
    ("How has Tesla stock done since the end of August?", "end of August"),
    ("How did Tesla stock do between March and June?", "between March and June"),
    ("How did Tesla stock do from June to August?", "from June to August"),
    ("How did Tesla stock do between 2022 and 2024?", "between 2022 and 2024"),
    ("How did Tesla stock do over the summer?", "over the summer"),
    ("How did Tesla stock do during the holidays?", "during the holidays"),
    ("What is Nvidia's all-time high?", "all-time"),
    ("How has Tesla stock done since inception?", "since inception"),
    ("How did Tesla stock do the last time earnings came out?", "the last time"),
    ("How has Tesla stock done since 2031?", "since 2031"),                            # a year that has not come
])
def test_a_period_that_cannot_be_read_is_flagged_with_the_phrase(question, phrase):
    w = read(question)
    assert not w.explicit and w.unmet and phrase.lower() in w.unmet.lower(), (question, w)


@pytest.mark.parametrize("question", [
    "How did Tesla stock do?",
    "What is Tesla's stock price?",
    "Is Apple stock up?",
    "How is Nvidia doing right now?",
    "What did Microsoft say about its cloud business?",
])
def test_a_question_with_no_period_stays_silent(question):
    w = read(question)
    assert not w.explicit and w.unmet is None, question


@pytest.mark.parametrize("question", [
    "How did Tesla stock do last month?",
    "How did Tesla stock do this week?",
    "How has Tesla stock done since July?",
    "How has Tesla stock done since the middle of September?",
    "How has Tesla stock done since last week?",
    "How has Tesla stock done over the past six months?",
    "How has Tesla stock done year to date?",
    "What was Nvidia's all-time high this year?",       # a period was read, so the phrase is not flagged on top of it
])
def test_periods_that_are_read_are_not_flagged(question):
    w = read(question)
    assert w.explicit and w.unmet is None, question


def test_the_old_flagged_periods_are_still_flagged():
    assert read("What was Microsoft's closing price at the end of last week?").unmet
    assert read("How did Tesla stock do in September?").unmet == "in September"
    assert read("How did Tesla stock do in 2024?").unmet == "in 2024"


# ---- the caution reaches headlines too ----

HEADLINES = [MarketEvidence("headline", "ZZUP", "ZZUP headline", "Funco wins a contract", "https://x", TODAY)]
PRICE = [MarketEvidence("price", "ZZUP", "ZZUP price data", "Latest close: 24.00", None, TODAY, change=1.0, change_pct=4.0)]


def test_an_unread_period_on_a_news_question_gets_a_caution_naming_the_days_used():
    w = read("What was said about Tesla since the election?")
    cautions = period_cautions(w, HEADLINES, TODAY)
    assert len(cautions) == 1 and "since the election" in cautions[0]
    assert "headlines" in cautions[0] and f"last {news_days(w)} days" in cautions[0]


def test_no_news_caution_for_a_period_that_was_read():
    assert period_cautions(read("What was said about Tesla over the past 3 weeks?"), HEADLINES, TODAY) == []


def test_a_question_with_both_prices_and_headlines_gets_one_caution_not_two():
    w = read("How has Tesla stock done since the election, and what is the news?")
    assert len(period_cautions(w, PRICE + HEADLINES, TODAY)) == 1


def test_no_caution_when_there_is_no_price_or_headline_source():
    assert period_cautions(read("How has Tesla stock done since the election?"), [], TODAY) == []


# ---- a window that reaches back past the stored prices ----

def test_a_window_reaching_past_the_oldest_stored_close_gets_a_caution_with_that_date():
    from data.db import connect
    sym = "ZZUP"
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Upco')", (sym,))
        for i in range(120):  # 120 daily bars ending today
            c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, %s, 'fake')",
                      (sym, date.fromordinal(TODAY.toordinal() - 119 + i), 100 + i))
        c.commit()
        try:
            first = date.fromordinal(TODAY.toordinal() - 119)
            far = price_evidence(c, sym, read("How has Upco stock done over the past decade?"), TODAY)
            assert far.starts == first
            cautions = period_cautions(read("How has Upco stock done over the past decade?"), [far], TODAY)
            assert len(cautions) == 1 and str(first) in cautions[0] and "past 10 years" in cautions[0]
            # within a week of the start of the data is not worth a warning (weekends and holidays)
            near = price_evidence(c, sym, Window("past 120 days", 123, True), TODAY)
            assert near.starts is None and period_cautions(Window("past 120 days", 123, True), [near], TODAY) == []
            # a window the data covers fully
            month = price_evidence(c, sym, read("How has Upco stock done over the past month?"), TODAY)
            assert month.starts is None
        finally:
            c.rollback()
            c.execute("DELETE FROM prices_daily WHERE symbol = %s", (sym,))
            c.execute("DELETE FROM instruments WHERE symbol = %s", (sym,))
            c.commit()
