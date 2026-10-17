"""Prices, headlines, headline sentiment, and company financial figures as numbered evidence for the copilot.

Every number the model may quote is worked out here (or in data/fundamentals.py), in Python, and written into the
source text. The model only copies figures; it never calculates them. Headlines are titles only (no article text), so
nothing here can show *why* a stock moved, and the financial figures can't show why a company's profit changed.

Usage: python -m ai.market AAPL "How has Apple stock done this year?"   (print the evidence the copilot would see)
"""
import argparse
import math
import re
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import psycopg

from data.db import connect
from data.fundamentals import Fundamentals, compute, format_money, latest_close, load_facts
from data.headlines import is_quote_page, title_key

from .sentiment import summarize

NEWS_PER_COMPANY = 6
STALE_AFTER_DAYS = 4  # a weekend plus a holiday; older than this and the answer says the data is behind
LATE_START_SLACK_DAYS = 7  # a window may start this many days before the first stored close without a warning


@dataclass(frozen=True)
class MarketEvidence:
    """One numbered source that isn't a filing passage."""

    kind: str  # "price" | "headline" | "sentiment" | "fundamentals"
    symbol: str
    header: str  # one line shown above the text in the prompt and above the excerpt in the app
    text: str
    url: Optional[str]
    as_of: date
    change: Optional[float] = None  # price only: the move over the window, in the stock's currency
    change_pct: Optional[float] = None  # price only: the same move as a percentage
    growth_pcts: tuple[float, ...] = ()  # fundamentals only: each growth figure stated in the text, in percent
    cautions: tuple[tuple[str, tuple[str, ...]], ...] = ()  # fundamentals only: (warning, the figures it concerns)
    starts: Optional[date] = None  # price only: the first stored close, when the window reaches back well before it


# ---- what is the question asking for? ----

