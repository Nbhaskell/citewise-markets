"""Advice and sentiment questions in wording the rules did not know (DECISIONS: "Second held-out round", items 3 and 4; fix (e)).

"My friend says Nvidia is a sure thing. Is she right?" and "Would you say Alphabet is cheap right now?" got no notice that
the app does not tell anyone to buy, sell or hold, and "Are reporters being kind or harsh to Nvidia right now?" was not read
as a question about the tone of the news. A probe of 24 further everyday advice wordings found 21 unflagged. Missing an
advice request is worse than one extra notice (CLAUDE.md), so the rules lean towards flagging; the negative cases keep that
honest: a plain filings or figures question must not be told it asked for advice.
"""
import pytest

from ai.market import asks_for_advice, detect_intent

# ---- advice ----


@pytest.mark.parametrize("question", [
    # a judgment of value
    "Is Nvidia undervalued?", "Is Apple overpriced?", "Would you say Alphabet is cheap right now?",
    "Is Tesla a bargain at this price?", "Is Microsoft fairly valued?", "Do you think Amazon is expensive today?",
    # an endorsement
    "My friend says Nvidia is a sure thing. Is she right?", "Does Microsoft look like a winner to you?",
    "Tell me if Apple is a keeper.", "Is AMD a screaming buy?", "Is Alphabet a solid long-term hold?",
    "Rate Apple as an investment.", "What's your take on Apple as an investment?", "Is Google stock worth owning?",
    "Would you bet on Tesla over Nvidia?", "Do you think Amazon will make me money?", "Am I crazy to like Microsoft here?",
    # timing
    "Is it too late to jump into Nvidia?", "Is now the moment to pick up some Nvidia?",
    "Is it smart to stay in Microsoft through earnings?", "What do you reckon about buying Amazon now?",
    # the reader's own money
    "I have $5,000. Where should it go, Apple or Microsoft?", "Would Tesla make a good addition to a retirement account?",
    "My dad wants me to load up on AMD. Thoughts?", "Should Tesla be in my portfolio?",
])
def test_these_wordings_are_requests_for_advice(question):
    assert asks_for_advice(question), question


@pytest.mark.parametrize("question", [
    "What does Tesla's 10-K say about its stock compensation?",
    "How many shares did Apple repurchase last quarter?",
    "Why did insiders sell Tesla shares?",
    "What is Nvidia's P/E ratio?",
    "How has Microsoft stock done this month?",
    "Who is the right person to run Tesla's AI?",
    "Is Apple's balance sheet strong?",
    "What risks does Amazon list for its cloud business?",
    "What does Apple's 10-K say about its investments in marketable securities?",
    "How does Amazon negotiate and bargain with its suppliers?",
    "Which of Tesla's segments is the most expensive to run?",
    "Is Tesla's operating margin better than its net margin?",
    "Where should Tesla build its next factory, according to its filings?",
    "Is it safe to say Microsoft's revenue grew last year?",
    "How much did Apple spend on cheap components?",
    "What is the winner-take-all risk Nvidia describes?",
    "How does Nvidia describe its stock repurchase program?",
])
def test_ordinary_questions_do_not_get_the_advice_notice(question):
    assert not asks_for_advice(question), question


def test_the_value_words_need_the_question_to_be_about_judging_the_stock():
    assert asks_for_advice("Is Alphabet cheap?") and asks_for_advice("Is Alphabet cheap right now?")
    assert not asks_for_advice("Why is Alphabet's cloud segment so expensive to operate?")


# ---- sentiment ----


@pytest.mark.parametrize("question", [
    "Are reporters being kind or harsh to Nvidia right now?",
    "Is the press piling on Tesla?",
    "How is the media treating Microsoft?",
    "Is anyone saying nice things about Tesla?",
    "What's the buzz on Microsoft: upbeat or gloomy?",
    "Are the headlines about AMD mostly good?",
    "Is the news flow on Amazon getting better?",
    "How favourable is coverage of Amazon?",
    "Is the coverage of Apple friendly?",
    "What's the general feeling about Nvidia in the news?",
    "Are writers upbeat on Apple?",
])
def test_these_wordings_are_questions_about_the_tone_of_the_news(question):
    got = detect_intent(question)
    assert got.sentiment and got.headlines, question


