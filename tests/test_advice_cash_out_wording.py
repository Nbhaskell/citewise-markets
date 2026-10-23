"""Everyday ways of asking whether to buy, sell or hold that carried no notice (DECISIONS: "Fresh held-out round", fix 3).

"Is it time to cash out of Nvidia?" got the data and no "I can't tell you whether to buy, sell, or hold" notice. A probe of 20 wordings
found 16 unflagged: the trade words "cash out", "take profits", "lock in gains", "unload", "ride it out", "hang on to" were not known, and
"is it time to", "would it be crazy to" were not decision cues. The project's rules say to lean towards flagging (a missed request is worse than one
extra notice), but the same words turn up in questions about a company's own plans ("Does Tesla say whether it will unload its Bitcoin?"),
so every new phrase is written to need the reader's own decision beside it. Each wording is new (none is an evaluation case).
"""
import pytest

from ai.market import asks_for_advice, detect_intent


@pytest.mark.parametrize("question", [
    "Is it time to cash out of Nvidia?",
    "Should I take profits on Tesla?",
    "Is now the moment to lock in gains on Amazon?",
    "Is it time to bail on AMD?",
    "Would you unload Apple here?",
    "Should I ride Microsoft out?",
    "Is it smart to hang on to Alphabet shares?",
    "Do I cut my losses on Tesla?",
    "Time to get out of Nvidia?",
    "Is it time to load up on AMD?",
    "Would now be a good point to enter Apple?",
    "Should we be adding Alphabet to the portfolio?",
    "Is it time to dump Nvidia?",
    "Is Amazon one to hold for the long term?",
    "Is it time to double down on AMD?",
    "Would it be crazy to sell Microsoft now?",
    "Would it be foolish to offload my Tesla?",
    "Is this a good level to get in on Alphabet?",
    "Is Apple one to own for the next decade?",
    "Is it time to go long on Nvidia?",
    "Thinking about cashing out of Amazon. Wise?",
    "Is it a mistake to hang onto AMD shares?",
    "Would it be ok to sell Microsoft here?",                           # "would it be ... to" is the only cue
    "Is it crazy to unload Amazon?",                                    # "crazy to" is the only cue
])
def test_these_wordings_are_requests_for_a_recommendation(question):
    assert asks_for_advice(question), question
    assert detect_intent(question).advice, question


@pytest.mark.parametrize("question", [
    "What does Apple say about its time to market for new products?",
    "How is Amazon positioned to exit the retail segment in India?",
    "Is it time for Tesla's annual shareholder meeting?",
    "What did Microsoft cash out of its investments last year?",
    "When will Nvidia take its profits tax charge?",
    "What is Apple's cash position?",
    "Does Tesla say whether it will unload its Bitcoin?",              # "whether" is a cue, but the company decides
    "Does Apple plan to unload its inventory of older iPhones?",
    "Is it time for Apple to exit the retail business?",               # "time for", not "time to"
    "Should Microsoft cut its losses in gaming?",
    "How much did Amazon offload in its latest debt sale?",
    "How long is Nvidia's time to ship an order, according to the 10-K?",
    "Would it be hard for Alphabet to enter the cloud market in China?",   # "would it be ... to", but a company entering a market
    "What cash did Tesla take out of its credit line?",
    "Does the 10-K say Amazon will hang on to its warehouse leases?",
    "Does Apple say whether it will cash out its stake in ARM?",
    "Does Tesla say whether it is unloading its Bitcoin?",              # a shorter match ("unloadin") must not slip past "its"
    "Does Nvidia say whether it will hang onto its inventory?",
    "Does Amazon say whether it will hang on to its warehouse leases?",  # "hang on" without the "to" must not slip past "its"
])
def test_questions_about_a_companys_own_plans_that_share_the_words_are_not_flagged(question):
    assert not asks_for_advice(question), question

