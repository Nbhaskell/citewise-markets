"""Price questions that did not use the usual words, found by the held-out round (DECISIONS: "Held-out round").

"Why is Tesla tanking?", "Why did Microsoft shares go up lately?" and "Give me the one-week move for Tesla" all went to
the filings only. The filings have no prices, so the answers said "not available" or, worse, the model invented headlines.
Each wording below was added to the price rules one at a time. The negative cases matter as much: the same words turn up
in filings questions, and a price route for those would swap a good answer for a wrong one.
"""
import pytest

from ai.market import detect_intent, parse_window


@pytest.mark.parametrize("question", [
    "Is Nvidia tanking right now?",
    "Tesla stock has been tanking, hasn't it?",
    "Could Amazon tank next year?",
    "Why did Apple shares go up lately?",
    "Did Nvidia stock go down this week?",
    "Why is Apple stock going up?",
    "Has Amazon stock gone higher since Monday?",
    "Did Microsoft shares go lower on Monday?",
    "What was Apple's two-week swing?",
    "Show the monthly move for Microsoft.",
    "What's the 3-month movement in Nvidia?",
    "Give me the one-week move for Tesla.",
])
def test_these_wordings_are_price_questions(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


def test_a_why_question_about_a_price_also_gets_headlines_but_no_filings():
    for question in ("Why is Tesla tanking?", "Why did Microsoft shares go up lately?"):
        got = detect_intent(question)
        assert (got.prices, got.headlines, got.filings) == (True, True, False), question


@pytest.mark.parametrize("question", [
    "How many shares go to employees under Tesla's stock plan?",   # "shares go", but not up or down
    "What is the one-year change in Apple's revenue?",             # a period and "change", not a price move
    "How did Apple's segment performance change over two years?",
    "What moves are planned in Tesla's supply chain?",              # "moves", no period word before it
    "Does Tesla make the tank for its Semi?",                       # the noun "tank"
    "What are the risks of an oil tank leak for Amazon's fulfilment centers?",
    "How do Microsoft employees go up the pay scale?",              # "go up", no stock or shares before it
])
def test_filings_questions_that_share_words_are_not_price_questions(question):
    assert not detect_intent(question).prices, question


@pytest.mark.parametrize("question,label,days", [
    ("Give me the one-week move for Tesla.", "past week", 7),
    ("What was Apple's two-week swing?", "past 2 weeks", 14),   # it used to be read as one week, since "week" is in it
    ("Show the weekly move for Microsoft.", "past week", 7),
    ("Show the monthly move for Microsoft.", "past month", 31),
    ("What's the 3-month movement in Nvidia?", "past 3 months", 92),
])
def test_the_period_in_the_question_is_the_period_used(question, label, days):
    window = parse_window(question)
    assert (window.label, window.days, window.explicit) == (label, days, True)
