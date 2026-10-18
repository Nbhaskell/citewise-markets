"""Price questions that say "lately" (DECISIONS: "Router second look, 'lately'").

"lately" was a news word everywhere, so "Has Nvidia been trending up or sagging lately?" fetched headlines it did not ask for, and a price
question with no word the price rules knew ("Is Amazon's share value holding steady lately?") went to the headlines ALONE. Two narrow
rules fix that: (1) "lately" brings headlines only when the question is not already a price question, and (2) a company, a movement
word and a recency word is a price question ("Has Apple been climbing or sliding lately?"). "lately" is still the news cue in "What are
people saying about Microsoft lately?", and a cause question still brings both. The negative cases matter as much as the positive ones:
the same movement words turn up in questions about a business ("climbing the ranks", "slipping on iPhone sales").
"""
import pytest

from ai.market import detect_intent


def route(question):
    got = detect_intent(question)
    return (got.prices, got.headlines, got.filings)


# ---- (1) "lately" is a news cue only when the question is not already about the price ----


@pytest.mark.parametrize("question", [
    "Has Microsoft stock been rising lately?",
    "Is Nvidia stock down lately?",
    "How has Tesla's stock moved lately?",
    "Did Amazon shares drop lately?",
    "Is Apple stock volatile lately?",
])
def test_a_price_question_with_lately_gets_no_headlines(question):
    assert route(question) == (True, False, False), question


@pytest.mark.parametrize("question", [
    "What are people saying about Microsoft lately?",
    "What has Tesla been up to lately?",
    "Anything new with Amazon lately?",
    "How is Tesla lately?",
    "Is Google doing well lately?",
])
def test_lately_is_still_a_news_cue_when_the_question_is_not_about_the_price(question):
    assert route(question) == (False, True, False), question


@pytest.mark.parametrize("question", [
    "Has Apple stock been rising, and are there headlines about it lately?",
    "Did Nvidia shares drop, and what is the buzz lately?",
    "Is Tesla stock down, and is there any news lately?",
])
def test_a_price_question_that_asks_for_news_too_still_gets_both(question):
    assert route(question) == (True, True, False), question


@pytest.mark.parametrize("question", [
    "Why did Microsoft shares go up lately?",
    "What drove Amazon stock down lately?",
    "Why has Nvidia been sliding lately?",
])
def test_a_cause_question_about_the_price_still_gets_both(question):
    assert route(question) == (True, True, False), question


def test_lately_does_not_change_a_mood_question():
    got = detect_intent("Are investors feeling positive about Nvidia lately?")
    assert (got.sentiment, got.headlines) == (True, True)


# ---- (2) a company, a movement word and a recency word is a price question ----


@pytest.mark.parametrize("question, verb", [
    ("Has Microsoft been climbing steadily lately?", "climbing"),
    ("Is Tesla sliding again these days?", "sliding"),
    ("Has AMD been slipping recently?", "slipping"),
    ("Is Nvidia drifting sideways lately?", "drifting"),
    ("Has Apple been sagging of late?", "sagging"),
    ("Has Google been trending lower recently?", "trending"),
    ("Is Amazon sinking again lately?", "sinking"),
    ("Has Tesla been dipping a bit lately?", "dipping"),
    ("Is Microsoft's stock holding firm lately?", "holding firm"),
    ("Is Alphabet's stock value holding steady lately?", "holding steady"),
    ("Is Apple's quote holding flat these days?", "holding flat"),
])
def test_each_movement_word_makes_a_price_question(question, verb):
    assert route(question) == (True, False, False), question


@pytest.mark.parametrize("question", [
    "Has Apple been climbing lately?",                             # each verb that may open the question
    "Is Apple climbing lately?",
    "Was Nvidia sliding recently?",
    "Were Tesla's shares drifting lately?",
])
def test_each_verb_that_may_open_the_question(question):
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Is Tesla's stock climbing lately?",
    "Is Amazon's share value drifting lately?",
    "Has Alphabet's stock value been sagging lately?",
    "Is Apple's quote sliding lately?",
    "Is Nvidia's stock slipping lately?",
])
def test_the_company_can_be_named_through_its_stock_or_quote(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "Has Apple been climbing or sliding lately?",                  # the question that started this
    "Is Amazon's share value holding steady lately?",
    "Has Alphabet's quote been drifting lately?",
    "Has Nvidia been trending up or sagging lately?",
])
def test_the_questions_that_started_this_are_price_questions_without_headlines(question):
    assert route(question) == (True, False, False), question


