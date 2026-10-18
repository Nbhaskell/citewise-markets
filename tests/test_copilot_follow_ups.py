"""Follow-ups that the rewrite step got wrong (DECISIONS: "Second held-out round", item 7).

"Now do Alphabet." after a risks question was not read as the same question for Alphabet, because "do" was not a filler
word, so the answer was a company summary. "Is that better or worse than Amazon?" after a question about Nvidia lost
Nvidia: the model rewrote it into a question about Amazon alone, so only Amazon was searched. Both are fixed in code, not
in the rewrite prompt: the model's own wording is trusted whenever it did the job, and replaced only when it did not.
Wordings here are new (none is an evaluation case). The fixture companies are Zetacorp (ZZCA) and Omegaware (ZZCB).
"""
import pytest

from ai.copilot import Turn
from test_copilot_history import HISTORY, PRIOR_ANSWER, RoutingLLM, ask, conn  # noqa: F401  (conn is a fixture)

EMPLOYEES_ZETA = "How many employees does Zetacorp have?"


# ---- "Now do Omegaware." keeps the topic ----


@pytest.mark.parametrize("question", [
    "Now do Omegaware.", "Do Omegaware now.", "Try Omegaware.", "Let's do Omegaware.", "Now do OMEGAWARE please.",
    "Check Omegaware.", "Same for Omegaware.", "Show me Omegaware.",
])
def test_a_do_or_try_switch_asks_the_previous_question_about_the_new_company(conn, question):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question)  # the model leaves it as written
    assert ans.interpreted_question is not None
    assert ans.interpreted_question.replace("OMEGAWARE", "Omegaware") == "How many employees does Omegaware have?"
    assert ans.symbols == ["ZZCB"]


@pytest.mark.parametrize("question", [
    "Do Omegaware's risks include litigation?",       # a question of its own
    "Does Omegaware have more employees?",            # "does", and words after the name
    "Do Omegaware and Zetacorp compete?",
    "Try to explain Omegaware.",
    "Now do Omegaware's employees.",                  # names the topic itself
])
def test_a_question_that_only_starts_with_do_or_try_is_not_a_switch(conn, question):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question)
    assert ans.interpreted_question is None


# ---- a comparison keeps both companies ----


@pytest.mark.parametrize("rewrite", [
    "Is that more or fewer than Omegaware?",                 # the model changed nothing
    "Is that more or fewer than Omegaware's employees?",     # it dropped Zetacorp, as it did for Nvidia
    "How many employees does Omegaware have?",               # it dropped Zetacorp and swapped the subject
])
def test_a_bare_comparison_is_rebuilt_when_the_rewrite_loses_the_earlier_company(conn, rewrite):
    llm = RoutingLLM(rewrite=rewrite)
    ans, emb = ask(conn, llm, "Is that more or fewer than Omegaware?")
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert ans.interpreted_question == "How many employees does Zetacorp have, compared with Omegaware?"
    assert ans.question == "Is that more or fewer than Omegaware?"          # the user's own words are kept
    assert set(emb.queries) == {ans.interpreted_question}                    # searched once per company, all on the rebuilt question
    assert all("SENTINEL-PRIOR-ANSWER" not in p for p in llm.answer_prompts)  # only the question is carried, never the answer


def test_the_company_is_written_as_the_user_typed_it(conn):
    ans, _ = ask(conn, RoutingLLM(rewrite="Is that bigger than ZZCB?"), "Is that bigger than ZZCB?")
    assert ans.interpreted_question == "How many employees does Zetacorp have, compared with ZZCB?"


@pytest.mark.parametrize("question", [
    "How does that stack up against Omegaware?", "Is it any better than Omegaware?", "That versus Omegaware?",
    "Compare that with Omegaware.", "Is that higher than Omegaware's?",
])
def test_other_comparison_wordings_are_rebuilt_too(conn, question):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question)
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert ans.interpreted_question == "How many employees does Zetacorp have, compared with Omegaware?"


def test_a_rewrite_that_kept_both_companies_is_no_longer_trusted_for_a_bare_comparison(conn):
    """Changed on purpose (fix 4 of the fresh round). It used to keep the rewrite when it named both companies, but a bare
    comparison names no topic, so a rewrite that kept both ("Did Nvidia do better than AMD?") had lost or invented the
    earlier topic. The earlier question, rebuilt, wins; here the two differ by a comma. Tests of the new rule:
    tests/test_copilot_follow_up_topics.py."""
    llm = RoutingLLM(rewrite="How many employees does Zetacorp have compared with Omegaware?")
    ans, _ = ask(conn, llm, "Is that more or fewer than Omegaware?")
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert ans.interpreted_question == "How many employees does Zetacorp have, compared with Omegaware?"


