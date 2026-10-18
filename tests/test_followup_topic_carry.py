"""A follow-up that points back without saying what about (DECISIONS: "Follow-up topic carry").

"Do the matching calculation for Google." after "What's Apple's P/E ratio?" was rewritten into "Do the matching calculation for
Alphabet.": the company came through and the topic did not, so the search ran on nothing and the filings were searched. The rewrite
step keeps vague phrases ("that stretch", "alongside it") that the app has no way to read. When ALL of these hold, the earlier
*question* (never its answer) is reused, and "Understood as" shows the result:
  - no company was chosen in the page and there is an earlier turn;
  - the user's own words contain a pointing-back word (that, those, same, matching, equivalent, counterpart, likewise, "just did",
    alongside, comparable, "by comparison", "as much");
  - the rewrite names no topic of its own (no market route, no filing noun, no 10-K or quarter, no unstored ratio, no advice request);
  - the nearest earlier question does name a topic.
A new company is swapped into the earlier question; a comparison ("Did Omegaware move more than that...") becomes "..., compared with
Omegaware"; a cause question about the same company ("What explains that?") is appended to the earlier question.
Fixture companies: Zetacorp (ZZCA) and Omegaware (ZZCB). Nothing here calls a model.
"""
import pytest

from ai.copilot import Turn, names_a_topic, resolve_question, routes_somewhere
from test_copilot_history import PRIOR_ANSWER, RoutingLLM, conn  # noqa: F401  (conn is a fixture)

PE = [Turn("What is Zetacorp's P/E ratio?", PRIOR_ANSWER, ("ZZCA",))]
PRICE = [Turn("How did Zetacorp stock do over the past month?", PRIOR_ANSWER, ("ZZCA",))]
NEWS = [Turn("What's the latest news on Zetacorp?", PRIOR_ANSWER, ("ZZCA",))]
RISKS = [Turn("What are Zetacorp's biggest risks?", PRIOR_ANSWER, ("ZZCA",))]
NO_TOPIC = [Turn("Tell me about Zetacorp.", PRIOR_ANSWER, ("ZZCA",))]


def resolve(conn, question, rewrite=None, history=PE, symbols=None):
    """The model leaves the question as written (its rewrite loses the topic) unless a rewrite is given."""
    return resolve_question(conn, RoutingLLM(rewrite=question if rewrite is None else rewrite), question, symbols, history)


# ---- a new company, a pointing-back word, no topic: the earlier question about the new company ----


@pytest.mark.parametrize("question, word", [
    ("Repeat that calculation for Omegaware.", "that"),
    ("Run those numbers for Omegaware.", "those"),
    ("Do the same check on Omegaware.", "same"),
    ("Do the matching calculation for Omegaware.", "matching"),
    ("Now the equivalent for Omegaware.", "equivalent"),
    ("Give me Omegaware's counterpart.", "counterpart"),
    ("Likewise for Omegaware.", "likewise"),
    ("Do what we just did for Omegaware.", "just did"),
])
def test_each_pointing_back_word_carries_the_earlier_topic_to_the_new_company(conn, question, word):
    search, found, note = resolve(conn, question)
    assert search == "What is Omegaware's P/E ratio?" and found == ["ZZCB"], (word, search)
    assert note == search


def test_a_price_topic_is_carried_with_its_period(conn):
    search, found, _ = resolve(conn, "Put Omegaware through the same stretch.", history=PRICE)
    assert search == "How did Omegaware stock do over the past month?" and found == ["ZZCB"]


def test_a_news_topic_is_carried(conn):
    search, found, _ = resolve(conn, "Do the same check on Omegaware.", history=NEWS)
    assert search == "What's the latest news on Omegaware?" and found == ["ZZCB"]


