"""The numbered sources worked out from stored data: prices, headlines, sentiment summaries, and the financial figures."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import psycopg

from data.fundamentals import Fundamentals, compute, format_money, latest_close, load_facts
from data.headlines import is_quote_page, title_key

from ..sentiment import summarize
from .intent import Intent
from .topics import figure_topics
from .windows import _WEEKDAY_NAMES, Window, news_days

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
    if window.day:  # "What was Microsoft's close last Wednesday?": that day's own close, worked out here
        name = _WEEKDAY_NAMES[window.day.weekday()].capitalize()
        row = next((r for r in rows if r[0] == window.day), None)
        lines.append(f"Close on {name} {window.day}: {_money(row[1])}." if row else
                     f"No close is stored for {name} {window.day} (a weekend or holiday, or outside the stored prices).")
        prev = [r for r in rows if r[0] < window.day][-1:] if row else []
        if prev:  # what the day did, against the close before it
            day_change = float(row[1]) - float(prev[0][1])
            day_pct = day_change / float(prev[0][1]) * 100 if prev[0][1] else 0.0
            lines.append(f"Close before that, {prev[0][0]}: {_money(prev[0][1])}. Change on that day: {day_change:+.2f} ({day_pct:+.2f}%), "
                         f"{_direction(day_change, day_pct)}.")
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

    def flow_lines(label: str, flow, fmt, meaning: str = "") -> None:
        if flow is None:
            return
        # `meaning` says what the figure is, because the model once quoted operating income as "what is left after all expenses"
        lines.append(f"{label} (last 12 months): {fmt(flow.value)}.{' ' + meaning if meaning else ''} How: {flow.how}.")
        line, pct = _growth_line(label, flow)
        if line:
            lines.append(line)
            growths.append(pct)

    flow_lines("Revenue", f.revenue, format_money)
    flow_lines("Net income", f.net_income, format_money,
               "This is the profit left after all expenses, including interest and taxes.")
    flow_lines("Diluted earnings per share", f.diluted_eps, lambda v: f"${v:.2f}")
    flow_lines("Operating income", f.operating_income, format_money,
               "This is the profit from running the business before interest and taxes, not what is left after all expenses.")
    for label, value, meaning in (
        ("Gross margin", f.gross_margin, "revenue minus the cost of making or buying what was sold, as a share of revenue"),
        ("Operating margin", f.operating_margin, "operating income, before interest and taxes, as a share of revenue"),
        ("Net margin", f.net_margin, "net income, after all expenses, as a share of revenue"),
    ):
        if value is not None:
            lines.append(f"{label}: {value:.1%} ({meaning}).")
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
