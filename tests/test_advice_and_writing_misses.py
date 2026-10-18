"""Two confident wrong answers from the third sealed round (DECISIONS: "Advice and writing misses").

"My cousin says to go all in on AMD. Should I?" got no "I can't tell you whether to buy, sell, or hold" notice, and "Put together a
short LinkedIn update on Amazon's quarter." was answered (with the router off the model invented a Q2 2024 post) instead of declined.
Every alternative in a new pattern has a question of its own, and so does every guard. The questions are new wordings (none is an
evaluation case); the evaluation cases for this fix are `ROUND_AW`.
"""
import pytest

from ai.market import asks_for_advice, detect_intent, writing_request


# ---- advice: the reader's own all-in decision ----
# Each question is flagged by ONE alternative and no other rule (no bare "Should I?" ending, no second trade word), so breaking
# that alternative on purpose fails exactly its question.


@pytest.mark.parametrize("question", [
    "My cousin says to go all in on AMD. Should I?",                       # the sealed miss
    "Is it wise to go all in with Apple?",                                 # "go all in" (not followed by "on")
    "Would you keep going all in with Tesla?",                             # "going all in"
    "Is it smart to be all in with Apple?",                                # "be all in"
    "Is it smart to keep being all in with Nvidia?",                       # "being all in"
    "I'm all in on Nvidia lately. Is that wise?",                          # "all in on"
    "Thinking of going all-in with Nvidia. Good call?",                    # "all-in" with a hyphen
    "Is it wise to bet big on Amazon?",                                    # "bet big"
    "Is it wise to bet heavy on Tesla?",                                       # "bet heavy"
    "Is it wise to bet heavily on Nvidia?",                               # "bet heavily"
    "Is it wise to bet everything on Microsoft?",                              # "bet everything"
    "Is it wise to bet it all on Alphabet?",                               # "bet it all"
    "Is it wise to bet the farm on AMD?",                                  # "bet the farm"
    "Is it wise to bet the house on Tesla?",                               # "bet the house"
    "Is it time to go big on Nvidia?",                                     # "go big on"
    "Is it wise to go heavy on Alphabet?",                                 # "go heavy on"
    "Is it wise to put everything into Microsoft?",                        # "put everything into"
    "Is it wise to put everything in Apple?",                              # "put everything in"
    "Is it wise to put everything on Amazon?",                             # "put everything on"
    "Is it time to pull the trigger on AMD?",                              # "pull the trigger"
    "Would you back up the truck on Tesla?",                               # "back up the truck"
    "Is it wise to throw money at Nvidia?",                                # "throw money at"
])
def test_all_in_wordings_are_requests_for_a_recommendation(question):
    assert asks_for_advice(question), question
    assert detect_intent(question).advice, question


# ---- advice: "Should I?" with the trade left unsaid ----


@pytest.mark.parametrize("question", [
    "Should I?",                                                            # bare, at the end
    "My brother loves Tesla stock. Should I?",
    "Everyone is talking about AMD. Should we?",                            # "we"
    "Nvidia looks strong lately... should I!",                              # ends in "!"
    "My boss mentioned Tesla. Should I do it?",                             # "do it"
    "A guy at work says Tesla is the one. Should I go for it?",             # "go for it"
    "Everybody keeps mentioning Microsoft. Should I join?",                 # "join" at the end
    "Everybody keeps mentioning Microsoft. Should I join in?",              # "join in"
    "My cousin loves AMD. Should I join them?",                             # "join them"
    "My uncle loves Apple. Should I join him?",                             # "join him"
    "My aunt loves Amazon. Should I join her?",                             # "join her"
    "Should I take the plunge on Nvidia?",                                  # "take the plunge"
    "Should I take the leap with Alphabet?",                                # "take the leap"
    "My neighbor swears by Apple. Should I take the bet?",                  # "take the bet"
    "Should I follow my brother's advice on Microsoft?",                    # "follow ... advice"
    "Should I trust my friend's tip about Tesla?",                          # "trust ... tip"
    "Should I take his recommendation on AMD?",                             # "take ... recommendation"
    "Should I listen to my broker's suggestion about Nvidia?",              # "listen to ... suggestion"
    "Should I heed her hunch about Amazon?",                                # "heed ... hunch"
    "A coworker is pushing Alphabet. Should I listen?",                     # "listen" at the end
    "My dad swears by Tesla. Should I listen to him?",                      # "listen to him"
    "My mom swears by Apple. Should I listen to her?",                      # "listen to her"
    "Some analysts swear by AMD. Should I listen to them?",                 # "listen to them"
    "A tip about Nvidia came in. Should I listen to it?",                   # "listen to it"
    "People keep saying that about Amazon. Should I listen to that?",       # "listen to that"
])
def test_a_bare_should_i_is_a_request_for_a_recommendation(question):
    assert asks_for_advice(question), question
    assert detect_intent(question).advice, question