def test_the_nearest_earlier_question_that_has_a_topic_is_used(conn):
    history = PE + [Turn("Switch to Zetacorp.", PRIOR_ANSWER, ("ZZCA",))]       # a bare switch has no topic, the one before it does
    search, _, _ = resolve(conn, "Do the same check on Omegaware.", history=history)
    assert search == "What is Omegaware's P/E ratio?"


# ---- a comparison: the earlier question, compared with the new company ----


@pytest.mark.parametrize("question", [
    "Did Omegaware move more than that over the same stretch?",       # than
    "Lay Omegaware alongside it.",                                    # alongside
    "Was Omegaware's month any rosier by comparison?",                # by comparison
    "Did Omegaware climb as much over that period?",                  # as much
    "Is Omegaware dealing with comparable issues?",                   # comparable
])
def test_a_comparison_names_both_companies_and_keeps_the_earlier_topic(conn, question):
    search, found, note = resolve(conn, question, history=PRICE)
    assert search == "How did Zetacorp stock do over the past month, compared with Omegaware?", question
    assert found == ["ZZCA", "ZZCB"] and note == search


def test_an_unknown_comparative_with_no_topic_word_now_carries_the_earlier_topic(conn):
    """A deliberate change from the closed comparison-word list (DECISIONS: "Follow-up topic carry"): "Is that wider than Omegaware?"
    used to keep the model's wording, because "wider" might be a topic the app cannot see. The question points back ("that") and
    names no topic, so the earlier question is reused; "Understood as" shows it."""
    history = [Turn("How many employees does Zetacorp have?", PRIOR_ANSWER, ("ZZCA",))]
    search, found, note = resolve(conn, "Is that wider than Omegaware?", history=history)
    assert search == "How many employees does Zetacorp have, compared with Omegaware?"
    assert found == ["ZZCA", "ZZCB"] and note == search


@pytest.mark.parametrize("question", [
    "Did Omegaware manage as much?",                          # "as much" is the only pointing-back word
    "Does Omegaware say anything like that?",                 # "anything like that" (the existing similarity cue)
    "Does Omegaware mention anything like that in detail?",   # the same, with words the old filler list does not know
])
def test_these_comparisons_keep_the_earlier_topic_too(conn, question):
    search, found, _ = resolve(conn, question, history=PRICE)
    assert search == "How did Zetacorp stock do over the past month, compared with Omegaware?", question
    assert found == ["ZZCA", "ZZCB"]


def test_a_rewrite_that_names_both_companies_but_no_topic_is_still_rebuilt(conn):
    search, found, _ = resolve(conn, "Lay Omegaware alongside it.", rewrite="Lay Omegaware alongside Zetacorp.", history=PRICE)
    assert search == "How did Zetacorp stock do over the past month, compared with Omegaware?" and found == ["ZZCA", "ZZCB"]


@pytest.mark.parametrize("history, question, rewrite, expected", [
    # The rewrite named the earlier company although the user did not: that IS a comparison, whatever words the user used. A swap here
    # would drop the earlier company (found by the evaluation: "Do Alphabet's worries overlap with those?", "Is Tesla in the same boat?").
    (RISKS,
     "Do Omegaware's worries overlap with those?", "Do Omegaware's worries overlap with Zetacorp's?",
     "What are Zetacorp's biggest risks, compared with Omegaware?"),
    (RISKS, "Is Omegaware in the same boat?", "Is Omegaware in the same boat as Zetacorp?",
     "What are Zetacorp's biggest risks, compared with Omegaware?"),
    (PRICE, "Has Omegaware held up better over that stretch?", "Has Omegaware held up better over that stretch than Zetacorp?",
     "How did Zetacorp stock do over the past month, compared with Omegaware?"),
])
def test_a_rewrite_that_added_the_earlier_company_makes_it_a_comparison_not_a_swap(conn, history, question, rewrite, expected):
    search, found, note = resolve(conn, question, rewrite=rewrite, history=history)
    assert search == expected and found == ["ZZCA", "ZZCB"] and note == search


