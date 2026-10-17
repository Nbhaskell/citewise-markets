"""A model-based router: which stored data does this question need? (DECISIONS: "Model-based routing experiment".)

The keyword rules in `ai/market.py` decide which evidence a question needs (prices, headlines, sentiment, financial figures, filings).
Every round of new wording missed in the same places, so when the keywords find no specific route (the question would be searched in
the filings only) the local model is asked one question: what kind of question is this? The answer is constrained to JSON and can only
pick among routes that already exist. The model never names a company, never writes an answer, and never removes a notice the keyword
rules attached; companies, periods, figures, the numbers checks and the cautions all stay in Python. Any failure (model offline, bad
JSON, a wrong type) leaves the keyword route alone, so the router can never make an answer fail.

Off unless asked for: COPILOT_ROUTER=model, or `answer_question(..., router=True)`.
"""
import json
import os
import re
from dataclasses import dataclass, replace
from typing import Optional

from .llm import LLM
from .market import FILING_FORM_RE, TWELVE_MONTHS_AS_QUARTERS_RE, WHY_RE, Intent

FIGURES = ("pe", "market_value", "eps", "shares", "profit", "margin", "revenue")
CATEGORIES = ("research", "outside", "writing")

ROUTER_SYSTEM = """You sort a question about public companies into the kinds of stored data needed to answer it. The app stores, for a few companies: daily stock prices; news headlines (titles only) with an automatic positive, negative or neutral label; a few financial figures worked out from SEC filings for the last twelve months; and the text of SEC filings (10-K and 10-Q), which describe risks, competition, legal proceedings, employees, suppliers, customers, strategy and operations.

Reply with JSON only. Most questions need only one or two kinds: set only what the question needs.
- category: "research" if the stored data can answer the question. "outside" if it is about something else: commodities, currencies, the economy, general knowledge, chit-chat, or a company that is not stored. "writing" only if it asks you to produce a text for the reader to use (an email, a post, a poem, a cheer, code, slides, a speech).
- price: true only for how the stock price moved or stands: where it traded, highs and lows, up or down over a period, comparing prices.
- news: true only for what is being said, published or reported in the news or the press (stories, headlines, articles, coverage), or when it asks why the stock price moved. A question about the price alone is not a news question, and neither is a question about why a company's business changed.
- sentiment: true only for the mood or tone of the coverage, or whether it is positive or negative.
- figures: leave empty unless the question asks for one of these numbers: pe (how many times earnings the stock sells for), market_value (what the whole company is worth), eps (earnings per share), shares (how many shares exist), profit (net income or earnings), margin (profit as a share of sales), revenue (sales, money brought in). These are the company's twelve-month totals only. If the question names a filing (a 10-K, 10-Q or annual report), a quarter, a segment or a product line (iPhone sales), asks about dividends or a payout, or asks why something changed, leave figures empty and set filings instead.
- filings: true when the answer is described in the filings: risks, competition, legal matters, employees, suppliers, customers, strategy, operations. Also true when the question needs none of the other kinds.
- advice: true only if it asks whether to buy, sell or hold, for a recommendation, or whether something is a good or safe investment. Such a question needs only advice and filings.
A follow-up has already been rewritten as a full question. Do not answer the question.

Examples:
Has the stock gone anywhere since spring? -> price
Is the coverage turning hostile? -> news and sentiment
How many times annual profit is the share price? -> figures pe
What do the filings say about customer concentration? -> filings
How does the company describe its rivals? -> filings
Did the shares hold up better than a rival over the same stretch? -> price only
Walk me through how the stock behaved lately. -> price only
What was behind that drop? -> price and news
Is it smart to put my money into this stock? -> advice and filings only
Write me a toast for my sister's wedding. -> category writing
What is a good name for a puppy? -> category outside"""

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "price": {"type": "boolean"},
        "news": {"type": "boolean"},
        "sentiment": {"type": "boolean"},
        "figures": {"type": "array", "items": {"type": "string", "enum": list(FIGURES)}},
        "filings": {"type": "boolean"},
        "advice": {"type": "boolean"},
    },
    "required": ["category", "price", "news", "sentiment", "figures", "filings", "advice"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Route:
    category: str
    prices: bool
    news: bool
    sentiment: bool
    figures: frozenset
    filings: bool
    advice: bool


def router_enabled(flag: Optional[bool] = None) -> bool:
    """An explicit True or False wins; otherwise the COPILOT_ROUTER environment variable ("model" or "on" turns it on)."""
    if flag is not None:
        return flag
    return os.environ.get("COPILOT_ROUTER", "off").strip().lower() in ("model", "on", "1", "true")


# The keyword rules send some questions to the filings ON PURPOSE even though they hold a figure word: the question names a filing
# (10-K, annual report), a quarter or a segment, asks why something changed, or is about dividends or a payout ("What were Apple's
# iPhone sales" is a product line, not the twelve-month total). The model cannot see those distinctions and sent them to the
# figures, so they are not put to it. "The last four quarters" is the twelve-month stretch, not a filing.
DIVIDEND_RE = re.compile(r"\bdividends?\b|\bpay\s?outs?\b|\bpay(?:s|ing)?\s+out\b", re.IGNORECASE)


# "Sales" that the keyword rules did not read as the company's total ("total / net sales", "Nvidia's sales" are read) is a product
# line or a department ("iPhone sales", "data center sales"): the twelve-month figures cannot answer it, and the model sent it to
# the total revenue.
SALES_RE = re.compile(r"\bsales\b", re.IGNORECASE)


def deliberately_filings(question: str) -> bool:
    return bool(
        FILING_FORM_RE.search(TWELVE_MONTHS_AS_QUARTERS_RE.sub(" ", question)) or WHY_RE.search(question) or DIVIDEND_RE.search(question)
        or SALES_RE.search(question)
    )


def needs_router(intent: Intent, question: str = "") -> bool:
    """Ask the model only when the keywords found no specific route (the filings default), and not when the answer is already
    decided in code (a ratio the app does not compute), the question already carries the buy/sell/hold notice, or the keywords
    chose the filings on purpose."""
    return not intent.market and not intent.unstored and not intent.advice and not deliberately_filings(question)


# The model is over-eager with headlines (a question about a stake or a price got "news" too). It may add them only when the
# question uses a word that is about news or why a stock moved; this only ever removes, never adds.
NEWS_CUE_RE = re.compile(
    r"\b(?:news|press|headlines?|stor(?:y|ies)|articles?|coverage|reports?|reported|reporting|said|saying|says?|written|write|"
    r"publish\w*|buzz|chatter|mood|tone|sentiment|reading|read|talk\w*|discuss\w*|opinions?|views?|think|thinks|feel\w*|bullish|"
    r"bearish|positive|negative|hostile|glowing|gloomy|why|behind|drove|driv\w+|caus\w+|sparked|sent|what\s+happened)\b",
    re.IGNORECASE,
)


def _parse(text: str) -> Optional[Route]:
    try:
        data = json.loads(text)
    except (ValueError, AttributeError):
        return None
    if not isinstance(data, dict) or data.get("category") not in CATEGORIES:
        return None
    flags = {k: data.get(k) for k in ("price", "news", "sentiment", "filings", "advice")}
    figures = data.get("figures")
    if not all(isinstance(v, bool) for v in flags.values()):
        return None
    if not isinstance(figures, list) or not all(isinstance(f, str) for f in figures):
        return None
    return Route(
        data["category"], flags["price"], flags["news"], flags["sentiment"], frozenset(f for f in figures if f in FIGURES),
        flags["filings"], flags["advice"],
    )


def ask_router(llm: LLM, question: str) -> Optional[Route]:
    """The model's route for a standalone question, or None on any failure. It sees the question alone: no history, no answers."""
    try:
        return _parse(llm.generate(ROUTER_SYSTEM, question, ROUTER_SCHEMA))
    except Exception:
        return None


# The model called an advice question ("Could Apple be a dependable long-term holding?") a writing request. It may decline only a
# question with a word about writing something in it; this only ever removes a decline, never adds one.
WRITING_CUE_RE = re.compile(
    r"\b(?:writ\w*|wrote|draft\w*|compos\w*|creat\w*|mak(?:e|ing)|generat\w*|prepar\w*|craft\w*|produc\w*|pen|phras\w*|word|"
    r"rephras\w*|rewrit\w*|put\s+together|come\s+up\s+with|help\s+me|give\s+me|get\s+me|text|send|translat\w*|sing|code|build|"
    r"e-?mails?|letters?|memos?|messages?|notes?|posts?|tweets?|captions?|scripts?|slides?|decks?|presentations?|resumes?|cvs?|"
    r"press\s+releases?|newsletters?|toasts?|cheers?|essays?|speeches|speech|poems?|songs?|haikus?|limericks?|jokes?|raps?|riddles?|"
    r"stor(?:y|ies)|blog|words|program|python|sql)\b",
    re.IGNORECASE,
)


def evidence_kinds(intent: Intent) -> list[str]:
    """The kinds of evidence an intent asks for, in the API's order (the same names as the sources' kinds)."""
    asked = {
        "price": intent.prices, "fundamentals": bool(intent.fundamentals), "sentiment": intent.sentiment,
        "headline": intent.headlines, "filing": intent.filings,
    }
    return [kind for kind, wanted in asked.items() if wanted]


def changed_kinds(before: Intent, after: Intent) -> list[str]:
    """What the model chose, for the answer to say so: the kinds of evidence the intent asks for after the router, or nothing when
    they are the same as the keyword route's. Which figures, and the advice flag, are not kinds: the notices say those themselves."""
    kinds = evidence_kinds(after)
    return kinds if kinds != evidence_kinds(before) else []


def apply_route(intent: Intent, route: Optional[Route], has_company: bool, question: str = "") -> tuple[Intent, Optional[str]]:
    """The intent after the model's say, and a verdict: "writing" (decline now), "outside" (a hint: the question may be about
    something the app does not hold; it is used only if nothing relevant is found), or None. The model only adds: the advice flag
    is the union of the keywords and the model, a verdict that chooses nothing leaves the keyword intent alone, and it can neither
    decline a question that has no writing word in it nor stop one the filings can answer."""
    if route is None:
        return intent, None
    if route.category == "writing":
        return (intent, "writing") if WRITING_CUE_RE.search(question) else (intent, None)
    if route.category == "outside":
        return (intent, None) if has_company else (intent, "outside")  # a named company is research whatever the model thinks
    headlines = (route.news or route.sentiment) and bool(NEWS_CUE_RE.search(question))
    sentiment = route.sentiment and headlines
    market = route.prices or headlines or bool(route.figures)
    return replace(
        intent,
        prices=route.prices, headlines=headlines, sentiment=sentiment, fundamentals=route.figures,
        filings=route.filings or not market, advice=intent.advice or route.advice,
    ), None
