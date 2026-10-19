"""Wrong answers found by the fourth sealed round (DECISIONS: "Fourth-round misses").

"How much of every sales dollar does Apple keep after paying for production?" went to the filings and said 15%; "What did Tesla clear
after all expenses?" was answered with operating income; "Anything interesting come out about Nvidia this morning?" went to the
filings and said there are no headlines; "What price did Alphabet end at on Thursday?" was told the days cannot be isolated; "Where
will Apple's stock be next March?" reached no prices and quoted a year-old filing price; and "Everyone says I'm crazy not to own
Nvidia. Am I?" got no buy/sell/hold notice. Every alternative and every guard has a question of its own, and the questions are new
wordings (none is an evaluation case; those are `ROUND_FR`). Nothing here calls a model.
"""
from datetime import date

import pytest

from ai.market import asks_for_advice, detect_intent, evidence_from_fundamentals, parse_window, price_evidence, PRICE_PREDICTION_RE
from test_copilot_fundamentals import figures
from test_market import A, TODAY, conn  # noqa: F401  (conn is a fixture)

# TODAY is Monday 2026-10-12; the fixture company has a close every day, 100 + the day's index, so the close on day D is 499 - (TODAY - D)


def topics(q):
    return detect_intent(q).fundamentals


# ---- what is left of a sales dollar ----


@pytest.mark.parametrize("question", [
    "How much of every sales dollar does Apple keep after paying for production?",   # the sealed miss
    "Of every dollar Amazon brings in, how many cents are left after all its costs?",
    "Out of each dollar of revenue, how much does Nvidia hold on to once everything is paid?",   # hold on to
    "For each dollar Microsoft sells, how much does it hold onto after costs?",        # hold onto
    "Of every revenue dollar, how much does Tesla hold on to?",                        # "revenue dollar"; holds
    "Of every dollar, how much does Alphabet keep?",                                   # keep
    "Of every dollar, how much does Apple keeps?",                                     # keeps (ungrammatical on purpose)
    "Of every dollar of sales, how much was kept by AMD?",                             # kept
    "Of each dollar, how much remains with Amazon after the cost of goods?",           # remains
    "Of each dollar, how much remain with Amazon?",                                    # remain
    "Of every dollar, how much is remaining for Microsoft?",                           # remaining
    "Of every dollar, how much does Nvidia retain?",                                   # retain
    "Of every dollar, how much does Tesla retains?",                                   # retains
    "Of every dollar, how much did Apple retained?",                                   # retained
    "Of every dollar Alphabet earns, how many cents does it pocket?",                  # pocket
    "Of every dollar, how much does Amazon pockets?",                                  # pockets
    "Of every dollar, how much did AMD pocketed?",                                     # pocketed
    "For every sales dollar Microsoft takes, how many cents stay after the cost of making its products?",   # stay
    "For every dollar, how many cents stays with Nvidia?",                             # stays
    "Of every dollar, how much is left for Tesla?",                                    # left
])
def test_what_a_company_keeps_of_each_dollar_is_a_margin_question(question):
    assert "margin" in topics(question), question


@pytest.mark.parametrize("question", [
    "How many dollars of every contract does Apple keep in escrow?",       # "dollars", not "dollar"
    "Which dollar figures does Microsoft keep in its filings?",             # no "every / each dollar"
    "Of every risk factor Amazon lists, how many mention China?",           # no dollar
    "Is every dollar Tesla spends on research in the 10-K?",                # "every dollar" but no keeping word
])
def test_a_dollar_without_a_keeping_word_is_not_a_margin_question(question):
    assert "margin" not in topics(question), question


# ---- what a company clears after its costs ----


@pytest.mark.parametrize("question", [
    "What did Alphabet pocket after expenses and taxes last year?",
    "What did Tesla clear after all expenses over the past year?",                      # the sealed miss: clear
    "What does Nvidia clears after all its costs?",                                     # clears
    "What has Amazon cleared after taxes?",                                             # cleared
    "How much did Microsoft net after everything?",                                     # net
    "How much does Apple nets after all costs?",                                        # nets
    "How much AMD netted after all expenses?",                                          # netted
    "How much does Alphabet pockets after taxes?",                                      # pockets
    "How much Tesla pocketed after costs?",                                             # pocketed
    "What does Amazon take home after expenses?",                                       # take home
    "Amazon takes home what after expenses?",                                           # takes home
    "What did Nvidia take home after the taxes?",                                       # "the"
    "What did Microsoft take home after its taxes?",                                    # "its"
    "What did Apple take home after their costs?",                                      # "their"
    "How much did AMD took home after everything?",                                     # took home
])
def test_what_a_company_clears_after_costs_is_a_profit_question(question):
    assert "profit" in topics(question), question


