"""Nightly refresh: bring every tracked company's data up to date.

Usage:
  python -m jobs.refresh                      refresh every active company, all steps
  python -m jobs.refresh --symbols AAPL NVDA  only these companies
  python -m jobs.refresh --steps prices news  only these steps (prices news filings index sentiment)
  python -m jobs.refresh --status             show recent runs and how fresh the data is

Each (step, company) is isolated: one failure is recorded and the rest still run. A run is logged in the
job_runs table and in logs/refresh.log. Exit code 0 = everything ran, 1 = something failed or was skipped,
2 = the database was unreachable, 3 = another run is already in progress, 4 = the job itself crashed.
Exit codes 1, 2 and 4 also show a Windows desktop alert (pass --no-alert to turn that off).
"""
import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Callable, Optional

import psycopg

from ai.embeddings import DEFAULT_MODEL, FastEmbedder
from ai.index_filings import index_filing
from ai.llm import LLM, get_llm
from ai.sentiment import score_symbol
from data.db import ROOT, connect, get_setting
from data.ingest import ingest_symbol
from data.ingest_filings import ingest_filings
from data.ingest_news import ingest_news
from data.sources.edgar import EdgarClient
from data.sources.google_news import GoogleNewsSource
from data.sources.yfinance_source import YFinanceSource

from .notify import send_notification

log = logging.getLogger("refresh")

JOB_NAME = "nightly_refresh"
LOCK_KEY = 7284001  # arbitrary number identifying this job's Postgres advisory lock
STEPS = ("prices", "news", "filings", "index", "sentiment")


class AlreadyRunning(Exception):
    pass


@dataclass
class Deps:
    """Everything the job talks to, so tests can swap in fakes."""

    price_source: object
    news_source: object
    edgar_factory: Callable[[], Optional[EdgarClient]]  # None if SEC_USER_AGENT isn't configured
    embedder_factory: Callable[[], object]
    embedder_name: str
    llm: LLM
    news_days: int = 7
    forms: tuple = ("10-K", "10-Q")
    filings_per_form: int = 2


@dataclass
class StepResult:
    step: str
    symbol: Optional[str]
    status: str  # ok | error | skipped
    count: int = 0
    detail: str = ""


@dataclass
class RunReport:
    run_id: int
    status: str  # success | partial | failed
    results: list[StepResult] = field(default_factory=list)
    seconds: float = 0.0


def default_deps() -> Deps:
    def edgar() -> Optional[EdgarClient]:
        agent = get_setting("SEC_USER_AGENT")
        return EdgarClient(agent) if agent and "example.com" not in agent else None

    return Deps(YFinanceSource(), GoogleNewsSource(), edgar, FastEmbedder, DEFAULT_MODEL, get_llm())


def choose_period(last_price: Optional[date], today: date) -> str:
    """How much price history to ask for: just enough to cover the gap since the last stored day."""
    if last_price is None:
        return "5y"
    gap = (today - last_price).days
    for limit, period in ((25, "1mo"), (85, "3mo"), (170, "6mo"), (350, "1y")):
        if gap <= limit:
            return period
    return "5y"


