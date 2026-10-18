"""Filings questions that carry a price or mood word (DECISIONS: "Filings questions with price or mood words").

"What does Apple say about falling demand in China?" went to the stock PRICES ("falling"), and "Does Tesla sound optimistic about its
factory expansion?" to the headlines and their mood ("optimistic"): the word that sounded like the market won, although the question is
about what the COMPANY says. When a tracked company, its management (executives, leadership, CEO, CFO) or its 10-K, 10-Q, annual report
or filings is the one speaking (say, describe, discuss, disclose, mention, state, explain, convey, sound), prices, headlines and mood
are switched off and the question goes to the filings. Not when the press is named (news, headlines, coverage, stories...): "Has
Apple said anything in the headlines today?" is still headlines. The stored figures are not touched. Fixture company: Marketco (ZZMA),
with prices, headlines and a filing (tests/test_market.py). Nothing here calls a model.
"""
import pytest

from ai.copilot import answer_question, company_is_speaking, route_by_speaker
from ai.market import Intent, detect_intent
from test_market import FakeEmbedder, conn  # noqa: F401  (conn is a fixture)
from test_router import RouterLLM, reply


def kinds(question, conn, **kwargs):
    ans = answer_question(conn, FakeEmbedder(), RouterLLM(answer="Marketco faces supply risk [1]."), question, expand=False, router=False, **kwargs)
    return {getattr(r, "kind", "filing") for r in ans.retrieved}


# ---- who is speaking: each verb, and each way of naming the speaker ----


@pytest.mark.parametrize("question, verb", [
    ("What does Marketco say about falling demand?", "say"),
    ("Marketco says demand is falling, so what is its plan?", "says"),
    ("What did Marketco said about falling demand?", "said"),
    ("Does Marketco describe falling demand?", "describe"),
    ("Marketco describes falling demand in its report.", "describes"),
    ("Marketco described falling demand, didn't it?", "described"),
    ("Does Marketco discuss falling demand?", "discuss"),
    ("Marketco discusses falling demand at length.", "discusses"),
    ("Marketco discussed falling demand, right?", "discussed"),
    ("Does Marketco disclose falling demand?", "disclose"),
    ("Marketco discloses falling demand somewhere.", "discloses"),
    ("Marketco disclosed falling demand, didn't it?", "disclosed"),
    ("Does Marketco mention falling demand?", "mention"),
    ("Marketco mentions falling demand once.", "mentions"),
    ("Marketco mentioned falling demand, I think.", "mentioned"),
    ("Does Marketco state that demand is falling?", "state"),
    ("Marketco states that demand is falling.", "states"),
    ("Marketco stated that demand was falling, right?", "stated"),
    ("Did Marketco explain falling demand?", "explain"),
    ("Marketco explains falling demand somewhere.", "explains"),
    ("Marketco explained falling demand, I think.", "explained"),
    ("What does Marketco convey about falling demand?", "convey"),
    ("Marketco conveys that demand is falling.", "conveys"),
    ("Marketco conveyed that demand was falling.", "conveyed"),
    ("Does Marketco sound worried about falling demand?", "sound"),
    ("Marketco sounds worried about falling demand.", "sounds"),
])
def test_each_speaker_verb_makes_the_company_the_speaker(conn, question, verb):
    assert company_is_speaking(conn, question), verb


@pytest.mark.parametrize("question", [
    "What does Marketco also say about falling demand?",        # a small word between the speaker and the verb
    "Does Marketco ever mention falling demand?",
    "Does Marketco really say demand is falling?",
    "Does Marketco actually describe falling demand?",
])
def test_a_small_word_between_the_company_and_the_verb_is_allowed(conn, question):
    assert company_is_speaking(conn, question), question


@pytest.mark.parametrize("question", [
    "How does Marketco's management describe falling demand?",
    "What do Marketco's executives say about falling demand?",
    "What does Marketco's leadership say about falling demand?",
    "What does Marketco's CEO say about falling demand?",
    "What does Marketco's CFO say about falling demand?",
    "What did Marketco's 10-K say about falling demand?",
    "What did Marketco's 10-Q say about falling demand?",
    "What did Marketco's annual report say about falling demand?",
    "What do Marketco's filings say about falling demand?",
    "What does marketco say about falling demand?",              # typed in lower case
])
def test_the_speaker_can_be_the_companys_staff_or_its_documents(conn, question):
    assert company_is_speaking(conn, question), question


@pytest.mark.parametrize("question", [
    "How worried is Marketco's management about falling demand?",     # the staff themselves, with no verb
    "How bullish are Marketco's executives about demand?",
    "How does Marketco's leadership feel about demand?",
    "Is Marketco's CEO optimistic about demand?",
    "Is Marketco's CFO bearish on demand?",
])
def test_the_companys_staff_are_the_speaker_even_with_no_speaking_verb(conn, question):
    assert company_is_speaking(conn, question), question


@pytest.mark.parametrize("question", [
    "What does the 10-K say about falling demand?",              # a document is the speaker, no company named
    "What does the 10-Q say about falling demand?",
    "What does the annual report say about falling demand?",
    "What do the filings say about falling demand?",
])
def test_a_document_is_the_speaker_even_with_no_company_named(conn, question):
    assert company_is_speaking(conn, question), question


