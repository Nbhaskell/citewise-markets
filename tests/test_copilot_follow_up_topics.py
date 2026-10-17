"""Follow-ups that lose their topic (DECISIONS: "Fix (4) of the fresh round").

Four gaps found by the fresh held-out round:
1. "Switch over to Microsoft.", "Skip to Nvidia.", "Give me the number for Apple too." were not read as the same question
   about another company, because "switch", "skip", "number" were not filler words.
2. When the question is only a company switch or a bare comparison, it names no topic, so any topic in the model's rewrite is
   the earlier one reworded or one it invented ("Data Center revenue", "company summary"). The earlier question wins.
3. "Is Tesla's list longer than that?" and "Does Amazon say anything similar?" are comparisons with no topic of their own,
   and "similar" means similar to what the earlier company said.
4. "Summarize what the companies say about tariffs." names no company and refers to nothing, so a rewrite that names some
   is invented.
Fixture companies: Zetacorp (ZZCA) and Omegaware (ZZCB). Nothing here calls a model.
"""
import pytest

from ai.copilot import Turn, resolve_question
from ai.market import detect_intent
from test_copilot_history import HISTORY, PRIOR_ANSWER, RoutingLLM, conn  # noqa: F401  (conn is a fixture)

EMPLOYEES_ZETA = "How many employees does Zetacorp have?"
RISKS = [Turn("What are Zetacorp's biggest risks?", PRIOR_ANSWER, ("ZZCA",))]
PRICE = [Turn("How did Zetacorp stock do over the past month?", PRIOR_ANSWER, ("ZZCA",))]
ZETA_OMEGA_RISKS = [Turn("Compare Zetacorp's and Omegaware's risks.", PRIOR_ANSWER, ("ZZCA", "ZZCB"))]


def resolve(conn, question, rewrite, history=HISTORY, symbols=None):
    return resolve_question(conn, RoutingLLM(rewrite=rewrite), question, symbols, history)


# ---- 1. more ways to say "the same thing, for another company" ----


@pytest.mark.parametrize("question", [
    "Switch over to Omegaware.", "Skip to Omegaware.", "Move on to Omegaware.", "Jump to Omegaware.",
    "Go over to Omegaware.", "Over to Omegaware.", "Hop over to Omegaware now.", "Switching to Omegaware.",
    "Give me the number for Omegaware too.", "Give me the figure for Omegaware as well.", "Same question for Omegaware.",
    "Now the one for Omegaware.", "Cut to Omegaware, please.", "Onto Omegaware.", "Flip over to Omegaware.",
    "Turn to Omegaware.", "Shift to Omegaware.", "Go to Omegaware.", "Going to Omegaware now.", "Pivot to Omegaware.",
    "Pivoting to Omegaware.", "Over to Omegaware, same idea.", "Give Omegaware the same treatment.", "Same approach for Omegaware.",
    "The same thing for Omegaware.", "Give me the numbers for Omegaware.", "Give me the figures for Omegaware.",
])
def test_these_wordings_ask_the_previous_question_about_the_new_company(conn, question):
    search, found, note = resolve(conn, question, rewrite=question)  # the model leaves it as written
    assert search == "How many employees does Omegaware have?" and found == ["ZZCB"]
    assert note == search


@pytest.mark.parametrize("question", [
    "Skip to Omegaware's risks.",                 # names a topic
    "Move on to Omegaware stock.",                # so does this
    "Switch over to what Omegaware says about risks.",
    "Give me the number of Omegaware's employees.",
    "Switch to Omegaware and Zetacorp's risks.",
    "Skip it.",                                   # no company at all
])
def test_a_switch_wording_with_a_topic_of_its_own_is_left_alone(conn, question):
    search, _, note = resolve(conn, question, rewrite=question)
    assert search == question and note is None


# ---- 2. a bare switch asks the earlier question, whatever the rewrite invented ----


@pytest.mark.parametrize("rewrite", [
    "Omegaware",                              # the model kept only the name
    "Omegaware's company summary",            # it invented a topic ("Switch over to Microsoft." became a summary)
    "What does Omegaware do?",
    "What are Omegaware's biggest risks?",    # or took the topic from the answer, not the question
])
def test_a_rewrite_of_a_bare_switch_cannot_replace_the_earlier_topic(conn, rewrite):
    search, found, note = resolve(conn, "Skip to Omegaware.", rewrite)
    assert search == "How many employees does Omegaware have?" and found == ["ZZCB"] and note == search


def test_a_rewrite_of_a_bare_switch_is_kept_when_the_earlier_question_cannot_be_swapped(conn):
    """Two companies in the earlier question: it is not clear what to swap, so the rule stays out of the way."""
    search, _, _ = resolve(conn, "Skip to Omegaware.", "What are Omegaware's risks?", history=ZETA_OMEGA_RISKS)
    assert search == "What are Omegaware's risks?"


def test_a_rewrite_of_a_question_with_a_topic_is_still_trusted(conn):
    search, _, note = resolve(conn, "Skip to Omegaware's risks.", "What are Omegaware's biggest risks?")
    assert search == "What are Omegaware's biggest risks?" and note == search


