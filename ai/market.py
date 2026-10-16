"""Prices, headlines, headline sentiment, and company financial figures as numbered evidence for the copilot.

Every number the model may quote is worked out here (or in data/fundamentals.py), in Python, and written into the
source text. The model only copies figures; it never calculates them. Headlines are titles only (no article text), so
nothing here can show *why* a stock moved, and the financial figures can't show why a company's profit changed.

Usage: python -m ai.market AAPL "How has Apple stock done this year?"   (print the evidence the copilot would see)
"""
import argparse
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
    r"\b(?:news|headlines?|announce\w*|lately|happening|going\s+on|what\s+happened|buzz|in\s+the\s+press|"
    r"(?:press|media|news)\s+coverage|coverage\s+of)\b",
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


def year_start_comparison(question: str, today: Optional[date] = None) -> bool:
    return bool(_year_start_re((today or date.today()).year).search(question))


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
    r"how\s+(?:negative|positive)\b)",
    re.IGNORECASE,
)
CAUSE_RE = re.compile(r"\b(?:why|reasons?|because|what\s+happened|what(?:'s|\s+is|\s+was)\s+(?:behind|driving|causing|moving))\b", re.IGNORECASE)
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
        (?:put|putting|park|parking)\s+(?:(?:any|some|a\s+little|a\s+lot\s+of)\s+)?(?:money|cash|savings)\s+(?:in|into|with)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)
TRADE_WORD_RE = re.compile(
    r"\b(?:buy(?:ing)?|sell(?:ing)?|hold(?:ing)?|invest(?:ing)?|dump|trim|short(?:ing)?|add(?:ing)?\s+to|accumulat\w+|"
    r"load(?:ing)?\s+up|get(?:ting)?\s+(?:in|out)|exit|position|put\s+(?:my|our)\s+(?:savings|money|cash)\s+(?:in|into))\b",
    re.IGNORECASE,
)
DECISION_CUE_RE = re.compile(
    r"\b(?:should|whether|wise|smart|safe(?:ly)?|good\s+idea|bad\s+idea|thinking\s+(?:about|of)|can\s+i|could\s+i|may\s+i|"
    r"my|our|worth|recommend\w*|advice|advise|suggest\w*|thoughts|opinion|would\s+you|do\s+you\s+think|right\s+time|"
    r"best\s+time|good\s+time|bad\s+time|reason\s+(?:not\s+)?to|enough\s+to|right\s+(?:stock|company|one)\s+to)\b",
    re.IGNORECASE,
)


# The reader's own money in the question ("park my money", "my retirement account", "my savings") is a request for a
# recommendation however it is worded. "its cash" and "an employee savings plan" are the company's, and are not caught.
OWN_MONEY_RE = re.compile(
    r"\b(?:my|our)\s+(?:money|cash|savings|retirement|nest\s+egg|portfolio|ira|401\s?\(?k\)?|brokerage|funds)\b", re.IGNORECASE
)


def asks_for_advice(question: str) -> bool:
    return bool(ADVICE_ASK_RE.search(question)) or bool(OWN_MONEY_RE.search(question)) or (
        bool(TRADE_WORD_RE.search(question)) and bool(DECISION_CUE_RE.search(question))
    )


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
    prices = (
        bool(PRICE_RE.search(price_text)) or bool(INDEX_RE.search(question)) or bool(BARE_STOCK_RE.search(question))
        or (bool(STOCK_NOUN_RE.search(question)) and parse_window(question).explicit)
        or (bool(PERIOD_MOVE_RE.search(question)) and parse_window(question).explicit)
        or year_start_comparison(question)
    )
    sentiment = bool(SENTIMENT_RE.search(question))
    general = bool(GENERAL_RE.search(question)) and not STOCK_WORD_RE.search(question)  # "How's Nvidia doing?" wants both
    headlines = bool(NEWS_RE.search(question)) or sentiment or general or (prices and bool(CAUSE_RE.search(question)))
    topics, rest = question_topics(question)
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


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
}
_ROUGH_AMOUNTS = {"few": 3, "couple": 2, "several": 4}  # "the last few weeks": a guess, and the label says so
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_MONTH_RE = r"(?:" + "|".join(_MONTHS) + r"|sept)"
_NUMBERED_PERIOD_RE = re.compile(
    r"\b(?:last|past|previous)\s+(?:(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")|(few|couple(?:\s+of)?|several))\s+(day|week|month|year)s?\b",
    re.IGNORECASE,
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
}
_UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 30.5, "year": 366.0}
MAX_NUMBERED_DAYS = 3660


