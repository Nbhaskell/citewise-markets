"""Download recent SEC filings (10-K, 10-Q, 8-K) as text for tickers in the instruments table.

Usage: python -m data.ingest_filings AAPL MSFT [--forms 10-K,10-Q] [--limit 2]
Needs SEC_USER_AGENT in .env, e.g. "Your Name your-email@example.com".
Filings already stored are skipped, so re-running is cheap.
"""
import argparse
import sys

import psycopg

from .db import connect, get_setting
from .sources.edgar import EdgarClient


def ingest_filings(
    conn: psycopg.Connection, edgar: EdgarClient, symbol: str, forms: list[str], limit: int
) -> int:
    symbol = symbol.upper()
    if conn.execute("SELECT 1 FROM instruments WHERE symbol = %s", (symbol,)).fetchone() is None:
        raise ValueError(f"{symbol} is not in instruments; run data.ingest {symbol} first")
    cik = edgar.cik_for_ticker(symbol)
    if cik is None:
        raise ValueError(f"no SEC CIK found for {symbol}")
    conn.execute("UPDATE instruments SET cik = %s WHERE symbol = %s", (cik, symbol))
    conn.commit()

    have = {
        r[0] for r in conn.execute("SELECT accession_number FROM filings WHERE symbol = %s", (symbol,))
    }
    added = 0
    for ref in edgar.list_filings(cik, forms, limit):
        if ref.accession_number in have:
            continue
        text = edgar.fetch_text(ref)
        conn.execute(
            "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, period_of_report, url, text) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (ref.accession_number, symbol, ref.cik, ref.form, ref.filed_at,
             ref.period_of_report, ref.url, text),
        )
        conn.commit()
        added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--forms", default="10-K,10-Q")
    parser.add_argument("--limit", type=int, default=2, help="most recent filings per form")
    args = parser.parse_args(argv)

    user_agent = get_setting("SEC_USER_AGENT")
    if not user_agent or "example.com" in user_agent:
        sys.exit("Set SEC_USER_AGENT in .env to your name and contact email (SEC requires it).")

    edgar = EdgarClient(user_agent)
    forms = [f.strip() for f in args.forms.split(",") if f.strip()]
    failures = 0
    with connect() as conn:
        for symbol in args.symbols:
            try:
                added = ingest_filings(conn, edgar, symbol, forms, args.limit)
                print(f"{symbol.upper()}: {added} new filings")
            except Exception as exc:
                failures += 1
                conn.rollback()
                print(f"{symbol.upper()}: FAILED - {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