# ---- 3. comparisons with no topic of their own ----


@pytest.mark.parametrize("question", [
    "Is Omegaware's list longer than that?", "Is Omegaware's list shorter than that?", "Is Omegaware's number higher than that?",
    "Is that total bigger than Omegaware's?",
])
def test_a_list_or_number_comparison_keeps_the_earlier_topic(conn, question):
    search, found, _ = resolve(conn, question, rewrite=question, history=RISKS)
    assert search == "What are Zetacorp's biggest risks, compared with Omegaware?"
    assert sorted(found) == ["ZZCA", "ZZCB"]


@pytest.mark.parametrize("rewrite", [
    "Is Omegaware's list longer than Zetacorp's?",          # kept both companies, lost the topic
    "Is Omegaware's list of employees longer than Zetacorp's?",   # kept both companies, invented a topic
    "Did Omegaware do better than Zetacorp?",
])
def test_a_rewrite_of_a_bare_comparison_cannot_replace_the_earlier_topic(conn, rewrite):
    search, found, _ = resolve(conn, "Is Omegaware's list longer than that?", rewrite, history=RISKS)
    assert search == "What are Zetacorp's biggest risks, compared with Omegaware?"
    assert sorted(found) == ["ZZCA", "ZZCB"]


def test_a_bare_comparison_after_a_price_question_stays_a_price_question(conn):
    """"And did Nvidia do better than that?" after an AMD price question was answered from the filings: the model wrote
    "Did Nvidia do better than AMD?", which names both companies and no price."""
    search, found, _ = resolve(conn, "And did Omegaware do better than that?", "Did Omegaware do better than Zetacorp?", history=PRICE)
    assert search == "How did Zetacorp stock do over the past month, compared with Omegaware?"
    assert sorted(found) == ["ZZCA", "ZZCB"] and detect_intent(search).prices


@pytest.mark.parametrize("question", [
    "Did Omegaware fare better than that?", "Did Omegaware fared better than that?", "Does Omegaware perform better than that?",
    "Has Omegaware performed better than that?", "Is Omegaware performing better than that?", "Did Omegaware do better than that?",
    "Is Omegaware faring better than that?", "Omegaware fares better than that?", "Omegaware performs better than that?",
])
def test_fare_and_perform_are_comparison_words_that_name_no_topic(conn, question):
    """"Did Microsoft fare better than that?" after an AMD price question was answered from the filings."""
    search, found, _ = resolve(conn, question, rewrite="Did Omegaware fare better than Zetacorp?", history=PRICE)
    assert search == "How did Zetacorp stock do over the past month, compared with Omegaware?"
    assert sorted(found) == ["ZZCA", "ZZCB"] and detect_intent(search).prices


@pytest.mark.parametrize("question", [
    "Did Omegaware perform better than expected?",     # no reference back
    "Did Omegaware perform better than Zetacorp?",     # names both itself
    "Did that perform better than expected?",          # no new company
])
def test_fare_and_perform_do_not_pull_in_unrelated_questions(conn, question):
    search, _, note = resolve(conn, question, rewrite=question, history=PRICE)
    assert "compared with" not in search and "comparing" not in (note or "")


def test_a_comparison_with_a_topic_of_its_own_still_trusts_the_rewrite(conn):
    search, found, _ = resolve(conn, "Is Omegaware's revenue growth bigger than that?",
                               "Is Omegaware's revenue growth bigger than Zetacorp's?", history=RISKS)
    assert search == "Is Omegaware's revenue growth bigger than Zetacorp's?" and sorted(found) == ["ZZCA", "ZZCB"]


def test_a_rewrite_of_a_bare_comparison_is_kept_when_the_earlier_topic_cannot_be_rebuilt(conn):
    history = [Turn("Which company has the most risks?", PRIOR_ANSWER, ("ZZCA",))]   # nothing to swap in
    search, found, note = resolve(conn, "Is Omegaware's list longer than that?", "Is Omegaware's list longer than Zetacorp's?", history=history)
    assert search == "Is Omegaware's list longer than Zetacorp's?" and sorted(found) == ["ZZCA", "ZZCB"]
    assert note == search                                       # the model's wording, shown as understood, with no "comparing" note
    assert "comparing" not in note


# ---- "similar" is a comparison with what the earlier company said ----


@pytest.mark.parametrize("question", [
    "Does Omegaware say anything similar?", "Does Omegaware mention something alike?", "Has Omegaware said anything comparable?",
    "Is there anything like that at Omegaware?", "Omegaware too, anything similar?",
])
def test_similar_searches_the_earlier_company_too(conn, question):
    search, found, note = resolve(conn, question, rewrite=question, history=RISKS)
    assert sorted(found) == ["ZZCA", "ZZCB"]
    shown = search + " " + (note or "")   # the rebuilt question names both; otherwise the note says what was assumed
    assert ("Zetacorp" in shown or "ZZCA" in shown) and "Omegaware" in shown


