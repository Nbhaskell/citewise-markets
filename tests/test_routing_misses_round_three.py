"""Routing misses found by the third sealed round (DECISIONS: "Routing misses of the third sealed round").

Each answer below was confidently wrong because a keyword rule did not know the wording: "How big is Apple, in terms of what all its
shares are worth?" went to the prices and said market value is not available; "Show me what the papers are printing about Amazon." went
to the filings and said there are no headlines; "Give me Nvidia's highest and lowest close of the past quarter." said the prices do not
cover it; "How wild have Alphabet's swings been since spring?" found nothing; and "Did Alphabet warn that ad prices were dropping?" went
to the stock prices because "warn" is not a speaker verb. Every alternative and every guard has a question of its own. The questions are
new wordings (none is an evaluation case; those are `ROUND_RM`). Nothing here calls a model.
"""
import pytest

from ai.copilot import answer_question, company_is_speaking
from ai.market import detect_intent
from test_market import FakeEmbedder, conn  # noqa: F401  (conn is a fixture)
from test_router import RouterLLM


def value_only(question):
    i = detect_intent(question)
    return "market_value" in i.fundamentals and not i.prices


# ---- a company's total value, worded around its shares ----


@pytest.mark.parametrize("question", [
    "How big is Apple, in terms of what all its shares are worth?",             # the sealed miss: "all its shares are worth"
    "What are all of Tesla's shares worth?",                                    # "all of Tesla's shares worth"
    "Roughly what are all of their shares worth?",                              # "all of their shares worth"
    "What do all of Tesla's shares add up to?",                                 # "add up to"
    "What do all Nvidia's shares add up to in value?",                          # "all X's shares add up to"
    "What is the combined worth of every Microsoft share?",                     # "combined worth of every ... share"
    "What is the total value of each Amazon share added together?",             # "total value of each ... share"
    "What is the aggregate worth of all AMD stock?",                            # "aggregate worth of all ... stock"
    "How much is the whole of AMD worth on the stock market?",                  # "the whole of X worth"
    "How much is the entire Alphabet worth?",                                   # "the entire X worth"
    "If you added up every share of Alphabet, what would it come to?",          # "added up every share"
    "Adding up all Apple shares, what does that make?",                         # "adding up all ... shares"
    "What if I add up each Microsoft share?",                                   # "add up each ... share"
    "What is the overall worth of all Tesla stock?",                            # "overall"
    "What is the collective value of every Nvidia share?",                      # "collective"
])
def test_a_companys_total_worth_in_shares_goes_to_the_stored_figure(question):
    assert value_only(question), question


@pytest.mark.parametrize("question", [
    "How many of all its shares did Apple buy back?",                           # "all its shares" with no "worth"
    "Did Tesla issue all of its shares in 2025?",
    "How much is each share of Nvidia worth?",                                  # one share: a price, not the company
    "What are the shares worth that Microsoft awarded to executives?",          # not "all"
    "What is the whole point of Amazon's AWS?",                                 # "the whole" without "worth"
    "How much is the whole AMD segment table worth reading?",                   # "how much is the whole AMD segment" is not "X worth"
])
def test_other_questions_with_shares_or_worth_are_not_the_total_value(question):
    assert "market_value" not in detect_intent(question).fundamentals, question


# ---- the press, named by what it does ----


@pytest.mark.parametrize("question", [
    "What are the newspapers saying about Microsoft?",                          # newspapers + saying
    "What is a newspaper writing about Amazon?",                                # newspaper (singular) + writing
    "Show me what the papers are printing about Amazon.",                       # the papers + printing (the sealed miss)
    "What are columnists writing about Nvidia?",                                # columnists
    "What do the tabloids say about Tesla?",                                    # tabloids + say
    "What are reporters saying about Tesla?",                                   # reporters + saying
    "What is a journalist saying about Alphabet?",                              # journalist (singular)
    "What are pundits saying about Apple?",                                     # pundits
    "What are commentators saying about AMD?",                                  # commentators
    "What are bloggers saying about Tesla?",                                    # bloggers
    "What is the press saying about Apple?",                                    # the press
    "What is the media saying about Nvidia?",                                   # the media
    "Have the papers been covering AMD much?",                                  # the papers + covering
    "Have the papers covered AMD much?",                                        # covered
    "Is anything being published by the papers on Nvidia?",                     # published, then the papers
    "What is being reported by journalists about Microsoft?",                   # reported
    "What did columnists write about Tesla?",                                   # write
    "What did columnists wrote about Tesla?",                                   # wrote
    "What have the newspapers run on Amazon?",                                  # run
    "What ran in the papers about Nvidia?",                                     # ran
    "What did the tabloids print about Tesla?",                                 # print
    "What has the media published on Apple?",                                   # published
    "What had the papers said about Apple?",                                    # said
    "What was written by columnists about AMD?",                                # written (by the source)
    "What are the newspapers running on Tesla?",                                # running
])
def test_a_news_source_doing_something_routes_to_the_headlines(question):
    assert detect_intent(question).headlines, question