# ---- advice: what must stay research (the company's own "all in", and "should I" about learning something) ----


@pytest.mark.parametrize("question", [
    "What does Tesla say about going all in on autonomy?",                  # the company's own decision
    "Is Microsoft going all in on AI, according to its 10-K?",
    "Does Amazon describe being all in on logistics?",
    "How big a bet is Alphabet making on cloud, per the 10-K?",             # no "bet big"
    "Did Nvidia put everything into data centers, according to its filing?",
    "What did AMD pull the trigger on last quarter?",                       # no cue
    "Should I know about Tesla's recall before reading the filing?",        # "should i" mid-question, not a decision
    "What should I look for in Apple's risk factors?",
    "Which filing should I read first for Microsoft?",
    "Should I listen to the Nvidia earnings call for the guidance numbers?",   # "listen to" an earnings call
    "How should I read Amazon's segment table?",
    "What did the heed-the-warning section of Tesla's 10-K say?",
    "Who follows Apple's advice program, according to the 10-K?",
    "Did Alphabet take the recommendation of its audit committee?",
])
def test_company_all_in_and_reading_questions_get_no_advice_notice(question):
    assert not asks_for_advice(question), question


# ---- writing: the things the first rule did not know ----


@pytest.mark.parametrize("question", [
    "Put together a short LinkedIn update on Amazon's quarter.",            # the sealed miss
    "Compose a short Facebook update about Apple's quarter.",               # another platform
    "Write an Instagram update about Tesla.",
    "Draft a Twitter update on Nvidia.",
    "Write a Reddit update about AMD.",
    "Make a blog update on Microsoft.",
    "Draft a social media update for Alphabet.",
    "Write a status update for my boss on Amazon's quarter.",               # "status update"
    "Prepare a team update on Microsoft's results.",                        # "team update"
    "Put together a weekly update about Tesla.",                            # "weekly update"
    "Write a monthly update on Nvidia for my manager.",
    "Draft a progress update about AMD.",
    "Write a blurb for my newsletter on AMD's chips.",                      # "blurb"
    "Come up with a catchy slogan for Tesla.",                              # "slogan"
    "Create a tagline for Apple.",                                          # "tagline"
    "Write a jingle about Amazon.",                                         # "jingle"
    "Write a bio for me.",                                                  # "bio"
    "Put together a brief announcement for my team about Microsoft's results.",     # "announcement for my"
    "Draft an announcement to our staff about the Nvidia numbers.",         # "announcement to our"
    "Give me a short LinkedIn update on Apple.",                            # "give me a"
])
def test_more_things_to_write_are_declined(question):
    assert writing_request(question), question


@pytest.mark.parametrize("question", [
    "Does Microsoft's 10-K include an update on its LinkedIn business?",   # no writing verb
    "What did Apple announce in its latest quarterly update?",
    "Did Apple make an announcement about its dividend?",                  # "make an announcement", the company's
    "What was in Tesla's last status update to investors?",
    "Write a summary of Microsoft's LinkedIn update.",                     # "of" blocks the thing
    "Summarize Amazon's team updates in three bullets.",
    "Create a table of Nvidia's weekly updates.",                          # "of"
    "What slogan does Tesla use, according to its filing?",
    "Which companies mention a tagline in their filings?",
    "Show me the announcement Alphabet made about its buyback.",           # "the", not a/an/some
    "Is there a blurb about AMD in the 10-K?",
    "What does Apple's bio of its CEO say?",
    "Pull up the Facebook update from Meta's press coverage of Apple.",
    "Give me a summary of the LinkedIn business.",
    # "give / get / show me" with these words asks for information, not for something to be written (only a platform post or
    # update is a writing request in that form: "Give me a short LinkedIn update on Apple.")
    "Give me a status update on Tesla's recall.", "Get me a weekly update on Nvidia's stock.",
    "Give me a progress update on Microsoft's lawsuit.", "Give me a bio of Tesla's CEO.", "Show me a blurb about AMD from the 10-K.",
    "Give me a monthly update on Amazon's shipping costs.", "Get me a team update on Alphabet's reorganization.",
    "Show me a slogan Tesla has used.", "Give me a tagline from Apple's filing.", "Show me an announcement for our investors from Nvidia.",
])
def test_research_questions_with_these_words_are_not_writing_requests(question):
    assert not writing_request(question), question