@pytest.mark.parametrize("question", [
    "What did Amazon clear after the acquisition closed?",                  # "after" but not costs
    "How did Nvidia net out its hedges in the filing?",                     # no "after expenses / costs / taxes"
    "Did Tesla clear regulatory review after the recall?",                  # clear, but no costs after it
    "Which filing says Apple takes home appliances back after repair?",     # "takes home", then not costs
])
def test_clearing_something_else_is_not_a_profit_question(question):
    assert "profit" not in topics(question), question


# ---- part of the day, and "come out about" ----


@pytest.mark.parametrize("question", [
    "Did anything come out about Tesla overnight?",                         # overnight
    "Tell me about Tesla overnight.",                                       # overnight alone
    "What's been said about Apple this afternoon?",                         # this afternoon
    "Anything interesting come out about Nvidia this morning?",             # the sealed miss: this morning + come out
    "Tell me about Nvidia this morning.",                                   # this morning alone
    "What is the talk around Microsoft this evening?",                      # this evening
    "Tell me about AMD tonight.",                                           # tonight
    "Tell me about Amazon first thing this morning.",                       # first thing this morning
    "Tell me about AMD first thing today.",                                 # first thing today
    "Has anything come out about Alphabet?",                                # come out about (no part of the day)
    "What comes out about Apple?",                                          # comes out
    "What came out on Tesla?",                                              # came out on
    "What has been coming out from Nvidia?",                                # coming out from
    "Has anything come out for Apple?",                                     # come out for
])
def test_a_part_of_the_day_or_coming_out_is_a_news_question(question):
    assert detect_intent(question).headlines, question


@pytest.mark.parametrize("question", [
    "Where did Nvidia trade this morning?",                                 # a price question with a part of the day
    "What was Microsoft's closing price this afternoon?",
    "What is Apple's P/E ratio this morning?",                              # a figures question
    "Where did AMD settle yesterday?",                                      # a price question, no part of the day
    "What does Tesla's 10-K say about how its vehicles come out of the factory?",   # "come out of" is not "come out about"
])
def test_a_part_of_the_day_does_not_turn_a_price_or_figures_question_into_news(question):
    assert not detect_intent(question).headlines, question


@pytest.mark.parametrize("question", [
    "Where did Nvidia trade this morning?",
    "Where did Nvidia trade yesterday?",
    "Where did AMD settle on Monday?",
    "Where did Apple finish last Friday?",
    "Where did Amazon open today?",
    "Where did Tesla end this week?",
    "Where did Microsoft close on Tuesday?",
    "Where did Microsoft close this morning?",                              # close, with a part of the day the older rule did not know
    "Where did Apple finish this afternoon?",                               # this afternoon
    "Where did Apple open overnight?",                                      # overnight
    "Where did Amazon end up today?",                                       # "end up" for the stock
    "Where did Microsoft close down yesterday?",                            # "close down" for the stock
])
def test_where_did_a_company_trade_on_a_day_is_a_price_question(question):
    assert detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Where did Tesla settle its lawsuit on Monday?",                        # settle + "its"
    "Where did Apple open the new store yesterday?",                        # open + "the"
    "Where did Nvidia finish the chip run this week?",                      # finish + "the"
    "Where did Tesla settle their dispute on Monday?",                      # settle + "their"
    "Where did Apple open a store yesterday?",                              # open + "a"
    "Where did Amazon open an office today?",                               # open + "an"
    "Where did Nvidia finish with the project this week?",                  # finish + "with"
    "Where did AMD start building this morning?",                           # a verb not in the list
])
def test_where_did_a_company_do_something_else_is_not_a_price_question(question):
    assert not detect_intent(question).prices, question


# ---- the close on one named weekday ----


