"""What changed lately, worked out from data already stored: new filings, unusually big daily moves, and notable
headlines. Everything is computed here in Python; no model is involved and nothing is written.

The rules are plain numbers (below) so they can be read, tested, and changed in one place.

- **Window.** The last `days` trading days that appear in the stored prices (not calendar days, so a weekend never
  shortens it). Filings and headlines use the same start date.
- **Big move.** One day's close against the previous stored close counts when it is at least `MIN_MOVE_PCT` and at least
  `TYPICAL_MULTIPLE` times that company's own median daily move over the `BASELINE_MOVES` days before the window. A
  fixed percentage alone doesn't work: AMD's ordinary day is about 2.4%, Apple's about 0.9%.
- **Market-wide day.** When at least `MARKET_WIDE_SHARE` of the companies with a move that day moved the same way by
  more than `MARKET_WIDE_PCT` (and at least `MARKET_WIDE_MIN_COMPANIES` had one), the day is labeled, so a day when
  everything fell reads as one event and not as seven.
- **Notable headlines.** Only those labeled positive or negative, each story once per company, quote and data-page
  templates left out, newest first, a few per company. "Notable" means only that: the labels lean neutral and are not
  always right. Headlines listed beside a big move were published on that date (UTC); they are timing, not a cause.
- **Mood shift.** The 7-day news score against the 7 days before it, when both have enough stories.
"""
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Iterable, Optional

import psycopg

from .headlines import is_template_page, title_key

MIN_MOVE_PCT = 3.0
TYPICAL_MULTIPLE = 2.0
BASELINE_MOVES = 60
MIN_BASELINE_MOVES = 20
MARKET_WIDE_PCT = 1.0
MARKET_WIDE_SHARE = 0.7
MARKET_WIDE_MIN_COMPANIES = 4
HEADLINES_PER_COMPANY = 3
MOVE_HEADLINES = 3
MOOD_DAYS = 7
MOOD_MIN_STORIES = 10
MOOD_SHIFT = 0.15
MAX_DAYS = 30
# Enough calendar days of bars for the longest window plus the baseline (about 91 trading days).
HISTORY_CALENDAR_DAYS = 170

Bar = tuple[date, float]


@dataclass(frozen=True)
class DailyMove:
    day: date
    prev_day: date
    close: float
    prev_close: float
    pct: float


@dataclass(frozen=True)
class BigMove:
    symbol: str
    move: DailyMove
    typical_pct: Optional[float]  # the company's median daily move before the window; None without enough history
    threshold_pct: float
    market_wide: bool


@dataclass(frozen=True)
class MarketDay:
    day: date
    direction: str  # "up" or "down"
    moved_that_way: int
    companies: int


def daily_moves(bars: list[Bar]) -> list[DailyMove]:
    """Each close against the one before it, oldest first. Bars are (date, close)."""
    ordered = sorted(bars)
    return [
        DailyMove(d, pd, c, pc, (c - pc) / pc * 100)
        for (pd, pc), (d, c) in zip(ordered, ordered[1:])
        if pc
    ]


def window_dates(series: dict[str, list[Bar]], days: int, since: Optional[date] = None) -> list[date]:
    """The last `days` distinct dates that have a stored price, oldest first. With `since`, the dates after it instead
    (still at most `MAX_DAYS`, the newest ones); none if nothing has been stored after that date."""
    every = sorted({d for bars in series.values() for d, _ in bars})
    if since is not None:
        return [d for d in every if d > since][-MAX_DAYS:]
    return every[-days:]


def analyze_moves(series: dict[str, list[Bar]], dates: list[date]) -> tuple[list[BigMove], list[MarketDay]]:
    """Big moves inside the window, and the days on which most companies moved the same way."""
    if not dates:
        return [], []
    start, in_window = min(dates), set(dates)
    flagged: list[tuple[str, DailyMove, Optional[float], float]] = []
    by_day: dict[date, list[float]] = defaultdict(list)
    for symbol, bars in series.items():
        moves = daily_moves(bars)
        baseline = [abs(m.pct) for m in moves if m.day < start][-BASELINE_MOVES:]
        typical = statistics.median(baseline) if len(baseline) >= MIN_BASELINE_MOVES else None
        threshold = MIN_MOVE_PCT if typical is None else max(MIN_MOVE_PCT, TYPICAL_MULTIPLE * typical)
        for m in moves:
            if m.day not in in_window:
                continue
            by_day[m.day].append(m.pct)
            if abs(m.pct) >= threshold:
                flagged.append((symbol, m, typical, threshold))

    market_days: list[MarketDay] = []
    for day in sorted(by_day, reverse=True):
        pcts = by_day[day]
        if len(pcts) < MARKET_WIDE_MIN_COMPANIES:
            continue
        for direction, count in (
            ("up", sum(p > MARKET_WIDE_PCT for p in pcts)),
            ("down", sum(p < -MARKET_WIDE_PCT for p in pcts)),
        ):
            if count / len(pcts) >= MARKET_WIDE_SHARE:
                market_days.append(MarketDay(day, direction, count, len(pcts)))

    wide = {(md.day, md.direction) for md in market_days}
    moves_out = [
        BigMove(sym, m, typical, threshold, (m.day, "up" if m.pct > 0 else "down") in wide)
        for sym, m, typical, threshold in flagged
    ]
    moves_out.sort(key=lambda b: (b.move.day, abs(b.move.pct)), reverse=True)
    return moves_out, market_days