def test_a_company_the_rewrite_invented_is_not_taken_for_the_earlier_one(conn):
    """Omegaware was not in the earlier turn, so the model misread the question: the existing rule trusts the user's words and the
    company of the earlier turn, and nothing is rebuilt (no comparison with an invented company)."""
    search, found, _ = resolve(conn, "Run the same numbers please.", rewrite="Run the same numbers for Omegaware.")
    assert search == "Run the same numbers please." and found == ["ZZCA"]


def test_a_comparison_with_no_earlier_topic_keeps_the_rewrite_and_says_which_companies(conn):
    search, found, note = resolve(conn, "Lay Omegaware alongside it.", history=NO_TOPIC)
    assert search == "Lay Omegaware alongside it." and found == ["ZZCA", "ZZCB"]
    assert note == "Lay Omegaware alongside it. (comparing ZZCA and ZZCB)"


def test_a_comparison_that_cannot_be_composed_keeps_the_rewrite_not_a_swapped_question(conn):
    pronoun = [Turn("How has it done this month?", PRIOR_ANSWER, ("ZZCA",))]       # no company in the earlier question to compare
    search, _, _ = resolve(conn, "Lay Omegaware alongside it.", rewrite="Lay Omegaware alongside Zetacorp.", history=pronoun)
    assert search == "Lay Omegaware alongside Zetacorp."


# ---- a cause question about the same company ----


@pytest.mark.parametrize("question", [
    "What explains that?",
    "So what was behind that move?",
    "Why did that happen?",
])
def test_a_cause_follow_up_is_appended_to_the_earlier_question(conn, question):
    search, found, note = resolve(conn, question, history=PRICE)
    assert search == f"How did Zetacorp stock do over the past month, and {question[0].lower()}{question[1:]}", question
    assert found == ["ZZCA"] and note == search


@pytest.mark.parametrize("question, kwargs", [
    ("Why did it happen?", {}),                                           # no pointing-back word: the existing rules handle it
    ("What explains that?", {"symbols": ["ZZCA"]}),                       # a company chosen in the page wins
    ("What explains that move in Zetacorp?", {}),                         # names a company: deliberately left as written
    ("What explains that?", {"history": [Turn("What are Zetacorp's biggest risks?", PRIOR_ANSWER, ("ZZCA",))]}),   # not a price question
    ("What explains that?", {"history": NO_TOPIC}),
])
def test_a_cause_question_is_appended_only_to_a_price_question(conn, question, kwargs):
    kwargs.setdefault("history", PRICE)
    search, _, _ = resolve(conn, question, **kwargs)
    assert search == question


def test_a_stock_word_in_the_rewrite_does_not_stop_the_cause_carry(conn):
    """"that move in Zetacorp's stock" routes to the filings (no price word the rules know), so the rewrite names no routable topic."""
    search, found, _ = resolve(conn, "So what was behind that move?", rewrite="So what was behind that move in Zetacorp's stock?", history=PRICE)
    assert search == "How did Zetacorp stock do over the past month, and so what was behind that move?" and found == ["ZZCA"]


def test_a_follow_up_with_no_cause_word_and_no_company_is_left_alone(conn):
    search, found, note = resolve(conn, "Was that unusual?", history=PRICE)
    assert search == "Was that unusual?" and note is None


# ---- when the rule must not fire ----


@pytest.mark.parametrize("question", [
    "Does Omegaware describe the same risks?",                 # a filing noun: a topic of its own
    "What did Omegaware say about that in its 10-K?",         # a filing named
    "Is Omegaware's P/E ratio the same?",                     # a market route
    "Should I buy the same one, Omegaware?",                  # an advice request
    "What is Omegaware's dividend yield, like that?",         # an unstored ratio
    "Is Omegaware's stock the same?",                         # a price word
    "Do the same for Omegaware's quarterly report.",          # a quarter
])
def test_a_question_with_a_topic_of_its_own_is_left_alone(conn, question):
    search, _, note = resolve(conn, question)
    assert search == question and note is None


