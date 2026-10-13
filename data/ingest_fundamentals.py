"""Download companies' reported figures (revenue, profit, earnings per share, share counts) from the SEC into Postgres.

Usage: python -m data.ingest_fundamentals AAPL MSFT
Needs SEC_USER_AGENT in .env, like the filings. One small download per company. Re-running is safe: a figure already
stored is skipped, and a restated figure arrives as its own row (the newest filing wins when ratios are computed).
Companies that report in another accounting vocabulary (foreign filers such as TSM) give nothing and are not an error.
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Optional

import psycopg

from .db import connect, get_setting
from .sources.edgar import EdgarClient, parse_company_facts

log = logging.getLogger("refresh")

HISTORY_YEARS = 7  # enough for the latest full year, a year-ago comparison, and some context

INSERT_FACT = """
INSERT INTO financial_facts (symbol, taxonomy, concept, unit, period_start, period_end, value, accession_number, form, filed_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, concept, unit, (COALESCE(period_start, DATE '0001-01-01')), period_end, accession_number) DO NOTHING
"""


def ingest_fundamentals(
    conn: psycopg.Connection, edgar: EdgarClient, symbol: str, today: Optional[date] = None
) -> int:
    """Store the company's reported figures. Returns how many were new."""
    symbol = symbol.upper()
    row = conn.execute("SELECT cik FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
    if row is None:
        raise ValueError(f"{symbol} is not in instruments; run data.ingest {symbol} first")
    cik = row[0] or edgar.cik_for_ticker(symbol)
    if cik is None:
        raise ValueError(f"no SEC CIK found for {symbol}")
    conn.execute("UPDATE instruments SET cik = %s WHERE symbol = %s", (cik, symbol))
    conn.commit()

    since = (today or date.today()) - timedelta(days=365 * HISTORY_YEARS)
    facts = parse_company_facts(edgar.company_facts(cik), since)
    if not facts:
        log.info("%s: no US-GAAP figures in the SEC data (a foreign filer?); nothing stored", symbol)
        return 0
    before = conn.execute("SELECT count(*) FROM financial_facts WHERE symbol = %s", (symbol,)).fetchone()[0]
    with conn.cursor() as cur:
        cur.executemany(INSERT_FACT, [
            (symbol, f.taxonomy, f.concept, f.unit, f.period_start, f.period_end, f.value, f.accession_number, f.form, f.filed_at)
            for f in facts
        ])
    conn.commit()
    after = conn.execute("SELECT count(*) FROM financial_facts WHERE symbol = %s", (symbol,)).fetchone()[0]
    return after - before


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+")
    args = parser.parse_args(argv)

    user_agent = get_setting("SEC_USER_AGENT")
    if not user_agent or "example.com" in user_agent:
        sys.exit("Set SEC_USER_AGENT in .env to your name and contact email (SEC requires it).")

    edgar = EdgarClient(user_agent)
    failures = 0
    with connect() as conn:
        for symbol in args.symbols:
            try:
                n = ingest_fundamentals(conn, edgar, symbol)
                print(f"{symbol.upper()}: {n} new figures")
            except Exception as exc:
                failures += 1
                conn.rollback()
                print(f"{symbol.upper()}: FAILED - {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