@pytest.mark.parametrize("question", [
    "Has Tesla been climbing lately?",                             # the movement word ends the question
    "Has Tesla been climbing up lately?",                          # then each word that may follow it
    "Has Tesla been sliding down lately?",
    "Has Tesla been trending higher lately?",
    "Has Tesla been trending lower lately?",
    "Has Tesla been drifting sideways lately?",
    "Has Tesla been slipping again lately?",
    "Has Tesla been climbing steadily lately?",
    "Has Tesla been sinking slowly lately?",
    "Has Tesla been dipping a bit lately?",
    "Has Tesla been climbing or sliding lately?",
    "Has Tesla been climbing and sliding lately?",
    "Has Tesla been sliding? It seems so lately.",
    "Has Tesla been sliding, lately?",
    "These days, has Tesla been climbing",                         # the movement word ends the text with no punctuation
])
def test_each_word_that_may_follow_the_movement_word(question):
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Has Tesla been climbing lately?",                             # "lately"
    "Has Tesla been climbing recently?",                           # each recency word
    "Has Tesla been climbing these days?",
    "Has Tesla been climbing of late?",
    "Has Tesla been climbing this week?",                          # or a named period
    "Has Tesla been climbing over the last month?",
    "Has Tesla been climbing since Monday?",
    "Has Tesla been dipping today?",
])
def test_each_recency_word_or_named_period_is_enough(question):
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Has Tesla been climbing the ranks of automakers lately?",     # an object: a ranking, not a price
    "Is Amazon slipping into the cloud market lately?",
    "Has Apple been slipping on iPhone sales lately?",
    "Is Microsoft's market share sliding lately?",
    "Is Tesla's demand dipping lately?",
    "Has Nvidia been trending toward custom chips lately?",
    "Has Amazon been drifting from its mission lately?",
    "Has Alphabet been sinking money into AI lately?",
    "Has the company been climbing lately?",                       # no company named
    "Has its business been sliding lately?",
    "Is revenue climbing lately for Tesla?",                       # the subject is a figure, not the company
    "Is demand sliding lately at Apple?",
    "Has spending been dipping lately at Amazon?",
    "Has debt been climbing lately at Microsoft?",
    "Has cash been drifting lately at Nvidia?",
    "Are sales slipping lately at Tesla?",
    "Has income been sagging lately at AMD?",
])
def test_the_same_words_in_a_business_question_are_not_a_price_question(question):
    assert not detect_intent(question).prices, question


def test_a_movement_word_with_no_recency_word_is_left_alone():
    # Deliberately narrow: without "lately", "recently" or a named period the rule does not fire (the filings answer is the old behavior).
    for question in ("Has Tesla been climbing?", "Has Tesla been sliding?", "Is Nvidia drifting?"):
        assert not detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Has Apple been climbing or sliding?",
    "Is Tesla slipping on deliveries?",
])
def test_no_recency_word_and_a_business_object_are_not_prices(question):
    assert not detect_intent(question).prices, question


# ---- a cause question about a company's "slide" or "jump": a recency word counts as the period ----


@pytest.mark.parametrize("question", [
    "What's behind Apple's slide lately?",
    "What caused Microsoft's jump recently?",
    "What explains Tesla's slide these days?",
    "What's the reason for Nvidia's swoon of late?",
])
def test_a_cause_question_about_a_move_with_a_recency_word_gets_prices_and_headlines(question):
    assert route(question) == (True, True, False), question


@pytest.mark.parametrize("question", [
    "What's behind Amazon's jump in cloud revenue lately?",        # a business figure, not the stock
    "What's behind Nvidia's slide in gross margin recently?",
    "What's behind Apple's slide?",                                # no period at all: left as before
])
def test_the_same_question_about_a_business_figure_or_with_no_period_is_not_a_price_question(question):
    assert not detect_intent(question).prices, question
