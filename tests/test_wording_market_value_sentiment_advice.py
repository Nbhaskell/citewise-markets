"""Three more groups of wording the held-out round found the keyword rules did not know (DECISIONS: "Held-out round").

- Market value: "How much is Apple worth in total?" went to the filings and was answered "the sources do not include the
  total market value", though the figure is stored.
- Sentiment: "Is the media tone around Apple turning sour?" was not read as a sentiment question.
- Advice: "Is Microsoft a smart place to park my money?" got no notice.

Each wording below is new (none is a held-out case). The negative lists matter as much as the positive ones: the same
words turn up in questions that are about something else, and the advice rule is allowed to over-flag but not by much.
"""
import pytest

from ai.market import asks_for_advice, detect_intent


def value_topics(question):
    return detect_intent(question).fundamentals


@pytest.mark.parametrize("question", [
    "What is Microsoft worth?",
    "How much is Apple worth in total?",
    "How much is all of Tesla worth?",
    "What's the total value of all of Tesla's shares?",
    "What is the combined value of Apple's stock?",
    "What is Amazon valued at?",
    "What is Tesla's company value?",
    "How much would it cost to buy all of Alphabet?",
])
def test_these_are_market_value_questions(question):
    got = detect_intent(question)
    assert "market_value" in got.fundamentals and not got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "Is Apple stock worth buying?",
    "What are Apple's shares worth to employees under the stock plan?",
    "What is the worth of Tesla's patents according to the 10-K?",
    "How much is Microsoft's goodwill worth?",            # a possessive: it is goodwill, not the company
    "What is the inventory worth?",
    "How much is Tesla's stock price?",
    "What is the value of Nvidia's inventory?",
    "How much would it cost to buy Tesla's Cybertruck?",   # not "all of"
])
def test_these_are_not_market_value_questions(question):
    assert "market_value" not in value_topics(question), question


def test_a_worth_question_about_the_stock_price_is_still_a_price_question():
    assert detect_intent("How much is Tesla's stock price today?").prices
    assert detect_intent("What is the P/E ratio, and how much is Apple stock?").prices


@pytest.mark.parametrize("question", [
    "Is the media tone around Apple turning sour?",
    "Is the press getting more negative on Nvidia?",
    "What's the vibe in the news about Tesla?",
    "Are people souring on Amazon?",
    "How is the coverage of Microsoft trending?",
    "How do reporters feel about Apple?",
    "Are journalists turning more positive on Alphabet?",
])
def test_these_are_sentiment_questions(question):
    got = detect_intent(question)
    assert got.sentiment and got.headlines, question


@pytest.mark.parametrize("question", [
    "What does the 10-K say about the tone at the top at Microsoft?",
    "How does Tesla's tone-deaf marketing hurt sales?",
    "What are Apple's biggest risks?",
    "What is Nvidia's revenue?",
    "Is Tesla's free cash flow turning negative?",           # a financial question: "negative" needs a press word near it
    "Did Amazon's operating margin turn positive this year?",
])
def test_these_are_not_sentiment_questions(question):
    assert not detect_intent(question).sentiment, question


@pytest.mark.parametrize("question", [
    "Is Microsoft a smart place to park my money?",
    "Would putting my savings into Nvidia be wise?",
    "Should my retirement account own Amazon?",
    "Is Apple a safe home for my cash?",
    "Is it sensible to put money in Tesla right now?",
    "Am I better off with Apple or Microsoft for my savings?",
    "Is Alphabet a sound long-term holding for me?",
    "Do you like Nvidia as an investment?",
    "What would you pick, Apple or Microsoft?",
])
def test_these_ask_for_a_recommendation(question):
    assert asks_for_advice(question), question
    assert detect_intent(question).advice, question


@pytest.mark.parametrize("question", [
    "Where does Microsoft park its cash?",
    "What does Apple do with its cash?",
    "How does Amazon's savings plan for employees work?",
    "Why did insiders sell Tesla shares?",
    "What are Nvidia's biggest risks?",
    "Will Tesla stock go up?",                    # a prediction, with its own rule
    "Where did Apple invest cash in 2025?",
    "What did the 10-K say about funds from operations?",
    "Is Microsoft good for the environment?",
])
def test_these_do_not_ask_for_a_recommendation(question):
    assert not asks_for_advice(question), question
