"""Prices, headlines, headline sentiment, and company financial figures as numbered evidence for the copilot.

Every number the model may quote is worked out here (or in data/fundamentals.py), in Python, and written into the
source text. The model only copies figures; it never calculates them. Headlines are titles only (no article text), so
nothing here can show *why* a stock moved, and the financial figures can't show why a company's profit changed.

Usage: python -m ai.market AAPL "How has Apple stock done this year?"   (print the evidence the copilot would see)
"""
import argparse
import re
import sys
from dataclasses import dataclass
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
        trading|traded|closed|closing|rall(?:y|ied|ies)|surg(?:e|ed|es)|plung\w+|tank(?:ed|s)?|sank|fell|fall(?:s|en|ing)?|
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
GENERAL_RE = re.compile(r"\bhow(?:'s|\s+is|\s+are|\s+has|\s+have)\s+.{1,40}?\s+(?:doing|done|going|performing|performed)\b", re.IGNORECASE)
STOCK_WORD_RE = re.compile(r"\b(?:stocks?|shares?|prices?)\b", re.IGNORECASE)
# No index data is stored, and a filing's "total return" chart (scaled from $100) reads like an index level to a model.
INDEX_RE = re.compile(r"\b(?:s&p(?:\s*500)?|dow(?:\s+jones)?|nasdaq(?:\s+composite)?|russell\s*\d+)\b", re.IGNORECASE)
STOCK_NOUN_RE = re.compile(r"\b(?:stocks?(?!-based)|shares)\b", re.IGNORECASE)  # not "stock-based compensation"
SENTIMENT_RE = re.compile(
    r"\b(?:sentiment|mood|bullish|bearish|optimis\w+|pessimis\w+|tone\s+of|(?:good|bad|positive|negative)\s+news|"
    r"how\s+(?:do|does)\s+(?:people|investors|the\s+market)\s+feel|"
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
_SPECIFIC_TOPICS = (
    ("pe", r"\bp\s?/\s?e\b|\bpe\s+(?:ratio|multiple)\b|\bprice[-\s]to[-\s]earnings\b|\bearnings\s+multiple\b"),
    ("market_value", r"\bmarket[-\s]cap(?:italization|italisation)?\b|\bmarket\s+(?:value|valuation)\b"),
    ("eps", r"\beps\b|\bearnings\s+per\s+share\b"),
    ("shares", r"\bshares\s+outstanding\b|\bshare\s+count\b|\bnumber\s+of\s+shares\b"),
)
# Everyday words that a filing can also answer. Left to the filings when the question names a filing, a quarter, a
# segment, or asks why (the figures are twelve-month totals and can't explain anything).
_BROAD_TOPICS = (
    ("profit", r"\bnet\s+income\b|\bprofit(?:s|ability|able)?\b|\bearnings\b|\boperating\s+income\b|\bbottom\s+line\b"),
    ("margin", r"\bmargins?\b"),
    ("revenue", r"\brevenues?\b|\btop\s+line\b"),
    ("general", r"\bfinancials?\b|\bfundamentals?\b|\bvaluation\b|\bfinancial\s+(?:figures|results|health|position|summary)\b"),
)
FILING_FORM_RE = re.compile(
    r"\b(?:10-?k|10-?q|8-?k|filings?|annual|quarter(?:s|ly)?|fiscal|segments?|earnings\s+(?:call|release|report)|"
    r"by\s+(?:product|region|geograph\w+|business|division))\b",
    re.IGNORECASE,
)
WHY_RE = re.compile(
    r"\b(?:why|reasons?|because|explain\w*|what\s+(?:happened|drove|drives|caused|causes)|driv(?:e|es|ing|en|ers?)|"
    r"caus(?:e|es|ed|ing)|what(?:'s|\s+is|\s+was)\s+behind)\b",
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
    if broad and (FILING_FORM_RE.search(question) or WHY_RE.search(question)):
        return frozenset(specific), rest  # the everyday words stay in the question, for the filings rules to see
    return frozenset(specific | broad), rest_without_broad


@dataclass(frozen=True)
class Intent:
    prices: bool = False
    headlines: bool = False
    sentiment: bool = False
    filings: bool = True
    fundamentals: frozenset[str] = frozenset()  # the financial figures asked for (pe, market_value, revenue, ...)

    @property
    def market(self) -> bool:
        return self.prices or self.headlines or self.sentiment or bool(self.fundamentals)


def detect_intent(question: str) -> Intent:
    """Which kinds of evidence the question needs. Plain keyword rules, so the choice is predictable and testable.
    With no market wording the copilot behaves exactly as it did before (filings only)."""
    # "stock" plus a named period ("Apple stock or Microsoft stock, this month?") is a price question even without a verb
    prices = (
        bool(PRICE_RE.search(question)) or bool(INDEX_RE.search(question))
        or (bool(STOCK_NOUN_RE.search(question)) and parse_window(question).explicit)
    )
    sentiment = bool(SENTIMENT_RE.search(question))
    general = bool(GENERAL_RE.search(question)) and not STOCK_WORD_RE.search(question)  # "How's Nvidia doing?" wants both
    headlines = bool(NEWS_RE.search(question)) or sentiment or general or (prices and bool(CAUSE_RE.search(question)))
    topics, rest = question_topics(question)
    market = prices or headlines or sentiment or bool(topics)
    # The words that sent the question to the figures ("revenue", "income") aren't also a reason to search the filings
    return Intent(prices, headlines, sentiment, filings=not market or bool(FILING_RE.search(rest)), fundamentals=topics)


# ---- how far back? ----


@dataclass(frozen=True)
class Window:
    label: str
    days: Optional[int]  # calendar days back from the latest stored price; None means since the start of the year
    explicit: bool = False  # False when the question named no period and the default was used


DEFAULT_WINDOW = Window("past month", 31)
_WINDOWS = [  # checked in order, so the specific forms win
    (r"year[-\s]to[-\s]date|\bytd\b|this\s+(?:calendar\s+)?year|so\s+far\s+this\s+year|year\s+so\s+far|"
     r"(?:start|beginning)\s+of\s+(?:the\s+|this\s+)?year|since\s+(?:january|jan\b)|since\s+new\s+year",
     Window("year to date", None, True)),
    (r"\b(?:5|five)\s+years?\b", Window("past 5 years", 1830, True)),
    (r"\b(?:6|six)\s+months?\b|\bhalf[-\s]year\b", Window("past 6 months", 183, True)),
    (r"\b(?:3|three)\s+months?\b|\bquarter\b|\b90\s+days\b", Window("past 3 months", 92, True)),
    (r"\b(?:12|twelve)\s+months?\b|\b(?:1|one)\s+year\b|52[-\s]?week|\byear\b", Window("past year", 366, True)),
    (r"\bmonth\b|\b30\s+days\b", Window("past month", 31, True)),
    (r"\bweek\b|\b(?:7|seven)\s+days\b", Window("past week", 7, True)),
    (r"\btoday\b|\byesterday\b|\bpast\s+day\b|\b(?:1|one)\s+day\b|\b24\s+hours\b", Window("past day", 1, True)),
]


def parse_window(question: str) -> Window:
    for pattern, window in _WINDOWS:
        if re.search(pattern, question, re.IGNORECASE):
            return window
    return DEFAULT_WINDOW


def news_days(window: Window) -> int:
    """Headlines default to the last week; a named period is honored up to 90 days."""
    if not window.explicit:
        return 7
    return min(window.days or 90, 90)


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
    rows = conn.execute(
        "SELECT ts, close FROM prices_daily WHERE symbol = %s AND ts >= %s ORDER BY ts",
        (symbol, latest - timedelta(days=reach)),
    ).fetchall()
    last_ts, last_close = rows[-1]
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
