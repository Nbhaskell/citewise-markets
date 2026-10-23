"""Fix (5) of the fresh round: more questions the app cannot answer are declined in code, before the model is asked.

1. A capitalised name that appears nowhere in the stored filings or headlines, in a question that names no tracked company, is
   declined by name ("How many restaurants does Chipotle run?"): a finite company list can never be complete, but the stored text is.
2. More outside assets and topics (gas prices, diesel, crops, the economy, REITs, stablecoins...) and more companies on the list.
3. A request to WRITE something (an email, a post, a poem, code, slides, a translation) is declined even when a tracked company is
   named, since the answer was a full email built from filing figures. Summaries and bullets are research and stay answerable.
Fake names (Zorblaxx, Quuxford Dynamics) stand in for companies the real data cannot contain. Fixture companies: Zetacorp (ZZCA) and
Omegaware (ZZCB); the stored text the names are looked up in is inserted by the `stored` fixture and removed afterwards.
"""
from datetime import date, datetime, timezone

import pytest

from ai.market import outside_scope, unknown_name, writing_request
from data.db import connect
from test_copilot_history import RoutingLLM, ask, conn  # noqa: F401  (conn is a fixture)


@pytest.fixture
def stored():
    """One stored filing and one stored headline, with no filing chunks: chunks inserted and deleted by many tests leave dead
    entries in the vector index and made the search tests flaky (see tests/conftest.py), so this fixture adds none."""
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZOUT', 'Outcorp Inc.')")
        c.execute(
            "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) VALUES ('0-ZO-A', 'ZZOUT', '1', '10-K', %s, "
            "'https://x', %s)", (date(2025, 1, 1), "Outcorp supplies the Plenvora platform to groups of customers, including in China. Item 1A."))
        c.execute(
            "INSERT INTO news_articles (id, source, title, url, published_at) VALUES ('zz-out-1', 'zz', %s, 'https://x', %s)",
            ("Mirvanta surges on guidance", datetime.now(timezone.utc)))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM news_articles WHERE id = 'zz-out-1'")
        c.execute("DELETE FROM filings WHERE symbol = 'ZZOUT'")
        c.execute("DELETE FROM instruments WHERE symbol = 'ZZOUT'")
        c.commit()


# ---- 1. a name found nowhere in the stored text ----


@pytest.mark.parametrize("question,name", [
    ("How many stores does Zorblaxx operate?", "Zorblaxx"),
    ("Is Zorblaxx's CEO about to change?", "Zorblaxx"),              # possessive stripped
    ("What are Quuxford Dynamics' biggest risks?", "Quuxford Dynamics"),   # two words, trailing apostrophe
    ("Tell me about Quuxford Dynamics.", "Quuxford Dynamics"),
    ("Zorblaxx's headcount, please?", "Zorblaxx"),                    # first word, but a possessive: a name
    ("Is it true that Zorblaxx is in trouble?", "Zorblaxx"),
    ("What did Zorblaxx say last quarter?", "Zorblaxx"),
    ("Does Zorblaxx have any debt coming due?", "Zorblaxx"),
])
def test_a_name_found_nowhere_in_the_stored_text_is_named_back(stored, question, name):
    assert unknown_name(stored, question) == name


@pytest.mark.parametrize("question", [
    "What does Plenvora do?",                       # in a stored filing
    "Is Mirvanta in the news?",                     # in a stored headline
    "How are the Plenvora and Mirvanta stories doing?",
    "What does PLENVORA do?",                       # any case
])
def test_a_name_that_is_stored_somewhere_is_not_unknown(stored, question):
    assert unknown_name(stored, question) is None


def test_a_name_is_matched_as_a_whole_word_not_as_part_of_a_longer_one(stored):
    assert unknown_name(stored, "What does Plen do?") == "Plen"      # "Plenvora" is stored; "Plen" is not a word in it