@pytest.mark.parametrize("question", [
    "What are Tesla's biggest risks?",
    "How many employees does Apple have?",
    "Is Nvidia's balance sheet strong?",
    "How is the weather affecting Amazon's deliveries?",
    "Did Apple's press release mention a new chip?",
    "What are the positive trends in Nvidia's data center revenue?",
    "Do analysts expect better earnings growth at Microsoft?",           # analysts are not a news source
    "Is the Tesla press release for the new Roadster delivery schedule in Texas and California good?",  # too far apart
    "What does the 10-K say about goodwill on Alphabet's balance sheet?",
    "Which news publishers does Alphabet pay?",
    "How kind is Tesla's warranty policy?",
    "What is the coverage ratio of Apple's debt?",
])
def test_other_questions_are_not_read_as_news_tone_questions(question):
    assert not detect_intent(question).sentiment, question


@pytest.mark.parametrize("question", [
    "What is Tesla's best selling model?",                  # "selling" is not "sell": found by the existing advice tests
    "Which is Apple's best holding company subsidiary?",
    "Is Amazon's best playbook its logistics network?",
])
def test_the_noun_after_a_good_or_best_must_be_a_whole_word(question):
    assert not asks_for_advice(question), question


def test_a_valuation_question_beside_a_figure_gets_the_notice_but_keeps_its_figure():
    got = detect_intent("Is Tesla overvalued given its P/E ratio?")
    assert got.advice and got.fundamentals == frozenset({"pe"})


@pytest.mark.parametrize("question", [
    "I have $5,000 saved and I'm looking at Apple.",         # only the amount: no "where should" in it
    "Where should it go: Apple or Microsoft?",                # only the "where should it go": no amount in it
    "Where should the money go, Nvidia or AMD?",
])
def test_each_form_of_a_personal_money_question_is_flagged_on_its_own(question):
    assert asks_for_advice(question), question


def test_a_good_word_far_from_a_trade_word_is_not_an_endorsement():
    assert not asks_for_advice("Is it true that Apple had a great year of record results and that insiders buy back stock?")


# ---- wordings found by the fresh held-out cases written for this step (they missed on the first run; see DECISIONS) ----


@pytest.mark.parametrize("question", [
    "Is Apple a smart addition to a growth portfolio?",
    "Would Microsoft be a good addition to my holdings portfolio?",
    "Is Microsoft too pricey to touch?",
    "Is Amazon too expensive to own?",
    "Is Tesla too cheap to ignore?",
    "Would you pile into Nvidia ahead of earnings?",
    "Would a cautious investor go for Tesla right now?",
    "Should a long-term investor pick Alphabet?",
])
def test_more_advice_wordings_are_flagged(question):
    assert asks_for_advice(question), question


@pytest.mark.parametrize("question", [
    "Which segment of Tesla is too expensive to scale?",                 # "too expensive to" a business action, not to own
    "What does Apple's 10-K say about an addition to its retail portfolio of stores?",
    "Is the cautious investor disclosure in Tesla's 10-K accurate?",     # an investor, but nothing about acting on a stock
    "How did the pile of inventory at Amazon change?",
])
def test_those_additions_leave_ordinary_questions_alone(question):
    assert not asks_for_advice(question), question


@pytest.mark.parametrize("question", [
    "Is the press giving Tesla an easy ride?",
    "Has the media turned on Amazon?",
    "Are reporters going easy on Nvidia?",
    "Is the press giving Apple a hard time?",
])
def test_more_news_tone_idioms_are_read_as_tone_questions(question):
    assert detect_intent(question).sentiment, question


def test_the_idioms_need_a_news_source_beside_them():
    assert not detect_intent("Did Tesla's CEO have a hard time at the shareholder meeting?").sentiment
    assert not detect_intent("Has the board turned on its founder at Apple?").sentiment
