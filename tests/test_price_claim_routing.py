"""Price claims and predictions that never reached the price data (DECISIONS: "Fresh held-out round", fix 3).

"Google doubled this month. What drove it?" went to the filings, which hold no prices, so nothing could show that Google rose about 1%.
"Everyone says Tesla can only go up from here" and "Do you think Microsoft reaches $650 before the year ends?" went there too, so the
prompt's no-prediction rule (which applies to price sources) was not in play. Each wording below was added one at a time. The negative
cases matter as much: "doubled" and "reach $100 billion" turn up in questions about a company's business, and a price route for those
would swap a good answer for a wrong one. The claim rule needs a capitalised company name, a verb that is not followed by an object, and
a named period or a stock word.
"""
import pytest

from ai.market import detect_intent


@pytest.mark.parametrize("question", [
    "Google doubled this month. What drove it?",
    "Why did Nvidia triple this year?",
    "Why did Tesla halve in a week?",
    "Has AMD doubled since the start of the year?",
    "Why did Microsoft plummet over the past week?",
    "Did Apple collapse last month?",
    "Amazon exploded over the last three weeks, didn't it?",
    "How did Alphabet nosedive this quarter?",
    "Everyone says Tesla can only go up from here. Do you agree?",
    "Some people say Nvidia can only go down from here.",
    "Some say Amazon can only go up.",                                  # no "from here": the end of the question is enough
    "Do you think Microsoft reaches $650 before the year ends?",
    "Will Apple reach $400 by spring?",
])
def test_these_claims_and_predictions_are_price_questions(question):
    got = detect_intent(question)
    assert got.prices and not got.filings, question


@pytest.mark.parametrize("question", [
    "Microsoft doubled its dividend over the last five years.",         # an object follows the verb
    "Amazon doubled down on AI spending last year.",
    "Apple halved its R&D budget this year.",
    "Tesla's deliveries doubled over the last year.",                    # a lowercase subject that is not the company
    "Tesla's vehicle shipments doubled over the last year.",
    "Did Tesla collapse?",                                               # no period and no stock word: could be the business
    "Revenue doubled at Nvidia in the last two years.",                  # a common noun that starts the sentence
    "Nvidia doubled in size over the last five years.",
    "Why did Amazon's headcount double last year?",
    "Does Tesla say the Semi can only go up to 80,000 pounds?",
    "When does Nvidia expect revenue to reach $100 billion?",
    "Nvidia reaches $100 billion in quarterly sales, doesn't it?",       # a dollar figure with a unit
    "How do Microsoft employees go up the pay scale?",
    "Did Alphabet collapse its two share classes into one?",             # an object follows the verb
])
def test_filings_questions_that_share_the_words_are_not_price_questions(question):
    assert not detect_intent(question).prices, question


def test_a_claim_with_no_period_and_no_stock_word_is_left_to_the_filings():
    # "Isn't Tesla about to collapse?" could be about the business: not routed (a known gap, see DECISIONS).
    assert not detect_intent("Isn't Tesla about to collapse?").prices