def active_symbols(conn: psycopg.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT symbol FROM instruments WHERE active ORDER BY symbol")]


def run_refresh(
    conn: psycopg.Connection,
    deps: Deps,
    symbols: Optional[list[str]] = None,
    steps: tuple = STEPS,
    today: Optional[date] = None,
    job: Optional[str] = None,
) -> RunReport:
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        raise AlreadyRunning("another refresh is already running")
    started = time.monotonic()
    try:
        symbols = [s.upper() for s in symbols] if symbols else active_symbols(conn)
        today = today or date.today()
        run_id = conn.execute(
            "INSERT INTO job_runs (job, status) VALUES (%s, 'running') RETURNING id", (job or JOB_NAME,)
        ).fetchone()[0]
        conn.commit()
        log.info("run %s: %d companies, steps: %s", run_id, len(symbols), ", ".join(steps))

        results: list[StepResult] = []

        def attempt(step: str, symbol: Optional[str], work: Callable[[], int], unit: str = "rows") -> None:
            try:
                n = work()
                results.append(StepResult(step, symbol, "ok", n))
                log.info("%-9s %-6s ok (%d %s)", step, symbol or "-", n, unit)
            except Exception as exc:  # isolate: one failure must not stop the rest of the run
                conn.rollback()
                results.append(StepResult(step, symbol, "error", 0, f"{type(exc).__name__}: {exc}"[:300]))
                log.error("%-9s %-6s FAILED: %s", step, symbol or "-", exc)

        def skip(step: str, why: str) -> None:
            results.append(StepResult(step, None, "skipped", 0, why))
            log.warning("%-9s skipped: %s", step, why)

        if "prices" in steps:
            for sym in symbols:
                def prices(sym=sym) -> int:
                    last = conn.execute("SELECT max(ts) FROM prices_daily WHERE symbol = %s", (sym,)).fetchone()[0]
                    return ingest_symbol(conn, deps.price_source, sym, choose_period(last, today))
                attempt("prices", sym, prices, "bars")
            # A ticker whose prices failed and that was never stored (a typo, say) would only add "not in
            # instruments" errors to every later step; the prices error already says what went wrong.
            stored = {r[0] for r in conn.execute("SELECT symbol FROM instruments WHERE symbol = ANY(%s)", (symbols,))}
            for sym in symbols:
                if sym not in stored:
                    log.warning("%-6s not stored (prices failed); leaving it out of the other steps", sym)
            symbols = [s for s in symbols if s in stored]

        if "news" in steps:
            for sym in symbols:
                attempt("news", sym, lambda sym=sym: ingest_news(conn, deps.news_source, sym, deps.news_days), "new headlines")

        if "filings" in steps:
            edgar = deps.edgar_factory()
            if edgar is None:
                skip("filings", "SEC_USER_AGENT is not set in .env")
            else:
                for sym in symbols:
                    attempt("filings", sym, lambda sym=sym: ingest_filings(
                        conn, edgar, sym, list(deps.forms), deps.filings_per_form), "new filings")

        if "index" in steps:
            pending = conn.execute(
                "SELECT f.accession_number, f.symbol FROM filings f WHERE f.symbol = ANY(%s) AND NOT EXISTS "
                "(SELECT 1 FROM filing_chunks c WHERE c.accession_number = f.accession_number AND c.embedding_model = %s) "
                "ORDER BY f.symbol, f.filed_at DESC", (symbols, deps.embedder_name)).fetchall()
            conn.commit()
            if not pending:
                results.append(StepResult("index", None, "ok", 0))
                log.info("index     -      ok (nothing new to embed)")
            else:
                try:
                    embedder = deps.embedder_factory()
                except Exception as exc:
                    skip("index", f"couldn't load the embedding model: {exc}")
                else:
                    for accession, sym in pending:
                        attempt("index", sym, lambda a=accession: index_filing(conn, embedder, a), "chunks")

        if "sentiment" in steps:
            check = getattr(deps.llm, "available", None)
            if callable(check) and not check():
                skip("sentiment", "the local AI model isn't reachable (is Ollama running?)")
            else:
                for sym in symbols:
                    attempt("sentiment", sym, lambda sym=sym: score_symbol(conn, deps.llm, sym)[0], "headlines")

        failed = [r for r in results if r.status == "error"]
        skipped = [r for r in results if r.status == "skipped"]
        if results and len(failed) == len(results):
            status = "failed"
        elif failed or skipped:
            status = "partial"
        else:
            status = "success"
        conn.execute(
            "UPDATE job_runs SET finished_at = now(), status = %s, details = %s::jsonb WHERE id = %s",
            (status, json.dumps([asdict(r) for r in results]), run_id),
        )
        conn.commit()
        return RunReport(run_id, status, results, time.monotonic() - started)
    finally:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()


def summarize(report: RunReport) -> str:
    lines = [f"Run {report.run_id}: {report.status.upper()} in {report.seconds:.0f}s"]
    for step in STEPS:
        rs = [r for r in report.results if r.step == step]
        if not rs:
            continue
        total = sum(r.count for r in rs)
        bad = [r for r in rs if r.status != "ok"]
        what = "bars refreshed" if step == "prices" else "new"
        line = f"  {step:<9} {total} {what}" + (f", {len(bad)} problem(s)" if bad else "")
        lines.append(line)
        lines += [f"    {r.symbol or '-'}: {r.status}: {r.detail}" for r in bad]
    return "\n".join(lines)


def alert_message(report: RunReport) -> tuple[str, str]:
    """A short title and body for the desktop alert about a run that had problems."""
    parts = []
    for step in STEPS:
        rs = [r for r in report.results if r.step == step and r.status != "ok"]
        if not rs:
            continue
        errors = sum(r.status == "error" for r in rs)
        skipped = len(rs) - errors
        bits = ([f"{errors} failed"] if errors else []) + ([f"skipped - {rs[0].detail}"] if skipped else [])
        parts.append(f"{step}: {', '.join(bits)}")
    return f"Nightly refresh: {report.status.upper()}", "; ".join(parts) + ". Run: python -m jobs.refresh --status"


def setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(ROOT / "logs" / "refresh.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv: list[str] | None = None, notify: Callable[[str, str], object] = send_notification) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", nargs="+", help="default: every active company in the database")
    parser.add_argument("--steps", nargs="+", choices=STEPS, default=list(STEPS))
    parser.add_argument("--status", action="store_true", help="show recent runs and data freshness, then exit")
    parser.add_argument("--no-alert", action="store_true", help="don't show a desktop alert if the run has problems")
    args = parser.parse_args(argv)
    setup_logging()

    def alert(title: str, body: str) -> None:
        if not args.no_alert:
            notify(title, body)

    try:
        conn = connect()
    except Exception as exc:
        log.error("Can't reach the database (is Docker running?): %s", exc)
        alert("Nightly refresh didn't run", "Can't reach the database. Is Docker Desktop running?")
        return 2
    try:
        with conn:
            if args.status:
                from .status import print_status

                print_status(conn, DEFAULT_MODEL, get_llm().name)
                return 0
            try:
                report = run_refresh(conn, default_deps(), args.symbols, tuple(args.steps))
            except AlreadyRunning as exc:
                log.warning("%s; exiting", exc)
                return 3
    except Exception as exc:  # a crash outside the per-company isolation; it still must not go unnoticed
        log.exception("the refresh crashed")
        alert("Nightly refresh crashed", f"{type(exc).__name__}: {exc}"[:200])
        return 4
    log.info("\n%s", summarize(report))
    if report.status != "success":
        alert(*alert_message(report))
    return 0 if report.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