def test_a_comparison_with_a_topic_of_its_own_keeps_both_companies_but_not_the_old_topic(conn):
    """"Its revenue" is the topic here, so the earlier question's topic (employees) is not carried. Only the companies are."""
    question = "Does its revenue look better than Omegaware's?"
    ans, _ = ask(conn, RoutingLLM(rewrite="Does revenue look better than Omegaware's?"), question)
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert "employees" not in ans.interpreted_question
    assert "ZZCA" in ans.interpreted_question and "ZZCB" in ans.interpreted_question   # what was assumed is shown


def test_the_topic_comes_from_the_last_question_that_had_one(conn):
    history = [HISTORY[0], Turn("What about Omegaware?", PRIOR_ANSWER, ("ZZCB",))]   # a bare switch has no topic of its own
    ans, _ = ask(conn, RoutingLLM(rewrite="Is that more or fewer than Zetacorp?"), "Is that more or fewer than Zetacorp?",
                 history=history)
    # "that" is Omegaware's answer, so Zetacorp is the new company; the topic is the one from before the switch
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert ans.interpreted_question == "How many employees does ZZCB have, compared with Zetacorp?"


@pytest.mark.parametrize("question,history,symbols", [
    ("Is that more or fewer than Zetacorp?", HISTORY, None),                   # the same company again: nothing new
    ("Is Omegaware bigger than the other one?", HISTORY, None),               # "other" refers back, not to the last answer
    ("What about Omegaware's employees?", HISTORY, None),                     # no comparison
    ("Is that more or fewer than Omegaware?", [], None),                      # no earlier turn
    ("Is that more or fewer than Omegaware?", [Turn("Which company is biggest?", "x", ())], None),  # no company to keep
    ("Is Omegaware more than Zetacorp?", HISTORY, None),                      # names both itself, no reference word
])
def test_the_comparison_rule_stays_out_of_the_way(conn, question, history, symbols):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question, history=history, symbols=symbols)
    assert "compared with" not in (ans.interpreted_question or "") and "comparing" not in (ans.interpreted_question or "")


def test_chosen_companies_are_never_second_guessed_by_the_comparison_rule(conn):
    q = "Is that more or fewer than Omegaware?"
    ans, _ = ask(conn, RoutingLLM(rewrite=q), q, symbols=["ZZCB"])
    assert ans.symbols == ["ZZCB"] and ans.interpreted_question is None


def test_a_comparison_with_the_company_just_discussed_is_not_a_comparison_with_itself(conn):
    q = "Is that more or fewer than Zetacorp?"
    ans, _ = ask(conn, RoutingLLM(rewrite=q), q)
    assert ans.symbols == ["ZZCA"]          # once, not twice
    assert ans.interpreted_question is None


def test_a_comparison_wording_outside_the_filler_list_still_keeps_both_companies(conn):
    """"Wider" is not on the list of comparison words and "revenue" names a topic of its own: the old topic is not carried, but both
    companies are, and the note says so. (Without a topic word, "Is that wider than Omegaware?" now carries the earlier topic:
    DECISIONS, "Follow-up topic carry", and tests/test_followup_topic_carry.py.)"""
    q = "Is that wider than Omegaware's revenue?"
    ans, _ = ask(conn, RoutingLLM(rewrite=q), q)
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert ans.interpreted_question == "Is that wider than Omegaware's revenue? (comparing ZZCA and ZZCB)"


# ---- wordings found by the fresh cases written for this step (they missed on the first run; see DECISIONS) ----


@pytest.mark.parametrize("question", [
    "Did that beat Omegaware?", "How does it measure up to Omegaware?", "Does that outperform Omegaware?",
])
def test_beat_outperform_and_measure_up_are_comparison_words(conn, question):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question)
    assert sorted(ans.symbols) == ["ZZCA", "ZZCB"]
    assert ans.interpreted_question == "How many employees does Zetacorp have, compared with Omegaware?"


@pytest.mark.parametrize("question", [
    "Go ahead and do Omegaware.", "Let's see Omegaware instead.", "Okay, do Omegaware next.", "Run the same for Omegaware.",
])
def test_more_everyday_switch_wordings_keep_the_topic(conn, question):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question)
    assert ans.interpreted_question == "How many employees does Omegaware have?" and ans.symbols == ["ZZCB"]


@pytest.mark.parametrize("question", [
    "Did Omegaware beat earnings estimates?",         # "beat", but no reference back to the last answer
    "Did that beat earnings estimates?",              # a reference and "beat", but no new company
    "Let's see Omegaware's employees.",               # a topic of its own
])
def test_the_new_words_do_not_pull_in_unrelated_questions(conn, question):
    ans, _ = ask(conn, RoutingLLM(rewrite=question), question)
    assert "compared with" not in (ans.interpreted_question or "") and ans.interpreted_question in (None, question)