PRICE_RE = re.compile(
    r"""\b(?:
        stock\s+price|share\s+price|price\s+(?:history|chart|change|movement|action)|current\s+price|latest\s+price|price\s+today|
        price\s+of|how\s+much\s+(?:is|does|did)|
        (?:stock|shares?)\s+(?:is|are|has|have|was|been|do|does|done|doing|did|up|down|moves?|moved|perform\w*|trad\w+|fell|rose|drop\w*|rall\w+|surg\w+|jump\w*|climb\w*|gain\w*)|
        how(?:'s|\s+is|\s+are)\s+(?:the\s+|its\s+|their\s+)?(?:stock|shares?)\b|
        (?:stock|shares?)\s+(?:go(?:es)?|going|went|gone)\s+(?:up|down|higher|lower|sideways)|
        \w+[-\s](?:day|week|month|year)s?\s+(?:move|movement|swing)s?|(?:daily|weekly|monthly|yearly)\s+(?:move|movement|swing)s?|
        trading|traded|closed|closing|rall(?:y|ied|ies)|surg(?:e|ed|es)|plung\w+|tank(?:ed|s|ing)|(?:will|would|could|might|may|to)\s+tank|sank|fell|fall(?:s|en|ing)?|
        drop(?:s|ped|ping)?|rose|rises?|rising|gain(?:ed|s)?|52[-\s]?week|all[-\s]time\s+(?:high|low)|year[-\s]to[-\s]date|ytd|
        crash\w*|tumbl\w+|soar\w*|slump\w*|spik\w+|skyrocket\w*|sell-?off|rebound\w*|
        volatil\w+|up\s+or\s+down|(?:is|was|are|been)\s+\w+\s+(?:up|down)|(?:up|down)\s+(?:today|this|over|since|in\s+the|for\s+the)|
        how(?:'s|\s+is|\s+are|\s+has|\s+have)\s+.{1,40}?\s+(?:doing|done|going|performing|performed)|
        (?:will|would|could)\s+.{1,40}?\s+(?:go|rise|fall|hit|reach|drop|climb|double)|forecast|predict\w*|price\s+target|
        next\s+(?:week|month|year)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
NEWS_RE = re.compile(
    r"\b(?:news|headlines?|announce\w*|lately|happening|going\s+on|what\s+happened|buzz|chatter|in\s+the\s+press|"
    r"(?:press|media|news)\s+coverage|coverage\s+of|"
    # "stories" only after a word that makes it the news ("customer success stories" is a filings topic)
    r"(?:recent|latest|new|newest|top|breaking|any|some|few|more|other)\s+stories|(?:latest|top|breaking|newest|recent)\s+story)\b",
    re.IGNORECASE,
)
# "Google doubled this month", "Why did Nvidia triple this year?": a company's stock moving by a multiple or collapsing. Only a
# capitalised company name counts as the subject ("Tesla's deliveries doubled", "revenue doubled" are not), a verb with an object
# is not ("doubled its dividend", "doubled down on", "doubled in size"), and the caller needs a named period or a stock word.
_CLAIM_VERB = (
    r"doubl(?:e|ed|es|ing)|tripl(?:e|ed|es|ing)|quadrupl(?:e|ed|es|ing)|halv(?:e|ed|es|ing)|collaps(?:e|ed|es|ing)|"
    r"plummet(?:ed|s|ing)?|nosedive[sd]?|nosediving|explod(?:e|ed|es|ing)|crater(?:ed|s|ing)?"
)
_NOT_A_COMPANY = (
    r"Revenue|Revenues|Sales|Profit|Profits|Income|Earnings|Dividend|Dividends|Net|Operating|Cash|Free|Margin|Margins|Deliveries|"
    r"Production|Costs|Expenses|Headcount|Employees|Cloud|Data|Services|Segment|Demand|Spending|Debt|Shares|Stock|Price|Prices|AI"
)
PRICE_CLAIM_RE = re.compile(
    rf"(?-i:\b(?!(?:{_NOT_A_COMPANY})\b)[A-Z][\w.&-]*)\s+(?:(?:has|have|had|just|really|actually|also)\s+)*(?:{_CLAIM_VERB})\b"
    r"(?!\s+(?:its|their|the|a|an|his|her|our|my|your|down|in\s+(?:size|number|scale|headcount))\b)",
    re.IGNORECASE,
)
# "Tesla can only go up from here", "Do you think Microsoft reaches $650?": predictions about the price, routed to the prices so the
# prompt's no-prediction rule applies. "reach $100 billion" (a unit) and "revenue to reach" (no capitalised name) are not.
PRICE_PREDICTION_RE = re.compile(
    r"\b(?:can|could|will)\s+only\s+go\s+(?:up|down)\b(?=\s+from\b|\s+forever\b|\W*$)|"
    r"\bonly\s+go(?:es)?\s+(?:up|down)\s+from\s+(?:here|now|this\s+point)\b|"
    r"(?-i:\b[A-Z][\w.&-]*)\s+(?:(?:will|would|could|might)\s+)?reach(?:es)?\s+\$\s?\d[\d,]*+(?:\.\d+)?+"
    r"(?!\s*(?:[bmk]\b|billion|million|trillion|thousand|percent|%))",
    re.IGNORECASE,
)
# "Tell me Apple's close from last Thursday", "Where did Nvidia close yesterday?": the noun or verb "close" as a price. Each form
# needs a day word or a company's possessive, so "Apple's close relationship with TSMC", "close its plant" and "close to a
# deal" stay filings questions.
_WEEKDAY = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
CLOSE_NOUN_RE = re.compile(
    rf"\b[\w.&-]+['’]s\s+close\s+(?:price\s+)?(?:from|on|at|for|in)\s+(?:last|yesterday|today|this|the\s+(?:day|week|month|end)|{_WEEKDAY}|\d)"
    rf"|\bthe\s+close\s+(?:price\s+)?(?:for|on)\s+(?!the\b)[\w.&-]+"
    rf"|\bclose\s+(?:from|on)\s+(?:last|yesterday|{_WEEKDAY})\b"
    r"|\bwhere\s+did\s+[\w.&-]+\s+close\b(?!\s+(?:its|their|the|a|an|down|out|off|to)\b)"
    rf"|\b(?:what\s+)?did\s+[\w.&-]+\s+close\s+(?:at|higher|lower|flat|today|yesterday|on\s+{_WEEKDAY})\b",
    re.IGNORECASE,
)
# "How much higher is Nvidia than it was a year ago?", "Is AMD lower than where it was a month ago?": the stock against its
# own past. The subject is one bare name, so "Apple's revenue" and "Tesla's headcount" are not caught; the caller also needs a
# named period and no financial-figure word ("revenue than a year ago" is a figures question).
_BARE_NAME = r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our)\b)[\w.&-]+"
_THAN_THEN = (
    r"than\s+(?:(?:where\s+)?(?:it|they)\s+(?:was|were|stood|sat)\b|"
    r"(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,3})\s+(?:day|week|month|year)s?\s+ago\b)"
)
PERIOD_COMPARE_RE = re.compile(
    rf"\bhow\s+much\s+(?:higher|lower|more|less)\s+(?:is|are|was)\s+{_BARE_NAME}\s+(?:now\s+)?{_THAN_THEN}"
    rf"|\b(?:is|are|was|were)\s+{_BARE_NAME}\s+(?:now\s+)?(?:higher|lower|above|below)\s+{_THAN_THEN}",
    re.IGNORECASE,
)
# A company and its stock with nothing else in the question ("What about Tesla's stock?", "Tesla stock?"). It has no verb,
# so PRICE_RE misses it and it went to the filings (the answer was Tesla's headcount and lawsuits). Deliberately narrow:
# only filler words may come before the one name-like word, and nothing but a time word ("now", "please") may follow
# "stock", so "Should I buy Tesla stock?", "Tesla's stock-based compensation" and "What does Tesla say about its stock?"
# are not caught.
BARE_STOCK_RE = re.compile(
    r"^\W*(?:(?:and|or|so|ok|okay|then|also|now|what|how|about|what's|whats|how's|hows)[\s,]+)*"
    r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our|what|which|who|why|how|any|some|each|every|no|"
    r"penny|growth|value|tech|cheap)\b)[\w.&-]+(?:['’]s)?\s+(?:stocks?|shares?)"
    r"(?:[\s,]+(?:now|currently|right now|today|please|then|too|again|as well|at the moment|lately))*\W*$",
    re.IGNORECASE,
)
# "Show me how Alphabet has moved over the last three months": a company, a movement verb, and (checked separately, with
# parse_window) a named period. No "stock" or "shares" is needed. The subject must be one bare name, so "Apple's headcount
# moved" is not caught, and the verb must not take an object ("move its supply chain", "move into cloud").
PERIOD_MOVE_RE = re.compile(
    r"\bhow\s+(?:(?:has|have|had|did|does|do)\s+)?"
    r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our|much|many)\b)[\w.&-]+\s+(?:(?:has|have|had)\s+)?"
    r"(?:moved?|trended|fared|swung|swing)\b(?!\s+(?:its|their|the|a|an|to|into|from|out|on|up\s+to|toward\w*)\b)"
    r"|\bwhere\s+(?:has|have|had|did)\s+(?!(?:the|its|their|this|that)\b)[\w.&-]+\s+(?:moved?|trended|fared|swung)\b"
    r"(?!\s+(?:its|their|the|a|an|to|into|from|out|on)\b)",
    re.IGNORECASE,
)
@lru_cache(maxsize=4)
def _year_start_re(year: int) -> re.Pattern:
    """"Is Amazon above where it started 2026?": a comparison with where the stock stood at the start of THIS year. Only the
    current year (or "the year", "last year"'s close) is accepted, because the year-to-date window is wrong for any other."""
    return re.compile(
        r"\bwhere\s+(?:it|they|the\s+stock|the\s+shares)\s+(?:"
        rf"(?:started|began|opened|stood|was|were|sat)\s+(?:the\s+year|(?:in\s+)?{year}|at\s+the\s+(?:start|beginning)\s+of\s+(?:the\s+year|{year}))|"
        r"(?:finished|ended|closed)\s+last\s+year)\b",  # not "was last year": that can be anything, such as revenue
        re.IGNORECASE,
    )


@lru_cache(maxsize=4)
def _when_year_opened_re(year: int) -> re.Pattern:
    """"Is Amazon's share price higher than when the year opened?", "Is Tesla up on where it was when 2026 began?": the same
    comparison, worded with "when". The caller also needs the stock or a bare company name as the subject, because
    "Was Tesla's headcount larger than when the year began?" is not about the price."""
    return re.compile(
        r"\b(?:than|on|from|above|below|ahead\s+of|behind|compared\s+(?:with|to)|versus|vs\.?|relative\s+to|against)\s+"
        r"(?:where\s+(?:it|they)\s+(?:was|were)\s+)?"
        rf"when\s+(?:the\s+year|{year})\s+(?:opened|began|started|kicked\s+off)\b",
        re.IGNORECASE,
    )


_BARE_PRICE_SUBJECT_RE = re.compile(rf"\b(?:is|are|was|were|has|have)\s+{_BARE_NAME}\s+(?:up|down|higher|lower|above|below|ahead|behind)\b", re.IGNORECASE)


def year_start_comparison(question: str, today: Optional[date] = None) -> bool:
    year = (today or date.today()).year
    if _year_start_re(year).search(question):
        return True
    return bool(_when_year_opened_re(year).search(question)) and bool(
        STOCK_WORD_RE.search(question) or _BARE_PRICE_SUBJECT_RE.search(question))


GENERAL_RE = re.compile(r"\bhow(?:'s|\s+is|\s+are|\s+has|\s+have)\s+.{1,40}?\s+(?:doing|done|going|performing|performed)\b", re.IGNORECASE)
STOCK_WORD_RE = re.compile(r"\b(?:stocks?|shares?|prices?)\b", re.IGNORECASE)
# "How much did Apple earn / pay in dividends / bring in?" begins like a price question ("how much did") but asks what the
# company did with money. Cut out only when the same question has a money verb or noun after it and no stock word anywhere
# (the caller checks that), so "How much did Apple stock lose?" is still a price question.
HOW_MUCH_MONEY_RE = re.compile(
    r"\bhow\s+much\s+(?:money\s+|cash\s+)?(?:did|does|is|has|have)\b(?=[^?.]{0,80}\b(?:earn\w*|mak(?:e|es|ing)|made|net(?:ted)?|"
    r"pa(?:y|id|ys)|spen[dt]\w*|sell\w*|sold|bring\w*|brought|rais(?:e|es|ed|ing)|generat\w*|report\w*|borrow\w*|owe\w*|profit\w*|"
    r"revenues?|sales|income|dividends?|cash)\b)",
    re.IGNORECASE,
)
# No index data is stored, and a filing's "total return" chart (scaled from $100) reads like an index level to a model.
INDEX_RE = re.compile(r"\b(?:s&p(?:\s*500)?|dow(?:\s+jones)?|nasdaq(?:\s+composite)?|russell\s*\d+)\b", re.IGNORECASE)
STOCK_NOUN_RE = re.compile(r"\b(?:stocks?(?!-based)|shares)\b", re.IGNORECASE)  # not "stock-based compensation"
_NEWS_SOURCE = r"reporters?|journalists?|press|media|coverage|headlines?|news(?:\s+flow)?|writers?|commentators?|pundits?|buzz|chatter"
_NEWS_TONE = (
    r"kind|harsh|friendly|hostile|fa?vou?rabl[ey]|unfa?vou?rabl[ey]|nice|piling\s+on|bashing|trashing|slamming|praising|"
    r"treating|upbeat|gloomy|supportive|critical|flattering|rosy|grim|optimistic|pessimistic|warm|cold|gentle|brutal|glowing|"
    r"scathing|good|bad|better|worse|improving|souring|warming|"
    r"turned\s+on|turning\s+on|easy\s+ride|rough\s+ride|hard\s+time|free\s+pass|going\s+(?:easy|hard)\s+on"
)
SENTIMENT_RE = re.compile(
    r"\b(?:sentiment|mood|bullish|bearish|optimis\w+|pessimis\w+|tone\s+of|(?:good|bad|positive|negative)\s+news|"
    r"how\s+(?:do|does|are)\s+(?:people|investors|the\s+market|reporters|journalists|the\s+press|the\s+media|commentators)\s+"
    r"(?:feel|think|see|view)|"
    r"\b(?:media|press|news|coverage)\b[^?.]{0,25}\b(?:tone|mood|vibe)\b|\b(?:tone|mood|vibe)\b[^?.]{0,25}\b(?:media|press|news|coverage)\b|"
    r"\bvibes?\b|\bsour(?:ing|ed)?\s+on\b|"
    r"\b(?:turn\w*|get\w*|grow\w*|becom\w*)\s+(?:more\s+)?(?:sour|bullish|bearish)\b|"  # not "negative": cash flow can turn negative
    r"\b(?:press|media|coverage|reporters|journalists)\b[^?.]{0,30}\b(?:negative|positive)\b|"
    r"\bcoverage\b[^?.]{0,30}\b(?:trend\w*|shift\w*|chang\w*|improv\w*|worsen\w*|deteriorat\w*)\b|"
    r"feel(?:ing|s)?\s+(?:positive|negative|good|bad)|investors?\s+(?:feel|are\s+feeling|think)|what\s+do\s+investors|"
    r"how\s+(?:negative|positive)\b|"
    # a news source near a word about its attitude, either order ("are reporters being kind or harsh", "headlines mostly good"):
    # structure, not one phrase per wording. Analysts are not a news source here ("do analysts expect positive growth").
    rf"\b(?:{_NEWS_SOURCE})\b[^?.]{{0,40}}\b(?:{_NEWS_TONE})\b|\b(?:{_NEWS_TONE})\b[^?.]{{0,40}}\b(?:{_NEWS_SOURCE})\b|"
    # stories, headlines or articles that are "mostly positive", "more negative than positive", "lean positive or negative"
    # (plural only, so "headline earnings" is not one; a bare "negative" is not enough, since a list of bad stories is not a score)
    r"\b(?:stories|headlines|articles|news|coverage)\b[^?.]{0,40}\b(?:(?:more|mostly|mainly|largely|predominantly)\s+(?:positive|negative)|"
    r"positive\s+(?:or|vs\.?|versus|than)\s+negative|negative\s+(?:or|vs\.?|versus|than)\s+positive|"
    r"(?:lean\w*|tilt\w*|skew\w*)\s+(?:positive|negative))\b|"
    r"\b(?:saying|said|writing|written)\s+(?:nice|good|bad|kind|mean|positive|negative)\s+things\s+about\b|"
    r"\b(?:feeling|feelings|attitude|stance|take)\s+(?:about|on|toward|towards)\b[^?.]{0,50}\b(?:news|press|media|coverage|headlines)\b)",
    re.IGNORECASE,
)
# A question that asks what moved the price. On a price question it brings the headlines too (published beside the move, never offered as
# its cause). "What drove it?", "What caused ...", "What triggered ...", "How come ...", "What's responsible for ..." count as well as "why".
CAUSE_RE = re.compile(
    r"\b(?:why|reasons?|because|what\s+happened|what(?:'s|\s+is|\s+was)\s+(?:behind|driving|causing|moving)|"
    r"what\s+(?:drove|caused|triggered|sparked|prompted|pushed|made|led\s+to|explains?|explained)|how\s+come|"
    r"what(?:'s|\s+is|\s+was)\s+(?:responsible\s+for|the\s+(?:story|cause|reason)\s+(?:behind|of|for))|"
    r"(?:drove|caused|triggered|sparked|prompted)\s+(?:it|that|this|the\s+(?:move|drop|jump|rise|fall|surge|plunge|rally|selloff|slide|spike)))\b",
    re.IGNORECASE,
)
# The move named as a noun: "Amazon's jump this month", "Nvidia's slide", "the move in Microsoft stock". With a cause word these are price
# questions even without a price verb or the word "stock". Only the nouns that no price rule knew ("jump", "slide", "swoon") are named here:
# "drop", "rally", "surge", "crash" were price words already. "Nvidia's slide in gross margin" is a business metric, not the stock.
PRICE_MOVE_NOUN_RE = re.compile(
    r"(?-i:\b[A-Z][\w.&-]*)['’]s\s+(?:jump|slide|swoon)\b(?!\s+in\s+(?!stock\b|shares?\b|price\b))|"
    r"\b(?:move|moves|jump|slide|swoon|selloff|sell-off|plunge|rally|surge)\s+in\s+(?-i:[A-Z][\w.&-]*)\s+(?:stock|shares?)\b",
    re.IGNORECASE,
)
FILING_RE = re.compile(
    r"\b(?:filings?|10-?k|10-?q|annual\s+report|quarterly\s+report|sec|risks?|risk\s+factors|legal|litigation|lawsuits?|"
    r"competition|competitors?|employees|headcount|revenues?|income|profits?|margins?|segments?|strategy|business|"
    r"operations|supply\s+chain|regulat\w+|cash|debt|liabilit\w+|guidance|capex|capital\s+expenditures?)\b",
    re.IGNORECASE,
)


# Company financial figures (P/E, market value, revenue, profit, margins) from the stored SEC figures.
# Specific wording first. Every match is cut out of the question before the next pattern runs, so "price-to-earnings"
# counts once as a P/E question and not again as an "earnings" (profit) one.
# A company named as the subject of "worth" or "valued at": one or two words with no possessive ("Microsoft", "Apple Inc",
# "all of Tesla"), so "Microsoft's goodwill", "the inventory" and "its patents" are not a company's total value.
_SUBJ = r"(?:all\s+of\s+)?(?!(?:the|its|their|a|an|this|that|these|those|my|your|our)\b)[\w.&-]+(?:\s+(?:inc|corp|corporation|company|co)\b\.?)?"
MARKET_VALUE_PATTERN = (
    r"\bmarket[-\s]cap(?:italization|italisation)?\b|\bmarket\s+(?:value|valuation)\b|"
    rf"\b(?:what(?:'s|\s+is|\s+are)|how\s+much\s+(?:is|are))\s+{_SUBJ}\s+worth\b(?!\s+(?:buying|selling|investing|holding|owning|it\b|the\b|a\b|an\b|to\b))|"
    rf"\bwhat(?:'s|\s+is|\s+was)\s+{_SUBJ}\s+valued\s+at\b|"
    r"\b(?:total|combined|overall|aggregate)\s+value\s+of\s+(?:all\s+of\s+)?[\w.&'’ -]{0,30}?\b(?:shares|stock|equity)\b|"
    r"\bcompany['’]?s?\s+value\b|\bcost\s+to\s+(?:buy|purchase|acquire)\s+(?:all\s+of|the\s+(?:whole|entire))\b"
)
_SPECIFIC_TOPICS = (
    ("pe", r"\bp\s?/\s?e\b|\bpe\s+(?:ratio|multiple)\b|\bprice[-\s]to[-\s]earnings\b|\bearnings\s+multiple\b"),
    ("market_value", MARKET_VALUE_PATTERN),
    ("eps", r"\beps\b|\bearnings\s+per\s+share\b"),
    ("shares", r"\bshares\s+outstanding\b|\bshare\s+count\b|\bnumber\s+of\s+shares\b"),
)
# Everyday words that a filing can also answer. Left to the filings when the question names a filing, a quarter, a
# segment, or asks why (the figures are twelve-month totals and can't explain anything).
_NOT_SALES_SIDE = (  # words after "sales" that make it a department, a tax, or a cost, not the company's revenue
    r"(?!\s+(?:tax|taxes|team|teams|force|staff|office|offices|people|reps?|channels?|practices|cycle|organi[sz]ation|"
    r"pipeline|commissions?|and\s+marketing|general|costs?|expenses?)\b)"
)
_BROAD_TOPICS = (
    # "earn" counts only as the company's own: "How much did Amazon earn", "What did Microsoft earn" (one bare name as the
    # subject), so "How much do Apple engineers earn?" is left alone
    ("profit", r"\bnet\s+income\b|\bprofit(?:s|ability|able)?\b|\bearnings\b|\boperating\s+income\b|\bbottom\s+line\b|"
               r"\b(?:what|how\s+much(?:\s+money)?)\s+(?:did|does|do|has|have|had|will|would)\s+"
               r"(?!(?:the|its|their|this|that|these|those|a|an|my|your|our)\b)[\w.&-]+\s+earn(?:ed)?\b"),
    ("margin", r"\bmargins?\b"),
    # "sales" counts as the company's revenue only in the forms that cannot mean a product or a department: "Nvidia's sales",
    # "total / net sales", "dollars of sales". Not "iPhone sales (over the past year)", "retail sales", "sales tax" or "the
    # sales team" (a "sales over the last ..." form was tried and dropped: it caught "iPhone sales over the past year").
    # Money coming in ("how much money did Tesla bring in") is revenue too.
    ("revenue", r"\brevenues?\b|\btop\s+line\b|"
                rf"\b(?:total|net|overall|combined|annual|yearly|its|their|[\w.&-]+['’]s)\s+sales\b{_NOT_SALES_SIDE}|"
                r"\b(?:dollars|amount|value)\s+of\s+sales\b|"
                r"\bhow\s+(?:much|many)\s+(?:money|cash|dollars)\b[^?.]{0,50}?\b(?:bring|brought|brings|take|took|pull|pulled)\s+in\b"),
    ("general", r"\bfinancials?\b|\bfundamentals?\b|\bvaluation\b|\bfinancial\s+(?:figures|results|health|position|summary)\b"),
)
FILING_FORM_RE = re.compile(
    r"\b(?:10-?k|10-?q|8-?k|filings?|annual|quarter(?:s|ly)?|fiscal|segments?|earnings\s+(?:call|release|report)|"
    r"by\s+(?:product|region|geograph\w+|business|division))\b",
    re.IGNORECASE,
)
# "The last four quarters" is the twelve months the stored figures cover, not a request for one quarter's filing; "last
# quarter" and "the second quarter" still are.
TWELVE_MONTHS_AS_QUARTERS_RE = re.compile(r"\b(?:last|past|previous|trailing|prior)\s+(?:4|four)\s+quarters\b", re.IGNORECASE)
WHY_RE = re.compile(
    r"\b(?:why|reasons?|because|explain\w*|what\s+(?:happened|drove|drives|caused|causes)|driv(?:e|es|ing|en|ers?)|"
    r"caus(?:e|es|ed|ing)|what(?:'s|\s+is|\s+was)\s+behind)\b",
    re.IGNORECASE,
)


# "How many shares does Apple have?" asks for the stored share count. The price rules used to read "shares does" as a
# price verb and answer it from price data, which has no share count. A question about what was done with shares
# (repurchased, issued, owned, sold, can I buy) is a filings question: the phrase is still cut out so it isn't read as a
# price question, but no figure is asked for.
HOW_MANY_SHARES_RE = re.compile(r"\bhow\s+many\s+(?:[\w.&'’-]+\s+){0,2}?shares\b", re.IGNORECASE)  # "how many Nvidia shares"
SHARES_ACTION_RE = re.compile(
    r"\b(?:repurchas\w*|buy\s?backs?|bought|buy|buying|issu\w*|sold|sell|selling|trad\w*|split\w*|own\w*|held|hold|"
    r"granted|vest\w*|award\w*|short|dividends?)\b",
    re.IGNORECASE,
)


def _topics(text: str, patterns) -> tuple[set[str], str]:
    found, rest = set(), text
    for topic, pattern in patterns:
        if re.search(pattern, rest, re.IGNORECASE):
            found.add(topic)
            rest = re.sub(pattern, " ", rest, flags=re.IGNORECASE)
    return found, rest


def figure_topics(text: str) -> frozenset[str]:
    """Which financial figures a piece of text is about. Used on a question and on an answer, with no exceptions."""
    specific, rest = _topics(text, _SPECIFIC_TOPICS)
    broad, _ = _topics(rest, _BROAD_TOPICS)
    return frozenset(specific | broad)


def question_topics(question: str) -> tuple[frozenset[str], str]:
    """The financial figures a question asks for, and the question with those words cut out (so they don't also send it
    to the filings). Everyday words are left to the filings when the question is plainly about a filing or asks why."""
    specific, rest = _topics(question, _SPECIFIC_TOPICS)
    broad, rest_without_broad = _topics(rest, _BROAD_TOPICS)
    if broad and (FILING_FORM_RE.search(TWELVE_MONTHS_AS_QUARTERS_RE.sub(" ", question)) or WHY_RE.search(question)):
        return frozenset(specific), rest  # the everyday words stay in the question, for the filings rules to see
    return frozenset(specific | broad), rest_without_broad


# Well-known ratios this app does not compute. Only the explicit names are listed (a bare "book value" or "dividends"
# can be a plain filings question). Asked for one of these, the copilot says it doesn't calculate it, in code, because
# the model only saw filing text, found no price, and said "the stock price is not provided" although prices are stored.
_UNSTORED = (
    ("dividend yield", r"\bdividend\s+yield\b"),
    ("price-to-book ratio", r"\bprice[-\s]to[-\s]book\b|\bp\s?/\s?b\b|\bpb\s+ratio\b"),
    ("price-to-sales ratio", r"\bprice[-\s]to[-\s]sales\b|\bp\s?/\s?s\b|\bps\s+ratio\b"),
    ("PEG ratio", r"\bpeg(?:\s+ratio)?\b"),
    ("EV/EBITDA", r"\bev\s?/\s?ebitda\b"),
    ("EV/sales", r"\bev\s?/\s?(?:sales|revenue)\b"),
    ("price-to-free-cash-flow ratio",
     r"\bprice[-\s]to[-\s](?:free[-\s]cash[-\s]flow|fcf)\b|\bp\s?/\s?fcf\b|\bpfcf\b"),
    ("price-to-cash-flow ratio", r"\bprice[-\s]to[-\s]cash[-\s]flow\b|\bp\s?/\s?cf\b"),
    ("free cash flow yield", r"\b(?:free[-\s]cash[-\s]flow|fcf)\s+yield\b"),
    ("earnings yield", r"\bearnings\s+yield\b"),
    ("current ratio", r"\bcurrent\s+ratio\b"),
    ("quick ratio", r"\b(?:quick|acid[-\s]test)\s+ratio\b"),
    ("return on invested capital", r"\broic\b|\breturn\s+on\s+(?:invested\s+)?capital\b"),
    ("interest coverage ratio", r"\binterest\s+coverage(?:\s+ratio)?\b"),
    ("enterprise value", r"\benterprise\s+value\b"),
    ("return on equity", r"\breturn\s+on\s+equity\b|\broe\b"),
    ("return on assets", r"\breturn\s+on\s+assets\b|\broa\b"),
    ("debt-to-equity ratio", r"\bdebt[-\s]to[-\s]equity\b"),
)


def unstored_figures(question: str) -> tuple[tuple[str, ...], str]:
    """The ratios the question asks for that aren't computed here, and the question with those words cut out (so
    "price-to-book" isn't also read as a price question)."""
    found, rest = [], question
    for name, pattern in _UNSTORED:
        if re.search(pattern, rest, re.IGNORECASE):
            found.append(name)
            rest = re.sub(pattern, " ", rest, flags=re.IGNORECASE)
    return tuple(found), rest


# A request for a buy, sell, or hold call. The model refused these in its own words only some of the time ("Is it a good
# time to buy Nvidia?" 3 of 10 runs), so the refusal is attached to the answer in code instead. People ask in endless ways
# (seven realistic wordings, none in the first phrase list, were all missed), so a question also counts when it has a
# trading word AND a decision cue. Missing a request is worse than flagging a harmless question (one extra notice), so
# this leans towards flagging. "Why did insiders sell Tesla shares?" has a trading word and no cue; "Will Tesla stock go
# up?" is a prediction with its own rule, not a request for a recommendation.
ADVICE_ASK_RE = re.compile(
    r"""\b(?:
        should\s+(?:i|we|one)\s+(?:\w+\s+){0,2}?(?:buy|sell|hold|invest|short|keep|dump|trim|add)\b|
        (?:good|bad|right|wrong|best|worst|smart)\s+(?:time|moment|idea)\s+to\s+(?:buy|sell|invest|hold)\b|
        (?:is|are|was)\b.{0,50}?\b(?:a\s+)?(?:good|great|better|best|bad|smart|safe|solid|risky)\s+(?:buy|sell|investment|bet|hold|pick|choice|play)\b|
        worth\s+(?:buying|selling|investing|holding)\b|
        (?:buy|sell)\s+or\s+(?:sell|hold|buy)\b|buy,?\s+sell,?\s+or\s+hold\b|
        would\s+you\s+(?:buy|sell|recommend|invest|hold)\b|
        do\s+you\s+(?:recommend|suggest)\b|(?:recommend|suggest)\s+(?:buying|selling|holding)\b|
        what\s+(?:stocks?|shares?)\s+should\s+(?:i|we)\b|
        (?:a|an)\s+(?:smart|safe|wise|sensible|sound|good|solid|reasonable)\s+(?:place|home|spot|vehicle|holding|investment)\b|
        better\s+off\s+(?:with|in|buying|owning|holding)\b|
        (?:do|would)\s+you\s+(?:like|favou?r|prefer|pick|choose)\b|
        \b(?:smart|wise|sensible|sound|safe|prudent|good|great|solid)\b.{0,60}?\bfor\s+(?:me|us)\b|
        (?:put|putting|park|parking)\s+(?:(?:any|some|a\s+little|a\s+lot\s+of)\s+)?(?:money|cash|savings)\s+(?:in|into|with)\b|
        (?:good|right|best|smart|wise)\s+(?:point|level|price|entry\s+point)\s+to\s+(?:buy|enter|get\s+in|add|sell|exit)\b|
        (?:one|something|stocks?)\s+to\s+(?:buy|sell|hold|own|keep|avoid)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)
TRADE_WORD_RE = re.compile(
    r"\b(?:buy(?:ing)?|sell(?:ing)?|hold(?:ing)?|invest(?:ing)?|dump|trim|short(?:ing)?|add(?:ing)?\s+to|accumulat\w+|"
    r"load(?:ing)?\s+up|get(?:ting)?\s+(?:in|out)|exit|position|put\s+(?:my|our)\s+(?:savings|money|cash)\s+(?:in|into)|"
    r"pick(?:ing)?\s+up|jump(?:ing)?\s+(?:in|into|on)|pil(?:e|ing)\s+(?:in|into|on)|stay(?:ing)?\s+(?:in|invested)|bail(?:ing)?\s+on|double(?:d|\s|-)*down|"
    r"get(?:ting)?\s+into|get(?:ting)?\s+out\s+of|"
    # "Is it time to cash out of Nvidia?": the reader's own sale. A company's own "unload its inventory" or "cash out its stake"
    # is not (the lookahead; the quantifiers are possessive so a shorter match cannot slip past it).
    r"cash(?:ing)?\s+out\b(?!\s+(?:its|their)\b)|(?:take|taking)\s+(?:some\s+|my\s+|our\s+)?profits?|"
    r"lock(?:ing)?\s+in\s+(?:my\s+|our\s+|some\s+|the\s+)?(?:gains?|profits?)|cut(?:ting)?\s+(?:my\s+|our\s+)?losses|"
    r"bail(?:ing)?\s+out|unload\w*+(?!\s+(?:its|their)\b)|offload\w*+(?!\s+(?:its|their)\b)|"
    r"ride\s+(?:it|this|that|them|[\w.&-]+)\s+out|hang(?:ing)?\s+on(?:to)?\b(?:\s+to\b)?+(?!\s+(?:its|their)\b)|go(?:ing)?\s+(?:long|short)\b|"
    r"add(?:ing)?\s+(?:[\w.&-]+\s+){1,2}to\s+(?:the|my|our|a|your)\s+(?:portfolio|holdings|watchlist))\b",
    re.IGNORECASE,
)
DECISION_CUE_RE = re.compile(
    r"\b(?:should|whether|wise|smart|safe(?:ly)?|good\s+idea|bad\s+idea|thinking\s+(?:about|of)|can\s+i|could\s+i|may\s+i|"
    r"my|our|worth|recommend\w*|advice|advise|suggest\w*|thoughts|opinion|would\s+you|do\s+you\s+think|right\s+time|"
    r"best\s+time|good\s+time|bad\s+time|reason\s+(?:not\s+)?to|enough\s+to|right\s+(?:stock|company|one)\s+to|"
    r"too\s+(?:late|early)|the\s+(?:moment|time)|reckon|your\s+(?:take|view|read)|"
    r"is\s+it\s+(?:the\s+)?(?:time|moment|point)\s+to|(?<!\w)time\s+to|would\s+it\s+be\s+(?:[\w-]+\s+){0,2}?to|"
    r"(?:crazy|reckless|foolish|stupid|dumb|mad|nuts|silly)\s+to|(?:a\s+)?(?:mistake|error|blunder)\s+to)\b",
    re.IGNORECASE,
)
# Judgments and endorsements that are a request for a recommendation however they are phrased (a probe of 24 everyday
# wordings found 21 unflagged): a judgment of value ("undervalued", "a bargain", "cheap right now"), an endorsement ("a sure
# thing", "a keeper", "worth owning", "rate it as an investment"), and the reader's own money ("I have $5,000. Where should
# it go?"). "Cheap" and "expensive" count only when they end the question or are followed by now / today / at this price,
# so "the most expensive segment to run" is left alone; "the winner-take-all risk" and "a retirement plan" are left alone too.
ADVICE_JUDGMENT_RE = re.compile(
    r"""\b(?:
        (?:over|under)(?:valued|priced)|fairly\s+(?:valued|priced)|(?:a|the)\s+(?:bargain|steal)|
        (?:cheap|expensive|pricey)(?=\s*(?:right\s+now|now|today|here|at\s+(?:this|the\s+current)\s+(?:price|level)|\W*$))|
        sure\s+thing|can'?t\s+lose|(?:safe|good|great|solid|sure|smart|risky)\s+bet|
        (?:a|the)\s+(?:winner(?!-)|keeper|no[-\s]?brainer)|screaming\s+buy|worth\s+(?:owning|holding|keeping|having)|
        (?:would|will|do|did)\s+you\s+(?:bet|wager)|rate\s+\w+\s+as\s+an?\s+investment|
        your\s+(?:take|view|opinion|read|thoughts)\s+on|make\s+(?:me|us)\s+(?:money|rich)|
        am\s+i\s+(?:crazy|nuts|wrong|silly|foolish|dumb|smart|right)\s+to|
        (?:is|are|was)\b.{0,50}?\b(?:good|great|solid|safe|smart|risky|better|best)\s+(?:[\w-]+\s+){0,2}(?:buy|sell|investment|bet|hold|pick|choice|play)\b|
        where\s+should\s+(?:it|that|the\s+money|i|we)\s+(?:go|be\s+put|put|invest)|(?:i|we)\s+(?:have|got)\s+\$\s?\d|
        (?:in|into|to|for)\s+(?:a|an|my|our|your)\s+(?:retirement|brokerage|savings|college)\s+(?:account|fund)|
        addition\s+to\s+(?:a|an|my|our|your)\s+(?:[\w-]+\s+){0,2}(?:portfolio|holdings)|
        too\s+(?:cheap|expensive|pricey|rich|hot)\s+to\s+(?:touch|buy|own|hold|ignore|consider|pass\s+up|miss|sell)|
        (?:would|should|will|can)\s+(?:a|an|the|some|any)\s+(?:[\w-]+\s+){0,2}investors?\s+(?:go|buy|bet|pick|pile|jump|hold|sell|choose|own)
    )""",
    re.IGNORECASE | re.VERBOSE,
)


# The reader's own money in the question ("park my money", "my retirement account", "my savings") is a request for a
# recommendation however it is worded. "its cash" and "an employee savings plan" are the company's, and are not caught.
OWN_MONEY_RE = re.compile(
    r"\b(?:my|our)\s+(?:money|cash|savings|retirement|nest\s+egg|portfolio|ira|401\s?\(?k\)?|brokerage|funds)\b", re.IGNORECASE
)


def asks_for_advice(question: str) -> bool:
    return bool(ADVICE_ASK_RE.search(question)) or bool(ADVICE_JUDGMENT_RE.search(question)) or bool(OWN_MONEY_RE.search(question)) or (
        bool(TRADE_WORD_RE.search(question)) and bool(DECISION_CUE_RE.search(question))
    )


# ---- questions about something this app does not hold ----

# Assets and topics with no data here. Listed by name because a question about one of them with no company in it used to be
# answered from whichever filing mentions it ("What did Bitcoin do this month?" from Tesla's Bitcoin note).
OUTSIDE_ASSET_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|ether|crypto(?:currenc\w+)?|dogecoin|solana|nfts?|gold|silver|platinum|crude(?:\s+oil)?|oil|brent|"
    r"natural\s+gas|copper|wheat|treasur(?:y|ies)|bond\s+yields?|mortgage\s+rates?|interest\s+rates?|inflation|cpi|gdp|recession|"
    r"unemployment|jobs\s+report|the\s+fed|federal\s+reserve|fomc|exchange\s+rates?|forex|the\s+(?:dollar|euro|yen|pound)|"
    r"housing\s+market|central\s+banks?|ecb|bank\s+of\s+(?:england|japan)|rate\s+(?:hikes?|cuts?))\b",
    re.IGNORECASE,
)
# A question that is about what the stored filings say, or compares the tracked companies, is a research question even when
# it mentions Bitcoin or interest rates ("Which of the companies mention interest rate risk?"): never declined.
FILINGS_CUE_RE = re.compile(
    r"\b(?:companies|company|which|mention\w*|disclos\w*|discuss\w*|filings?|10-?[kq]s?|annual\s+reports?|quarterly\s+reports?|"
    r"risk\s+factors?|according\s+to|exposure|exposed|each|every|any\s+of|all\s+of|across)\b",
    re.IGNORECASE,
)
# Well-known public companies this app is not tracking. A list, because telling "Intel" from an ordinary capitalised word is
# not something a rule can do; it goes stale, and a company missing from it is simply answered as before (from the filings,
# which say they do not contain it). Ambiguous words (Target, Visa, Ford, Shell, Block, Square) are left out on purpose.
UNTRACKED_COMPANIES = (
    "Meta Platforms", "Facebook", "Netflix", "Intel", "Walmart", "Disney", "Coca-Cola", "PepsiCo", "Nike", "Boeing", "Exxon",
    "ExxonMobil", "Chevron", "JPMorgan", "Goldman Sachs", "Bank of America", "Wells Fargo", "Citigroup", "Mastercard", "Oracle",
    "Salesforce", "Adobe", "IBM", "Cisco", "Qualcomm", "Broadcom", "Uber", "Lyft", "Airbnb", "PayPal", "Starbucks",
    "McDonald's", "Costco", "Home Depot", "Lowe's", "Pfizer", "Moderna", "Johnson & Johnson", "UnitedHealth",
    "Berkshire Hathaway", "Procter & Gamble", "Verizon", "AT&T", "Comcast", "Spotify", "Pinterest", "Shopify", "Palantir",
    "Snowflake", "CrowdStrike", "ServiceNow", "Micron", "Texas Instruments", "Lockheed Martin", "Caterpillar", "Toyota",
    "Honda", "Ferrari", "Rivian", "Lucid", "GameStop", "Robinhood", "Coinbase", "Samsung", "Sony", "Alibaba", "Tencent",
    "Baidu", "ASML", "Zoom",
)
CAPITALISED_ONLY = {"Intel", "Oracle", "Lucid", "Snowflake", "Uber", "Micron", "Cisco", "Sony", "Zoom"}  # also ordinary words: need the capital
UNTRACKED_COMPANY_RE = re.compile(
    r"(?<![\w&])(" + "|".join(re.escape(n) for n in sorted(UNTRACKED_COMPANIES, key=len, reverse=True)) + r")(?![\w&])",
    re.IGNORECASE,
)
# Not a research question at all: writing, jokes, recipes, the weather, sports scores.
NOT_RESEARCH_RE = re.compile(
    r"^\W*(?:please\s+)?(?:write|compose|draft|create|generate)\s+(?:me\s+|us\s+)?(?:a|an|some|the)\s+(?:[\w-]+\s+){0,2}"
    r"(?:poem|song|story|joke|essay|haiku|limerick|rap|speech|tweet)\b|"
    r"\btell\s+me\s+(?:a\s+)?(?:joke|story)\b|\b(?:recipes?|weather|who\s+won|final\s+score|horoscope|lyrics)\b",
    re.IGNORECASE,
)


def outside_scope(question: str) -> tuple[str, str] | None:
    """("asset" | "company" | "chat", name) when the question is about something this app does not hold, else None. The
    caller must only use it for a question that names no tracked company: this looks at the words alone."""
    if NOT_RESEARCH_RE.search(question):
        return "chat", ""
    if FILINGS_CUE_RE.search(question):
        return None
    for m in UNTRACKED_COMPANY_RE.finditer(question):
        name = next(n for n in UNTRACKED_COMPANIES if n.lower() == m.group(1).lower())
        if name in CAPITALISED_ONLY and m.group(1) != name:
            continue  # "any intel on the market", "a lucid argument": the word, not the company
        return "company", name
    if OUTSIDE_ASSET_RE.search(question):
        return "asset", ""
    return None


def join_names(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@dataclass(frozen=True)
class Intent:
    prices: bool = False
    headlines: bool = False
    sentiment: bool = False
    filings: bool = True
    fundamentals: frozenset[str] = frozenset()  # the financial figures asked for (pe, market_value, revenue, ...)
    unstored: tuple[str, ...] = ()  # ratios asked for that this app doesn't compute (dividend yield, price-to-book, ...)
    unstored_only: bool = False  # True when that is the whole question: nothing else here can be answered
    advice: bool = False  # the question asks for a buy, sell, or hold call

    @property
    def market(self) -> bool:
        return self.prices or self.headlines or self.sentiment or bool(self.fundamentals)


def detect_intent(question: str) -> Intent:
    """Which kinds of evidence the question needs. Plain keyword rules, so the choice is predictable and testable.
    With no market wording the copilot behaves exactly as it did before (filings only)."""
    advice = asks_for_advice(question)
    unstored, question = unstored_figures(question)
    share_count = bool(HOW_MANY_SHARES_RE.search(question)) and not SHARES_ACTION_RE.search(question)
    question = HOW_MANY_SHARES_RE.sub(" ", question)  # "shares does" is not a price verb, so cut the phrase out first
    # "stock" plus a named period ("Apple stock or Microsoft stock, this month?") is a price question even without a verb
    price_text = re.sub(MARKET_VALUE_PATTERN, " ", question, flags=re.IGNORECASE)  # "How much is Apple worth?" is not "how much is" a price
    if not STOCK_WORD_RE.search(question):  # "How much did Apple earn / pay in dividends?" asks about money, not the stock price
        price_text = HOW_MUCH_MONEY_RE.sub(" ", price_text)
    topics, rest = question_topics(question)
    prices = (
        bool(PRICE_RE.search(price_text)) or bool(INDEX_RE.search(question)) or bool(BARE_STOCK_RE.search(question))
        or (bool(STOCK_NOUN_RE.search(question)) and parse_window(question).explicit)
        or (bool(PERIOD_MOVE_RE.search(question)) and parse_window(question).explicit)
        or year_start_comparison(question)
        or bool(CLOSE_NOUN_RE.search(question))
        or bool(PRICE_PREDICTION_RE.search(question))
        or (
            bool(PRICE_MOVE_NOUN_RE.search(question)) and bool(CAUSE_RE.search(question))
            and (parse_window(question).explicit or bool(STOCK_NOUN_RE.search(question)))
        )
        or (bool(PRICE_CLAIM_RE.search(question)) and (parse_window(question).explicit or bool(STOCK_NOUN_RE.search(question))))
        or (bool(PERIOD_COMPARE_RE.search(question)) and not topics and parse_window(question).explicit)  # not "revenue than a year ago"
    )
    sentiment = bool(SENTIMENT_RE.search(question))
    general = bool(GENERAL_RE.search(question)) and not STOCK_WORD_RE.search(question)  # "How's Nvidia doing?" wants both
    headlines = bool(NEWS_RE.search(question)) or sentiment or general or (prices and bool(CAUSE_RE.search(question)))
    if share_count:
        topics = topics | {"shares"}
    market = prices or headlines or sentiment or bool(topics)
    # The words that sent the question to the figures ("revenue", "income") aren't also a reason to search the filings
    return Intent(
        prices, headlines, sentiment, filings=not market or bool(FILING_RE.search(rest)), fundamentals=topics,
        unstored=unstored, unstored_only=bool(unstored) and not market and not FILING_RE.search(rest), advice=advice,
    )


# ---- how far back? ----


@dataclass(frozen=True)
class Window:
    label: str
    days: Optional[int]  # calendar days back from the latest stored price; None means since the start of the year
    explicit: bool = False  # False when the question named no period and the default was used
    since: Optional[date] = None  # "since July": the first day of the window, which wins over `days` when pricing it
    unmet: Optional[str] = None  # a period the question named that no window here can match ("the end of last week")
    asked_day: Optional[str] = None  # "today" or "yesterday": checked against the newest stored close


DEFAULT_WINDOW = Window("past month", 31)
_WINDOWS = [  # checked in order, so the specific forms win
    (r"year[-\s]to[-\s]date|\bytd\b|this\s+(?:calendar\s+)?year|so\s+far\s+this\s+year|year\s+so\s+far|"
     r"(?:start|beginning)\s+of\s+(?:the\s+|this\s+)?year|since\s+(?:january|jan\b)|since\s+new\s+year",
     Window("year to date", None, True)),
    (r"\b(?:5|five)[-\s]years?\b", Window("past 5 years", 1830, True)),  # "5-year" as well as "5 years"
    (r"\b(?:6|six)[-\s]months?\b|\bhalf[-\s]year\b", Window("past 6 months", 183, True)),
    (r"\b(?:3|three)[-\s]months?\b|\bquarter\b|\b90\s+days\b", Window("past 3 months", 92, True)),
    (r"\b(?:12|twelve)[-\s]months?\b|\b(?:1|one)[-\s]year\b|52[-\s]?week|\byear\b", Window("past year", 366, True)),
    (r"\bmonth(?:ly)?\b|\b30\s+days\b", Window("past month", 31, True)),
    (r"\b(?:2|two)[-\s]weeks?\b|\bfortnight\b|\b14\s+days\b", Window("past 2 weeks", 14, True)),  # before "week", which it contains
    (r"\bweek(?:ly)?\b|\b(?:7|seven)\s+days\b", Window("past week", 7, True)),
    (r"\btoday\b|\byesterday\b|\bpast\s+day\b|\b(?:1|one)\s+day\b|\b24\s+hours\b", Window("past day", 1, True)),
]


_ONES = "one|two|three|four|five|six|seven|eight|nine"
_TEENS = "ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_BELOW_100 = rf"(?:(?:{_TENS})(?:[-\s](?:{_ONES}))?|{_TEENS}|{_ONES})"
# "ninety", "forty-five", "two hundred", "one hundred and twenty", "a hundred": a number written out, up to 999
_NUMBER_WORD = rf"(?:(?:a|{_ONES})\s+hundred(?:\s+(?:and\s+)?{_BELOW_100})?|hundred|{_BELOW_100})"
_NUM = rf"(?:\d{{1,4}}|{_NUMBER_WORD})"
_WORD_VALUES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen".split())}
_WORD_VALUES.update({w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})
_ROUGH_AMOUNTS = {"few": 3, "couple": 2, "several": 4}  # "the last few weeks": a guess, and the label says so
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_MONTH_RE = r"(?:" + "|".join(_MONTHS) + r"|sept)"
_UNIT_RE = r"(trading\s+days?|sessions?|days?|weeks?|months?|quarters?|years?)"
_NUMBERED_PERIOD_RE = re.compile(
    rf"\b(?:last|past|previous)\s+(?:({_NUM})|(few|couple(?:\s+of)?|several))\s+{_UNIT_RE}\b", re.IGNORECASE,
)
# The lengths the app has always used for these, so a number written out in words keeps its old label and length.
_CANONICAL = {
    (1, "day"): Window("past day", 1, True), (7, "day"): Window("past week", 7, True),
    (14, "day"): Window("past 2 weeks", 14, True), (30, "day"): Window("past month", 31, True),
    (90, "day"): Window("past 3 months", 92, True),
    (1, "week"): Window("past week", 7, True), (2, "week"): Window("past 2 weeks", 14, True),
    (1, "month"): Window("past month", 31, True), (3, "month"): Window("past 3 months", 92, True),
    (6, "month"): Window("past 6 months", 183, True), (12, "month"): Window("past year", 366, True),
    (1, "year"): Window("past year", 366, True), (5, "year"): Window("past 5 years", 1830, True),
    (1, "quarter"): Window("past 3 months", 92, True),
}
# A trading day is about 5 of every 7 calendar days, so 10 sessions reach back about 14 calendar days.
_UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 30.5, "quarter": 91.5, "year": 366.0, "session": 1.4}
MAX_NUMBERED_DAYS = 3660
_AGO_PERIOD_RE = re.compile(rf"\b({_NUM})\s+{_UNIT_RE}\s+ago\b", re.IGNORECASE)
# "a year and a half", "two and a half years": exact, with the half in the label
_HALF_PERIOD_RES = (
    re.compile(rf"\b(an?|last|past|previous|{_NUM})\s+(year|month|week|quarter)s?\s+and\s+a\s+half\b", re.IGNORECASE),
    re.compile(rf"\b({_NUM})\s+and\s+a\s+half\s+(year|month|week|quarter)s?\b", re.IGNORECASE),
)
_DECADE_RE = re.compile(r"\b(?:last|past|previous)\s+decade\b", re.IGNORECASE)
_DECADE = Window("past 10 years", 3660, True)


def _to_int(raw: str) -> int:
    """"18", "ninety", "forty-five", "two hundred", "a hundred", "one hundred and twenty"."""
    raw = raw.lower().strip()
    if raw.isdigit():
        return int(raw)
    total = current = 0
    for token in re.split(r"[-\s]+", raw):
        if token == "and":
            continue
        if token == "a":
            current = 1
        elif token == "hundred":
            total += (current or 1) * 100
            current = 0
        else:
            current += _WORD_VALUES[token]
    return total + current


def _unit_key(unit: str) -> str:
    unit = unit.lower()
    return "session" if unit.startswith(("trading", "session")) else unit.rstrip("s")


def _numbered_period(question: str) -> Optional[Window]:
    """"the last four weeks", "past ninety days", "the last few weeks", "six weeks ago", "a year and a half", "past decade",
    "the last 8 quarters", "the last 10 trading days". None when the number is out of range."""
    if _DECADE_RE.search(question):
        return _DECADE
    for half in _HALF_PERIOD_RES:
        if h := half.search(question):
            n, unit = _to_int("1" if h.group(1).lower() in ("a", "an", "last", "past", "previous") else h.group(1)) + 0.5, h.group(2).lower()
            return Window(f"past {n:g} {unit}s", int(round(n * _UNIT_DAYS[unit])), True)
    m = _NUMBERED_PERIOD_RE.search(question)
    if m:
        number, rough, unit = m.group(1), m.group(2), _unit_key(m.group(3))
    elif a := _AGO_PERIOD_RE.search(question):  # "than it was six weeks ago": the window back to then
        number, rough, unit = a.group(1), None, _unit_key(a.group(2))
    else:
        return None
    if rough:  # few / couple / several
        word = re.sub(r"\s+of$", "", rough.lower())
        n, note = _ROUGH_AMOUNTS[word], f" (reading '{word}' as {_ROUGH_AMOUNTS[word]})"
    else:
        n, note = _to_int(number), ""
    if n < 1 or n * _UNIT_DAYS[unit] > MAX_NUMBERED_DAYS:
        return None
    if not note and (n, unit) in _CANONICAL:
        return _CANONICAL[(n, unit)]
    if unit == "session":
        days = int(math.ceil(n * _UNIT_DAYS[unit]))
        return Window(f"past {n} trading day{'' if n == 1 else 's'} (about {days} calendar day{'' if days == 1 else 's'})", days, True)
    return Window(f"past {n} {unit}{'' if n == 1 else 's'}{note}", int(round(n * _UNIT_DAYS[unit])), True)


_SINCE_YEAR_RE = re.compile(r"\bsince\s+(?:the\s+(?:start|beginning)\s+of\s+)?((?:19|20)\d\d)\b", re.IGNORECASE)


def _since_year(question: str, today: date) -> Optional[Window]:
    """"since 2024" (or "since the start of 2024"): from January 1 of that year. This year is year to date; a year that has not
    come is not read (the caller flags it)."""
    m = _SINCE_YEAR_RE.search(question)
    if not m:
        return None
    year = int(m.group(1))
    if year == today.year:
        return _WINDOWS[0][1]
    if year > today.year:
        return None
    since = date(year, 1, 1)
    return Window(f"since January 1, {year}", (today - since).days, True, since=since)


_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_SINCE_WEEKDAY_RE = re.compile(rf"\bsince\s+({_WEEKDAY})\b", re.IGNORECASE)


def _since_weekday(question: str, today: date) -> Optional[Window]:
    """"since Monday": from the most recent Monday before today (a week ago when today is one). "Since last Monday" is left
    alone: on a Monday it could mean either, so it is flagged instead."""
    m = _SINCE_WEEKDAY_RE.search(question)
    if not m:
        return None
    name = m.group(1).lower()
    days_back = (today.weekday() - _WEEKDAY_NAMES.index(name)) % 7 or 7
    since = today - timedelta(days=days_back)
    return Window(f"since {name.capitalize()} {since}", days_back, True, since=since)


_SINCE_MONTH_RE = re.compile(
    rf"\bsince\s+(?:(?:the\s+)?(?:start|beginning)\s+of\s+|(?P<middle>(?:the\s+)?middle\s+of\s+|mid[\s-]+))?(?P<month>{_MONTH_RE})\b",
    re.IGNORECASE,
)


def _since_month(question: str, today: date) -> Optional[Window]:
    """"since July": from the first of that month, this year, or last year when the month has not come yet. January is
    left to the year-to-date window, which is the same thing. "Since the middle of August" (or "mid-August") starts on the
    15th, and the label says that is how it was read. "Since the end of August" and "late August" are not read: nothing in the
    daily closes marks them, and a guess of the 25th would be a made-up period."""
    m = _SINCE_MONTH_RE.search(question)
    if not m:
        return None
    middle = m.group("middle") is not None
    name = m.group("month").lower()
    month = 9 if name == "sept" else _MONTHS.index(name) + 1
    if month == 1 and not middle:
        return None
    day = 15 if middle else 1
    since = date(today.year, month, day)
    if since > today:  # the month has not come yet this year (or its middle has not)
        since = date(today.year - 1, month, day)
    label = f"since {_MONTHS[month - 1].capitalize()} 15 (reading 'the middle' as the 15th)" if middle else f"since {_MONTHS[month - 1].capitalize()} 1"
    return Window(label, (today - since).days, True, since=since)


# Periods the stored daily closes cannot isolate: a day or a calendar stretch. The window used is the nearest one, and
# the answer is told (and the reader warned) that it is not the period asked. "last month" and "this week" are not here:
# people use them loosely for "the past month" and "the past week", and a warning on every one would be noise.
_UNMET_PATTERNS = [
    r"\b(?:the\s+)?end\s+of\s+(?:last|this|the)\s+(?:week|month|quarter|year)\b",
    r"\b(?:on|last)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    rf"\b(?:on\s+)?{_MONTH_RE}\s+\d{{1,2}}(?:st|nd|rd|th)?\b",
    rf"\b(?:in|during)\s+{_MONTH_RE}\b",
    r"\bq[1-4]\b|\b(?:first|second|third|fourth)\s+quarter\b",
    r"\b(?:in|during|for)\s+20\d\d\b",
]


def _unmet_period(question: str) -> Optional[str]:
    for pattern in _UNMET_PATTERNS:
        if m := re.search(pattern, question, re.IGNORECASE):
            return m.group(0)
    return None


# Periods that are named but that nothing above reads. Checked only when no window was read at all, so a question that fell
# to the default month says so (a caution on the answer) instead of passing the month off as the period asked. The last
# pattern is the net: "since" and up to four more words, which catches "since earnings", "since the election", "since the IPO".
_UNREAD_PATTERNS = [
    rf"\b(?:early|late)\s+{_MONTH_RE}\b|\b(?:the\s+)?(?:end|middle)\s+of\s+{_MONTH_RE}\b|\bmid[\s-]?{_MONTH_RE}\b",
    rf"\bbetween\s+(?:{_MONTH_RE}|20\d\d)\s+and\s+(?:{_MONTH_RE}|20\d\d)\b",
    rf"\bfrom\s+(?:{_MONTH_RE}|20\d\d)\s+(?:to|through|until)\s+(?:{_MONTH_RE}|20\d\d)\b",
    r"\b(?:over|during|throughout|across)\s+the\s+(?:summer|winter|spring|fall|autumn|holidays?|holiday\s+season)\b",
    r"\ball[-\s]time\b|\bsince\s+inception\b|\bthe\s+last\s+time\b",
    r"\bsince\s+[\w'’-]+(?:\s+[\w'’-]+){0,3}",
]


def _unread_period(question: str) -> Optional[str]:
    for pattern in _UNREAD_PATTERNS:
        if m := re.search(pattern, question, re.IGNORECASE):
            return m.group(0)
    return None


def parse_window(question: str, today: Optional[date] = None) -> Window:
    today = today or date.today()
    window = _read_window(question, today)
    unmet = _unmet_period(question)
    if not unmet and not window.explicit:
        unmet = _unread_period(question)
    asked = "today" if re.search(r"\btoday\b", question, re.IGNORECASE) else (
        "yesterday" if re.search(r"\byesterday\b", question, re.IGNORECASE) else None)
    if unmet or asked:
        window = replace(window, unmet=unmet, asked_day=asked)
    return window


def _read_window(question: str, today: date) -> Window:
    if year_start_comparison(question, today):
        return _WINDOWS[0][1]  # year to date
    if (
        (w := _since_month(question, today)) or (w := _since_year(question, today)) or (w := _since_weekday(question, today))
        or (w := _numbered_period(question))
    ):
        return w
    for pattern, window in _WINDOWS:
        if re.search(pattern, question, re.IGNORECASE):
            return window
    return DEFAULT_WINDOW


def period_cautions(window: Window, evidence: list, today: Optional[date] = None) -> list[str]:
    """Warnings, attached in code, for a period the question named that the price source does not cover. Only when a price
    source was given: with none, there is no wrong period to warn about."""
    today = today or date.today()
    prices = [e for e in evidence if e.kind == "price"]
    newest = [e.as_of for e in prices]
    if not newest:  # headlines only: the same warning for a period the news window cannot match
        if window.unmet and any(e.kind in ("headline", "sentiment") for e in evidence):
            return [
                f"You asked about “{window.unmet}”, which the stored headlines can't isolate. The answer uses the last "
                f"{news_days(window)} days of headlines, so it may not be the period you meant."
            ]
        return []
    oldest = min(newest)
    out = []
    if window.unmet:
        out.append(
            f"You asked about “{window.unmet}”, which the stored daily prices can't isolate. The answer uses the "
            f"{window.label}, up to the close on {oldest}, so it may not be the period you meant."
        )
    for e in prices:  # a window that reaches back past the first stored close is measured from that close
        if e.starts:
            out.append(
                f"The stored daily prices for {e.symbol} start on {e.starts}, so the change is measured from then, not over "
                f"the full {window.label} you asked about."
            )
    if window.asked_day == "today" and oldest != today:
        out.append(f"You asked about today, but the newest stored close is from {oldest}, so the answer is not about today.")
    elif window.asked_day == "yesterday" and oldest != today - timedelta(days=1):
        out.append(f"You asked about yesterday, but the newest stored close is from {oldest}, so the answer may not be about yesterday.")
    return out


# ---- a move the question assumes, checked against the stored closes ----

_UP_VERBS = r"rise|rose|rises|jump(?:ed|s)?|surg(?:e|ed|es)|soar(?:ed|s)?|gain(?:ed|s)?|climb(?:ed|s)?|rall(?:y|ied|ies)|spik(?:e|ed|es)|increas(?:e|ed|es)|up"
_DOWN_VERBS = (
    r"fall|fell|falls|drop(?:ped|s)?|plung(?:e|ed|es)|sink|sank|tumbl(?:e|ed|es)|slid(?:e|es)?|slump(?:ed|s)?|crash(?:ed|es)?|"
    r"declin(?:e|ed|es)|los(?:t|e|es)|tank(?:ed|s)?|down"
)
_PCT_CLAIM_RE = re.compile(
    rf"\b(?P<verb>{_UP_VERBS}|{_DOWN_VERBS})\s+(?:by\s+|about\s+|nearly\s+|over\s+|around\s+|more\s+than\s+)?"
    r"(?P<n>\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_UP_RE = re.compile(rf"(?:{_UP_VERBS})$", re.IGNORECASE)
# the least a move must be for the question's word to be fair: "doubled" is +100%, so +80% or more passes; "halved" is -50%
_MULTIPLE_CLAIMS = (
    (re.compile(r"\bdoubl(?:e|ed|es|ing)\b", re.IGNORECASE), 80.0, "min"),
    (re.compile(r"\btripl(?:e|ed|es|ing)\b", re.IGNORECASE), 160.0, "min"),
    (re.compile(r"\bquadrupl(?:e|ed|es|ing)\b", re.IGNORECASE), 240.0, "min"),
    (re.compile(r"\bhalv(?:e|ed|es|ing)\b|\b(?:dropp(?:ed|ing)|fell|falling|cut|down|lost|losing)\s+(?:by\s+|in\s+)half\b", re.IGNORECASE), -40.0, "max"),
)
_STRONG_UP_RE = re.compile(r"\b(?:soar\w*|skyrocket\w*|surg(?:e|ed|es|ing)|spik(?:e|ed|es|ing)|rocket\w*|explod\w*)\b", re.IGNORECASE)
_STRONG_DOWN_RE = re.compile(r"\b(?:crash\w*|plung\w*|plummet\w*|tank(?:ed|s|ing)?|collaps\w*|crater\w*|nosedive\w*|tumbl\w*)\b", re.IGNORECASE)
STRONG_MOVE_PCT = 3.0  # "soared" and "crashed" need at least this much, in the right direction
_PREDICTION_WORDS_RE = re.compile(
    r"\b(?:will|would|could|might|may|can|if|whether|going\s+to|about\s+to|likely\s+to|what\s+if)\b", re.IGNORECASE
)


def _claims(question: str):
    """(the words as written, a test of the actual percentage change) for each move the question asserts or asks about. Predictions and
    hypotheticals ("will soar", "could crash", "what if it doubles") are skipped: there is nothing to compare."""
    found, taken = [], []

    def usable(m) -> bool:
        sentence_start = max(question.rfind(c, 0, m.start()) for c in ".?!") + 1
        return not _PREDICTION_WORDS_RE.search(question[sentence_start:m.start()])

    for m in _PCT_CLAIM_RE.finditer(question):
        if not usable(m):
            continue
        n = float(m.group("n"))
        signed = n if _UP_RE.match(m.group("verb")) else -n
        ok = lambda actual, signed=signed: (
            abs(actual - signed) <= 1.0 or (actual * signed > 0 and 0.5 <= abs(actual) / abs(signed) <= 2.0)
        )
        found.append((m.start(), m.group(0), ok))
        taken.append(m.span())
    for pattern, bound, kind in _MULTIPLE_CLAIMS:
        for m in pattern.finditer(question):
            if usable(m):
                test = (lambda actual, b=bound: actual >= b) if kind == "min" else (lambda actual, b=bound: actual <= b)
                found.append((m.start(), m.group(0), test))
                taken.append(m.span())
    for pattern, test in ((_STRONG_UP_RE, lambda actual: actual >= STRONG_MOVE_PCT), (_STRONG_DOWN_RE, lambda actual: actual <= -STRONG_MOVE_PCT)):
        for m in pattern.finditer(question):
            if usable(m) and not any(a <= m.start() < b for a, b in taken):
                found.append((m.start(), m.group(0), test))
    return [(phrase, ok) for _, phrase, ok in sorted(found, key=lambda t: t[0])]


def premise_cautions(question: str, evidence: list, window: Window) -> list[str]:
    """A plain statement of what the stored closes show when the question assumes a move they do not support ("Google doubled this
    month" when it rose 1%). It quotes the claim and the data and never calls the question wrong. Silent when there is nothing to compare:
    no price source, several companies, a period that could not be read, a prediction. At most one statement."""
    prices = [e for e in evidence if e.kind == "price"]
    if len(prices) != 1 or window.unmet or prices[0].change_pct is None:
        return []
    e = prices[0]
    for phrase, supported in _claims(question):
        if not supported(e.change_pct):
            return [
                f"You mention that {e.symbol} “{phrase}”; the stored closes show {e.change_pct:+.1f}% over the {window.label}, "
                "so the question may assume a move that did not happen."
            ]
    return []


def news_days(window: Window) -> int:
    """Headlines default to the last week; a named period is honored up to 90 days."""
    if not window.explicit:
        return 7
    return min(window.days or 90, 90)  # a "since July" window has its own length in `days`


# ---- the evidence ----


def _money(x) -> str:
    return f"{float(x):.2f}"


def _direction(change: float, pct: float) -> str:
    """In words, so a question that assumes the wrong direction can't talk the model into it."""
    if round(change, 2) == 0 and round(pct, 2) == 0:
        return "no change"
    return "a rise" if change > 0 else "a fall"


def price_evidence(conn: psycopg.Connection, symbol: str, window: Window, today: Optional[date] = None) -> Optional[MarketEvidence]:
    today = today or date.today()
    latest = conn.execute("SELECT max(ts) FROM prices_daily WHERE symbol = %s", (symbol,)).fetchone()[0]
    if latest is None:
        return None
    reach = max(window.days or 366, 366) + 10
    if window.since:
        reach = max(reach, (latest - window.since).days + 10)
    rows = conn.execute(
        "SELECT ts, close FROM prices_daily WHERE symbol = %s AND ts >= %s ORDER BY ts",
        (symbol, latest - timedelta(days=reach)),
    ).fetchall()
    last_ts, last_close = rows[-1]
    if window.since:
        start = window.since
    else:
        start = date(last_ts.year - 1, 12, 31) if window.days is None else last_ts - timedelta(days=window.days)
    before = [r for r in rows if r[0] <= start]
    base_ts, base_close = before[-1] if before else rows[0]
    in_window = [r for r in rows if r[0] >= base_ts]
    high = max(in_window, key=lambda r: r[1])
    low = min(in_window, key=lambda r: r[1])
    year = [r for r in rows if r[0] > last_ts - timedelta(days=365)]
    change = float(last_close) - float(base_close)
    pct = change / float(base_close) * 100 if base_close else 0.0

    lines = [
        f"{symbol} daily closing prices, from stored data.",
        f"Window: {window.label}, from {base_ts} to {last_ts} ({len(in_window) - 1} trading days).",
        f"Latest close: {_money(last_close)} on {last_ts}.",
        f"Close on {base_ts}: {_money(base_close)}.",
        f"Change over the window: {change:+.2f} ({pct:+.2f}%), {_direction(change, pct)}.",
        f"Highest close in the window: {_money(high[1])} on {high[0]}. Lowest close in the window: {_money(low[1])} on {low[0]}.",
        f"52-week closing range: {_money(min(r[1] for r in year))} to {_money(max(r[1] for r in year))}.",
    ]
    if not before:
        lines.append(f"Note: stored prices only start on {base_ts}, so the change is measured from then.")
    if (today - last_ts).days > STALE_AFTER_DAYS:
        lines.append(f"Note: stored prices end on {last_ts}; newer prices have not been loaded.")
    elif last_ts == today:
        lines.append("Note: the latest day may be a partial trading day.")
    if window.asked_day == "today" and last_ts != today:
        lines.append(f"Note: the question asked about today ({today}), but the newest stored close is from {last_ts}; no close for today is stored.")
    elif window.asked_day == "yesterday" and last_ts != today - timedelta(days=1):
        lines.append(f"Note: the question asked about yesterday, but the newest stored close is from {last_ts}.")
    if window.unmet:
        lines.append(
            f"Note: the question asked about “{window.unmet}”, which these daily closes do not isolate; the figures above "
            f"are for the {window.label}, from {base_ts} to {last_ts}."
        )
    header = f"{symbol} price data (stored daily closes), as of {last_ts}"
    # A week of slack: the window starts on a weekend or holiday, or the first stored close is a few days later.
    late_start = base_ts if not before and (base_ts - start).days > LATE_START_SLACK_DAYS else None
    return MarketEvidence("price", symbol, header, "\n".join(lines), None, last_ts, change=change, change_pct=pct, starts=late_start)


def headline_evidence(conn: psycopg.Connection, symbol: str, model: str, days: int, limit: int = NEWS_PER_COMPANY) -> list[MarketEvidence]:
    rows = conn.execute(
        "SELECT a.title, a.publisher, a.url, a.published_at, n.label "
        "FROM news_articles a JOIN news_article_symbols s ON s.article_id = a.id AND s.symbol = %(s)s "
        "LEFT JOIN news_sentiment n ON n.article_id = a.id AND n.symbol = s.symbol AND n.model = %(m)s "
        "WHERE a.published_at >= now() - make_interval(days => %(d)s) AND n.label IS DISTINCT FROM 'irrelevant' "
        "ORDER BY a.published_at DESC LIMIT %(l)s",
        {"s": symbol, "m": model, "d": days, "l": limit * 8},
    ).fetchall()
    seen, out = set(), []
    for title, publisher, url, published, label in rows:  # the same story often arrives from several sources
        key = title_key(title, publisher)
        if key in seen or is_quote_page(title):  # the copilot leaves quote pages out of its sources
            continue
        seen.add(key)
        day = published.astimezone(timezone.utc).date() if isinstance(published, datetime) else published
        header = f"{symbol} headline, {publisher or 'unknown publisher'}, {day}, automatic label: {label or 'not labeled'}"
        out.append(MarketEvidence("headline", symbol, header, title, url, day))
        if len(out) == limit:
            break
    return out


def sentiment_evidence(conn: psycopg.Connection, symbol: str, model: str, days: int, today: Optional[date] = None) -> Optional[MarketEvidence]:
    s = summarize(conn, symbol, model, days)
    if s.counted + s.irrelevant == 0:
        return None
    score = "no score" if s.score is None else f"{s.score:+.2f}"
    text = (
        f"Headlines from the last {days} days, labeled automatically by an AI model ({model}), counting each story once "
        "and leaving out stock-quote and comparison pages: "
        f"{s.positive} positive, {s.neutral} neutral, {s.negative} negative, {s.irrelevant} not actually about the company.\n"
        f"Score: {score} (positives minus negatives, divided by the relevant headlines). Most headlines are labeled "
        "neutral, so scores stay close to zero. The labels are imperfect."
    )
    return MarketEvidence("sentiment", symbol, f"{symbol} headline sentiment summary, last {days} days", text, None, today or date.today())


def _growth_line(label: str, flow) -> tuple[Optional[str], Optional[float]]:
    """A growth figure with its direction in words (so a question assuming the wrong direction can't talk the model into
    it) and the same figure in percent for the direction check."""
    if flow is None or flow.growth is None:
        return None, None
    pct = flow.growth * 100
    word = "no change" if round(pct, 1) == 0 else ("an increase" if pct > 0 else "a decrease")
    # Says what the rate is measured on, and that it isn't the growth of the 12-month total: a model once wrote "revenue
    # for the last 12 months was $303.0 billion, an increase of 95.8%" when 95.8% compared only the latest 6 months.
    return (f"{label} growth: {flow.growth:+.1%}, {word}. Measured on {flow.growth_label}"
            f"{'' if flow.growth_label.startswith('the 12 months') else ' only (not the growth of the 12-month total)'}."), pct


def evidence_from_fundamentals(f: Fundamentals, today: Optional[date] = None) -> MarketEvidence:
    """The company's financial figures as one numbered source. Every number was worked out in Python
    (data/fundamentals.py); the cautions are written into the text and also carried separately so the copilot can attach
    the relevant ones to the answer itself, whether or not the model repeats them."""
    sym = f.symbol
    if not f.available:
        text = f"{sym} financial figures are not available: {f.unavailable_reason}."
        return MarketEvidence("fundamentals", sym, f"{sym} financial figures (not available)", text, None,
                              f.close_date or today or date.today())
    lines = [
        f"{sym} financial figures, calculated in Python from the company's SEC 10-K and 10-Q filings and the latest stored price.",
        f"Latest reported period ends {f.period_end}. Every figure covers the last 12 months unless it says otherwise.",
    ]
    growths: list[float] = []

    def flow_lines(label: str, flow, fmt) -> None:
        if flow is None:
            return
        lines.append(f"{label} (last 12 months): {fmt(flow.value)}. How: {flow.how}.")
        line, pct = _growth_line(label, flow)
        if line:
            lines.append(line)
            growths.append(pct)

    flow_lines("Revenue", f.revenue, format_money)
    flow_lines("Net income", f.net_income, format_money)
    flow_lines("Diluted earnings per share", f.diluted_eps, lambda v: f"${v:.2f}")
    flow_lines("Operating income", f.operating_income, format_money)
    for label, value in (("Gross margin", f.gross_margin), ("Operating margin", f.operating_margin), ("Net margin", f.net_margin)):
        if value is not None:
            lines.append(f"{label}: {value:.1%}.")
    if f.shares:
        lines.append(f"Shares outstanding: {f.shares.value / 1e9:.2f} billion, from {f.shares.source}.")
    if f.close is not None:
        lines.append(f"Latest stored close: {f.close:.2f} on {f.close_date}.")
    lines.append(f"Market value: {format_money(f.market_value)} (shares outstanding x latest stored close)."
                 if f.market_value else "Market value: not available (no share count or no stored price).")
    lines.append(f"P/E ratio: {f.pe:.1f} (the latest stored close divided by diluted earnings per share for the last 12 months)."
                 if f.pe else f"P/E ratio: {f.pe_note or 'not available'}.")
    lines += [f"CAUTION: {c}." for c in f.cautions]
    return MarketEvidence(
        "fundamentals", sym, f"{sym} financial figures from SEC filings (calculated), latest period ends {f.period_end}",
        "\n".join(lines), None, f.period_end, growth_pcts=tuple(growths),
        cautions=tuple((c, f.caution_scopes.get(c, ("all",))) for c in f.cautions),
    )


def fundamentals_evidence(conn: psycopg.Connection, symbol: str, today: Optional[date] = None) -> MarketEvidence:
    close, close_date = latest_close(conn, symbol)
    return evidence_from_fundamentals(compute(symbol, load_facts(conn, symbol), close, close_date, today), today)


# What each kind of question is about, in the terms the cautions are tagged with (see Fundamentals.caution_scopes).
TOPIC_SCOPES = {
    "pe": ("pe", "eps", "net_income"),
    "eps": ("eps", "pe", "net_income", "net_margin"),
    "profit": ("net_income", "eps", "pe", "net_margin"),
    "margin": ("net_margin",),
    "market_value": ("market_value", "shares"),
    "shares": ("shares", "market_value"),
    "revenue": ("revenue",),
}


def relevant_cautions(evidence: list, topics: frozenset[str], answer: str) -> list[str]:
    """The financial-figure cautions that concern what the question asked or the answer actually said, in words fit to
    show with the answer. Added in code, not left to the model: a correct P/E can still mislead (Alphabet's is flattered
    by investment gains), and a model that forgets the warning must not be able to hide it."""
    asked = set(topics) | set(figure_topics(answer))
    everything = "general" in asked
    wanted = {s for t in asked for s in TOPIC_SCOPES.get(t, ())}
    out: list[str] = []
    for ev in evidence:
        if not (isinstance(ev, MarketEvidence) and ev.kind == "fundamentals"):
            continue
        for text, scopes in ev.cautions:
            if everything or "all" in scopes or wanted & set(scopes):
                line = f"Caution for {ev.symbol}: {text}."
                if line not in out:
                    out.append(line)
    return out


def gather_market_evidence(
    conn: psycopg.Connection, symbols: list[str], intent: Intent, window: Window, model: str, today: Optional[date] = None,
) -> list[MarketEvidence]:
    """Price facts, financial figures, sentiment summary, and headlines for each company, grouped by company."""
    per_company = max(2, NEWS_PER_COMPANY // max(1, len(symbols)))
    days = news_days(window)
    out: list[MarketEvidence] = []
    for symbol in symbols:
        if intent.prices and (p := price_evidence(conn, symbol, window, today)):
            out.append(p)
        if intent.fundamentals:
            out.append(fundamentals_evidence(conn, symbol, today))
        if intent.sentiment and (s := sentiment_evidence(conn, symbol, model, days, today)):
            out.append(s)
        if intent.headlines:
            out += headline_evidence(conn, symbol, model, days, per_company)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbol")
    parser.add_argument("question")
    parser.add_argument("--model", default="ollama:qwen3:latest", help="whose sentiment labels to use")
    args = parser.parse_args(argv)
    intent, window = detect_intent(args.question), parse_window(args.question)
    print(f"intent: {intent}\nwindow: {window}\n")
    with connect() as conn:
        for i, ev in enumerate(gather_market_evidence(conn, [args.symbol.upper()], intent, window, args.model), 1):
            print(f"[{i}] {ev.header}\n{ev.text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