@pytest.mark.parametrize("question, day", [
    ("What was Microsoft's closing price last Wednesday?", date(2026, 10, 7)),
    ("How did Amazon close on Tuesday?", date(2026, 10, 6)),
    ("What price did Alphabet end at on Thursday?", date(2026, 10, 8)),
    ("Where did AMD settle on Friday?", date(2026, 10, 9)),
    ("What was Apple's close on Saturday?", date(2026, 10, 10)),
    ("What was Tesla's close on Sunday?", date(2026, 10, 11)),
    ("How did Nvidia close on Monday?", date(2026, 10, 5)),                  # today is a Monday: a week ago, not today
    ("What was Microsoft's close last Tuesday?", date(2026, 10, 6)),
    ("What was Amazon's Wednesday close?", None),                             # no "on / last": not read (flagged by nothing, uses the default)
    ("What was Tesla's Thursday's close?", date(2026, 10, 8)),                # Thursday's close
    ("What was Apple's Friday's closing price?", date(2026, 10, 9)),          # Friday's closing
])
def test_a_named_weekday_is_read_as_the_most_recent_such_day_before_today(question, day):
    w = parse_window(question, TODAY)
    assert w.day == day, question
    if day:
        assert w.unmet is None, question          # it is read, so it is no longer reported as a period the prices cannot isolate


def test_since_last_monday_is_still_not_read_as_one_day():
    w = parse_window("How has Nvidia done since last Monday?", TODAY)
    assert w.day is None and w.unmet == "last Monday"


def test_another_unmet_period_is_kept_when_a_weekday_is_also_read():
    w = parse_window("What was the close on Thursday, and the end of last quarter?", TODAY)
    assert w.day == date(2026, 10, 8) and w.unmet is not None


def test_the_price_source_gives_the_close_on_that_day(conn):
    w = parse_window("What was Microsoft's closing price last Wednesday?", TODAY)
    ev = price_evidence(conn, A, w, TODAY)
    assert "Close on Wednesday 2026-10-07: 494.00." in ev.text
    assert "do not isolate" not in ev.text            # it is isolated now
    # and what that day did, against the close before it (so "did it go lower on Monday?" can be answered from the source)
    assert "Close before that, 2026-10-06: 493.00. Change on that day: +1.00 (+0.20%), a rise." in ev.text


def test_a_day_that_fell_says_a_fall_and_the_day_before_it_is_the_previous_stored_close(conn):
    conn.execute("UPDATE prices_daily SET close = 480 WHERE symbol = %s AND ts = %s", (A, date(2026, 10, 8)))   # Thursday
    conn.execute("DELETE FROM prices_daily WHERE symbol = %s AND ts = %s", (A, date(2026, 10, 7)))             # no Wednesday close
    conn.commit()
    ev = price_evidence(conn, A, parse_window("Did Alphabet shares go lower on Thursday?", TODAY), TODAY)
    assert "Close on Thursday 2026-10-08: 480.00." in ev.text
    assert "Close before that, 2026-10-06: 493.00. Change on that day: -13.00 (-2.64%), a fall." in ev.text      # skips the missing day


def test_the_close_on_a_day_with_no_stored_price_says_so(conn):
    conn.execute("DELETE FROM prices_daily WHERE symbol = %s AND ts = %s", (A, date(2026, 10, 7)))
    conn.commit()
    w = parse_window("What was Microsoft's closing price last Wednesday?", TODAY)
    ev = price_evidence(conn, A, w, TODAY)
    assert "No close is stored for Wednesday 2026-10-07" in ev.text and "Close on Wednesday" not in ev.text
    assert "Change on that day" not in ev.text


def test_a_question_with_no_named_day_gets_no_day_line(conn):
    ev = price_evidence(conn, A, parse_window("How has ZZMA stock done this month?", TODAY), TODAY)
    assert "Close on " not in ev.text.replace("Close on 2026", "")      # only the window's own "Close on <start date>" line remains
    assert parse_window("How has ZZMA stock done this month?", TODAY).day is None


# ---- where a stock will be ----


@pytest.mark.parametrize("question", [
    "Can you tell me where Apple's stock will be next March?",              # the sealed miss: stock ... will be
    "Where do you see Nvidia's shares being in the spring?",                # where do you see
    "Where will Tesla's stock be in January?",                              # where will
    "Where might Alphabet's share price end the year?",                     # where might
    "Where might Tesla's price be by June?",                                # where ... price (no stock or share word)
    "Where would Amazon's shares trade by summer?",                         # where would
    "Where could Microsoft's stock be by June?",                            # where could
    "Where do you think AMD's shares are headed?",                          # where do you think
    "Where do you expect Apple's stock to be?",                             # where do you expect
    "Apple's stock will be around 400 by June, won't it?",                  # stock will be
    "Tesla's share price would end the year higher, wouldn't it?",          # price would end
    "Apple's price will end near 400.",                                     # will ... price alone
    "Nvidia's shares will trade lower, right?",                             # will trade
    "AMD's stock could close at 600 by Friday.",                            # could close
    "Amazon's shares might stand at 300 soon.",                             # might stand
    "Alphabet's stock will sit near 350.",                                  # will sit
])
def test_where_a_stock_will_be_is_a_prediction_about_the_prices(question):
    assert PRICE_PREDICTION_RE.search(question) and detect_intent(question).prices, question