@pytest.mark.parametrize("question", [
    "Which companies mention Zorblaxx?",            # a filings cue: a research question about the stored companies
    "Does any filing discuss Zorblaxx?",
    "According to the 10-K, who supplies Zorblaxx?",
    "Do both companies compete with Zorblaxx?",
    "Is anyone exposed to Zorblaxx?",
])
def test_a_filings_cue_keeps_a_question_about_an_unknown_name_answerable(stored, question):
    assert unknown_name(stored, question) is None


@pytest.mark.parametrize("question", [
    "Zorblaxx makes what?",                         # a lone leading word with no possessive is not looked at
    "what does zorblaxx do?",                       # lowercase is not a name
    "How are things at the end of March?",          # months and weekdays
    "What happened on Monday?",
    "How does the SEC treat Q3 EPS?",               # acronyms
    "Ok, And what about the risks?",                # capitalised function words after punctuation
    "Is the Fed a risk for chip makers?",
    "What are the biggest risks in 2026?",
    "Item 1A says what?",
    "Is China a risk for chip makers?",             # places that the stored text names
])
def test_ordinary_capitals_are_not_names(stored, question):
    assert unknown_name(stored, question) is None


# ---- through the whole copilot ----


def test_an_unknown_name_is_declined_before_the_model_is_asked(conn):
    llm = RoutingLLM()
    ans, emb = ask(conn, llm, "How many stores does Zorblaxx operate?", history=[])
    assert ans.refused and ans.retrieved == [] and ans.symbols == []
    assert "Zorblaxx" in ans.text and "stored" in ans.text and "Add a company" in ans.text and "ZZCA" in ans.text
    assert llm.calls == [] and emb.queries == []


def test_a_tracked_company_that_is_named_is_never_declined_for_an_unknown_name(conn):
    ans, _ = ask(conn, RoutingLLM(), "Does Zetacorp compete with Zorblaxx?", history=[])
    assert not ans.refused and ans.symbols == ["ZZCA"]


def test_chosen_companies_are_never_second_guessed_by_the_unknown_name_rule(conn):
    ans, _ = ask(conn, RoutingLLM(), "How many stores does Zorblaxx operate?", history=[], symbols=["ZZCA"])
    assert not ans.refused


def test_a_cross_company_question_about_an_unknown_name_still_searches_the_filings(conn):
    ans, emb = ask(conn, RoutingLLM(), "Which companies mention Zorblaxx?", history=[])
    assert not ans.refused and emb.queries


def test_a_follow_up_that_switches_to_an_unknown_company_is_declined(conn):
    ans, _ = ask(conn, RoutingLLM(rewrite="What about Zorblaxx's risks?"), "What about Zorblaxx's risks?")
    assert ans.refused and "Zorblaxx" in ans.text


def test_the_company_list_message_is_kept_for_a_listed_company(conn):
    ans, _ = ask(conn, RoutingLLM(), "What does Netflix say about competition?", history=[])
    assert ans.refused and "Netflix" in ans.text and "isn't one of the companies tracked" in ans.text


# ---- 2. more outside assets and topics, and more companies ----


@pytest.mark.parametrize("question", [
    "What are gas prices doing at the pump?", "How is gasoline trending?", "Is diesel getting more expensive?",
    "Is jet fuel getting cheaper?", "Are fuel prices up this year?",
    "Are coffee prices up this year?", "What's corn doing?", "How is soybean pricing?", "Is sugar rallying?", "What are cattle futures at?",
    "How is cotton trading?", "Has lumber come down?",
    "What is the VIX at?", "What's the ten-year yield?", "Where are yields heading?",
    "How is the economy doing?", "Is the stock market overvalued?", "Is the housing bubble about to burst?",
    "How are REITs doing?", "What is the best index fund?", "What ETFs should I look at?", "Are meme stocks back?",
    "How are student loans doing?", "How is consumer confidence?", "What are retail sales looking like?",
    "Is the labor market tight?", "What did the jobs numbers show?", "Is Tether stable?", "Are stablecoins safe?",
    "How's the yuan doing?", "Where is the yen?", "How is the peso?", "Will there be a government shutdown?",
])
def test_more_outside_assets_and_topics(question):
    assert outside_scope(question) == ("asset", ""), question