def _numbered_period(question: str) -> Optional[Window]:
    """"the last four weeks", "past 10 days", "the last few weeks". None when the number is out of range."""
    m = _NUMBERED_PERIOD_RE.search(question)
    if not m:
        return None
    unit = m.group(3).lower()
    if m.group(2):  # few / couple / several
        word = re.sub(r"\s+of$", "", m.group(2).lower())
        n, note = _ROUGH_AMOUNTS[word], f" (reading '{word}' as {_ROUGH_AMOUNTS[word]})"
    else:
        raw = m.group(1).lower()
        n, note = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw], ""
    if n < 1 or n * _UNIT_DAYS[unit] > MAX_NUMBERED_DAYS:
        return None
    if not note and (n, unit) in _CANONICAL:
        return _CANONICAL[(n, unit)]
    return Window(f"past {n} {unit}{'' if n == 1 else 's'}{note}", int(round(n * _UNIT_DAYS[unit])), True)


_SINCE_MONTH_RE = re.compile(rf"\bsince\s+(?:the\s+(?:start|beginning)\s+of\s+)?({_MONTH_RE})\b", re.IGNORECASE)


def _since_month(question: str, today: date) -> Optional[Window]:
    """"since July": from the first of that month, this year, or last year when the month has not come yet. January is
    left to the year-to-date window, which is the same thing."""
    m = _SINCE_MONTH_RE.search(question)
    if not m:
        return None
    name = m.group(1).lower()
    month = 9 if name == "sept" else _MONTHS.index(name) + 1
    if month == 1:
        return None
    since = date(today.year if month <= today.month else today.year - 1, month, 1)
    return Window(f"since {_MONTHS[month - 1].capitalize()} 1", (today - since).days, True, since=since)


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


def parse_window(question: str, today: Optional[date] = None) -> Window:
    today = today or date.today()
    window = _read_window(question, today)
    unmet = _unmet_period(question)
    asked = "today" if re.search(r"\btoday\b", question, re.IGNORECASE) else (
        "yesterday" if re.search(r"\byesterday\b", question, re.IGNORECASE) else None)
    if unmet or asked:
        window = replace(window, unmet=unmet, asked_day=asked)
    return window


def _read_window(question: str, today: date) -> Window:
    if year_start_comparison(question, today):
        return _WINDOWS[0][1]  # year to date
    if (w := _since_month(question, today)) or (w := _numbered_period(question)):
        return w
    for pattern, window in _WINDOWS:
        if re.search(pattern, question, re.IGNORECASE):
            return window
    return DEFAULT_WINDOW


def period_cautions(window: Window, evidence: list, today: Optional[date] = None) -> list[str]:
    """Warnings, attached in code, for a period the question named that the price source does not cover. Only when a price
    source was given: with none, there is no wrong period to warn about."""
    today = today or date.today()
    newest = [e.as_of for e in evidence if e.kind == "price"]
    if not newest:
        return []
    oldest = min(newest)
    out = []
    if window.unmet:
        out.append(
            f"You asked about “{window.unmet}”, which the stored daily prices can't isolate. The answer uses the "
            f"{window.label}, up to the close on {oldest}, so it may not be the period you meant."
        )
    if window.asked_day == "today" and oldest != today:
        out.append(f"You asked about today, but the newest stored close is from {oldest}, so the answer is not about today.")
    elif window.asked_day == "yesterday" and oldest != today - timedelta(days=1):
        out.append(f"You asked about yesterday, but the newest stored close is from {oldest}, so the answer may not be about yesterday.")
    return out


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
    return MarketEvidence("price", symbol, header, "\n".join(lines), None, last_ts, change=change, change_pct=pct)


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
