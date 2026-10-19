"""Price and news questions that never reached the price or news data (DECISIONS: "Fresh held-out round", cause 1).

"Where has AMD stock gone since the middle of August?", "Tell me Tesla's close from last Friday", "How much higher is Nvidia
than it was twelve months ago?", "What's the chatter around Microsoft this week?", "Pull up some recent stories about Amazon"
and "Were the stories on Tesla more positive or negative?" all fell through to the filings, which hold no prices and no
headlines, so the answers said the data was not there. Each wording below was added one at a time and is written in new
words (none is an evaluation case). The negative cases matter as much: the same words turn up in filings questions, and a
price or news route for those would swap a good answer for a wrong one.
"""
from datetime import date

import pytest

from ai.market import detect_intent, news_days, parse_window

TODAY = date(2026, 10, 16)


# ---- "since the middle of <month>" ----

@pytest.mark.parametrize("question,since", [
    ("How has Tesla stock held up since the middle of September?", date(2026, 9, 15)),
    ("Where have Microsoft shares been since mid-July?", date(2026, 7, 15)),
    ("Has Amazon stock recovered since mid August?", date(2026, 8, 15)),
    ("Show me Apple stock since the middle of December.", date(2025, 12, 15)),   # December has not come yet this year
    ("Is Nvidia stock up since the middle of January?", date(2026, 1, 15)),      # not year to date: it starts on the 15th
])
def test_since_the_middle_of_a_month_starts_on_the_15th_and_says_so(question, since):
    w = parse_window(question, TODAY)
    assert w.since == since and w.explicit and w.days == (TODAY - since).days, question
    assert f"{since.strftime('%B')} 15" in w.label and "middle" in w.label, w.label  # the reading is stated, not hidden


def test_since_the_start_of_a_month_still_starts_on_the_1st():
    w = parse_window("How has AMD stock done since the start of August?", TODAY)
    assert w.since == date(2026, 8, 1) and "middle" not in w.label


@pytest.mark.parametrize("question", [
    "Where has Tesla stock gone since the middle of September?",
    "How have Nvidia shares done since mid-March?",
])
def test_a_stock_with_a_middle_of_the_month_start_is_a_price_question(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


# ---- "<number> <unit> ago" is a period too ----

@pytest.mark.parametrize("question,label,days", [
    ("Is Nvidia stock higher than six weeks ago?", "past 6 weeks", 42),
    ("Where was Tesla stock 3 days ago compared with now?", "past 3 days", 3),
    ("How much has Apple stock moved since eight months ago?", "past 8 months", 244),
    ("Is Amazon stock above where it was twelve months ago?", "past year", 366),
])
def test_a_number_of_units_ago_is_read_as_the_period(question, label, days):
    w = parse_window(question, TODAY)
    assert (w.label, w.days, w.explicit) == (label, days, True), question


# ---- "close" as a noun ----

@pytest.mark.parametrize("question", [
    "Tell me Apple's close from last Thursday.",
    "What was Amazon's close on Monday?",
    "Where did Nvidia close yesterday?",
    "Did Tesla close higher this week?",
    "What was the close for Microsoft at the end of last month?",
])
def test_a_question_about_a_close_is_a_price_question(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


def test_a_close_on_a_named_day_is_read_as_that_day_and_no_longer_warned():
    # Before 2026-10-19 this was "unmet" (the daily closes were said not to isolate a day); now the day's own close is given
    # (DECISIONS: "Fourth-round misses"), so there is nothing to warn about.
    w = parse_window("Tell me Apple's close from last Thursday.", TODAY)
    assert w.unmet is None and w.day is not None and w.day.strftime("%A") == "Thursday"


@pytest.mark.parametrize("question", [
    "How important is Apple's close relationship with TSMC?",
    "Did Tesla close its Shanghai plant on Friday?",
    "When does Amazon's fiscal year close?",
    "Is Microsoft close to finishing its acquisition?",
    "What did Alphabet say about the close of the Mandiant deal?",
    "Which Nvidia customers are close partners?",
    "Where did Tesla close its first retail store?",                           # "where did ... close", but a thing is closed
    "Microsoft's close on the Activision deal was delayed, wasn't it?",         # a possessive and "close on", but a deal
])
def test_filings_questions_that_share_the_word_close_are_not_price_questions(question):
    assert not detect_intent(question).prices, question


# ---- "how much higher is X than it was <period> ago" ----

@pytest.mark.parametrize("question", [
    "How much higher is Nvidia than it was a year ago?",
    "How much lower is Tesla than it was six months ago?",
    "Is Amazon higher than it was two years ago?",
    "Is AMD lower than where it was a month ago?",
])
def test_a_company_compared_with_itself_a_while_ago_is_a_price_question(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "How much higher is Apple's revenue than a year ago?",             # the stored figures, not prices
    "Is Microsoft's cloud revenue higher than it was two years ago?",
    "Is Tesla's headcount higher than it was two years ago?",          # a possessive subject
    "How much higher is revenue than it was a year ago?",              # a figures word
    "How much higher is Amazon than Walmart?",                         # no period
    "Is Tesla lower than it was?",                                      # no period named
])
def test_a_comparison_about_something_other_than_the_stock_is_not_a_price_question(question):
    assert not detect_intent(question).prices, question


# ---- news wording ----

@pytest.mark.parametrize("question", [
    "What's the chatter around Alphabet?",
    "Any chatter about AMD today?",
    "Pull up the latest stories on Nvidia.",
    "What new stories are there on Tesla?",
    "Give me the top stories about Microsoft this week.",
    "Are there any stories on Apple?",
])
def test_these_wordings_are_news_questions(question):
    got = detect_intent(question)
    assert got.headlines and not got.filings, question


def test_the_week_in_a_chatter_question_is_the_news_window():
    assert news_days(parse_window("What's the chatter around Alphabet this week?", TODAY)) == 7


@pytest.mark.parametrize("question", [
    "How does Apple describe its customer success stories in the 10-K?",
    "What is the story behind Tesla's Semi program?",
    "What does Microsoft say about stories told by its game studios?",
    "Is Alphabet still chattering with regulators about the settlement?",            # "chattering" is not "chatter"
])
def test_filings_questions_that_share_words_with_news_are_not_news_questions(question):
    assert not detect_intent(question).headlines, question


# ---- stories / headlines that are more positive or negative ----

@pytest.mark.parametrize("question", [
    "Over the last month, were the headlines on Amazon mostly positive or negative?",
    "Are the stories about Nvidia more negative than positive?",
    "Were the stories on Tesla more positive or negative over the past month?",
    "Is the news on Apple mostly negative these days?",
    "Would you say the articles about AMD lean positive or negative?",
])
def test_stories_that_are_mostly_positive_or_negative_are_a_sentiment_question(question):
    got = detect_intent(question)
    assert got.sentiment and got.headlines and not got.filings, question


@pytest.mark.parametrize("question", [
    "Is Apple's cash flow positive or negative?",
    "Were Tesla's headline earnings positive or negative?",             # "headline" as an adjective
    "Is Amazon's free cash flow more positive than last year?",
    "Which stories in the 10-K are negative for Microsoft?",             # not the news source words
])
def test_something_positive_or_negative_that_is_not_the_news_is_not_a_sentiment_question(question):
    assert not detect_intent(question).sentiment, question
