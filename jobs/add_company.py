"""Add companies: download prices, news, and filings, build the search index, label headlines, then say what worked.

Usage:
  python -m jobs.add_company TICKER [TICKER ...]

Runs the same five steps as the nightly refresh (prices, news, filings, index, sentiment) for just these tickers.
Safe to repeat: a company that is already tracked is simply brought up to date. Needs Docker (the database) and
Ollama (headline labels); without Ollama the sentiment step is reported as skipped, and the nightly job fills it in.
It can take a few minutes: the first price download is five years, and the local model labels each headline.

Exit code 0 = everything worked, 1 = something failed, was skipped, or is missing (the report says what),
2 = the database was unreachable, 3 = another refresh is already running, 4 = the command itself crashed.
"""
import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

import psycopg

from data.db import connect

from .refresh import STEPS, AlreadyRunning, Deps, RunReport, StepResult, default_deps, run_refresh, setup_logging

log = logging.getLogger("refresh")

ADD_JOB = "add_company"  # its own name in job_runs, so these runs don't show up as nightly refreshes
FOREIGN_FORMS = ["20-F", "40-F"]  # what companies based outside the US file instead of a 10-K
TICKER_RE = re.compile(r"^[A-Z0-9]{1,6}(-[A-Z])?$")


def normalize_ticker(raw: str) -> str:
    """'brk.b' -> 'BRK-B' (Yahoo and the SEC both spell a share class with a dash). Raises ValueError for anything else."""
    ticker = re.sub(r"\.([A-Z])$", r"-\1", raw.strip().upper())
    if not TICKER_RE.match(ticker):
        raise ValueError(f"'{raw}' doesn't look like a US stock ticker (letters and digits, e.g. AMD or BRK-B)")
    return ticker


@dataclass
class Outcome:
    symbol: str
    name: Optional[str] = None
    stored: bool = False
    already_tracked: bool = False
    turned_back_on: bool = False
    lines: list[tuple[str, str, str]] = field(default_factory=list)  # (step, status word, text)
    gaps: list[str] = field(default_factory=list)  # anything that makes this less than a complete add

    @property
    def complete(self) -> bool:
        return self.stored and not self.gaps

    @property
    def verdict(self) -> str:
        if not self.stored:
            return "NOT ADDED"
        word = "UPDATED" if self.already_tracked else "ADDED"
        return word if self.complete else f"{word}, WITH GAPS"


def _scalar(conn: psycopg.Connection, sql: str, *params):
    return conn.execute(sql, params).fetchone()[0]


def filings_gap_reason(conn: psycopg.Connection, deps: Deps, symbol: str) -> str:
    """Why no filings were stored for a company the SEC lookup didn't reject: ask the SEC for the foreign forms."""
    cik = _scalar(conn, "SELECT cik FROM instruments WHERE symbol = %s", symbol)
    edgar = deps.edgar_factory()
    if cik and edgar is not None:
        try:
            foreign = edgar.list_filings(cik, FOREIGN_FORMS, 1)
        except Exception as exc:  # the explanation is a bonus; never let it hide the real result
            log.warning("couldn't check %s for foreign-company forms: %s", symbol, exc)
            foreign = []
        if foreign:
            return (f"{symbol} files {foreign[0].form}, the form companies based outside the US use, not 10-K or 10-Q. "
                    "This app stores only 10-K and 10-Q, so it has no filings for this company and the copilot "
                    "can't answer from them (prices, headlines, and sentiment still work)")
    return f"the SEC has no 10-K or 10-Q on file for {symbol} (a new listing, a fund, or a company that isn't an SEC filer)"