@pytest.mark.parametrize("question", [
    "What research papers does Apple cite?",                                    # papers without "the"
    "Does Tesla file papers with the SEC?",
    "What does the 10-K say about the press release process?",                  # "press" as a noun, no news action
    "How many reporters does Amazon employ?",                                   # a source, no news action
    "Which journalists does Nvidia sue?",
    "What columns does the segment table have for Microsoft?",                  # "columns", not columnists
    "Does AMD say anything about the papers it filed with the court?",          # papers, no "the papers" + action? ("filed" is not an action here)
    "What does Alphabet say about the media business?",                         # "media" with no news action
    "What does the press release say about Nvidia's guidance?",                 # "the press release" is a company document
    "What does the press release cover about Tesla's recall?",                  # same, with "cover"
])
def test_a_news_word_without_the_news_doing_something_is_not_a_headlines_question(question):
    assert not detect_intent(question).headlines, question


# ---- a best or worst close ----


@pytest.mark.parametrize("question", [
    "Give me Nvidia's highest and lowest close of the past quarter.",           # the sealed miss: "highest and lowest close"
    "What's the lowest close Apple has had in the last three months?",          # "lowest close"
    "What was Microsoft's highest close this year?",                            # "highest close"
    "Which was Amazon's best close in the last month?",                         # "best close"
    "What was Tesla's worst close over the past week?",                         # "worst close"
    "What was AMD's peak close this quarter?",                                  # "peak close"
    "What was the top close for Alphabet in the past month?",                   # "top close"
    "What was Amazon's bottom close this month?",                               # "bottom close"
    "Give me Apple's lowest closes this month.",                                # "lowest closes"
    "Tell me Nvidia's highest or lowest close in the last two weeks.",          # "highest or lowest close"
    "Which day did Nvidia close highest in the past month?",                    # "close highest"
    "Which day did Tesla close lowest this quarter?",                           # "close lowest"
    "On what day did AMD close at its highest in the last month?",              # "close at its highest"
    "Did Apple close at a lowest point this week?",                             # "close at a lowest" (the 'a' form)
])
def test_a_best_or_worst_close_is_a_price_question(question):
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Which day did Tesla close its Fremont plant?",                             # "close" as a verb with an object
    "Did Apple close the highest number of stores last year?",                  # "close ... highest" but not a price
    "What was the highest close call in Nvidia's legal proceedings?",           # "close call"
    "Does Microsoft have a close partner with the lowest cost?",                # "close partner" after the extreme words
    "Does Microsoft have the best close partners in cloud?",                    # "best close partners"
    "What are Amazon's top close relationships with suppliers?",                # "top close relationships"
    "Who are Apple's best close competitors?",                                  # "best close competitors"
    "Is the highest close competition for AMD in servers?",                     # "highest close competition"
    "What is the lowest cost Tesla has reported for its factory?",              # "lowest" with no close
])
def test_close_in_another_sense_is_not_a_price_question(question):
    assert not detect_intent(question).prices, question


# ---- swings ----


