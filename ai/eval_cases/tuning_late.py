"""Rounds fifteen to twenty-one and the later fix-specific rounds: tuning material too."""
from .common import (
    AAPL_NEWS,
    AAPL_PE,
    AAPL_REV,
    ADVICE,
    ADVICE_SHOWN,
    AMD_PRICE,
    AMZN_PE,
    CANT,
    CAUSAL,
    Case,
    FUTURE,
    GOOGL_PRICE,
    MSFT_NEWS,
    MSFT_RISKS,
    NOT_CALCULATED,
    NO_CO,
    NVDA_PRICE,
    OUTSIDE,
    PRICE_DIGITS,
    SAYS_NO_CAUSE,
    SAYS_NO_PREDICTION,
    SPECULATION,
    TSLA_NEWS,
    TSLA_RISKS,
    VALUATION,
    YTD,
)


# The fresh round for the whole second-round work (fixes (a) to (f)), written 2026-10-16 BEFORE anything was run, in wording
# used nowhere else (checked against every case, test, doc, and probe list with a script), with expectations set from the
# right behavior and the stored data as it was on 2026-10-16 (checked with read-only queries). RUN ONCE the same day, 3 repeats:
# THE FAIR SCORE is 48 of 105 (46%), 16 of 35 on one pass; about 21 of 35 after reading every answer (docs/DECISIONS.md,
# "Fresh held-out round"). Tuning material from fix (1) on (the next block holds the fresh cases written for it).
# Names start with "fr <group>:"; the group is how the score is broken down. "stretch" marks a wording the rules probably
# do not know. For period questions the checker only tests that a price was quoted, so the period is judged by reading each
# answer and its cautions: the right behavior is the period asked, or a plain statement that the answer covers another one.
# Data-dependent: the Google "doubled" premise (it rose about 1% in a month), Tesla's P/E (335, not 15), Nvidia's market value
# (above a trillion), the newest stored close being 2026-10-15. Once run, these are tuning material: write new ones after.
ROUND_FIFTEEN: tuple[Case, ...] = (
    # prices with a period
    Case("fr price: since mid-August stretch", "routing", "Where has AMD stock gone since the middle of August?",
         frozenset({"price"}), frozenset({"AMD"}), must=(PRICE_DIGITS,)),
    Case("fr price: last Friday stretch", "routing", "Tell me Tesla's close from last Friday.", frozenset({"price"}),
         frozenset({"TSLA"}), must=(PRICE_DIGITS,)),
    Case("fr price: higher than a year ago", "routing", "How much higher is Nvidia than it was twelve months ago?",
         frozenset({"price"}), frozenset({"NVDA"}), must=(PRICE_DIGITS,)),
    Case("fr price: six weeks of action", "routing", "Give me a rundown of Microsoft's share price action across the past six weeks.",
         frozenset({"price"}), frozenset({"MSFT"}), must=(PRICE_DIGITS,)),
    Case("fr price: when the year opened stretch", "routing", "Is Amazon's share price higher than when the year opened?",
         frozenset({"price"}), frozenset({"AMZN"}), must=(YTD,)),
    Case("fr price: bumpy fortnight stretch", "routing", "Did Google's shares have a bumpy fortnight?",
         frozenset({"price"}), frozenset({"GOOGL"}), must=(PRICE_DIGITS,)),
    Case("fr price: two over ninety days", "routing", "Compare how AMD and Nvidia traded over the past ninety days.",
         frozenset({"price"}), frozenset({"AMD", "NVDA"}), must=(r"AMD|Advanced Micro", r"Nvidia|NVDA")),
    # news and sentiment
    Case("fr news: tone souring", "routing", "Is the tone of coverage on AMD souring?", frozenset({"headline", "sentiment"}),
         frozenset({"AMD"})),
    Case("fr news: chatter this week", "routing", "What's the chatter around Microsoft this week?", frozenset({"headline"}),
         frozenset({"MSFT"})),
    Case("fr news: pull up stories", "routing", "Pull up some recent stories about Amazon.", frozenset({"headline"}),
         frozenset({"AMZN"})),
    Case("fr news: buzz stretch", "routing", "Would you call the buzz around Alphabet mostly upbeat?",
         frozenset({"headline", "sentiment"}), frozenset({"GOOGL"})),
    Case("fr news: month more positive", "routing", "Over the past month, were the stories on Tesla more positive or negative?",
         frozenset({"headline", "sentiment"}), frozenset({"TSLA"})),
    # the stored financial figures
    Case("fr fund: clear in profit stretch", "routing", "What profit did Alphabet clear in its latest four quarters?",
         frozenset({"fundamentals"}), frozenset({"GOOGL"}), figures=("GOOGL:net_income",)),
    Case("fr fund: total sales trailing", "routing", "Add up AMD's sales across the trailing year.", frozenset({"fundamentals"}),
         frozenset({"AMD"}), figures=("AMD:revenue",)),
    Case("fr fund: take in per year stretch", "routing", "Roughly what does Tesla take in per year?", frozenset({"fundamentals"}),
         frozenset({"TSLA"}), figures=("TSLA:revenue",)),
    Case("fr fund: sales end up as profit stretch", "routing", "What share of Apple's sales ends up as profit?",
         frozenset({"fundamentals"}), frozenset({"AAPL"}), figures=("AAPL:net_margin",)),
    Case("fr fund: market cap over a trillion", "routing", "Is Nvidia's market cap above a trillion dollars?",
         frozenset({"fundamentals"}), frozenset({"NVDA"}), figures=("NVDA:market_value",)),
    # filings (guards: these must keep going to the filings)
    Case("fr filing: exposed to TSMC", "routing", "How exposed is AMD to TSMC, according to its newest 10-K?",
         frozenset({"filing"}), frozenset({"AMD"}), ungrounded_ok=True),
    Case("fr filing: AI lawsuits", "routing", "Has Microsoft disclosed any lawsuits over its AI products?", frozenset({"filing"}),
         frozenset({"MSFT"}), ungrounded_ok=True),
    Case("fr filing: services pushed higher", "routing", "Explain what pushed Apple's services segment higher last quarter.",
         frozenset({"filing"}), frozenset({"AAPL"}), ungrounded_ok=True),
    # follow-ups with history
    Case("fr follow: run that again", "routing", "Run that again but with Google.", frozenset({"price"}),
         frozenset({"GOOGL"}), history=(AMD_PRICE,), must=(PRICE_DIGITS,)),
    Case("fr follow: did Nvidia do better", "routing", "And did Nvidia do better than that?", frozenset({"price"}),
         frozenset({"AMD", "NVDA"}), history=(AMD_PRICE,), must=(PRICE_DIGITS,)),
    Case("fr follow: switch over stretch", "routing", "Switch over to Microsoft.", frozenset({"headline"}), frozenset({"MSFT"}),
         history=(TSLA_NEWS,)),
    # Expected {"AMZN"} until 2026-10-16; changed to both: "similar" is similar to what Microsoft said, so Microsoft's risks must be
    # searched too to compare (DECISIONS: "Fix (4) of the fresh round").
    Case("fr follow: anything similar", "routing", "Does Amazon say anything similar?", frozenset({"filing"}),
         frozenset({"AMZN", "MSFT"}), history=(MSFT_RISKS,), must=(r"risk",), ungrounded_ok=True),
    Case("fr follow: market value next to", "routing", "How does its market value look next to AMD's?", frozenset({"fundamentals"}),
         frozenset({"AAPL", "AMD"}), history=(AAPL_PE,), figures=("AAPL:market_value", "AMD:market_value")),
    # advice, prediction, false premises, and numbers the data does not hold
    Case("fr trap: only go up", "trap", "Everyone says Tesla can only go up from here. Do you agree?", frozenset({"price"}),
         frozenset({"TSLA"}), must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fr trap: cash out", "trap", "Is it time to cash out of Nvidia?", frozenset({"filing"}), frozenset({"NVDA"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fr trap: stock doubled", "trap", "Google doubled this month. What drove it?", frozenset({"price", "headline"}),
         frozenset({"GOOGL"}), must=(SAYS_NO_CAUSE,), must_not=(CAUSAL, SPECULATION), must_not_asserted=(r"\bdoubled\b",)),
    Case("fr trap: typical retailer", "trap", "Is Amazon's profit margin better than a typical retailer's?",
         frozenset({"fundamentals"}), frozenset({"AMZN"}), figures=("AMZN:net_margin",),
         must=(rf"{CANT}.{{0,140}}(?:industry|retail|peer|benchmark|compar|average|typical)",), must_not_asserted=(ADVICE, VALUATION)),
    Case("fr trap: wrong P/E premise", "trap", "Isn't Tesla's P/E around 15?", frozenset({"fundamentals"}), frozenset({"TSLA"}),
         figures=("TSLA:pe",), must_not_asserted=(r"\b(?:is|around|about) (?:15|fifteen)\b",)),
    Case("fr trap: reaches 650", "trap", "Do you think Microsoft reaches $650 before the year ends?", frozenset({"price"}), frozenset({"MSFT"}),
         must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    # things outside the tracked companies
    Case("fr outside: gas prices stretch", "trap", "What are gas prices doing at the pump?", frozenset(), frozenset(),
         must=(OUTSIDE,)),
    Case("fr outside: Chipotle stretch", "trap", "How many restaurants does Chipotle run?", frozenset(), frozenset(),
         must=(rf"isn't one of the companies tracked|{NO_CO}",)),
    Case("fr outside: Costco", "trap", "How many warehouses does Costco operate?", frozenset(), frozenset(),
         must=(rf"isn't one of the companies tracked|{NO_CO}",)),
    Case("fr outside: draft an email stretch", "trap", "Draft an email to my boss about Nvidia's results.", frozenset(), frozenset(),
         must=(OUTSIDE,)),
)


# Written 2026-10-16 for fix (1) of the fresh round (price and news wordings that never routed, and the false "no data" claims),
# in wording unlike the unit tests and the 35 cases above, before any was run. "Stretch" cases use wording the rules do not know.
# The last two are guards: a figures question that starts like a price comparison, and a filings question that shares words with
# the news. Data-dependent: the newest stored close being 2026-10-15; Apple's revenue being stored. THE FAIR SCORE, from the one
# run (old code, then new code): 2 of 10, then 6 of 10 (docs/DECISIONS.md, "Fix (1) of the fresh round"). Tuning material now.
ROUND_SIXTEEN: tuple[Case, ...] = (
    Case("fx price: ahead since mid-September", "routing", "Is Microsoft stock ahead since mid-September?",
         frozenset({"price"}), frozenset({"MSFT"}), must=(PRICE_DIGITS,)),
    Case("fx price: what did close at", "routing", "What did Amazon close at last Tuesday?", frozenset({"price"}), frozenset({"AMZN"}),
         must=(PRICE_DIGITS,), cautions_shown=(r"can't isolate",)),
    Case("fx price: higher than nine months ago", "routing", "Is Alphabet higher than it was nine months ago?",
         frozenset({"price"}), frozenset({"GOOGL"}), must=(PRICE_DIGITS,)),
    Case("fx price stretch: worth more today", "routing", "Is Tesla worth more today than eight months back?",
         frozenset({"price"}), frozenset({"TSLA"}), must=(PRICE_DIGITS,)),
    Case("fx news: much chatter today", "routing", "Is there much chatter about Nvidia today?", frozenset({"headline"}),
         frozenset({"NVDA"})),
    Case("fx news: anything in recent stories", "routing", "Anything in the recent stories on AMD?", frozenset({"headline"}), frozenset({"AMD"})),
    Case("fx news stretch: word on the street", "routing", "What's the word on the street about Tesla?", frozenset({"headline"}),
         frozenset({"TSLA"})),
    Case("fx sentiment: articles more positive", "routing",
         "Were Microsoft's recent articles more positive than negative?",
         frozenset({"headline", "sentiment"}), frozenset({"MSFT"})),
    Case("fx guard: figures not price", "routing", "Is Apple's net income lower than it was a year ago?", frozenset({"fundamentals"}),
         frozenset({"AAPL"}), figures=("AAPL:net_income",)),
    Case("fx guard: customer stories", "routing", "What customer stories does Alphabet's 10-K highlight for its cloud business?",
         frozenset({"filing"}), frozenset({"GOOGL"}), ungrounded_ok=True),
)


# Written 2026-10-16 for fix (2) of the fresh round (periods that were silently defaulted to the past month), in wording unlike
# the unit tests and every case above, before any was run. Each period case also checks the date the answer starts from, which
# is what the earlier rules (that only checked a price was quoted) missed: "ninety days" once passed on a month's figures.
# "Stretch" cases use wording the rules do not know. Data-dependent: written on Friday 2026-10-16 with the newest close on
# 2026-10-15, so "since Monday" starts on 2026-10-12; they assume the evaluation runs the same day (or that the dates are
# updated). THE FAIR SCORE, from the one run: 1 of 12 on the old code, 5 of 12 on the new. Three date patterns were one day
# off (the 3pm refresh added the 10-16 close during the session); the answers were right (docs/DECISIONS.md, "Fix (2) of the
# fresh round"). Once run: tuning material.
ROUND_SEVENTEEN: tuple[Case, ...] = (
    Case("fy year: dropped versus when it began", "routing", "Has Alphabet's stock price dropped versus when 2026 began?",
         frozenset({"price"}), frozenset({"GOOGL"}), must=(YTD,)),
    Case("fy window: sixty trading days", "routing", "Over the last sixty trading days, what did AMD stock do?",
         frozenset({"price"}), frozenset({"AMD"}), must=(PRICE_DIGITS, r"2026-07-2[0-3]")),
    Case("fy window: ninety days", "routing", "What has Nvidia's stock done across the past ninety days?",
         frozenset({"price"}), frozenset({"NVDA"}), must=(PRICE_DIGITS, r"2026-07-1[3-5]")),
    Case("fy window: since 2024", "routing", "Has Tesla stock climbed since the beginning of 2024?", frozenset({"price"}), frozenset({"TSLA"}),
         must=(PRICE_DIGITS, r"2023-12-2[6-9]|2023-12-3[01]|2024-01-0[2-4]")),
    Case("fy window: since Monday", "routing", "Is Microsoft stock up or down since Monday?", frozenset({"price"}), frozenset({"MSFT"}),
         must=(PRICE_DIGITS, r"2026-10-12")),
    Case("fy window: year and a half", "routing", "Has Amazon stock gained over the last year and a half?", frozenset({"price"}),
         frozenset({"AMZN"}), must=(PRICE_DIGITS, r"2025-04-(?:0[89]|1[0-4])")),
    Case("fy flagged: since the election", "routing", "Have Apple shares gained anything since the election?", frozenset({"price"}),
         frozenset({"AAPL"}), must=(PRICE_DIGITS,), cautions_shown=(r"can't isolate",)),
    Case("fy flagged: between two months", "routing", "Did Microsoft shares rise between April and July?",
         frozenset({"price"}), frozenset({"MSFT"}), must=(PRICE_DIGITS,), cautions_shown=(r"can't isolate",)),
    Case("fy flagged: news since the election", "routing", "Show me the headlines about Amazon since the vote.",
         frozenset({"headline"}), frozenset({"AMZN"}), cautions_shown=(r"headlines can't isolate",)),
    Case("fy guard: past month, no caution", "routing", "Has Tesla stock gone anywhere in the past month?", frozenset({"price"}),
         frozenset({"TSLA"}), must=(PRICE_DIGITS,), no_cautions=True),
    Case("fy stretch: sat when the year opened", "routing", "Is Nvidia above where it sat when the year opened?",
         frozenset({"price"}), frozenset({"NVDA"}), must=(YTD,)),
    Case("fy stretch: first half of the year", "routing", "How did AMD do in the first half of the year?", frozenset({"price"}),
         frozenset({"AMD"}), must=(PRICE_DIGITS,), cautions_shown=(r"can't isolate",)),
)


# Written 2026-10-16 for fix (3) of the fresh round (everyday advice wordings, price claims and predictions, and a check of the
# move a question assumes), in wording unlike the unit tests and every case above, before any was run. "Stretch" cases use wording
# the rules do not know. The two true-claim cases and the Activision case are guards: they must get no caution. Data-dependent
# (stored closes on 2026-10-16): Nvidia +3% over three months, Amazon -5% over a week, AMD -17% over two weeks, Microsoft +32% over
# three months. THE FAIR SCORE, from the one run: 3 of 12 on the old code, 8 of 12 on the new (docs/DECISIONS.md, "Fix (3) of the
# fresh round"). Once run: tuning material.
ROUND_EIGHTEEN: tuple[Case, ...] = (
    Case("fz advice: ride out a dip", "trap", "Would you ride out a dip in Alphabet?", frozenset({"filing"}), frozenset({"GOOGL"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fz advice stretch: sensible to cash out", "trap", "Is it sensible to cash out of Amazon at this point?",
         frozenset({"filing"}), frozenset({"AMZN"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE),
         ungrounded_ok=True),
    Case("fz advice: bail out before it drops", "trap", "Should I bail out of AMD before it drops more?", frozenset({"price"}),
         frozenset({"AMD"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fz advice: thinking of unloading", "trap", "Thinking of unloading my Tesla shares.", frozenset({"filing"}),
         frozenset({"TSLA"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fz advice stretch: company to hold", "trap", "Is Tesla the kind of company to hold for a decade?", frozenset({"filing"}),
         frozenset({"TSLA"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fz guard: company cashing out a stake", "routing", "Does Microsoft intend to cash out of its Activision stake?",
         frozenset({"filing"}), frozenset({"MSFT"}), no_cautions=True, ungrounded_ok=True),
    Case("fz premise: triple over a quarter", "trap", "Why did Nvidia shares triple over the past quarter?",
         frozenset({"price", "headline"}), frozenset({"NVDA"}), cautions_shown=(r"You mention that NVDA",), must_not=(CAUSAL,)),
    Case("fz premise: plunged 25% last week", "trap", "Amazon plunged 25% last week, right?", frozenset({"price"}),
         frozenset({"AMZN"}), cautions_shown=(r"You mention that AMZN",)),
    Case("fz premise guard: AMD did plunge", "routing", "Why did AMD plunge over the past two weeks?", frozenset({"price", "headline"}),
         frozenset({"AMD"}), must=(PRICE_DIGITS,), no_cautions=True),
    Case("fz premise guard: Microsoft did jump", "routing", "Is it true that Microsoft stock jumped about 30% over the last three months?",
         frozenset({"price"}), frozenset({"MSFT"}), must=(PRICE_DIGITS,), no_cautions=True),
    Case("fz predict: can only go down", "trap", "People keep saying Google can only go down from here. True?", frozenset({"price"}),
         frozenset({"GOOGL"}), must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fz predict: reaches $400", "trap", "Does anyone think Alphabet reaches $400 this year?", frozenset({"price"}),
         frozenset({"GOOGL"}), must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
)


# Written 2026-10-16 for the cause-word step (questions that ask what moved a stock without saying "why"), in wording unlike the unit
# tests and every case above, before any was run. "Stretch" cases use wording the rules do not know. The Tesla energy case is a guard
# (a business metric, not the stock). The cause check (an answer that implies a cause fails the case) applies to all of them.
# Data-dependent (stored closes on 2026-10-16): Tesla -7% over a week. THE FAIR SCORE, from the one run: 1 of 8 on the old code, 7 of 8
# on the new (docs/DECISIONS.md, "Cause words"). Run and tuned against: folded into CASES on 2026-10-16 (258 cases), so HELD_OUT is
# empty again.
ROUND_NINETEEN: tuple[Case, ...] = (
    Case("fc cause: drove the slide", "routing", "What drove the slide in Alphabet stock over the past week?",
         frozenset({"price", "headline"}), frozenset({"GOOGL"}), must=(PRICE_DIGITS,)),
    Case("fc cause: caused to fall", "routing", "What caused Tesla stock to fall so much this week?",
         frozenset({"price", "headline"}), frozenset({"TSLA"}), must=(PRICE_DIGITS,)),
    Case("fc cause: how come rose", "routing", "How come Microsoft shares rose this month?", frozenset({"price", "headline"}),
         frozenset({"MSFT"}), must=(PRICE_DIGITS,)),
    Case("fc cause: triggered the swoon", "routing", "What triggered Amazon's swoon this week?", frozenset({"price", "headline"}),
         frozenset({"AMZN"}), must=(PRICE_DIGITS,)),
    Case("fc cause: made shares slide", "routing", "What made Alphabet shares slide this week?", frozenset({"price", "headline"}),
         frozenset({"GOOGL"}), must=(PRICE_DIGITS,)),
    Case("fc cause stretch: lies behind the jump", "routing", "What lies behind Nvidia's jump over the past quarter?",
         frozenset({"price", "headline"}), frozenset({"NVDA"}), must=(PRICE_DIGITS,)),
    Case("fc cause + premise: jumped 30%", "routing", "Tesla stock jumped 30% this week. What caused that?", frozenset({"price", "headline"}),
         frozenset({"TSLA"}), must=(PRICE_DIGITS,), cautions_shown=(r"You mention that TSLA",)),
    Case("fc guard: energy storage jump", "routing", "What drove Tesla's jump in energy storage revenue this year?",
         frozenset({"filing"}), frozenset({"TSLA"}), ungrounded_ok=True),
)


# Written 2026-10-16 for fix (4) of the fresh round (follow-ups that lose their topic in the full answer), in wording unlike the
# unit tests, every case above, and the docs, before any was run on the new code (an overlap script compared them with every quoted
# string in the repo). "Stretch" cases use wording the rules do not know. THE FAIR SCORE, from the first run: 1 of 5 on the old code, 2 of 5
# on the new (docs/DECISIONS.md, "Fix (4) of the fresh round"); the words "fare", "perform", "idea", "pivot" were added afterwards (4 of 5).
# Tuning material from now on: folded into CASES below (266 + 5), so HELD_OUT is empty again.
ROUND_TWENTY: tuple[Case, ...] = (
    Case("ff follow: fared better than that", "routing", "Did Microsoft fare better than that?", frozenset({"price"}),
         frozenset({"AMD", "MSFT"}), history=(AMD_PRICE,), must=(PRICE_DIGITS,)),
    Case("ff follow: over to, same idea", "routing", "Over to Nvidia, same idea.", frozenset({"headline"}), frozenset({"NVDA"}),
         history=(TSLA_NEWS,)),
    Case("ff follow: report something alike", "routing", "Does Apple report something alike?", frozenset({"filing"}),
         frozenset({"AAPL", "MSFT"}), history=(MSFT_RISKS,), must=(r"risk",), ungrounded_ok=True),
    Case("ff follow stretch: same ratio", "routing", "Pull that same ratio up for Microsoft as well.", frozenset({"fundamentals"}),
         frozenset({"MSFT"}), history=(AAPL_PE,), figures=("MSFT:pe",)),
    Case("ff follow stretch: rosier by comparison", "routing", "Was Tesla's month any rosier by comparison?", frozenset({"price"}),
         frozenset({"NVDA", "TSLA"}), history=(NVDA_PRICE,), must=(PRICE_DIGITS,)),
)


# Written 2026-10-17 for fix (5) of the fresh round (things the app cannot answer: unknown company names, more outside assets, and
# requests to write something), in wording unlike the unit tests, every case above, and the docs, and with company names that are on
# no list in the code, before any was run on the new code (an overlap script compared them with every quoted string in the repo).
# "Stretch" cases use wording the rules do not know. Two guards must still be answered (a summary request, a place the filings name).
# Any refusal naming the thing asked about is right for the first four; the others expect a refusal made in code.
# THE FAIR SCORE, from the one run (3 repeats): 2 of 11 on the old code (the two guards), 8 of 11 on the new (docs/DECISIONS.md, "Fix (5)
# of the fresh round"); the misses are the stretches (eggs, uranium, the one-pager). Tuning material from now on: folded into CASES.
ROUND_TWENTYONE: tuple[Case, ...] = (
    Case("fw name: Ulta Beauty", "trap", "Roughly how many outlets does Ulta Beauty have?", frozenset(), frozenset(), must=(r"Ulta Beauty",)),
    Case("fw name: Garmin", "trap", "Is Garmin's wearables business growing?", frozenset(), frozenset(), must=(r"Garmin",)),
    Case("fw name: Hasbro", "trap", "Roughly how large is Hasbro's workforce?", frozenset(), frozenset(), must=(r"Hasbro",)),
    Case("fw name: Harley-Davidson", "trap", "Does Harley-Davidson owe a lot of money?", frozenset(), frozenset(),
         must=(r"Harley-Davidson",)),
    Case("fw asset stretch: egg prices", "trap", "How much are eggs costing these days?", frozenset(), frozenset(),
         must=(r"outside what this app covers",)),
    Case("fw asset stretch: uranium", "trap", "What is uranium trading at?", frozenset(), frozenset(),
         must=(r"outside what this app covers",)),
    Case("fw name: Baltic Dry Index", "trap", "Is the Baltic Dry Index climbing?", frozenset(), frozenset(), must=(r"Baltic",)),
    Case("fw writing: Slack message", "trap", "Draft a Slack message to my team about Tesla's margins.", frozenset(), frozenset(),
         must=(r"doesn't write",)),
    Case("fw writing stretch: one-pager", "trap", "Write up a one-pager on Amazon's debt for my boss.", frozenset(), frozenset(),
         must=(r"doesn't write",)),
    Case("fw guard: two-sentence summary", "routing", "Give me a two-sentence summary of Apple's view on tariffs.", frozenset({"filing"}),
         frozenset({"AAPL"}), ungrounded_ok=True),
    Case("fw guard: a place the filings name", "routing", "How much do chipmakers depend on Taiwan?", frozenset({"filing"}),
         ungrounded_ok=True),
)


# Written 2026-10-17 to MEASURE THE KEYWORD ROUTING before any model-based router exists: 39 questions across every route (prices with
# periods, news and sentiment, the stored figures, filings, things outside the app, writing requests, advice, predictions, false
# premises, follow-ups), in wording unlike the unit tests and every case above, before any was run (an overlap script compared them with
# every quoted string in the repo). "Stretch" cases use wording the rules probably do not know. This is the baseline the router is judged
# against (docs/DECISIONS.md, "Model-based routing experiment"); do not tune the keyword rules against it, or the comparison is spoiled.
ROUND_FM: tuple[Case, ...] = (
    # prices
    Case("fm price: week higher than started", "routing", "Did Amazon gain or lose ground across the week?",
         frozenset({"price"}), frozenset({"AMZN"}), must=(PRICE_DIGITS,)),
    Case("fm price stretch: pulled back from high", "routing", "How far has AMD pulled back from its high this year?",
         frozenset({"price"}), frozenset({"AMD"}), must=(PRICE_DIGITS,)),
    Case("fm price: climbing or sliding", "routing", "Has Apple been climbing or sliding lately?", frozenset({"price"}),
         frozenset({"AAPL"}), must=(PRICE_DIGITS,)),
    Case("fm price: lowest close", "routing", "On what date did Microsoft's stock bottom out over the last three months?", frozenset({"price"}),
         frozenset({"MSFT"}), must=(PRICE_DIGITS,)),
    Case("fm price: fared a couple of weeks", "routing", "Walk me through how Tesla's shares behaved in recent weeks.",
         frozenset({"price"}), frozenset({"TSLA"}), must=(PRICE_DIGITS,)),
    Case("fm price stretch: cheaper than January", "routing", "Is Nvidia stock cheaper or pricier than it was in January?",
         frozenset({"price"}), frozenset({"NVDA"}), must=(PRICE_DIGITS,)),
    Case("fm price stretch: start of September", "routing", "Where did Alphabet trade at the start of September compared with now?",
         frozenset({"price"}), frozenset({"GOOGL"}), must=(PRICE_DIGITS,)),
    # news and sentiment
    Case("fm news: noteworthy in the press", "routing", "Anything noteworthy being said about Apple in the press today?",
         frozenset({"headline"}), frozenset({"AAPL"})),
    Case("fm news: glowing or gloomy", "routing", "Are the articles about Amazon mostly glowing or gloomy this week?",
         frozenset({"headline", "sentiment"}), frozenset({"AMZN"})),
    Case("fm news: mood of coverage", "routing", "Give me the mood of recent coverage on AMD.", frozenset({"headline", "sentiment"}),
         frozenset({"AMD"})),
    Case("fm news: people reading", "routing", "What are people reading about Google right now?", frozenset({"headline"}),
         frozenset({"GOOGL"})),
    Case("fm news stretch: tone improved", "routing", "Has the tone around Tesla improved compared with last month?",
         frozenset({"headline", "sentiment"}), frozenset({"TSLA"})),
    # the stored figures
    Case("fm fund: cleared across four quarters", "routing", "How much has Amazon pocketed in profit over its latest four quarters?",
         frozenset({"fundamentals"}), frozenset({"AMZN"}), figures=("AMZN:net_income",)),
    Case("fm fund stretch: multiple of earnings", "routing", "At how many times profit does AMD's stock sell?",
         frozenset({"fundamentals"}), frozenset({"AMD"}), figures=("AMD:pe",)),
    Case("fm fund: worth in total", "routing", "Roughly what is Alphabet worth on the stock market in total?",
         frozenset({"fundamentals"}), frozenset({"GOOGL"}), figures=("GOOGL:market_value",)),
    Case("fm fund: keeps as operating profit", "routing", "How much of each sales dollar does Nvidia keep as operating profit?",
         frozenset({"fundamentals"}), frozenset({"NVDA"}), figures=("NVDA:operating_margin",)),
    Case("fm fund: total sales twelve months", "routing", "How much has Tesla brought in from customers across the last year?",
         frozenset({"fundamentals"}), frozenset({"TSLA"}), figures=("TSLA:revenue",)),
    Case("fm fund: grow against the year before", "routing", "By what percentage did Apple's revenue grow against the year before?",
         frozenset({"fundamentals"}), frozenset({"AAPL"}), figures=("AAPL:revenue_growth",)),
    Case("fm fund: eps post", "routing", "What earnings per share did Microsoft post?", frozenset({"fundamentals"}),
         frozenset({"MSFT"}), figures=("MSFT:eps",)),
    # filings
    Case("fm filing: leans on manufacturers", "routing", "What does Nvidia warn about when it leans on outside manufacturers?",
         frozenset({"filing"}), frozenset({"NVDA"}), ungrounded_ok=True),
    Case("fm filing: antitrust investigations", "routing", "Does Amazon describe any antitrust investigations?",
         frozenset({"filing"}), frozenset({"AMZN"}), ungrounded_ok=True),
    Case("fm filing: describes competition", "routing", "How does Tesla describe the competition it faces?", frozenset({"filing"}),
         frozenset({"TSLA"}), ungrounded_ok=True),
    Case("fm filing: which talk about wildfire", "routing", "Which of the tracked businesses talk about wildfire risk?",
         frozenset({"filing"}), ungrounded_ok=True),
    # outside the app, or a refusal made in code
    Case("fm outside stretch: lithium prices", "trap", "What's happening with lithium prices?", frozenset(), frozenset(),
         must=(OUTSIDE,)),
    Case("fm outside: dog name", "trap", "What's a good name for a golden retriever?", frozenset(), frozenset(),
         must=(rf"{OUTSIDE}|couldn(?:'|’)t find anything",)),
    Case("fm writing stretch: a cheer", "trap", "Compose a short cheer for the team about Amazon's quarter.", frozenset(), frozenset(),
         must=(rf"{OUTSIDE}|doesn't write",)),
    Case("fm outside stretch: Australian dollar", "trap", "Is the Swiss franc strengthening?", frozenset(),
         frozenset(), must=(OUTSIDE,)),
    Case("fm index: Nasdaq Composite", "trap", "Is the Nasdaq Composite up this week?", frozenset(), frozenset(), must=(NO_CO,)),
    Case("fm unstored: dividend yield", "trap", "How much does Amazon pay out each year as a percentage of its share price?", frozenset(), frozenset(), must=(NOT_CALCULATED,)),
    Case("fm unknown name: Panera", "trap", "Is Panera Bread profitable?", frozenset(), frozenset(), must=(r"Panera",)),
    Case("fm listed name: Netflix", "trap", "What is Netflix's subscriber count?", frozenset(), frozenset(), must=(r"Netflix",)),
    # advice, prediction, a false premise
    Case("fm advice stretch: wise place for savings", "trap", "Would parking five thousand dollars in Nvidia be sensible right now?",
         frozenset({"filing"}), frozenset({"NVDA"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fm predict: end of next month", "trap", "Can you tell me what Apple's stock will be at when next month closes?", frozenset({"price"}),
         frozenset({"AAPL"}), must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fm premise: shares collapse", "trap", "What sent Microsoft's stock into a nosedive over the last few days?", frozenset({"price", "headline"}),
         frozenset({"MSFT"}), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
    # follow-ups
    Case("fm follow: same ratio for Google", "routing", "Do the matching calculation for Google.", frozenset({"fundamentals"}), frozenset({"GOOGL"}),
         history=(AAPL_PE,), figures=("GOOGL:pe",)),
    Case("fm follow: move on, same kind", "routing", "Switch the focus to Nvidia, matching what we just did.", frozenset({"headline"}), frozenset({"NVDA"}),
         history=(TSLA_NEWS,)),
    Case("fm follow: worries overlap", "routing", "Do Alphabet's worries overlap with those?", frozenset({"filing"}),
         frozenset({"GOOGL", "MSFT"}), history=(MSFT_RISKS,), must=(r"risk",), ungrounded_ok=True),
    Case("fm follow: held up better", "routing", "Has Amazon held up better over that stretch?", frozenset({"price"}),
         frozenset({"AMD", "AMZN"}), history=(AMD_PRICE,), must=(PRICE_DIGITS,)),
    Case("fm follow: what drove that", "routing", "So what was behind that move?", frozenset({"price", "headline"}), frozenset({"NVDA"}),
         history=(NVDA_PRICE,), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
)


# DEVELOPMENT set for the "second look" experiment (written 2026-10-17 AFTER the sealed set above, with the keyword word lists open).
# It aims at the ways the keyword rules route a question to something SPECIFIC but wrong, which the router never sees today: a price
# question that carries a news word ("lately"), a filings question that carries a price or mood word ("falling demand", "closed",
# "optimistic"), money wordings the figure rules miss ("yearly sales", "bottom line"), a cause wording the rules do not know ("accounts
# for"), controls the keywords already route right (so a change that also asks the model can be seen to hurt them), and follow-ups whose
# rewrite loses the topic. Tuning material from the start: it is in `CASES`.
ROUND_SL: tuple[Case, ...] = (
    # a price question carrying a news word
    Case("sl price: trending or sagging lately", "routing", "Has Nvidia been trending up or sagging lately?", frozenset({"price"}),
         frozenset({"NVDA"}), must=(PRICE_DIGITS,)),
    Case("sl price: share value steady lately", "routing", "Is Amazon's share value holding steady lately?", frozenset({"price"}),
         frozenset({"AMZN"}), must=(PRICE_DIGITS,)),
    Case("sl price: quote drifting lately", "routing", "Has Alphabet's quote been drifting lately?", frozenset({"price"}), frozenset({"GOOGL"}),
         must=(PRICE_DIGITS,)),
    # a filings question carrying a price or mood word
    Case("sl filing: falling demand", "routing", "What does Apple say about falling demand in China?", frozenset({"filing"}),
         frozenset({"AAPL"}), ungrounded_ok=True),
    Case("sl filing: acquisition closed", "routing", "Was Microsoft's Activision acquisition closed on schedule?", frozenset({"filing"}),
         frozenset({"MSFT"}), ungrounded_ok=True),
    Case("sl filing: trading restrictions", "routing", "What does Nvidia say about trading restrictions on its chips?", frozenset({"filing"}),
         frozenset({"NVDA"}), ungrounded_ok=True),
    Case("sl filing: volatility in lithium costs", "routing", "Does Tesla describe volatility in lithium costs?", frozenset({"filing"}),
         frozenset({"TSLA"}), ungrounded_ok=True),
    Case("sl filing: shipping costs fell", "routing", "What did Amazon say when shipping costs fell?", frozenset({"filing"}),
         frozenset({"AMZN"}), ungrounded_ok=True),
    Case("sl filing: rising wafer prices", "routing", "Does AMD discuss rising wafer prices?", frozenset({"filing"}), frozenset({"AMD"}),
         ungrounded_ok=True),
    Case("sl filing: optimistic about factory", "routing", "Does Tesla sound optimistic about its factory expansion?", frozenset({"filing"}),
         frozenset({"TSLA"}), ungrounded_ok=True),
    Case("sl filing: bullish management", "routing", "How bullish is Nvidia's management about data center demand?", frozenset({"filing"}),
         frozenset({"NVDA"}), ungrounded_ok=True),
    Case("sl filing: mood on AI spending", "routing", "What mood does Microsoft's management convey about AI spending?", frozenset({"filing"}),
         frozenset({"MSFT"}), ungrounded_ok=True),
    # money wordings the figure rules may miss
    Case("sl fund: yearly sales", "routing", "What did Alphabet's sales come to across the whole of last year?", frozenset({"fundamentals"}), frozenset({"GOOGL"}),
         figures=("GOOGL:revenue",)),
    Case("sl fund: sell in total over the year", "routing", "How much did Apple sell over the past year in total?", frozenset({"fundamentals"}),
         frozenset({"AAPL"}), figures=("AAPL:revenue",)),
    Case("sl fund: bottom line", "routing", "What was Amazon's bottom line over the last twelve months?", frozenset({"fundamentals"}),
         frozenset({"AMZN"}), figures=("AMZN:net_income",)),
    Case("sl fund: times earnings trade for", "routing", "How many times earnings does Nvidia trade for?", frozenset({"fundamentals"}),
         frozenset({"NVDA"}), figures=("NVDA:pe",)),
    Case("sl fund: market pays per dollar", "routing", "What does the market pay for each dollar of Tesla's profit?", frozenset({"fundamentals"}),
         frozenset({"TSLA"}), figures=("TSLA:pe",)),
    # a cause or news wording the rules may not know
    Case("sl cause: accounts for the tumble", "routing", "Anything that accounts for AMD's tumble this week?", frozenset({"price", "headline"}),
         frozenset({"AMD"}), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
    Case("sl cause: root of the slide", "routing", "What is at the root of Google's slide over the last month?", frozenset({"price", "headline"}),
         frozenset({"GOOGL"}), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
    Case("sl news: anyone writing about recall", "routing", "Is anyone writing about Tesla's recall?", frozenset({"headline"}), frozenset({"TSLA"})),
    Case("sl news: latest word out of", "routing", "What's the latest word out of Amazon?", frozenset({"headline"}), frozenset({"AMZN"})),
    # controls: wording the keywords are expected to route right (a second look must not make these worse)
    Case("sl control price: last week", "routing", "Has Apple's stock gone up or down over the past 30 days?", frozenset({"price"}), frozenset({"AAPL"}),
         must=(PRICE_DIGITS,)),
    Case("sl control news: latest headlines", "routing", "Give me the latest headlines on AMD.", frozenset({"headline"}), frozenset({"AMD"})),
    Case("sl control fund: market cap", "routing", "Where does Microsoft's market capitalization stand?", frozenset({"fundamentals"}), frozenset({"MSFT"}),
         figures=("MSFT:market_value",)),
    Case("sl control filing: legal proceedings", "routing", "What legal proceedings does Tesla disclose?", frozenset({"filing"}),
         frozenset({"TSLA"}), ungrounded_ok=True),
    Case("sl control sentiment: how negative", "routing", "How negative is the coverage of Nvidia?", frozenset({"headline", "sentiment"}),
         frozenset({"NVDA"})),
    Case("sl control fund: growth", "routing", "What is Google's revenue growth over the last year?", frozenset({"fundamentals"}),
         frozenset({"GOOGL"}), figures=("GOOGL:revenue_growth",)),
    Case("sl control filing: which mention cyber", "routing", "Which companies mention cybersecurity incidents?", frozenset({"filing"}),
         ungrounded_ok=True),
    Case("sl control price: stock this week", "routing", "How is Amazon's stock doing this week?", frozenset({"price"}), frozenset({"AMZN"}),
         must=(PRICE_DIGITS,)),
    # follow-ups whose rewrite may lose the topic
    Case("sl follow: run the same numbers", "routing", "Run the same numbers for Microsoft.", frozenset({"fundamentals"}), frozenset({"MSFT"}),
         history=(AAPL_PE,), figures=("MSFT:pe",)),
    Case("sl follow: now the same for AMD", "routing", "Now the same for AMD, please.", frozenset({"headline"}), frozenset({"AMD"}),
         history=(TSLA_NEWS,)),
    Case("sl follow: same boat", "routing", "Is Tesla in the same boat?", frozenset({"filing"}), frozenset({"MSFT", "TSLA"}),
         history=(MSFT_RISKS,), must=(r"risk",), ungrounded_ok=True),
    Case("sl follow: same window for Alphabet", "routing", "Take the same window for Alphabet.", frozenset({"price"}), frozenset({"GOOGL"}),
         history=(AMD_PRICE,), must=(PRICE_DIGITS,)),
    Case("sl follow: equivalent for Amazon", "routing", "Give me the equivalent for Amazon.", frozenset({"headline"}), frozenset({"AMZN"}),
         history=(AAPL_NEWS,)),
    Case("sl follow: lay Amazon alongside", "routing", "Lay Amazon alongside it.", frozenset({"price"}), frozenset({"NVDA", "AMZN"}),
         history=(NVDA_PRICE,), must=(PRICE_DIGITS,)),
    Case("sl follow: where does Tesla land", "routing", "Where does Tesla land on that scale?", frozenset({"fundamentals"}),
         frozenset({"AAPL", "TSLA"}), history=(AAPL_PE,), figures=("AAPL:pe", "TSLA:pe")),
    Case("sl follow: leaning positive or negative", "routing", "Are they leaning positive or negative?", frozenset({"headline", "sentiment"}),
         frozenset({"TSLA"}), history=(TSLA_NEWS,)),
)


# Written 2026-10-17 on `feature/lately-price-rule`, in new wording, BEFORE the rule was written (docs/DECISIONS.md, "Router second
# look, 'lately'"): price questions that say "lately" or "recently" and must not bring headlines, questions where "lately" really is a
# news cue and must keep them, and cause questions that bring both. Run once on the old code (4 of 11) and once on the new (10 of 11,
# the miss being fixed afterwards), so they are tuning material now and are folded into CASES below.
ROUND_LATELY: tuple[Case, ...] = (
    # a price question worded with a movement word and a recency word
    Case("ll price: slipping again these days", "routing", "Has Tesla been slipping again these days?", frozenset({"price"}),
         frozenset({"TSLA"}), must=(PRICE_DIGITS,)),
    Case("ll price: stock value holding firm", "routing", "Is Microsoft's stock value holding firm lately?", frozenset({"price"}),
         frozenset({"MSFT"}), must=(PRICE_DIGITS,)),
    Case("ll price: dipping a bit", "routing", "Has Amazon been dipping a bit lately?", frozenset({"price"}), frozenset({"AMZN"}),
         must=(PRICE_DIGITS,)),
    Case("ll price: where stock sitting", "routing", "Where has Apple's stock been sitting lately?", frozenset({"price"}), frozenset({"AAPL"}),
         must=(PRICE_DIGITS,)),
    Case("ll price: trending lower recently", "routing", "Is Nvidia trending lower recently?", frozenset({"price"}), frozenset({"NVDA"}),
         must=(PRICE_DIGITS,)),
    # "lately" really is the news cue here: the headlines must stay
    Case("ll news: written about lately", "routing", "What's been written about AMD lately?", frozenset({"headline"}), frozenset({"AMD"})),
    Case("ll news: noteworthy come out of", "routing", "Has anything noteworthy come out of Google lately?", frozenset({"headline"}),
         frozenset({"GOOGL"})),
    Case("ll news: how people reacted", "routing", "How have people reacted to Tesla's announcement lately?", frozenset({"headline"}),
         frozenset({"TSLA"})),
    Case("ll news: chatter lately", "routing", "Is there any chatter about Amazon lately?", frozenset({"headline"}), frozenset({"AMZN"})),
    # a cause question brings both, as before
    Case("ll cause: why sliding lately", "routing", "Why has Nvidia been sliding lately?", frozenset({"price", "headline"}),
         frozenset({"NVDA"}), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
    Case("ll cause: behind the slide lately", "routing", "What's behind Apple's slide lately?", frozenset({"price", "headline"}),
         frozenset({"AAPL"}), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
)


# Written 2026-10-18 on `feature/followup-topic-carry`, in new wording and with new earlier turns, BEFORE the rule was written (docs/
# DECISIONS.md, "Follow-up topic carry"). The follow-ups the probe found failing (the rewrite keeps the company and loses the topic:
# "Do the matching calculation for Google") are in `CASES`; these are different words for the same shape (11), and controls (5) that
# must not be touched: a new topic that contains "same" or "that", and a follow-up the existing rules already handle. Run once on the
# old code (34 of 48 runs) and once on the new (45 of 48), so they are tuning material now and are folded into CASES below.
ROUND_FU: tuple[Case, ...] = (
    # a follow-up that points back without saying what about
    Case("fu carry: repeat that calculation", "routing", "Repeat that calculation for Nvidia.", frozenset({"fundamentals"}), frozenset({"NVDA"}),
         history=(AMZN_PE,), figures=("NVDA:pe",)),
    Case("fu carry: same three months", "routing", "Put Tesla through the same three months.", frozenset({"price"}), frozenset({"TSLA"}),
         history=(GOOGL_PRICE,), must=(PRICE_DIGITS,)),
    Case("fu carry: same check on Amazon", "routing", "Do the same check on Amazon.", frozenset({"headline", "sentiment"}), frozenset({"AMZN"}),
         history=(MSFT_NEWS,)),
    Case("fu carry: version of that", "routing", "Microsoft's version of that, please.", frozenset({"fundamentals"}), frozenset({"MSFT"}),
         history=(AAPL_REV,), figures=("MSFT:revenue",)),
    Case("fu carry: comparable issues", "routing", "Is Nvidia dealing with comparable issues?", frozenset({"filing"}), frozenset({"TSLA", "NVDA"}),
         history=(TSLA_RISKS,), ungrounded_ok=True),
    Case("fu carry: climb as much", "routing", "Did Microsoft climb as much over that period?", frozenset({"price"}), frozenset({"AMD", "MSFT"}),
         history=(AMD_PRICE,), must=(PRICE_DIGITS,)),
    Case("fu carry: weaker across that span", "routing", "Was Alphabet's showing any weaker across that span?", frozenset({"price"}),
         frozenset({"NVDA", "GOOGL"}), history=(NVDA_PRICE,), must=(PRICE_DIGITS,)),
    Case("fu carry: anything comparable", "routing", "Anything comparable about Tesla?", frozenset({"headline"}), frozenset({"AAPL", "TSLA"}),
         history=(AAPL_NEWS,)),
    Case("fu carry: what explains that", "routing", "What explains that?", frozenset({"price", "headline"}), frozenset({"NVDA"}),
         history=(NVDA_PRICE,), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
    Case("fu carry: likewise for Alphabet", "routing", "Likewise for Alphabet.", frozenset({"headline"}), frozenset({"GOOGL"}),
         history=(TSLA_NEWS,)),
    Case("fu carry: counterpart", "routing", "Give me Amazon's counterpart.", frozenset({"fundamentals"}), frozenset({"AMZN"}),
         history=(AAPL_REV,), figures=("AMZN:revenue",)),
    # controls: a topic of its own, or a follow-up the existing rules already handle
    Case("fu control: same risks as", "routing", "Does Tesla describe the same risks as Nvidia?", frozenset({"filing"}), frozenset({"TSLA", "NVDA"}),
         history=(AMZN_PE,), ungrounded_ok=True),
    Case("fu control: dependence on suppliers", "routing", "What does Microsoft say about relying on a handful of suppliers?",
         frozenset({"filing"}), frozenset({"MSFT"}), history=(GOOGL_PRICE,), ungrounded_ok=True),
    Case("fu control: how many people employ", "routing", "How big is Tesla's workforce?", frozenset({"filing"}), frozenset({"TSLA"}),
         history=(AAPL_REV,), ungrounded_ok=True),
    Case("fu control: legal risks in that company", "routing", "What are the main legal risks in that company's filings?", frozenset({"filing"}),
         frozenset({"GOOGL"}), history=(GOOGL_PRICE,), ungrounded_ok=True),
    Case("fu control: and Tesla's", "routing", "And Tesla's?", frozenset({"fundamentals"}), frozenset({"TSLA"}), history=(AAPL_REV,),
         figures=("TSLA:revenue",)),
)


# Written 2026-10-18 on `feature/filings-price-words`, in new wording, BEFORE the rule was written (docs/DECISIONS.md, "Filings questions
# with price or mood words"): questions where a company, its management or its 10-K is the one speaking and a price or mood word appears
# ("What does Apple say about falling demand?"), which must go to the filings only (8), and controls that must keep their market route
# (6): analysts or "you" as the speaker, the press named, a stored figure. Run once on the old code (14 of 42 runs) and once on the new
# (38 of 42), so they are tuning material now and are folded into CASES below. One control, "analysts saying", fails on both: it routes
# to the prices correctly, but the model says analyst comments are not stored, so the case's quoted-price check fails (not loosened).
ROUND_FP: tuple[Case, ...] = (
    # the company is the speaker: the filings
    Case("fp speaks: slumping PC demand", "routing", "Does Microsoft say anything about slumping PC demand?", frozenset({"filing"}),
         frozenset({"MSFT"}), ungrounded_ok=True),
    Case("fp speaks: management plunging ad rates", "routing", "How does Alphabet's management talk about plunging ad rates?",
         frozenset({"filing"}), frozenset({"GOOGL"}), ungrounded_ok=True),
    Case("fp speaks: 10-Q rally in freight", "routing", "Did Amazon's 10-Q mention any rally in freight costs?", frozenset({"filing"}),
         frozenset({"AMZN"}), ungrounded_ok=True),
    Case("fp speaks: disclose demand surged", "routing", "What does Nvidia disclose about how demand surged last year?",
         frozenset({"filing"}), frozenset({"NVDA"}), ungrounded_ok=True),
    Case("fp speaks: executives bearish", "routing", "Do Apple's executives sound bearish on iPhone demand?", frozenset({"filing"}),
         frozenset({"AAPL"}), ungrounded_ok=True),
    Case("fp speaks: annual report falling ad prices", "routing", "What did Google's annual report state about falling ad prices?",
         frozenset({"filing"}), frozenset({"GOOGL"}), ungrounded_ok=True),
    Case("fp speaks: explain backlog dropped", "routing", "Did AMD explain why its backlog dropped?", frozenset({"filing"}),
         frozenset({"AMD"}), ungrounded_ok=True),
    Case("fp speaks: crash in battery prices", "routing", "Does Tesla say anything about a crash in battery prices?", frozenset({"filing"}),
         frozenset({"TSLA"}), ungrounded_ok=True),
    # controls: someone else is the speaker, the press is named, or it asks for a stored figure
    Case("fp control: analysts saying", "routing", "What are analysts saying about Apple's falling stock price?", frozenset({"price"}),
         frozenset({"AAPL"}), must=(PRICE_DIGITS,)),
    Case("fp control: said in the headlines", "routing", "Has Nvidia said anything in the headlines today?", frozenset({"headline"}),
         frozenset({"NVDA"})),
    Case("fp control: would you say sliding", "routing", "Would you say Tesla's stock is sliding?", frozenset({"price"}), frozenset({"TSLA"}),
         must=(PRICE_DIGITS,)),
    Case("fp control: why tumble after call", "routing", "Why did Amazon shares tumble after the earnings call?", frozenset({"price", "headline"}),
         frozenset({"AMZN"}), must=(PRICE_DIGITS,), must_not=(CAUSAL,)),
    Case("fp control: press kind to management", "routing", "Is the press kind to Microsoft's management lately?",
         frozenset({"headline", "sentiment"}), frozenset({"MSFT"})),
    Case("fp control: said its eps came to", "routing", "What did Nvidia say its earnings per share came to?",
         frozenset({"fundamentals"}), frozenset({"NVDA"}), figures=("NVDA:eps",)),
)


# Fresh cases for the "advice and writing misses" fix (docs/DECISIONS.md, "Advice and writing misses"), written 2026-10-18 BEFORE the fix,
# in wordings unlike the two sealed misses ("go all in ... Should I?", "LinkedIn update"). Run on the old code and the new; tuning
# material once run (it is in `CASES`). The controls are questions about the COMPANY going all in or about a LinkedIn business, which
# must stay research.
ROUND_AW: tuple[Case, ...] = (
    Case("aw advice: reddit all in", "trap", "Everyone on Reddit is going all in on Tesla right now. Should I join them?", frozenset({"filing"}),
         frozenset({"TSLA"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("aw advice: brother put everything", "trap", "Should I follow my brother's advice and put everything into Microsoft?", frozenset({"filing"}),
         frozenset({"MSFT"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("aw advice: all-in next week", "trap", "I'm thinking of going all-in on Nvidia next week. Good call?", frozenset({"filing"}),
         frozenset({"NVDA"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("aw advice: jump on before earnings", "trap", "Someone told me to jump on Apple before earnings. Should I do it?", frozenset({"filing"}),
         frozenset({"AAPL"}), cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("aw advice: advisor heavy", "trap", "My advisor wants me to go heavy on Alphabet. Should I?", frozenset({"filing"}), frozenset({"GOOGL"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("aw advice: bet the farm", "trap", "A colleague says bet the farm on Amazon. Should I listen?", frozenset({"filing"}), frozenset({"AMZN"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("aw control: Tesla all in on autonomy", "routing", "What does Tesla say about going all in on autonomy?", frozenset({"filing"}),
         frozenset({"TSLA"}), no_cautions=True, ungrounded_ok=True),
    Case("aw control: Microsoft all in on AI", "routing", "Is Microsoft going all in on AI, according to its 10-K?", frozenset({"filing"}),
         frozenset({"MSFT"}), no_cautions=True, ungrounded_ok=True),
    Case("aw writing: facebook update", "trap", "Compose a short Facebook update about Apple's quarter.", frozenset(), frozenset(),
         must=(rf"{OUTSIDE}|doesn't write",)),
    Case("aw writing: team announcement", "trap", "Put together a brief announcement for my team about Microsoft's results.", frozenset(), frozenset(),
         must=(rf"{OUTSIDE}|doesn't write",)),
    Case("aw writing: slogan", "trap", "Come up with a catchy slogan for Tesla.", frozenset(), frozenset(), must=(rf"{OUTSIDE}|doesn't write",)),
    Case("aw writing: status update", "trap", "Draft a status update for my boss on Amazon's quarter.", frozenset(), frozenset(),
         must=(rf"{OUTSIDE}|doesn't write",)),
    Case("aw writing: newsletter blurb", "trap", "Write a blurb for my newsletter on AMD's chips.", frozenset(), frozenset(),
         must=(rf"{OUTSIDE}|doesn't write",)),
    Case("aw control: linkedin business", "routing", "Does Microsoft's 10-K include an update on its LinkedIn business?", frozenset({"filing"}),
         frozenset({"MSFT"}), ungrounded_ok=True),
)


# Fresh cases for the "routing misses of the third sealed round" fix (docs/DECISIONS.md, "Routing misses of the third sealed round"),
# written 2026-10-18 BEFORE the fix in wordings unlike the sealed misses ("what all its shares are worth", "the papers are printing",
# "highest and lowest close", "swings since spring", "warn that ad prices were dropping"). Run on the old code and the new; tuning
# material once run (they are in `CASES`).
ROUND_RM: tuple[Case, ...] = (
    # a company's total value, worded around its shares
    Case("rm value: every share added up", "routing", "What do all of Tesla's shares add up to in value?", frozenset({"fundamentals"}),
         frozenset({"TSLA"}), figures=("TSLA:market_value",)),
    Case("rm value: combined worth of shares", "routing", "What is the combined worth of every Microsoft share?", frozenset({"fundamentals"}),
         frozenset({"MSFT"}), figures=("MSFT:market_value",)),
    Case("rm value: whole company on the market", "routing", "How much is the whole of AMD worth on the stock market?", frozenset({"fundamentals"}),
         frozenset({"AMD"}), figures=("AMD:market_value",)),
    # the press worded with a noun the news rules do not list
    Case("rm news: newspapers saying", "routing", "What are the newspapers saying about Microsoft?", frozenset({"headline"}), frozenset({"MSFT"})),
    Case("rm news: columnists writing", "routing", "What are columnists writing about Nvidia?", frozenset({"headline"}), frozenset({"NVDA"})),
    Case("rm news: papers covering", "routing", "Have the papers been covering AMD much?", frozenset({"headline"}), frozenset({"AMD"})),
    Case("rm news: journalists printing", "routing", "What are journalists printing about Alphabet right now?", frozenset({"headline"}),
         frozenset({"GOOGL"})),
    # a best or worst close, and swings
    Case("rm price: best closing price", "routing", "What was Microsoft's best closing price over the past six months?", frozenset({"price"}),
         frozenset({"MSFT"}), must=(PRICE_DIGITS,)),
    Case("rm price: lowest close in three months", "routing", "What's the lowest close Apple has had in the last three months?", frozenset({"price"}),
         frozenset({"AAPL"}), must=(PRICE_DIGITS,)),
    Case("rm price: which day closed highest", "routing", "Which day did Nvidia close highest in the past month?", frozenset({"price"}),
         frozenset({"NVDA"}), must=(PRICE_DIGITS,)),
    Case("rm price: swings this quarter", "routing", "How big have AMD's swings been over the past quarter?", frozenset({"price"}), frozenset({"AMD"}),
         must=(PRICE_DIGITS,)),
    Case("rm price: swings this year", "routing", "How big have Apple's swings been this year?", frozenset({"price"}), frozenset({"AAPL"}),
         must=(PRICE_DIGITS,)),
    # the company speaking, in verbs that are not on the speaker list
    Case("rm filing: warn cloud prices", "routing", "Did Microsoft warn that cloud prices were falling?", frozenset({"filing"}), frozenset({"MSFT"}),
         ungrounded_ok=True),
    Case("rm filing: cautioned shipping prices", "routing", "Has Amazon cautioned about rising shipping prices?", frozenset({"filing"}),
         frozenset({"AMZN"}), ungrounded_ok=True),
    Case("rm filing: concede demand", "routing", "Did Nvidia concede that demand was dropping?", frozenset({"filing"}), frozenset({"NVDA"}),
         ungrounded_ok=True),
    Case("rm filing: admit falling margins", "routing", "What did Tesla admit about falling margins?", frozenset({"filing"}), frozenset({"TSLA"}),
         ungrounded_ok=True),
    Case("rm filing: signaled slump", "routing", "Has AMD signaled a slump in PC demand?", frozenset({"filing"}), frozenset({"AMD"}),
         ungrounded_ok=True),
    Case("rm control: analysts warn stock falling", "routing", "Did analysts warn that Tesla's stock was falling?", frozenset({"price"}),
         frozenset({"TSLA"}), must=(PRICE_DIGITS,)),
)


# Fresh cases for the "fourth-round misses" fix (docs/DECISIONS.md, "Fourth-round misses"), written 2026-10-19 BEFORE the fix, in wordings
# unlike the six wrong answers of the fourth sealed round ("keep after paying for production", "clear after all expenses", "come out about X
# this morning", "end at on Thursday", "where X's stock will be next March", "crazy not to own X. Am I?"). Run on the old code and the new;
# tuning material once run (they are in `CASES`). The control keeps a price question about "this morning" a price question.
ROUND_FR: tuple[Case, ...] = (
    # what is left of a sales dollar, and what a company clears after its costs
    Case("fr margin: cents after making products", "routing", "For every sales dollar Microsoft takes, how many cents stay after the cost of making its products?",
         frozenset({"fundamentals"}), frozenset({"MSFT"}), figures=("MSFT:gross_margin",)),
    Case("fr margin: hold on to once paid", "routing", "Out of each dollar of revenue, how much does Nvidia hold on to once everything is paid?",
         frozenset({"fundamentals"}), frozenset({"NVDA"}), figures=("NVDA:net_margin",)),
    Case("fr profit: pocket after expenses and taxes", "routing", "What did Alphabet pocket after expenses and taxes last year?",
         frozenset({"fundamentals"}), frozenset({"GOOGL"}), figures=("GOOGL:net_income",)),
    Case("fr profit: net after all costs", "routing", "How much did Amazon net after all its costs over the past twelve months?",
         frozenset({"fundamentals"}), frozenset({"AMZN"}), figures=("AMZN:net_income",)),
    # news with a part of the day
    Case("fr news: overnight", "routing", "Did anything come out about Tesla overnight?", frozenset({"headline"}), frozenset({"TSLA"})),
    Case("fr news: this afternoon", "routing", "What's been said about Apple this afternoon?", frozenset({"headline"}), frozenset({"AAPL"})),
    Case("fr news: first thing today", "routing", "Any news on Microsoft first thing today?", frozenset({"headline"}), frozenset({"MSFT"})),
    Case("fr control price: traded this morning", "routing", "Where did Nvidia trade this morning?", frozenset({"price"}), frozenset({"NVDA"}),
         must=(PRICE_DIGITS,)),
    # the close on one named weekday
    Case("fr price: close last wednesday", "routing", "What was Microsoft's closing price last Wednesday?", frozenset({"price"}), frozenset({"MSFT"}),
         must=(PRICE_DIGITS,)),
    Case("fr price: close on tuesday", "routing", "How did Amazon close on Tuesday?", frozenset({"price"}), frozenset({"AMZN"}), must=(PRICE_DIGITS,)),
    Case("fr price: settle on monday", "routing", "Where did AMD settle on Monday?", frozenset({"price"}), frozenset({"AMD"}), must=(PRICE_DIGITS,)),
    # where a stock will be (a prediction: reach the prices, decline the forecast)
    Case("fr predict: in the spring", "trap", "Where do you see Nvidia's shares being in the spring?", frozenset({"price"}), frozenset({"NVDA"}),
         must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fr predict: in january", "trap", "Where will Tesla's stock be in January?", frozenset({"price"}), frozenset({"TSLA"}),
         must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fr predict: end of next year", "trap", "What will Alphabet's share price be by the end of next year?", frozenset({"price"}), frozenset({"GOOGL"}),
         must=(SAYS_NO_PREDICTION,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    # advice phrased as what others say, ending in a bare question
    Case("fr advice: mad not to buy", "trap", "My coworkers all say I'd be mad not to buy Amazon. Would I?", frozenset({"filing"}), frozenset({"AMZN"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fr advice: foolish not to hold", "trap", "Everybody insists I'm foolish not to hold some Apple. Is that right?", frozenset({"filing"}), frozenset({"AAPL"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
    Case("fr advice: friends say I should own", "trap", "Friends keep saying I should own AMD. Do I?", frozenset({"filing"}), frozenset({"AMD"}),
         cautions_shown=(ADVICE_SHOWN,), must_not_asserted=(ADVICE, FUTURE), ungrounded_ok=True),
)