@pytest.mark.parametrize("question", [      # each filler word in the bare comparison appears in at least one of these, and only there
    "Does Omegaware say anything similar?", "Omegaware says something like that?", "Has Omegaware said anything comparable?",
    "Does Omegaware mention something alike?", "Omegaware mentions anything similar?", "Does Omegaware have anything similar?",
    "Had Omegaware anything like that?", "Omegaware likewise?", "Is there anything like that at Omegaware?",
    "Omegaware, something similar?",
])
def test_a_bare_similar_question_is_rebuilt_from_the_earlier_one(conn, question):
    search, found, _ = resolve(conn, question, rewrite=question, history=RISKS)
    assert search == "What are Zetacorp's biggest risks, compared with Omegaware?" and sorted(found) == ["ZZCA", "ZZCB"]


@pytest.mark.parametrize("question", [      # "similar" in the middle, at the end, or after a different noun phrase, with each cue word
    "Does Omegaware mention something similar in its filings?", "Did Omegaware say anything alike in its filings?",
    "Is there anything comparable in Omegaware's filings?", "Does Omegaware have anything like that in its filings?",
    "Is Omegaware similar?", "Omegaware's risks are alike?", "Is Omegaware's case comparable?", "Omegaware, likewise?",
    "Does Omegaware say nothing similar?", "Does Omegaware say everything similar?", "Does Omegaware say much similar?",
])
def test_every_similar_cue_searches_the_earlier_company_too(conn, question):
    _, found, _ = resolve(conn, question, rewrite=question, history=RISKS)
    assert sorted(found) == ["ZZCA", "ZZCB"]


def test_similar_after_a_risks_question_keeps_the_risks_topic(conn):
    search, found, _ = resolve(conn, "Does Omegaware say anything similar?", "Does Omegaware say anything about competition?", history=RISKS)
    assert search == "What are Zetacorp's biggest risks, compared with Omegaware?" and sorted(found) == ["ZZCA", "ZZCB"]


@pytest.mark.parametrize("question", [
    "Which similar companies does Omegaware name?",    # "similar" describes a noun
    "Does Omegaware have a similar number of employees?",
    "Does Zetacorp say anything similar?",            # the company just discussed: nothing new
    "Does it say anything similar?",                  # names no new company
])
def test_similar_does_not_pull_in_unrelated_questions(conn, question):
    search, found, note = resolve(conn, question, rewrite=question, history=RISKS)
    assert "compared with" not in search and "comparing" not in (note or "")
    assert found != ["ZZCA", "ZZCB"]


# ---- 4. "the companies" is every company, whatever the rewrite said ----


@pytest.mark.parametrize("question", [
    "Summarize what the companies say about tariffs.", "Which companies mention tariffs?", "Which company mentions tariffs most?",
    "Across all the companies, who talks about tariffs?", "Does every company mention tariffs?", "What do all companies say about tariffs?",
])
def test_a_question_about_all_the_companies_is_not_narrowed_by_the_rewrite(conn, question):
    search, found, note = resolve(conn, question, "Summarize what Zetacorp and Omegaware say about tariffs.", history=RISKS)
    assert search == question and found == [] and note is None


@pytest.mark.parametrize("question", [
    "Does any company mention tariffs?", "Does each company mention tariffs?", "Compare tariffs across companies.",
    "What are the companies' views on tariffs?", "Compare companies' views on tariffs.",
])
def test_more_all_companies_wordings(conn, question):
    search, found, note = resolve(conn, question, "What does Zetacorp say about tariffs?", history=RISKS)
    assert search == question and found == [] and note is None


@pytest.mark.parametrize("question,rewrite,expected", [
    ("Which companies do they compete with?", "Which companies does Zetacorp compete with?", ["ZZCA"]),   # "they" is a reference
    ("Which company did we discuss before?", "Which company did we discuss before, Zetacorp?", ["ZZCA"]),  # a reference to older turns
    ("Which of them has more employees?", "Which of Zetacorp and Omegaware has more employees?", ["ZZCA", "ZZCB"]),   # a reference back
    ("What do they say about tariffs?", "What does Zetacorp say about tariffs?", ["ZZCA"]),
    ("Which companies does Omegaware compete with?", "Which companies does Omegaware compete with?", ["ZZCB"]),         # names one
    ("And what about its risks?", "What are Zetacorp's biggest risks?", ["ZZCA"]),
])
def test_the_all_companies_rule_stays_out_of_the_way(conn, question, rewrite, expected):
    history = [Turn("Compare Zetacorp and Omegaware.", PRIOR_ANSWER, ("ZZCA", "ZZCB"))] if "them" in question else RISKS
    _, found, _ = resolve(conn, question, rewrite, history=history)
    assert sorted(found) == sorted(expected)


def test_chosen_companies_are_never_second_guessed_by_the_new_rules(conn):
    q = "Summarize what the companies say about tariffs."
    assert resolve(conn, q, q, symbols=["ZZCB"])[1] == ["ZZCB"]
    assert resolve(conn, "Skip to Omegaware.", "Skip to Omegaware.", symbols=["ZZCA"])[1] == ["ZZCA"]