@dataclass(frozen=True)
class Headline:
    id: str
    symbol: str
    title: str
    publisher: Optional[str]
    url: str
    published_at: datetime
    label: Optional[str]


def distinct_stories(rows: Iterable[Headline]) -> list[Headline]:
    """Newest first, each story once per company, quote and data-page templates dropped."""
    seen: set[tuple[str, str]] = set()
    out = []
    for h in sorted(rows, key=lambda h: (h.published_at, h.id), reverse=True):
        key = (h.symbol, title_key(h.title, h.publisher))
        if key in seen or is_template_page(h.title):
            continue
        seen.add(key)
        out.append(h)
    return out


def notable_headlines(rows: Iterable[Headline], per_company: int = HEADLINES_PER_COMPANY) -> list[dict]:
    """Per company: the newest positive and negative stories (a few), and how many there were in all."""
    by_symbol: dict[str, list[Headline]] = defaultdict(list)
    for h in distinct_stories(rows):
        if h.label in ("positive", "negative"):
            by_symbol[h.symbol].append(h)
    return [
        {"symbol": sym, "positive": sum(h.label == "positive" for h in items),
         "negative": sum(h.label == "negative" for h in items), "items": items[:per_company]}
        for sym, items in sorted(by_symbol.items())
    ]


def headlines_on(rows: Iterable[Headline], symbol: str, day: date, limit: int = MOVE_HEADLINES) -> list[Headline]:
    """Stories about `symbol` published on `day` (UTC date): positive and negative first, then the rest, not off-topic."""
    same_day = [
        h for h in distinct_stories(h for h in rows if h.symbol == symbol)
        if h.published_at.astimezone(timezone.utc).date() == day and h.label != "irrelevant"
    ]
    same_day.sort(key=lambda h: h.label not in ("positive", "negative"))  # stable: newest first within each group
    return same_day[:limit]


def _score(counts: dict[str, int]) -> tuple[Optional[float], int]:
    pos, neg, neu = counts.get("positive", 0), counts.get("negative", 0), counts.get("neutral", 0)
    counted = pos + neg + neu
    return ((pos - neg) / counted if counted else None), counted


def mood_shifts(now_counts: dict[str, dict[str, int]], two_periods: dict[str, dict[str, int]]) -> list[dict]:
    """Companies whose news score moved by at least `MOOD_SHIFT` between the last 7 days and the 7 before.

    `now_counts` covers the last 7 days and `two_periods` the last 14 (both from `label_counts`, which counts each story
    once, by its newest copy), so the earlier week is the difference."""
    out = []
    for symbol, recent in now_counts.items():
        total = two_periods.get(symbol, {})
        before = {k: max(0, total.get(k, 0) - recent.get(k, 0)) for k in ("positive", "neutral", "negative")}
        score_now, n_now = _score(recent)
        score_before, n_before = _score(before)
        if score_now is None or score_before is None or min(n_now, n_before) < MOOD_MIN_STORIES:
            continue
        if abs(score_now - score_before) >= MOOD_SHIFT:
            out.append({"symbol": symbol, "score_now": round(score_now, 4), "stories_now": n_now,
                        "score_before": round(score_before, 4), "stories_before": n_before})
    return sorted(out, key=lambda r: r["symbol"])


def _load_series(conn: psycopg.Connection, symbols: list[str], since: date) -> dict[str, list[Bar]]:
    series: dict[str, list[Bar]] = {s: [] for s in symbols}
    for sym, ts, close in conn.execute(
        "SELECT symbol, ts, close FROM prices_daily WHERE symbol = ANY(%s) AND ts >= %s ORDER BY symbol, ts",
        (symbols, since),
    ):
        series[sym].append((ts, float(close)))
    return series


def _load_headlines(
    conn: psycopg.Connection, model: str, symbols: list[str], start: datetime, end: Optional[datetime] = None
) -> list[Headline]:
    rows = conn.execute(
        "SELECT a.id, s.symbol, a.title, a.publisher, a.url, a.published_at, n.label "
        "FROM news_articles a JOIN news_article_symbols s ON s.article_id = a.id "
        "LEFT JOIN news_sentiment n ON n.article_id = a.id AND n.symbol = s.symbol AND n.model = %(m)s "
        "WHERE s.symbol = ANY(%(s)s) AND a.published_at >= %(start)s AND (%(end)s::timestamptz IS NULL OR a.published_at < %(end)s) "
        "ORDER BY a.published_at DESC",
        {"m": model, "s": symbols, "start": start, "end": end},
    ).fetchall()
    return [Headline(*r) for r in rows]


