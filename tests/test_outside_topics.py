"""Questions about things outside the tracked companies (DECISIONS: "Second held-out round", item 5; fix (f)).

"What did Bitcoin do this month?" was answered from Tesla's Bitcoin note ("Tesla's other income, net, changed favorably..."),
"What are Intel's biggest risks?" from filings of the companies that name Intel as a competitor, and "Write me a poem about
stocks" with a poem that cites no source at all. A question that names no tracked company and is about an asset or topic the
app does not hold (crypto, commodities, rates, the economy), a well-known company it does not track, or something that is not
a research question at all is now declined in code, with a plain message, before the model is asked. The negative cases
matter as much: cross-company filings questions legitimately mention Bitcoin and interest rates.
"""
import pytest

from ai.market import outside_scope
from test_copilot_history import HISTORY, RoutingLLM, ask, conn  # noqa: F401  (conn is a fixture)


@pytest.mark.parametrize("question", [
    "What did Bitcoin do this month?", "How is Ethereum doing?", "What's the price of gold?", "Is oil going up?",
    "What are mortgage rates doing?", "What did the Fed decide?", "Is inflation coming down?",
    "Will there be a recession?", "How's the dollar doing against the euro?", "Is crypto crashing?",
    "What is the Federal Reserve going to do about interest rates?",
])
def test_an_outside_asset_or_topic_is_out_of_scope(question):
    assert outside_scope(question) == ("asset", ""), question


@pytest.mark.parametrize("question,name", [
    ("What does Netflix say about competition?", "Netflix"),
    ("What are Intel's biggest risks?", "Intel"),
    ("How many employees does Walmart have?", "Walmart"),
    ("Tell me about Disney's legal proceedings.", "Disney"),
    ("What does Meta Platforms say about its users?", "Meta Platforms"),
    ("What are Johnson & Johnson's biggest risks?", "Johnson & Johnson"),
    ("Is Starbucks growing?", "Starbucks"),
])
def test_a_well_known_company_that_is_not_tracked_is_named_back(question, name):
    assert outside_scope(question) == ("company", name), question


@pytest.mark.parametrize("question", [
    "Write me a poem about stocks.", "Tell me a joke.", "What's a good recipe for lasagna?", "Who won the game last night?",
    "Compose a song about the market.", "What's the weather like in Seattle?",
])
def test_something_that_is_not_a_research_question_is_out_of_scope(question):
    assert outside_scope(question) == ("chat", ""), question


@pytest.mark.parametrize("question", [
    "Which of the companies mention interest rate risk?",
    "Which companies mention Bitcoin?",
    "Which companies compete with Intel?",
    "How does inflation affect the companies' costs, according to their 10-Ks?",
    "Which company has the most employees?",
    "What are Tesla's biggest risks?",
    "Compare the companies' exposure to oil prices.",
    "Any of the filings discussing a recession?",
    "What is the S&P 500 at?",                          # already declined elsewhere; not this rule's business
    "How many employees does Apple have?",
    "What is the best way to read a 10-K?",
    "Is the gold standard for revenue recognition described in any 10-K?",          # "gold", with a filing word
])
def test_cross_company_and_ordinary_questions_are_not_out_of_scope(question):
    assert outside_scope(question) is None, question


# ---- through the whole copilot, with a fake model ----


def test_an_outside_asset_is_declined_before_the_model_is_asked(conn):
    llm = RoutingLLM()
    ans, emb = ask(conn, llm, "What did Bitcoin do this month?", history=[])
    assert ans.refused and ans.retrieved == [] and ans.symbols == []
    assert "outside what this app covers" in ans.text and "Add a company" not in ans.text
    assert llm.calls == [] and emb.queries == []        # no model call and no filing search


def test_an_untracked_company_is_named_and_the_reader_is_told_how_to_add_it(conn):
    llm = RoutingLLM()
    ans, _ = ask(conn, llm, "What does Netflix say about competition?", history=[])
    assert ans.refused and "Netflix" in ans.text and "Add a company" in ans.text and "ZZCA" in ans.text
    assert llm.calls == []


def test_a_tracked_company_that_is_named_is_never_declined(conn):
    ans, _ = ask(conn, RoutingLLM(), "What does Zetacorp say about its Bitcoin holdings?", history=[])
    assert not ans.refused and ans.symbols == ["ZZCA"]
    ans, _ = ask(conn, RoutingLLM(), "How might Intel and oil prices affect Omegaware?", history=[])
    assert not ans.refused and ans.symbols == ["ZZCB"]


def test_a_cross_company_question_that_mentions_bitcoin_still_searches_the_filings(conn):
    llm = RoutingLLM()
    ans, emb = ask(conn, llm, "Which of the companies mention Bitcoin?", history=[])
    assert not ans.refused and emb.queries


def test_a_follow_up_that_switches_to_an_untracked_company_is_declined(conn):
    ans, _ = ask(conn, RoutingLLM(rewrite="What about Netflix?"), "What about Netflix?")
    assert ans.refused and "Netflix" in ans.text


def test_chosen_companies_are_never_second_guessed_by_the_scope_rule(conn):
    ans, _ = ask(conn, RoutingLLM(), "What did Bitcoin do this month?", history=[], symbols=["ZZCA"])
    assert not ans.refused and ans.symbols == ["ZZCA"]


@pytest.mark.parametrize("question", [
    "Any intel on the market this week?",                     # "intel" the noun, not the company
    "Is the argument for lower rates lucid?",                 # "lucid" the adjective
    "What did the oracle say about the sales target?",        # "oracle" the noun, "target" the word
    "Does the visa process matter for hiring?",               # an ambiguous word that is not on the list
    "Is the shell company risk disclosed anywhere?",
])
def test_ordinary_words_that_are_also_company_names_are_not_taken_for_the_company(question):
    result = outside_scope(question)
    assert result is None or result[0] != "company", question


@pytest.mark.parametrize("question,name", [
    ("What are Intel's biggest risks?", "Intel"),
    ("How is Lucid doing financially?", "Lucid"),
    ("What does Oracle say about its cloud business?", "Oracle"),
    ("what does netflix say about competition", "Netflix"),     # a distinctive name is matched in any case
])
def test_the_capitalised_form_or_a_distinctive_name_is_the_company(question, name):
    assert outside_scope(question) == ("company", name), question


def test_a_price_worded_question_about_an_outside_asset_gets_the_specific_message(conn):
    """"the price of copper" reads as a price question with no company, which has its own generic refusal. The scope rule says
    what is missing, so it goes first."""
    llm = RoutingLLM()
    ans, _ = ask(conn, llm, "Has the price of copper been rising?", history=[])
    assert ans.refused and "outside what this app covers" in ans.text and "Tell me which company" not in ans.text
    assert llm.calls == []


def test_a_price_question_with_no_asset_and_no_company_keeps_the_generic_refusal(conn):
    ans, _ = ask(conn, RoutingLLM(), "How has the stock done this month?", history=[])
    assert ans.refused and "Tell me which company" in ans.text


# ---- wordings found by the fresh held-out cases written for this step (they missed on the first run; see DECISIONS) ----


@pytest.mark.parametrize("question", [
    "Tell me what the central bank is up to.", "Will the ECB cut rates?", "Is another rate hike coming?",
])
def test_more_outside_topics(question):
    assert outside_scope(question) == ("asset", ""), question


def test_zoom_is_a_company_only_when_capitalised():
    assert outside_scope("What risks does Zoom flag?") == ("company", "Zoom")
    result = outside_scope("Can you zoom in on the segment results?")
    assert result is None or result[0] != "company"
