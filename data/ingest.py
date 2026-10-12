"""Pull daily prices for tickers into Postgres.

Usage: python -m data.ingest AAPL MSFT NVDA [--period 5y]
Re-running is safe: rows are upserted by (symbol, date).
"""
import argparse
import sys

import psycopg

from .db import connect
from .sources.base import PriceSource
from .sources.yfinance_source import YFinanceSource

UPSERT_INSTRUMENT = """
INSERT INTO instruments (symbol, name, exchange, sector, industry, currency)
VALUES (%(symbol)s, %(name)s, %(exchange)s, %(sector)s, %(industry)s, %(currency)s)
ON CONFLICT (symbol) DO UPDATE SET
    name = EXCLUDED.name, exchange = EXCLUDED.exchange, sector = EXCLUDED.sector,
    industry = EXCLUDED.industry, currency = EXCLUDED.currency, updated_at = now()
"""

UPSERT_BAR = """
INSERT INTO prices_daily (symbol, ts, open, high, low, close, adj_close, volume, source)
VALUES (%(symbol)s, %(ts)s, %(open)s, %(high)s, %(low)s, %(close)s, %(adj_close)s, %(volume)s, %(source)s)
ON CONFLICT (symbol, ts) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
    adj_close = EXCLUDED.adj_close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""


def ingest_symbol(conn: psycopg.Connection, source: PriceSource, symbol: str, period: str) -> int:
    symbol = symbol.upper()
    run_id = conn.execute(
        "INSERT INTO ingestion_runs (source, symbol) VALUES (%s, %s) RETURNING id",
        (source.name, symbol),
    ).fetchone()[0]
    conn.commit()
    try:
        instrument = source.get_instrument(symbol)
        bars = source.get_daily_bars(symbol, period)
        if not bars:
            raise ValueError(f"no price data returned for {symbol}")
        with conn.transaction():
            conn.execute(UPSERT_INSTRUMENT, instrument.__dict__)
            with conn.cursor() as cur:
                cur.executemany(
                    UPSERT_BAR, [{**b.__dict__, "source": source.name} for b in bars]
                )
            conn.execute(
                "UPDATE ingestion_runs SET finished_at = now(), rows_written = %s WHERE id = %s",
                (len(bars), run_id),
            )
        return len(bars)
    except Exception as exc:
        conn.rollback()
        conn.execute(
            "UPDATE ingestion_runs SET finished_at = now(), error = %s WHERE id = %s",
            (str(exc), run_id),
        )
        conn.commit()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--period", default="5y", help="yfinance period, e.g. 1mo, 1y, 5y, max")
    args = parser.parse_args(argv)

    source = YFinanceSource()
    failures = 0
    with connect() as conn:
        for symbol in args.symbols:
            try:
                n = ingest_symbol(conn, source, symbol, args.period)
                print(f"{symbol.upper()}: {n} rows")
            except Exception as exc:
                failures += 1
                print(f"{symbol.upper()}: FAILED - {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