def describe(conn: psycopg.Connection, deps: Deps, symbol: str, results: list[StepResult],
             already_tracked: bool = False) -> Outcome:
    """Turn a refresh run's raw results into a plain per-company report, checked against what is really stored."""
    row = conn.execute("SELECT name FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
    out = Outcome(symbol, name=row[0] if row else None, stored=row is not None, already_tracked=already_tracked)
    mine = [r for r in results if r.symbol in (symbol, None)]  # symbol None = a whole-step result (skipped, or nothing to do)

    for step in STEPS:
        rs = [r for r in mine if r.step == step]
        errors = [r for r in rs if r.status == "error"]
        skipped = [r for r in rs if r.status == "skipped"]
        if not out.stored and step != "prices":  # shared "nothing to do" results must not read as success
            out.lines.append((step, "--", "not tried: the ticker wasn't found"))
            continue
        if not rs:
            out.lines.append((step, "--", "not run"))
            continue
        if errors:
            detail = "; ".join(sorted({r.detail for r in errors}))
            if not out.stored:
                detail += " (check the spelling; only US-listed tickers work)"
            out.lines.append((step, "FAILED", detail))
            out.gaps.append(f"{step} failed")
            continue
        if skipped:
            out.lines.append((step, "SKIPPED", skipped[0].detail))
            out.gaps.append(f"{step} skipped")
            continue

        n = sum(r.count for r in rs)
        if step == "prices":
            first, last, total = conn.execute(
                "SELECT min(ts), max(ts), count(*) FROM prices_daily WHERE symbol = %s", (symbol,)).fetchone()
            out.lines.append((step, "OK", f"{total:,} daily prices stored, {first} to {last}"))
        elif step == "news":
            total = _scalar(conn, "SELECT count(*) FROM news_article_symbols WHERE symbol = %s", symbol)
            text = f"{n} new headlines ({total} stored)" if total else "no headlines found for the last 7 days"
            out.lines.append((step, "OK", text))
        elif step == "filings":
            total = _scalar(conn, "SELECT count(*) FROM filings WHERE symbol = %s", symbol)
            if total:
                out.lines.append((step, "OK", f"{n} new filings ({total} stored)"))
            else:
                out.lines.append((step, "NONE", filings_gap_reason(conn, deps, symbol)))
                out.gaps.append("no filings stored")
        elif step == "fundamentals":
            total = _scalar(conn, "SELECT count(*) FROM financial_facts WHERE symbol = %s", symbol)
            if total:
                out.lines.append((step, "OK", f"{n} new figures ({total} stored)"))
            else:
                out.lines.append((step, "NONE", f"the SEC has no US-GAAP figures for {symbol}: companies based outside the US "
                                  "report under another accounting standard that isn't supported, so there is no revenue, "
                                  "P/E, or margin for it"))
                out.gaps.append("no fundamentals stored")
        elif step == "index":
            total = _scalar(conn, "SELECT count(*) FROM filings WHERE symbol = %s", symbol)
            ready = _scalar(
                conn, "SELECT count(*) FROM filings f WHERE f.symbol = %s AND EXISTS (SELECT 1 FROM filing_chunks c "
                      "WHERE c.accession_number = f.accession_number AND c.embedding_model = %s)", symbol, deps.embedder_name)
            out.lines.append((step, "OK", f"{ready} of {total} filings searchable by the copilot"))
            if ready < total:
                out.gaps.append("some filings are not searchable yet")
        elif step == "sentiment":
            left = _scalar(
                conn, "SELECT count(*) FROM news_article_symbols s WHERE s.symbol = %s AND NOT EXISTS (SELECT 1 FROM "
                      "news_sentiment n WHERE n.article_id = s.article_id AND n.symbol = s.symbol AND n.model = %s)",
                symbol, deps.llm.name)
            total = _scalar(conn, "SELECT count(*) FROM news_article_symbols WHERE symbol = %s", symbol)
            note = f", {left} unlabeled (the model skipped them; the nightly refresh retries)" if left else ""
            out.lines.append((step, "OK", f"{n} headlines labeled{note}"))
            if total and left == total:  # a few skipped is normal for the local model; none labeled is a real gap
                out.gaps.append("no headlines were labeled")
    return out


def add_companies(conn: psycopg.Connection, deps: Deps, symbols: list[str]) -> tuple[RunReport, list[Outcome]]:
    """Run the full refresh for these tickers and describe the result per company. Raises AlreadyRunning."""
    before = {r[0]: r[1] for r in conn.execute("SELECT symbol, active FROM instruments WHERE symbol = ANY(%s)", (symbols,))}
    report = run_refresh(conn, deps, symbols, job=ADD_JOB)
    outcomes = []
    for sym in symbols:
        out = describe(conn, deps, sym, report.results, already_tracked=sym in before)
        if out.stored and before.get(sym) is False:  # the nightly job skips inactive companies, so a re-add switches it back on
            conn.execute("UPDATE instruments SET active = true WHERE symbol = %s", (sym,))
            conn.commit()
            out.turned_back_on = True
        outcomes.append(out)
    return report, outcomes


def format_outcome(out: Outcome) -> str:
    head = f"{out.symbol} - {out.name}" if out.name else out.symbol
    lines = [head]
    if out.already_tracked:
        lines.append("  (already tracked; brought up to date)")
    if out.turned_back_on:
        lines.append("  (it had been switched off, so the nightly refresh was skipping it; now switched back on)")
    for step, status, text in out.lines:
        lines.append(f"  {step:<10} {status:<8} {text}")
    lines.append(f"  => {out.verdict}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+", metavar="TICKER")
    args = parser.parse_args(argv)
    try:
        symbols = list(dict.fromkeys(normalize_ticker(s) for s in args.symbols))
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
            print(f"Adding {', '.join(symbols)}. This can take a few minutes (is Ollama running?)...")
            try:
                report, outcomes = add_companies(conn, default_deps(), symbols)
            except AlreadyRunning:
                log.warning("another refresh is running (the nightly job, or another add); try again in a few minutes")
                return 3
    except Exception:
        log.exception("add_company crashed")
        return 4
    print()
    print("\n\n".join(format_outcome(o) for o in outcomes))
    return 0 if all(o.complete for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