def headline_dict(h: Headline) -> dict:
    return {"id": h.id, "title": h.title, "publisher": h.publisher, "url": h.url, "published_at": h.published_at,
            "sentiment": h.label}


def _midnight_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def build_changes(
    conn: psycopg.Connection, model: str, days: int, mood_counts: Callable[[int], dict[str, dict[str, int]]],
    symbols: Optional[list[str]] = None, since: Optional[date] = None,
) -> dict:
    """Everything the "what changed" page shows. `symbols` limits it to some companies (default: every active one).
    `since` replaces `days`: the window is the stored trading dates after that date (the last time the reader looked).
    `mood_counts(n)` returns per-company label counts for the last n days (`ai.sentiment.label_counts`, passed in so
    this layer doesn't depend on the AI layer)."""
    days = max(1, min(days, MAX_DAYS))
    active = [r[0] for r in conn.execute("SELECT symbol FROM instruments WHERE active ORDER BY symbol")]
    symbols = active if symbols is None else [s for s in symbols if s in active]  # a removed company is never listed, even when named
    names = dict(conn.execute("SELECT symbol, name FROM instruments WHERE symbol = ANY(%s)", (symbols,)).fetchall())

    latest = conn.execute("SELECT max(ts) FROM prices_daily WHERE symbol = ANY(%s)", (symbols,)).fetchone()[0]
    series = _load_series(conn, symbols, (latest or date.today()) - timedelta(days=HISTORY_CALENDAR_DAYS))
    dates = window_dates(series, days, since)
    if dates:
        start_day = dates[0]
    else:  # no stored price in the window: filings and headlines still go back to the day after `since`
        start_day = since + timedelta(days=1) if since is not None else date.today() - timedelta(days=days)
    big, market_days = analyze_moves(series, dates)

    # A company whose newest bar is older than the newest anywhere has nothing for the latest days; say so.
    stale = [{"symbol": s, "as_of": bars[-1][0] if bars else None}
             for s, bars in sorted(series.items()) if not bars or bars[-1][0] < dates[-1]] if dates else []

    filing_cols = "f.symbol, f.form, f.filed_at, f.period_of_report, f.url, f.accession_number"
    filings = [
        dict(zip(("symbol", "form", "filed_at", "period_of_report", "url", "accession_number"), r))
        for r in conn.execute(
            f"SELECT {filing_cols} FROM filings f WHERE f.symbol = ANY(%s) AND f.filed_at >= %s "
            "ORDER BY f.filed_at DESC, f.symbol, f.form", (symbols, start_day))
    ]
    newest = conn.execute(
        f"SELECT {filing_cols} FROM filings f WHERE f.symbol = ANY(%s) ORDER BY f.filed_at DESC, f.symbol LIMIT 1",
        (symbols,)).fetchone()

    headlines = _load_headlines(conn, model, symbols, _midnight_utc(start_day))
    moves_out = []
    if big:
        first, last = min(b.move.day for b in big), max(b.move.day for b in big)
        around = _load_headlines(conn, model, sorted({b.symbol for b in big}), _midnight_utc(first),
                                 _midnight_utc(last + timedelta(days=1)))
        for b in big:
            moves_out.append({
                "symbol": b.symbol, "name": names.get(b.symbol), "date": b.move.day, "previous_date": b.move.prev_day,
                "close": round(b.move.close, 4), "previous_close": round(b.move.prev_close, 4),
                "change_pct": round(b.move.pct, 2),
                "typical_pct": None if b.typical_pct is None else round(b.typical_pct, 2),
                "threshold_pct": round(b.threshold_pct, 2), "market_wide": b.market_wide,
                "headlines": [headline_dict(h) for h in headlines_on(around, b.symbol, b.move.day)],
            })

    wanted = set(symbols)
    shifts = mood_shifts({s: c for s, c in mood_counts(MOOD_DAYS).items() if s in wanted},
                         {s: c for s, c in mood_counts(2 * MOOD_DAYS).items() if s in wanted})
    return {
        "days": len(dates) if since is not None else days, "since": since,
        "as_of": dates[-1] if dates else (latest if since is not None else None),
        "window_start": start_day if dates else None,
        "stale": stale, "filings": filings,
        "newest_filing": None if newest is None else dict(zip(
            ("symbol", "form", "filed_at", "period_of_report", "url", "accession_number"), newest)),
        "moves": moves_out,
        "market_days": [{"date": m.day, "direction": m.direction, "moved_that_way": m.moved_that_way,
                         "companies": m.companies} for m in market_days],
        "headlines": [{**c, "items": [headline_dict(h) for h in c["items"]]} for c in notable_headlines(headlines)],
        "mood_shifts": shifts,
        "rules": {"min_move_pct": MIN_MOVE_PCT, "typical_multiple": TYPICAL_MULTIPLE, "baseline_days": BASELINE_MOVES,
                  "headlines_per_company": HEADLINES_PER_COMPANY, "mood_days": MOOD_DAYS},
    }
