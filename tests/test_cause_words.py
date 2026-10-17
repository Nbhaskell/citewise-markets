"""Questions that ask what moved a stock, in words other than "why" (DECISIONS: "Fix (3) of the fresh round", the known gap).

"Google doubled this month. What drove it?" and "What caused Nvidia's last big drop?" were price questions with no headlines, because only
"why", "reason", "because", "what happened" and "what's behind / driving / causing / moving" were cause words: the model then had no
headlines to point at, and said none were provided. Now the other everyday forms count too ("what drove / caused / triggered / sparked /
prompted / pushed / made / led to", "how come", "what's responsible for", "the story behind"). And a cause question that names the move
as a noun ("Amazon's jump this month", "the selloff in Tesla stock", "the move in Microsoft stock") reaches the prices, which a price
verb or a stock word used to be needed for. Cause words only matter on a price question, so the filings questions that share them
("What drove Apple's services revenue growth?") are unchanged; the move-noun rule is the one that could misroute, so its guards are the
business metrics ("Nvidia's slide in gross margin", "the drop in Apple's revenue"). Every wording is new (none is an evaluation case).
"""
import pytest

from ai.market import detect_intent


@pytest.mark.parametrize("question", [
    "Google doubled this month. What drove it?",
    "What caused Nvidia's last big drop?",
    "What triggered the selloff in Tesla stock this week?",
    "What sparked Amazon's jump this month?",
    "What explains the rally in AMD stock?",
    "What made Apple shares fall this week?",
    "What pushed Microsoft stock higher this month?",
    "What led to the drop in Alphabet stock yesterday?",
    "How come Tesla stock fell this week?",
    "What's responsible for Nvidia's slide this month?",
    "What's the story behind Amazon's jump this week?",
    "Any idea what drove AMD stock down last week?",
    "What prompted the surge in Tesla stock?",
    "Apple stock dropped 5% this week. What caused that?",
    "What is behind the move in Microsoft stock?",
    "What was responsible for the plunge in Nvidia shares?",
    "Tesla stock tumbled this week. What triggered it?",
    "Tesla stock tumbled this week. Anything that triggered it?",          # "triggered it" with no "what" before it
    "What triggered Nvidia stock's decline this week?",                    # "what triggered" and none of the objects named in the rule
])
def test_these_cause_questions_about_a_move_get_prices_and_headlines(question):
    got = detect_intent(question)
    assert got.prices and got.headlines and not got.filings, question


@pytest.mark.parametrize("question", [
    "What drove Apple's services revenue growth?",
    "What caused the increase in Tesla's R&D spending?",
    "What triggered the legal proceedings against Amazon?",
    "What made Microsoft's cloud segment grow?",
    "What does Apple say about what drove its margins?",
    "Does the 10-K explain what caused the supply shortage?",
    "How come Apple's revenue grew this year?",
])
def test_cause_questions_about_the_business_are_not_price_or_news_questions(question):
    got = detect_intent(question)
    assert not got.prices and not got.headlines, question


# "jump", "slide" and "swoon" are the move nouns this rule adds; "rally", "surge", "plunge", "crash", "drop" and the like were already price
# words everywhere (which misroutes "the drop in Apple's revenue" and "the crash test results": a known gap, see DECISIONS).
@pytest.mark.parametrize("question", [
    "What drove the increase in Tesla's R&D spending this year?",
    "What caused Nvidia's slide in gross margin this year?",
    "What sparked Amazon's jump in AWS revenue this year?",
    "What explains the jump in Microsoft's cloud revenue this quarter?",
    "What was behind the slide in Apple's services margin this quarter?",
])
def test_a_move_noun_about_a_business_metric_is_not_a_price_question(question):
    got = detect_intent(question)
    assert not got.prices, question


@pytest.mark.parametrize("question", [
    "What sparked Amazon's jump?",              # no period and no stock word: could be a segment
    "What sparked its jump this month?",        # no company named
    "What sparked the company's jump this month?",
])
def test_a_move_noun_needs_a_company_and_a_period_or_a_stock_word(question):
    assert not detect_intent(question).prices, question


def test_a_move_noun_without_a_cause_word_is_left_alone():
    # No cause is asked for: "Amazon's jump this month" alone is not routed by this rule.
    assert not detect_intent("Tell me about Amazon's jump this month.").prices


@pytest.mark.parametrize("question", [
    "How has Tesla stock done this month?",
    "Why did Nvidia drop this week?",
    "Can you explain why Nvidia shares fell?",
])
def test_the_routes_that_already_worked_still_do(question):
    got = detect_intent(question)
    assert got.prices and (got.headlines or "Why" not in question and "why" not in question), question