@pytest.mark.parametrize("question", [
    "What are analysts saying about Marketco's falling stock price?",
    "What do investors say about Marketco stock falling?",
    "What does the market say about Marketco shares?",
    "Would you say Marketco's stock is sliding?",
    "Can you explain why Marketco shares fell?",
    "Everyone says Marketco can only go up from here, right?",
    "What explains Marketco's slide these days?",
    "Marketco shares fell, said a Reuters story.",
    "Why did Marketco stock fall?",
    "How is Marketco doing?",
])
def test_someone_else_speaking_does_not_make_the_company_the_speaker(conn, question):
    assert not company_is_speaking(conn, question), question


# ---- what the rule does with a market route ----


@pytest.mark.parametrize("question", [
    "Does Marketco say anything about slumping demand?",         # a price word
    "Does Marketco sound optimistic about its factory?",         # a mood word
    "What did Marketco's 10-K say about falling demand?",        # a filing named: no prices beside the filings
    "How bullish is Marketco's management about demand?",
    "Did Marketco explain why its backlog dropped?",             # a cause word adds the headlines: gone too
])
def test_a_company_speaking_with_a_market_word_goes_to_the_filings_only(conn, question):
    assert detect_intent(question).market                        # the keywords did read it as a market question
    assert kinds(question, conn) == {"filing"}, question


def test_the_route_changes_only_the_market_flags(conn):
    intent = detect_intent("What does Marketco say about falling demand?")
    assert intent.prices
    routed = route_by_speaker(conn, "What does Marketco say about falling demand?", intent)
    assert (routed.prices, routed.headlines, routed.sentiment, routed.filings, routed.fundamentals) == (False, False, False, True, frozenset())


def test_a_mood_question_loses_the_mood_and_the_headlines_it_rides_on(conn):
    question = "How bullish is Marketco's management about demand?"
    intent = detect_intent(question)
    assert intent.sentiment and intent.headlines                  # the keywords read it as mood, which comes with the headlines
    routed = route_by_speaker(conn, question, intent)
    assert (routed.sentiment, routed.headlines, routed.prices, routed.filings) == (False, False, False, True)


def test_a_headlines_only_question_with_the_company_speaking_goes_to_the_filings(conn):
    question = "What did Marketco say about what happened at its plant?"      # "what happened" is a news cue, no price or mood word
    intent = detect_intent(question)
    assert intent.headlines and not intent.prices and not intent.sentiment
    assert kinds(question, conn) == {"filing"}


@pytest.mark.parametrize("question", [
    "What are analysts saying about Marketco's falling stock price?",
    "Would you say Marketco's stock is sliding?",
    "Why did Marketco shares tumble after the earnings call?",
])
def test_a_market_question_with_someone_else_speaking_keeps_its_route(conn, question):
    assert "price" in kinds(question, conn), question


@pytest.mark.parametrize("question, word", [
    ("Did Marketco say anything in the news about falling demand?", "news"),
    ("Has Marketco said anything in the headlines today?", "headlines"),
    ("What did Marketco say about falling shares in the headline?", "headline"),
    ("Did Marketco say anything in the press about falling demand?", "press"),
    ("What coverage is there of what Marketco says about falling shares?", "coverage"),
    ("What stories say Marketco discussed falling shares?", "stories"),
    ("Is there a story where Marketco described falling shares?", "story"),
    ("Which articles say Marketco mentioned falling shares?", "articles"),
    ("Is there an article where Marketco discussed falling shares?", "article"),
    ("What are reporters saying about what Marketco said about falling shares?", "reporters"),
    ("What is the media saying about what Marketco said on falling shares?", "media"),
    ("What are journalists saying about what Marketco disclosed on falling shares?", "journalists"),
])
def test_naming_the_press_keeps_the_market_route(conn, question, word):
    intent = detect_intent(question)
    assert route_by_speaker(conn, question, intent) == intent, word


def test_the_stored_figures_are_not_touched(conn):
    question = "What did Marketco say its earnings per share came to?"
    intent = detect_intent(question)
    assert intent.fundamentals and not (intent.prices or intent.headlines or intent.sentiment)
    assert route_by_speaker(conn, question, intent) == intent


def test_a_figure_beside_a_price_word_keeps_the_figure(conn):
    question = "What did Marketco say its earnings per share were when shares fell?"
    intent = detect_intent(question)
    assert intent.fundamentals and intent.prices
    routed = route_by_speaker(conn, question, intent)
    assert routed.fundamentals == intent.fundamentals and not routed.prices and routed.filings


def test_a_question_with_no_market_route_is_returned_unchanged(conn):
    question = "What does Marketco say about its suppliers?"
    intent = detect_intent(question)
    assert not intent.market and route_by_speaker(conn, question, intent) is intent


def test_the_rule_does_not_need_a_company_in_the_question_for_a_document_speaker(conn):
    question = "What does the 10-K say about falling demand?"
    assert route_by_speaker(conn, question, detect_intent(question)).prices is False


# ---- the router is not asked about a question the keyword rule decided ----


def test_the_router_is_not_asked_about_a_question_the_speaker_rule_sent_to_the_filings(conn):
    llm = RouterLLM(reply(price=True), answer="Marketco faces supply risk [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "What does Marketco say about falling demand?", expand=False, router=True)
    assert "route" not in llm.calls
    assert {getattr(r, "kind", "filing") for r in ans.retrieved} == {"filing"}


def test_a_question_nobody_speaks_in_is_still_put_to_the_router_when_it_is_on(conn):
    llm = RouterLLM(reply(price=True), answer="Marketco faces supply risk [1].")
    answer_question(conn, FakeEmbedder(), llm, "Has Marketco pulled back from its high this year?", expand=False, router=True)
    assert "route" in llm.calls