@pytest.mark.parametrize("question", [
    "How big have AMD's swings been over the past quarter?",                    # company + swings
    "How wild have Alphabet's swings been since spring?",                       # the sealed miss
    "Have Apple's price swings calmed down?",                                   # one adjective
    "How large are Tesla's daily swings these days?",                           # "daily swings"
    "Are Nvidia's swings in the stock getting bigger?",                         # "swings in the stock"
    "What was the size of Amazon's swing in shares last week?",                 # "swing in shares"
    "How big was Tesla's swing last week?",                                     # singular "swing"
    "Did Nvidia's swings in price ease?",                                       # "swings in price"
    "Were Alphabet's swings in shares large?",                                  # "swings in shares"
])
def test_a_companys_swings_are_a_price_question(question):
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "What are the swings in Apple's revenue?",                                  # not a possessive company before "swings"
    "How big were Apple's swings in operating expenses?",                       # "swings in" something that is not the stock
    "Did Tesla's swings in sentiment ease?",
    "Why does AMD talk about swings in demand?",
    "What does Nvidia say about swings in its supply chain?",
    "How big were the department's swings last quarter?",                       # a lowercase noun before 's is not a company
])
def test_swings_of_something_else_are_not_a_price_question(question):
    assert not detect_intent(question).prices, question


# ---- more verbs for the company speaking ----


@pytest.mark.parametrize("question, verb", [
    ("Did Marketco warn that cloud prices were falling?", "warn"),
    ("Marketco warns that prices are falling.", "warns"),
    ("Marketco warned that prices were falling.", "warned"),
    ("Marketco cautions that prices are falling.", "cautions"),
    ("Has Marketco cautioned about rising prices?", "cautioned"),
    ("Does Marketco admit falling demand?", "admit"),
    ("Marketco admits falling demand.", "admits"),
    ("What did Marketco admit about falling margins?", "admit (past, with 'did')"),
    ("Marketco admitted falling demand.", "admitted"),
    ("Marketco acknowledges falling demand.", "acknowledges"),
    ("Marketco acknowledged falling demand.", "acknowledged"),
    ("Does Marketco acknowledge falling demand?", "acknowledge"),
    ("Did Marketco concede that demand was dropping?", "concede"),
    ("Marketco concedes demand is dropping.", "concedes"),
    ("Marketco conceded demand was dropping.", "conceded"),
    ("Has Marketco signaled a slump in demand?", "signaled"),
    ("Has Marketco signalled a slump in demand?", "signalled"),
    ("Marketco signals a slump in demand.", "signals"),
    ("Does Marketco signal a slump in demand?", "signal"),
    ("Marketco indicates demand is slumping.", "indicates"),
    ("Marketco indicated demand was slumping.", "indicated"),
    ("Does Marketco indicate a slump in demand?", "indicate"),
    ("Marketco flags a slump in demand.", "flags"),
    ("Marketco flagged a slump in demand.", "flagged"),
    ("Does Marketco flag a slump in demand?", "flag"),
    ("Marketco notes a slump in demand.", "notes"),
    ("Marketco noted a slump in demand.", "noted"),
    ("Does Marketco note a slump in demand?", "note"),
    ("Does Marketco talk about falling demand?", "talk"),
    ("Marketco talks about falling demand.", "talks"),
    ("Marketco talked about falling demand.", "talked"),
    ("Did Marketco tell investors demand was falling?", "tell"),
    ("Marketco tells investors demand is falling.", "tells"),
    ("Marketco told investors demand was falling.", "told"),
])
def test_more_speaker_verbs_make_the_company_the_speaker(conn, question, verb):
    assert company_is_speaking(conn, question), verb


@pytest.mark.parametrize("question", [
    "Did analysts warn that Marketco's stock was falling?",                     # the analysts speak
    "Did Marketco stock fall after the warning?",                               # a noun, not a verb of the company
    "Marketco's notes payable fell, why?",                                      # "'s notes" is a noun after the possessive
    "Is the Marketco signal bullish?",                                          # a noun between the name and nothing else
    "Did the Marketco flag fall at half mast?",                                 # a noun
    "Why did Marketco shares fall after investors were told demand was weak?",  # "told" belongs to someone else
])
def test_these_are_not_the_company_speaking(conn, question):
    assert not company_is_speaking(conn, question), question


def kinds(question, conn):
    ans = answer_question(conn, FakeEmbedder(), RouterLLM(answer="Marketco faces supply risk [1]."), question, expand=False, router=False)
    return {getattr(r, "kind", "filing") for r in ans.retrieved}


def test_a_company_warning_about_falling_prices_goes_to_the_filings_not_the_stock(conn):
    assert kinds("Did Marketco warn that cloud prices were falling?", conn) == {"filing"}


def test_a_warning_by_analysts_about_the_stock_still_goes_to_the_prices(conn):
    assert "price" in kinds("Did analysts warn that Marketco's stock was falling?", conn)