@pytest.mark.parametrize("question", [
    "Which companies mention gasoline costs?", "Do any filings discuss diesel prices?", "Which of the companies cite fuel prices as a risk?",
    "According to the 10-K, how exposed is anyone to the yen?", "What do the filings say about the economy?",
    "Which companies mention student loans?", "Does any company discuss consumer confidence?",
])
def test_a_filings_cue_still_keeps_these_answerable(question):
    assert outside_scope(question) is None, question


@pytest.mark.parametrize("question,name", [
    ("How many restaurants does Chipotle run?", "Chipotle"),
    ("What does Etsy say about competition?", "Etsy"),
    ("Is Peloton in legal trouble?", "Peloton"),
    ("How many stores does Lululemon operate?", "Lululemon"),
    ("Tell me about Marriott's debt.", "Marriott"),
    ("What are Delta Air Lines' biggest risks?", "Delta Air Lines"),
    ("How many employees does FedEx have?", "FedEx"),
    ("What does Eli Lilly say about its pipeline?", "Eli Lilly"),
    ("What are CVS Health's risks?", "CVS Health"),
    ("How is Kroger's revenue trending?", "Kroger"),
    ("Does Nintendo disclose anything about piracy?", "Nintendo"),
    ("What did General Motors say about EV demand?", "General Motors"),
    ("Tell me about Taiwan Semiconductor's customers.", "Taiwan Semiconductor"),
    ("What are Merck's risks?", "Merck"),
    ("Does AbbVie have patent troubles?", "AbbVie"),
    ("How many people work at UPS?", "UPS"),
    ("Are Dollar General's margins shrinking?", "Dollar General"),
    ("What does Carvana say about its debt?", "Carvana"),
    ("How big is DoorDash?", "DoorDash"),
    ("What are Medtronic's biggest risks?", "Medtronic"),
    ("What risks does Arm Holdings face in China?", "Arm Holdings"),
    ("What does Dell say about AI servers?", "Dell"),
    ("How is Nestle doing?", "Nestle"),
    ("What's Tyson Foods' biggest risk?", "Tyson Foods"),
    ("How many hotels does Hilton run?", "Hilton"),
    ("What does Etsy's CEO say?", "Etsy"),
])
def test_more_well_known_companies_are_named_back(question, name):
    assert outside_scope(question) == ("company", name), question


def test_every_listed_company_is_declined_by_name():
    """Guards the list itself: an entry with a typo, a regex character, or the wrong capitalisation rule would silently never match."""
    from ai.market import UNTRACKED_COMPANIES

    for name in UNTRACKED_COMPANIES:
        assert outside_scope(f"What does {name} say about its competition?") == ("company", name), name
        assert outside_scope(f"How big is {name}'s workforce these days?") == ("company", name), name


@pytest.mark.parametrize("question", [
    "Which companies mention Chipotle?", "According to the 10-K, who competes with Nintendo?",
])
def test_a_filings_cue_keeps_a_listed_company_question_answerable(question):
    assert outside_scope(question) is None


# ---- 3. a request to write something ----


@pytest.mark.parametrize("question", [
    "Draft an email to my boss about Nvidia's results.", "Write a LinkedIn post about Apple's earnings.",
    "Write me a short poem about Tesla.", "Compose a tweet about Microsoft's cloud revenue.",
    "Write a cover letter for a job at Amazon.", "Make a slide deck about AMD's risks.",
    "Write a memo to my team about Alphabet's revenue.", "Translate Apple's risk factors into Spanish.",
    "Write a blog post on Nvidia's growth.", "Text my friend about Google's stock price.", "Write a joke about Tesla.",
    "Write a Python script that scrapes Apple's stock price.", "Email my boss the Tesla numbers.",
    "Please prepare a presentation on Microsoft's segments.", "Can you put together a newsletter about Nvidia?",
    "Give me a haiku about spring.", "Write a thank-you note to my landlord.", "Draft an email to my boss.",
    "Can you write a cover letter for me?", "Sing me a song about the market.", "Write a SQL query for Apple's revenue.",
    "Craft a speech about Tesla's year.", "Generate a press release about Amazon.", "Write an essay on Microsoft's strategy.",
    "Create a resume for me.", "Write a toast for my friend's wedding.", "Whip up a caption about Nvidia for Instagram.",
    "Translate this sentence into French.", "Write me a function to sort a list.",
])
def test_a_request_to_write_something_is_declined(question):
    assert writing_request(question), question


