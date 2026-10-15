"""Add-company jobs for the web app: look up a ticker, start a background add, and report how it is going.

The add runs in its own process (`python -m jobs.add_company TICKER --job-id N`), so it keeps going if the API
restarts. It takes the same database lock as the nightly refresh and backup, so only one of them runs at a time.
Progress lives in the `job_runs` row: nothing here writes except to create the row and, if the process can't start,
to mark it failed.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import psycopg

from jobs.add_company import ADD_JOB
from jobs.refresh import LOCK_KEY

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = ROOT / "logs" / "add_company.log"
QUEUED_GRACE = timedelta(minutes=2)  # the process takes a few seconds to get the lock; longer means it never started
STALE_HEARTBEAT = timedelta(minutes=15)  # no step has reported in this long: treat the job as dead
BUSY_MESSAGE = "Another update is running (the nightly refresh, a backup, or another add). Try again in a few minutes."

Launcher = Callable[[str, int], None]


def lock_is_free(conn: psycopg.Connection) -> bool:
    """True if no refresh, backup or add holds the database lock right now. Takes and gives back the lock."""
    if conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()
        return True
    return False


def launch_add_process(symbol: str, job_id: int) -> None:
    """Start the add as a separate, windowless process. Its output goes to logs/add_company.log."""
    LOG_FILE.parent.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    extra = {"start_new_session": True}
    if sys.platform == "win32":
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    with open(LOG_FILE, "ab") as log:
        subprocess.Popen(
            [sys.executable, "-m", "jobs.add_company", symbol, "--job-id", str(job_id)],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **extra,
        )


def start_add(conn: psycopg.Connection, symbol: str, launch: Launcher) -> int:
    """Create the job row and start the process. Returns the job id. The caller checks the lock first."""
    job_id = conn.execute(
        "INSERT INTO job_runs (job, status, symbols) VALUES (%s, 'running', %s) RETURNING id", (ADD_JOB, [symbol])
    ).fetchone()[0]
    conn.commit()
    try:
        launch(symbol, job_id)
    except OSError:
        conn.execute(
            "UPDATE job_runs SET status = 'failed', finished_at = now(), report = %s::jsonb WHERE id = %s",
            ('{"message": "The add process could not be started.", "companies": []}', job_id),
        )
        conn.commit()
        raise
    return job_id


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    return ts.replace(tzinfo=timezone.utc) if ts and ts.tzinfo is None else ts


def job_out(conn: psycopg.Connection, job_id: int) -> Optional[dict]:
    """The page's view of one add job. The status is worked out here, not stored, so a dead process can't leave a lie."""
    row = conn.execute(
        "SELECT status, started_at, finished_at, symbols, current_step, heartbeat_at, report "
        "FROM job_runs WHERE id = %s AND job = %s",
        (job_id, ADD_JOB),
    ).fetchone()
    if row is None:
        return None
    status, started, finished, symbols, step, heartbeat, report = row
    report = report or {}
    companies = report.get("companies", [])
    message = report.get("message")
    now = datetime.now(timezone.utc)
    started, heartbeat, finished = _aware(started), _aware(heartbeat), _aware(finished)

    if status == "running":
        if heartbeat and now - heartbeat > STALE_HEARTBEAT:
            status = "interrupted"
        elif lock_is_free(conn):
            status = "queued" if now - started < QUEUED_GRACE else "interrupted"
        else:
            status = "running"
    else:
        if not companies:
            status = "failed"
            message = message or "The add ended without a report. See logs/add_company.log."
        elif any("NOT ADDED" in c["verdict"] for c in companies):
            status = "failed"
        elif any("WITH GAPS" in c["verdict"] for c in companies):
            status = "partial"
        else:
            status = "success"

    if status == "queued":
        message = "Starting..."
    elif status == "running":
        message = f"Working on: {step}" if step else "Working..."
    elif status == "interrupted":
        message = ("The add stopped before it finished (the API or the PC may have restarted). "
                   "The company may be partly added. Retry to finish it.")
    return {
        "job_id": job_id,
        "symbol": symbols[0] if symbols else "",
        "status": status,
        "step": step if status == "running" else None,
        "started_at": started,
        "finished_at": finished,
        "companies": companies,
        "message": message,
    }
