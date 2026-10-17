"""Company-figure questions worded with "earn", "sales", "bring in" and "the last four quarters" (DECISIONS: "Second held-out
round", item 2; fix (d)).

"How much did Amazon earn over the past twelve months?" went to the price data, because "how much did" is a price phrase,
and the answer was that earnings were not in the sources. "How many dollars of sales did Nvidia bring in over the last four
quarters?" went to the filings, because any "quarters" reads as a filing, and the filings have no twelve-month total. The
stored figures are twelve-month totals, so both are figures questions. The negative cases matter as much: "earn" and
"sales" turn up in questions about pay, products, taxes and one quarter, which the figures cannot answer.
"""
import pytest

from ai.market import detect_intent


@pytest.mark.parametrize("question,topics", [
    ("How much did Amazon earn over the past twelve months?", {"profit"}),
    ("What did Microsoft earn last year?", {"profit"}),
    ("How much does Apple earn?", {"profit"}),
    ("How much money has Alphabet earned over the last four quarters?", {"profit"}),
    ("How much has Amazon pocketed in profit over its latest four quarters?", {"profit"}),     # "latest" and "recent" are the same stretch
    ("What are Microsoft's net sales across the most recent four quarters?", {"revenue"}),
    ("How much did Apple's sales grow?", {"revenue"}),
    ("How many dollars of sales did Nvidia bring in over the last four quarters?", {"revenue"}),
    ("What were Nvidia's sales over the trailing twelve months?", {"revenue"}),
    ("What are Microsoft's net sales for the past four quarters?", {"revenue"}),
    ("Total sales for Amazon in the last year?", {"revenue"}),
    ("How much money did Tesla bring in over the past year?", {"revenue"}),
    ("What was the dollar amount of sales at Amazon over the last twelve months?", {"revenue"}),   # only the "amount of sales" form
])
def test_these_wordings_are_figures_questions(question, topics):
    got = detect_intent(question)
    assert got.fundamentals == frozenset(topics) and not got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "How much do Apple engineers earn?",                              # pay, not the company's profit
    "How much do Tesla employees earn on average?",
    "What were Apple's iPhone sales last year?",                      # a product, not the company's revenue
    "What were Apple's iPhone sales over the past year?",             # found by a fresh evaluation case: a period must not turn product sales into revenue
    "How did iPad sales for Apple change over the last twelve months?",
    "How have retail sales held up for Amazon?",
    "What is Amazon's sales tax liability?",
    "How big is Tesla's sales team?",
    "How much did Microsoft earn in the second quarter?",             # one quarter: the 10-Q, not a twelve-month total
    "What were Nvidia's sales last quarter?",
    "How much did Apple's sales grow in its latest quarterly report?",
    "Why did Amazon's sales fall last year?",                         # a "why" is a filings question
    "How much did Apple pay in dividends last year?",
    "How much did Microsoft pay to buy Activision?",
])
def test_look_alikes_do_not_get_the_figures(question):
    assert detect_intent(question).fundamentals == frozenset(), question


@pytest.mark.parametrize("question", [
    "How much did Microsoft earn in the second quarter?",
    "How much did Apple pay in dividends last year?",
    "How much did Microsoft pay to buy Activision?",
    "How much did Apple's sales grow in its latest quarterly report?",
])
def test_how_much_did_a_company_do_something_with_money_is_not_a_price_question(question):
    got = detect_intent(question)
    assert not got.prices and got.filings, question


@pytest.mark.parametrize("question", [
    "How much did Apple stock go up this week?",
    "How much did Nvidia close at yesterday?",
    "How much did Tesla shares lose last month?",
    "How much is Tesla's stock price today?",
    "How much did the price of Amazon stock earn holders this year?",    # a stock word keeps it a price question
    "How much does Apple cost to buy, per share?",
    "How much did Tesla stock sell for on Monday?",                      # "sell" is a money verb; only the stock word keeps this a price question
])
def test_how_much_questions_about_the_stock_are_still_price_questions(question):
    assert detect_intent(question).prices, question


def test_the_last_four_quarters_is_twelve_months_but_one_quarter_is_not():
    four = detect_intent("What was Nvidia's revenue over the last four quarters?")
    assert four.fundamentals == frozenset({"revenue"}) and not four.filings
    one = detect_intent("What was Nvidia's revenue last quarter?")
    assert one.fundamentals == frozenset() and one.filings
    two = detect_intent("What was Nvidia's revenue over the last two quarters?")                  # not twelve months
    assert two.fundamentals == frozenset() and two.filings
    named = detect_intent("What did Nvidia's quarterly report say about the last four quarters of revenue?")
    assert named.fundamentals == frozenset()                           # a filing is named: that wins


def test_a_figures_question_that_also_asks_for_the_price_keeps_both():
    got = detect_intent("How much did Amazon earn over the past year, and how has the stock done?")
    assert got.fundamentals == frozenset({"profit"}) and got.prices and not got.filings
