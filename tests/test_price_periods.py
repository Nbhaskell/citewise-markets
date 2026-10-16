"""Price questions that name a period but use none of the usual price words (DECISIONS: "Second held-out round").

"Show me how Alphabet has moved over the last three months" has no "stock" or "shares" next to "moved", so it went to the
filings, which hold no prices, and the answer said there was no price data. Each phrase below was added one at a time. The
wordings here are new (none is a held-out or evaluation case). The negative cases matter as much: "moved" and a period
turn up in filings questions too, and a price route for those would swap a good answer for a wrong one.
"""
from datetime import date

import pytest

from ai.market import detect_intent, parse_window

THIS_YEAR = date.today().year


@pytest.mark.parametrize("question", [
    "How has AMD moved over the past six months?",
    "Where has Tesla trended in the last 90 days?",
    "Show me how Nvidia has fared over the past two weeks.",
    "How did Microsoft move this year?",
    "Walk me through how Amazon has swung during the last twelve months.",
])
def test_a_company_that_moved_over_a_named_period_is_a_price_question(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "How did Apple move its supply chain this year?",                # "move its": something moved, not the price
    "How did Microsoft move into cloud over the last five years?",   # "move into"
    "How has Apple's headcount moved over the last year?",           # the subject is the headcount
    "Where has Tesla's Bitcoin holding trended over the past year?",
    "How has Amazon's revenue moved over the past year?",            # the stored figures, not prices
    "How has AMD moved?",                                            # no period named: not this rule's business
])
def test_filings_questions_with_moved_and_a_period_are_not_price_questions(question):
    assert not detect_intent(question).prices, question


# ---- a comparison with where the stock started the year ----


@pytest.mark.parametrize("template", [
    "Is Tesla trading above where it opened {y}?",
    "Has AMD fallen below where it began {y}?",
    "Is Microsoft higher than where it was at the start of {y}?",
    "Are Nvidia shares ahead of where they stood at the beginning of the year?",
    "Is Amazon still above where it finished last year?",
])
def test_a_comparison_with_where_it_started_the_year_is_a_year_to_date_price_question(template):
    question = template.format(y=THIS_YEAR)
    got = detect_intent(question)
    assert got.prices and not got.filings, question
    assert parse_window(question).label == "year to date", question


@pytest.mark.parametrize("question", [
    f"Where did Apple's revenue stand at the start of {THIS_YEAR}?",              # revenue, not a price
    f"Where was Tesla's headcount at the beginning of {THIS_YEAR}?",              # a possessive subject
    "Is Amazon above where it started 1999?",                                      # not this year: left alone, not guessed
])
def test_other_start_of_year_questions_are_not_read_as_year_to_date_price_questions(question):
    assert not detect_intent(question).prices, question


def test_only_this_years_start_counts_as_year_to_date():
    from ai.market import year_start_comparison

    assert year_start_comparison("Is Amazon above where it started 2026?", today=date(2026, 10, 15))
    assert not year_start_comparison("Is Amazon above where it started 2026?", today=date(2027, 3, 1))  # a different year's start
    assert not year_start_comparison("Is Amazon above where it started 2025?", today=date(2026, 10, 15))


def test_where_it_was_last_year_is_not_a_price_question_on_its_own():
    assert not detect_intent("Is Apple's revenue higher than where it was last year?").prices


# ---- a stock noun plus a period that is now understood ("the last few weeks") ----


@pytest.mark.parametrize("question", [
    "Have Nvidia shares treated holders well over the past several weeks?",
    "Has the stock market been kind to Amazon over the last few weeks?",
    "Has Tesla stock been rewarding over the last four weeks?",
])
def test_a_stock_noun_with_a_period_that_is_now_understood_is_a_price_question(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "How many Tesla shares were repurchased over the last four weeks?",     # a count of shares, not their price
    "Is Apple's stock-based compensation larger than in the last six months?",  # "stock-based" is not the stock
    "What did Microsoft's 10-Q say about risks over the past two months?",  # a period, no stock noun
])
def test_a_wider_period_reading_does_not_pull_in_filings_questions(question):
    assert not detect_intent(question).prices, question