@pytest.mark.parametrize("question", [
    "Summarize Nvidia's risks in three bullets.", "Write a summary of Apple's legal proceedings.",
    "Give me a summary of Tesla's year.", "Make a list of Amazon's risk factors.", "Create a table of AMD's segments.",
    "Draft a comparison of Apple's and Microsoft's debt.", "Prepare an overview of Nvidia's customers.",
    "Which companies mention a letter of credit?", "What does the memo of understanding with Intel say?",
    "How many posts did Tesla make about its Cybertruck?", "What does the cover letter template have to do with Amazon's hiring?",
    "Does Microsoft mention a presentation of its results to the board?", "What is Apple's message to investors?",
    "What does the poem on Tesla's website say?", "Is there a script for Nvidia's earnings call?",
    "What do the slides from Alphabet's conference say?", "What are Amazon's thoughts on a speech by the Fed chair?",
    "Pull up some recent stories about Amazon.", "How does Tesla text its customers about recalls?",
    "Translation losses hurt Apple's results, how much?", "What did Microsoft say about its code of conduct?",
])
def test_research_questions_are_not_taken_for_writing_requests(question):
    assert not writing_request(question), question


def test_a_writing_request_that_names_a_tracked_company_is_declined_before_the_model_is_asked(conn):
    llm = RoutingLLM()
    ans, emb = ask(conn, llm, "Draft an email to my boss about Zetacorp's results.", history=[])
    assert ans.refused and ans.retrieved == []
    assert "email" in ans.text.lower() and "write" in ans.text.lower() and "Zetacorp" not in ans.text.split("(")[0]
    assert llm.calls == [] and emb.queries == []


def test_a_writing_request_is_declined_even_for_chosen_companies(conn):
    ans, _ = ask(conn, RoutingLLM(), "Write me a short poem about Zetacorp.", history=[], symbols=["ZZCA"])
    assert ans.refused


def test_a_summary_request_for_a_tracked_company_is_answered(conn):
    ans, emb = ask(conn, RoutingLLM(), "Write a summary of Zetacorp's risks.", history=[])
    assert not ans.refused and emb.queries


def test_a_follow_up_that_asks_for_writing_is_declined(conn):
    llm = RoutingLLM(rewrite="Now write a poem about Zetacorp.")
    ans, _ = ask(conn, llm, "Now write a poem about it.")      # the company comes from the earlier turn
    assert ans.refused and "answer" not in llm.calls


# ---- found by breaking each rule on purpose (see DECISIONS): every alternative and guard needs a question of its own ----


@pytest.mark.parametrize("question", [
    "What is cocoa doing?", "What is the volatility index at?", "Where are yields going?", "Did payrolls surprise?",
    "What is USDC pegged to?", "What is the renminbi at?", "What is the Japanese yen at?", "How is the Indian rupee?", "Will the debt ceiling be raised?",
    "Are people queuing at the pump?", "Where are yields?",
])
def test_the_remaining_outside_topics(question):
    assert outside_scope(question) == ("asset", ""), question


@pytest.mark.parametrize("question", [
    "Produce a poem for me.", "Pen a poem about spring.", "Come up with a limerick about banks.", "Write a message to my team.",
    "Write a script for a video.", "Make slides about AMD's risks.", "Make a slide deck for Friday.", "Make decks for the board.",
    "Write a cv for me.", "Draft speeches for the conference.", "Write songs about Tesla.", "Write limericks about Nvidia.",
    "Write a rap about Apple.", "Write a riddle about Amazon.", "Draft a blog about Alphabet.", "Write a thank you note to a banker.",
    "Write a note to my landlord.", "Write me a message about Microsoft.", "Draft scripts for a video.",
    "Write a thank-you note for my aunt.",
])
def test_every_writing_verb_and_thing_is_declined(question):
    assert writing_request(question), question