def test_a_topic_in_the_users_words_wins_even_when_the_rewrite_dropped_it(conn):
    search, _, _ = resolve(conn, "Does Omegaware describe the same risks?", rewrite="Does Omegaware describe the same thing?")
    assert search == "Does Omegaware describe the same thing?"


def test_a_rewrite_that_kept_the_topic_is_not_replaced(conn):
    search, found, note = resolve(conn, "Do the matching check for Omegaware.", rewrite="What is Omegaware's price-to-earnings ratio?")
    assert search == "What is Omegaware's price-to-earnings ratio?" and found == ["ZZCB"]


def test_no_pointing_back_word_means_the_rule_does_not_fire(conn):
    search, found, note = resolve(conn, "Tell me about Omegaware.")
    assert search == "Tell me about Omegaware." and found == ["ZZCB"] and note is None


def test_an_earlier_question_with_no_topic_gives_nothing_to_carry(conn):
    search, _, _ = resolve(conn, "Do the same for Omegaware.", history=NO_TOPIC)
    assert search == "Do the same for Omegaware."


def test_a_company_chosen_in_the_page_wins(conn):
    search, found, _ = resolve(conn, "Do the same for Omegaware.", symbols=["ZZCA"])
    assert found == ["ZZCA"] and search == "Do the same for Omegaware."


def test_there_is_nothing_to_carry_without_an_earlier_turn(conn):
    search, _, note = resolve(conn, "Do the same for Omegaware.", history=[])
    assert search == "Do the same for Omegaware." and note is None


def test_a_comparison_that_names_the_earlier_company_too_says_what_it_means(conn):
    question = "Did Zetacorp move more than Omegaware over the same stretch?"
    search, _, _ = resolve(conn, question, history=PRICE)
    assert search == question


def test_the_earlier_answer_is_never_used(conn):
    search, _, _ = resolve(conn, "Do the same check on Omegaware.", history=PRICE)
    assert "SENTINEL" not in search and "1234" not in search


# ---- what counts as a topic ----


@pytest.mark.parametrize("text", [
    "How did Zetacorp stock do this month?",                  # prices
    "What is the latest news on Zetacorp?",                   # headlines
    "What is Zetacorp's P/E ratio?",                          # the stored figures
    "What are Zetacorp's biggest risks?",                     # a filing noun
    "What did Zetacorp say in its 10-K?",                     # a filing named
    "What did Zetacorp report last quarter?",                 # a quarter
    "What is Zetacorp's dividend yield?",                     # a ratio the app does not compute
    "Should I buy Zetacorp?",                                 # advice
    "Is Zetacorp's stock the same?",                          # a stock word with no verb
    "Zetacorp's shares, the same way?",
    "The price of Zetacorp, likewise?",
])
def test_these_name_a_topic(text):
    assert names_a_topic(text), text


@pytest.mark.parametrize("text", [
    "Do the matching calculation for Omegaware.",
    "Put Omegaware through the same stretch.",
    "Tell me about Omegaware.",
    "What explains that?",
])
def test_these_name_no_topic(text):
    assert not names_a_topic(text), text


def test_a_bare_stock_word_names_a_topic_but_does_not_route_anywhere():
    """The user's own "stock" counts as a topic (their words win), but a rewrite with only a stock word still goes to the filings."""
    text = "So what was behind that move in Zetacorp's stock?"
    assert names_a_topic(text) and not routes_somewhere(text)


@pytest.mark.parametrize("text", [
    "How did Zetacorp stock do this month?", "What is the latest news on Zetacorp?", "What is Zetacorp's P/E ratio?",
    "What are Zetacorp's biggest risks?", "What did Zetacorp say in its 10-K?", "What did Zetacorp report last quarter?",
    "What is Zetacorp's dividend yield?", "Should I buy Zetacorp?",
])
def test_these_route_somewhere(text):
    assert routes_somewhere(text), text
