"""A headline the answer quotes must be one of the stored sources.

In the held-out round, "Why is Tesla tanking?" went to the filings only, and in one of three runs the model listed three
"headlines" with sentiment tags ("Tesla Faces Legal Challenges [Sentiment: Negative]" and two more) that exist nowhere in
the stored data. The numbers check cannot catch that: there are no digits and no citations. `invented_titles` looks at
what the answer presents as a headline or a quotation and compares its words with every source the model was given.
"""
from datetime import date

import pytest

from ai.copilot import _generate_checked_full, invented_titles, invented_titles_caution, quoted_titles
from ai.market import MarketEvidence
from ai.search import SearchResult

HEADLINE = MarketEvidence(
    "headline", "ZZT", "ZZT headline, Example Wire, 2026-10-14, automatic label: negative",
    "Tesla Recalls 200,000 Vehicles Over Software Fault - Example Wire", None, date(2026, 10, 14),
)
FILING = SearchResult(2, "0-ZT", "ZZT", "10-K", date(2026, 1, 1), None, "https://x", "Item 1A",
                      'We face "intense competition in the electric vehicle market" from established makers.', 1.0)
SOURCES = [HEADLINE, FILING]

INVENTED = (
    "Recent headlines:\n"
    "- Tesla Faces Legal Challenges [Sentiment: Negative]\n"
    "- Tesla Stock Hits New Low [Sentiment: Negative]\n"
    "- Analysts Question Tesla's Strategy [Sentiment: Neutral]"
)


def test_the_invented_headlines_from_the_held_out_round_are_found():
    found = invented_titles(INVENTED, SOURCES, "Why is Tesla tanking?")
    assert found == ["Tesla Faces Legal Challenges", "Tesla Stock Hits New Low", "Analysts Question Tesla's Strategy"]


@pytest.mark.parametrize("answer", [
    'The newest headline is "Tesla Recalls 200,000 Vehicles Over Software Fault" [1].',
    'The newest headline is “Tesla recalls 200,000 vehicles over software fault” [1].',  # case and curly quotes
    '- Tesla Recalls 200,000 Vehicles Over Software Fault [Sentiment: Negative] [1]',  # the list format, with a real title
    '1. Headline: Tesla Recalls 200,000 Vehicles Over Software Fault (Sentiment: negative)',
    'It reports "intense competition in the electric vehicle market" [2].',  # a real quotation from a filing
    'It warns of "intense competition ... from established makers" [2].',  # an ellipsis inside a real quotation
    'The headline "Tesla Recalls 200,000 Vehicles Over Software Fault" was labeled negative.',
])
def test_a_title_that_is_in_the_sources_passes(answer):
    assert invented_titles(answer, SOURCES) == []


@pytest.mark.parametrize("answer", [
    'The headline "Tesla Recalls 300,000 Vehicles Over Software Fault" was labeled negative.',  # one word changed
    'It reports "fierce competition in the electric vehicle market" [2].',  # a paraphrase presented as a quote
    'One headline says “Tesla Faces Legal Challenges” [1].',
])
def test_a_quote_that_is_not_in_the_sources_is_found(answer):
    assert len(invented_titles(answer, SOURCES)) == 1


def test_short_quotes_and_unquoted_text_are_not_titles():
    answer = 'Tesla calls this a "reasonable" step. The "market value" is below. Tesla faces legal challenges [1].'
    assert quoted_titles(answer) == [] and invented_titles(answer, SOURCES) == []


def test_a_phrase_the_user_typed_is_not_invented():
    question = 'Is the "Tesla is doomed" story true?'
    assert invented_titles('The sources do not support "Tesla is doomed" [1].', SOURCES, question) == []


def test_a_title_is_found_even_when_there_are_no_news_sources_at_all():
    """The Tesla case: the question went to the filings only, so no headline was in the prompt."""
    assert len(invented_titles(INVENTED, [FILING], "Why is Tesla tanking?")) == 3


def test_the_caution_names_what_was_made_up():
    text = invented_titles_caution(["Tesla Faces Legal Challenges"])
    assert "Tesla Faces Legal Challenges" in text and "not in the stored sources" in text and "made up" in text


# ---- the retry, with a fake model ----

class ScriptedLLM:
    name = "fake"

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def generate(self, system, user, json_schema=None):
        self.calls.append((system, user))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def test_invented_headlines_are_retried_and_the_second_answer_is_used():
    llm = ScriptedLLM(INVENTED, "The stored sources contain one headline: Tesla Recalls 200,000 Vehicles Over Software Fault [1].")
    text, cited, bad, causes, titles = _generate_checked_full(llm, "Why is Tesla tanking?", SOURCES)
    assert len(llm.calls) == 2 and "Tesla Faces Legal Challenges" in llm.calls[1][1]  # the complaint names what was invented
    assert titles == [] and "Faces Legal" not in text


def test_a_second_answer_that_still_invents_is_reported_not_hidden():
    llm = ScriptedLLM(INVENTED)  # repeats the same invented answer both times
    *_, titles = _generate_checked_full(llm, "Why is Tesla tanking?", SOURCES)
    assert len(llm.calls) == 2 and len(titles) == 3


def test_a_clean_answer_costs_no_extra_model_call():
    llm = ScriptedLLM('The newest headline is "Tesla Recalls 200,000 Vehicles Over Software Fault" [1].')
    *_, titles = _generate_checked_full(llm, "Any Tesla news?", SOURCES)
    assert len(llm.calls) == 1 and titles == []