@pytest.mark.parametrize("question", [
    "Create a list of tweets that mention Apple.",                 # "of" before the thing
    "Prepare a report about presentations Apple gave.",
    "Prepare a summary on letters to shareholders.",
    "Create a table from emails Tesla disclosed.",
    "Draft a summary regarding memos Apple filed.",
    "Prepare a chart for speeches by Tesla's CEO.",
    "Create a deckhand schedule for Tesla's shipping.",           # "deck" inside a longer word
    "Make a messaging summary for Microsoft.",
])
def test_a_thing_after_a_preposition_or_inside_a_longer_word_is_research(question):
    assert not writing_request(question), question


def test_a_name_with_a_known_first_word_and_an_unknown_second_word_is_unknown(stored):
    assert unknown_name(stored, "What does Plenvora Zorblaxx do?") == "Plenvora Zorblaxx"


def test_a_name_is_not_found_inside_a_longer_stored_word(stored):
    assert unknown_name(stored, "What does Vora do?") == "Vora"           # "Plenvora" is stored; "Vora" is only the end of it


def test_a_stored_headline_matches_in_any_case(stored):
    assert unknown_name(stored, "Is MIRVANTA in the news?") is None


def test_a_leading_function_word_after_punctuation_is_not_part_of_the_name(stored):
    assert unknown_name(stored, "Yes, And Zorblaxx's headcount?") == "Zorblaxx"


def test_exposure_is_a_filings_cue(stored):
    assert unknown_name(stored, "What is the exposure to Zorblaxx?") is None


@pytest.mark.parametrize("question", [
    "What happened in March?", "How did May go?", "Is Monday a holiday?", "What about Friday?", "Is it open on Sunday?",
    "And then what?", "Ok, But what about that?", "Hello, What now?", "Thanks, Please do that.",
])
def test_stop_words_are_dropped_from_a_capitalised_run_before_the_stored_text_is_asked(question):
    """Tested on the words alone, since the real stored text names every month: a database that lacks one must still not flag it."""
    from ai.market import NAME_RUN_RE, _name_run_words

    for run in NAME_RUN_RE.finditer(question):
        assert _name_run_words(question, run) == [], (question, run.group())


@pytest.mark.parametrize("name", ["CVS", "Hertz", "Okta", "Puma", "UPS", "Carnival", "Arista", "Dell"])
def test_these_listed_companies_are_named_back_with_a_capital(name):
    assert outside_scope(f"What risks does {name} flag?") == ("company", name)


@pytest.mark.parametrize("sentence", [
    "What are the ups and downs of chip demand?", "Did a puma appear in the ad?", "Can you intuit the trend?",
    "When does the workday end?", "Was the carnival of rumours loud?", "Is hertz a unit of frequency?", "Did the okta of hope fade?",
    "Is the arista of the cut clear?", "Why dell into this?",
])
def test_words_that_are_also_company_names_need_the_capital(sentence):
    result = outside_scope(sentence)
    assert result is None or result[0] != "company", sentence


def test_a_writing_request_is_declined_when_only_the_question_asks_for_it(conn):
    llm = RoutingLLM(rewrite="What are Zetacorp's risks?")        # the rewrite lost the request
    ans, _ = ask(conn, llm, "Draft an email to my boss about Zetacorp's results.")
    assert ans.refused and "doesn't write" in ans.text


def test_a_writing_request_is_declined_when_only_the_rewrite_makes_it_explicit(conn):
    llm = RoutingLLM(rewrite="Write a poem about Zetacorp.")        # "that as a poem" becomes explicit in the rewrite
    ans, _ = ask(conn, llm, "Now do that as a poem, please.")
    assert ans.refused and "doesn't write" in ans.text


def test_an_unknown_name_that_only_the_rewrite_contains_is_declined(conn):
    llm = RoutingLLM(rewrite="What are Zorblaxx's biggest risks?")  # "And the competitor?" has no name and no reference word
    ans, _ = ask(conn, llm, "And the competitor?")
    assert ans.refused and "Zorblaxx" in ans.text
