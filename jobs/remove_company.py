"""Remove a company: stop tracking it. Nothing is deleted.

Usage:
  python -m jobs.remove_company TICKER

The company is switched off (`instruments.active = false`). It leaves the dashboard, the "What changed" page, the nightly
refresh, and the copilot's list of companies, but its prices, filings, headlines, and figures stay stored. Add it again
(`python -m jobs.add_company TICKER`, or the "Add a company" box) and it comes back with that history, brought up to date.
It takes the same database lock as the nightly refresh, a backup, and an add, so it never runs in the middle of one.

Exit code 0 = removed, 1 = not a tracked company (or already removed), 2 = the database was unreachable,
3 = another update is running, 4 = the command itself crashed.
"""
import argparse
import logging
import sys
from dataclasses import dataclass

import psycopg

from data.db import connect

from .add_company import normalize_ticker
from .refresh import LOCK_KEY, AlreadyRunning, setup_logging

log = logging.getLogger("refresh")

BUSY_TEXT = "Another update is running (the nightly refresh, a backup, or an add). Try again in a few minutes."


class NotTracked(Exception):
    """The ticker is not a company that is being tracked right now (never added, or already removed)."""


@dataclass
class Removal:
    symbol: str
    name: str | None
    kept: dict[str, int]  # what stays stored: prices, filings, headlines, figures


def kept_counts(conn: psycopg.Connection, symbol: str) -> dict[str, int]:
    def n(sql: str) -> int:
        return conn.execute(sql, (symbol,)).fetchone()[0]

    return {
        "prices": n("SELECT count(*) FROM prices_daily WHERE symbol = %s"),
        "filings": n("SELECT count(*) FROM filings WHERE symbol = %s"),
        "headlines": n("SELECT count(*) FROM news_article_symbols WHERE symbol = %s"),
        "figures": n("SELECT count(*) FROM financial_facts WHERE symbol = %s"),
    }


def remove_company(conn: psycopg.Connection, symbol: str) -> Removal:
    """Switch the company off. Raises NotTracked (never added, or already removed) or AlreadyRunning (another update has the lock)."""
    symbol = normalize_ticker(symbol)
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        conn.rollback()
        raise AlreadyRunning("another update is running")
    try:
        row = conn.execute("SELECT name, active FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
        if row is None:
            raise NotTracked(f"{symbol} isn't a tracked company, so there is nothing to remove.")
        name, is_active = row
        if not is_active:
            raise NotTracked(f"{symbol} is already removed (switched off). Add it again to track it.")
        conn.execute("UPDATE instruments SET active = false, updated_at = now() WHERE symbol = %s", (symbol,))
        conn.commit()
        return Removal(symbol, name, kept_counts(conn, symbol))
    finally:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()


def format_removal(removal: Removal) -> str:
    head = f"{removal.symbol} - {removal.name}" if removal.name else removal.symbol
    k = removal.kept
    return "\n".join([
        f"{head} is no longer tracked.",
        "  It is off the dashboard, the nightly refresh, \"What changed\", and the copilot. Nothing was deleted; still stored:",
        f"  {k['prices']:,} daily prices, {k['filings']:,} filings, {k['headlines']:,} headlines, {k['figures']:,} financial figures.",
        f"  To track it again: python -m jobs.add_company {removal.symbol}",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbol", metavar="TICKER")
    args = parser.parse_args(argv)
    try:
        symbol = normalize_ticker(args.symbol)
    except ValueError as exc:
        parser.error(str(exc))
    setup_logging()

    try:
        conn = connect()
    except Exception as exc:
        log.error("Can't reach the database (is Docker Desktop running?): %s", exc)
        return 2
    try:
        with conn:
            try:
                removal = remove_company(conn, symbol)
            except NotTracked as exc:
                print(exc)
                return 1
            except AlreadyRunning:
                print(BUSY_TEXT)
                return 3
    except Exception:
        log.exception("remove_company crashed")
        return 4
    print(format_removal(removal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
