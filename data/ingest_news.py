"""Pull recent news headlines for tickers already in the instruments table.

Usage: python -m data.ingest_news AAPL MSFT [--days 7]
Re-running is safe: articles are deduplicated by their source ID.
"""
import argparse
import sys

import psycopg

from .db import connect
from .sources.base import NewsSource
from .sources.google_news import GoogleNewsSource


def ingest_news(conn: psycopg.Connection, source: NewsSource, symbol: str, days: int) -> int:
    symbol = symbol.upper()
    row = conn.execute("SELECT name FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
    if row is None:
        raise ValueError(f"{symbol} is not in instruments; run data.ingest {symbol} first")
    items = source.get_news(symbol, row[0], days)
    new = 0
    with conn.transaction():
        for item in items:
            inserted = conn.execute(
                "INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (item.id, item.source, item.title, item.publisher, item.url, item.published_at),
            ).rowcount
            new += inserted
            conn.execute(
                "INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (item.id, symbol),
            )
    conn.commit()
    return new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)

    source = GoogleNewsSource()
    failures = 0
    with connect() as conn:
        for symbol in args.symbols:
            try:
                new = ingest_news(conn, source, symbol, args.days)
                print(f"{symbol.upper()}: {new} new articles")
            except Exception as exc:
                failures += 1
                conn.rollback()
                print(f"{symbol.upper()}: FAILED - {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
