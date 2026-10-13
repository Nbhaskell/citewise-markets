"""SQL behind the API endpoints. Each function takes a connection and returns plain Python data."""
from typing import Optional

import psycopg

from ai.sentiment import SentimentSummary as Counts, label_counts
from data.headlines import title_key

RANGE_DAYS: dict[str, Optional[int]] = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1830, "MAX": None}

STOCK_SQL = """
SELECT i.symbol, i.name, i.sector, i.industry, i.exchange, i.currency,
       l.ts, l.close, l.volume, pr.close
FROM instruments i
LEFT JOIN LATERAL (SELECT ts, close, volume FROM prices_daily WHERE symbol = i.symbol
                   ORDER BY ts DESC LIMIT 1) l ON true
LEFT JOIN LATERAL (SELECT close FROM prices_daily WHERE symbol = i.symbol AND ts < l.ts
                   ORDER BY ts DESC LIMIT 1) pr ON true
WHERE (%(symbol)s::text IS NULL AND i.active) OR i.symbol = %(symbol)s
ORDER BY i.symbol
"""


def _f(value) -> Optional[float]:
    return None if value is None else float(value)


def stock_rows(conn: psycopg.Connection, symbol: Optional[str] = None) -> list[dict]:
    rows = conn.execute(STOCK_SQL, {"symbol": symbol}).fetchall()
    out = []
    for sym, name, sector, industry, exchange, currency, as_of, close, volume, prev in rows:
        change = None if close is None or prev is None else float(close - prev)
        out.append({
            "symbol": sym, "name": name, "sector": sector, "industry": industry, "exchange": exchange,
            "currency": currency, "as_of": as_of, "last_price": _f(close), "volume": volume,
            "change": None if change is None else round(change, 4),
            "change_pct": None if change is None or not prev else round(change / float(prev) * 100, 4),
        })
    return out


def sentiment_by_symbol(conn: psycopg.Connection, model: str, days: int, symbol: Optional[str] = None) -> dict[str, dict]:
    counts = label_counts(conn, model, days, symbol)
    return {sym: sentiment_dict(sym, c, days) for sym, c in counts.items()}


def sentiment_dict(symbol: str, counts: dict[str, int], days: int) -> dict:
    s = Counts(symbol, counts.get("positive", 0), counts.get("neutral", 0), counts.get("negative", 0), counts.get("irrelevant", 0))
    score = None if s.score is None else round(s.score, 4)
    return {"days": days, "positive": s.positive, "neutral": s.neutral, "negative": s.negative,
            "irrelevant": s.irrelevant, "score": score}


def year_range(conn: psycopg.Connection, symbol: str) -> tuple[Optional[float], Optional[float]]:
    row = conn.execute(
        "SELECT max(high), min(low) FROM prices_daily WHERE symbol = %(s)s "
        "AND ts >= (SELECT max(ts) FROM prices_daily WHERE symbol = %(s)s) - 365",
        {"s": symbol},
    ).fetchone()
    return _f(row[0]), _f(row[1])


def price_points(conn: psycopg.Connection, symbol: str, range_key: str) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM prices_daily WHERE symbol = %(s)s "
        "AND (%(days)s::int IS NULL OR ts >= (SELECT max(ts) FROM prices_daily WHERE symbol = %(s)s) - %(days)s::int) "
        "ORDER BY ts",
        {"s": symbol, "days": RANGE_DAYS[range_key]},
    ).fetchall()
    return [
        {"date": d, "open": _f(o), "high": _f(h), "low": _f(lo), "close": float(c), "volume": v}
        for d, o, h, lo, c, v in rows
    ]


# The same story often arrives once per outlet. Fetch extra rows so that dropping repeats still leaves `limit` headlines.
DEDUPE_OVERFETCH = 8


def news_items(
    conn: psycopg.Connection, symbol: str, model: str, days: int, limit: int, include_irrelevant: bool
) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, a.title, a.publisher, a.url, a.published_at, n.label "
        "FROM news_articles a JOIN news_article_symbols s ON s.article_id = a.id AND s.symbol = %(s)s "
        "LEFT JOIN news_sentiment n ON n.article_id = a.id AND n.symbol = s.symbol AND n.model = %(m)s "
        "WHERE a.published_at >= now() - make_interval(days => %(d)s) "
        "AND (%(irr)s OR n.label IS DISTINCT FROM 'irrelevant') "
        "ORDER BY a.published_at DESC LIMIT %(l)s",
        {"s": symbol, "m": model, "d": days, "irr": include_irrelevant, "l": limit * DEDUPE_OVERFETCH},
    ).fetchall()
    seen: set[str] = set()
    out = []
    for i, t, p, u, at, label in rows:  # newest first, so the newest copy of a story is the one kept
        key = title_key(t, p)
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": i, "title": t, "publisher": p, "url": u, "published_at": at, "sentiment": label})
        if len(out) == limit:
            break
    return out


def news_feed(
    conn: psycopg.Connection, model: str, days: int, limit: int, include_irrelevant: bool,
    symbols: Optional[list[str]], labels: Optional[list[str]],
) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, a.title, a.publisher, a.url, a.published_at, s.symbol, n.label "
        "FROM news_articles a JOIN news_article_symbols s ON s.article_id = a.id "
        "JOIN instruments i ON i.symbol = s.symbol AND i.active "
        "LEFT JOIN news_sentiment n ON n.article_id = a.id AND n.symbol = s.symbol AND n.model = %(m)s "
        "WHERE a.published_at >= now() - make_interval(days => %(d)s) "
        "AND (%(irr)s OR n.label IS DISTINCT FROM 'irrelevant') "
        "AND (%(symbols)s::text[] IS NULL OR s.symbol = ANY(%(symbols)s)) "
        "AND (%(labels)s::text[] IS NULL OR n.label = ANY(%(labels)s)) "
        "ORDER BY a.published_at DESC, s.symbol LIMIT %(l)s",
        {"m": model, "d": days, "irr": include_irrelevant, "symbols": symbols, "labels": labels,
         "l": limit * DEDUPE_OVERFETCH},
    ).fetchall()
    seen: set[tuple[str, str]] = set()  # per company: a story about two companies still appears once for each
    out = []
    for i, t, p, u, at, sym, label in rows:
        key = (sym, title_key(t, p))
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": i, "title": t, "publisher": p, "url": u, "published_at": at, "symbol": sym, "sentiment": label})
        if len(out) == limit:
            break
    return out


def filing_rows(conn: psycopg.Connection, symbol: str) -> list[dict]:
    rows = conn.execute(
        "SELECT f.accession_number, f.form, f.filed_at, f.period_of_report, f.url, "
        "       EXISTS (SELECT 1 FROM filing_chunks c WHERE c.accession_number = f.accession_number) "
        "FROM filings f WHERE f.symbol = %s ORDER BY f.filed_at DESC, f.form",
        (symbol,),
    ).fetchall()
    keys = ("accession_number", "form", "filed_at", "period_of_report", "url", "searchable")
    return [dict(zip(keys, r)) for r in rows]


def tracked_symbols(conn: psycopg.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT symbol FROM instruments")}