@pytest.mark.parametrize("question", [
    "Where will Tesla build its next plant?",                               # no stock word
    "What will Apple's stock-based compensation be next year?",             # "stock-based"
    "Where do you see Apple's supply chain going?",                         # where, but no stock word
    "Will Tesla deliver more cars in January?",                             # will, but no stock word
    "What will be Amazon's share count?",                                   # "will be" comes before the share word
    "Which stock exchange will Spotify list on?",                           # a stock word but not "stock will be"
    "Where will Apple's stock-based compensation be next year?",            # where will ... stock-based (the hyphen guard)
    "Apple's stock-based compensation will be higher next year, right?",   # stock-based ... will be (the hyphen guard)
])
def test_other_questions_about_the_future_are_not_price_predictions(question):
    assert not PRICE_PREDICTION_RE.search(question), question


# ---- advice: "crazy not to own", and a bare question at the end ----


@pytest.mark.parametrize("adjective", ["crazy", "mad", "foolish", "stupid", "dumb", "nuts", "silly", "insane", "wrong"])
def test_each_adjective_before_not_to_own_is_a_request_for_a_recommendation(adjective):
    q = f"Folks say it would be {adjective} not to own Nvidia."
    assert asks_for_advice(q), q


@pytest.mark.parametrize("verb", ["own", "buy", "hold", "invest in", "have", "keep", "get", "pick up"])
def test_each_verb_after_not_to_is_a_request_for_a_recommendation(verb):
    q = f"Folks say it is crazy not to {verb} Tesla."
    assert asks_for_advice(q), q


@pytest.mark.parametrize("question", [
    "Everyone says I'm crazy not to own Nvidia. Am I?",                     # the sealed miss
    "Friends keep saying I should own AMD. Do I?",                          # do I
    "They all say Nvidia is the one. Shall we?",                            # shall we
    "Everyone says Alphabet is the one. Ought I?",                          # ought I
    "Everyone says I must buy Amazon. Must I?",                             # must I
    "A coworker thinks we are safe in Microsoft. Are we?",                  # are we
    "They say Alphabet is the one. Do we?",                                 # do we
    "Am I?",                                                                # alone
])
def test_a_bare_am_i_do_i_at_the_end_is_a_request_for_a_recommendation(question):
    assert asks_for_advice(question), question


@pytest.mark.parametrize("question", [
    "Where do I find Apple's 10-K?",                                        # "do I" in the middle
    "Do I need an account to see Tesla's filings?",                         # a question that starts with it
    "Which sections should I read first to learn what I do?",               # ends with "do?" but not "do I?"
    "What does Nvidia say about what we do?",                               # "what we do?" is not "Do we?"
    "Tell me how Amazon works, and how do I?",                              # "how do I?" is not a bare "Do I?"
])
def test_do_i_inside_a_question_is_not_a_request_for_a_recommendation(question):
    assert not asks_for_advice(question), question


# ---- the figures source says what each profit figure means ----


def test_net_income_is_described_as_what_is_left_after_all_expenses():
    text = evidence_from_fundamentals(figures()).text
    net = next(line for line in text.split("\n") if line.startswith("Net income"))
    assert "after all expenses" in net and "interest and taxes" in net


def test_operating_income_is_described_as_before_interest_and_taxes():
    text = evidence_from_fundamentals(figures()).text
    op = next(line for line in text.split("\n") if line.startswith("Operating income"))
    assert "before interest and taxes" in op and "not what is left after all expenses" in op


def test_gross_margin_is_described_as_after_the_cost_of_making_the_products():
    text = evidence_from_fundamentals(figures()).text
    line = next(line for line in text.split("\n") if line.startswith("Gross margin"))
    assert "cost of making" in line


def test_operating_and_net_margin_are_described_too():
    text = evidence_from_fundamentals(figures()).text
    op = next(line for line in text.split("\n") if line.startswith("Operating margin"))
    net = next(line for line in text.split("\n") if line.startswith("Net margin"))
    assert "before interest and taxes" in op and "after all expenses" in net
