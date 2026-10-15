"""The Add company box's API: lookup (read-only), start (the one write), and job status.

Uses the real dev database with ZZADD/ZZADE tickers. The company-name source and the process launcher are fakes, so
nothing calls Yahoo and no add process starts.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.deps import get_instrument_source, get_job_launcher
from data.db import connect
from data.sources.base import Instrument
from jobs.refresh import LOCK_KEY

ADD, GONE = "ZZADD", "ZZADE"
LOCAL = {"Origin": "http://localhost:5173", "Content-Type": "application/json"}
SECRET = "contact-secret@example.invalid"


class FakeSource:
    def __init__(self, found=True, error=None):
        self.found, self.error = found, error

    def get_instrument(self, symbol):
        if self.error:
            raise self.error
        return Instrument(symbol=symbol, name="Zeta Test, Inc." if self.found else None, exchange="NMS")


class FakeLauncher:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __call__(self, symbol, job_id):
        if self.error:
            raise self.error
        self.calls.append((symbol, job_id))


@pytest.fixture
def conn():
    c = connect()
    yield c
    c.rollback()
    c.execute("DELETE FROM job_runs WHERE job = 'add_company' AND symbols && %s", ([ADD, GONE],))
    c.commit()
    c.close()


@pytest.fixture
def launcher():
    fake = FakeLauncher()
    app.dependency_overrides[get_job_launcher] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_job_launcher, None)


@pytest.fixture
def source():
    holder = {"src": FakeSource()}
    app.dependency_overrides[get_instrument_source] = lambda: holder["src"]
    yield holder
    app.dependency_overrides.pop(get_instrument_source, None)


@pytest.fixture
def client():
    return TestClient(app)


def count_jobs(conn):
    return conn.execute("SELECT count(*) FROM job_runs WHERE symbols && %s", ([ADD],)).fetchone()[0]


def insert_job(conn, *, status="running", started_ago=timedelta(0), heartbeat=None, step=None, report=None):
    started = datetime.now(timezone.utc) - started_ago
    finished = datetime.now(timezone.utc) if status != "running" else None
    job_id = conn.execute(
        "INSERT INTO job_runs (job, status, started_at, symbols, current_step, heartbeat_at, report, finished_at) "
        "VALUES ('add_company', %s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
        (status, started, [ADD], step, heartbeat, json.dumps(report) if report else None, finished),
    ).fetchone()[0]
    conn.commit()  # the API reads through its own connection, so the row must be committed
    return job_id


def hold_lock(conn):
    """Another process holding the database lock, as the nightly refresh does."""
    assert conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]
    conn.commit()


def release_lock(conn):
    conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    conn.commit()


# --- lookup: read-only -------------------------------------------------------

def test_lookup_returns_the_name_and_writes_nothing(client, source, conn):
    before = count_jobs(conn)
    r = client.get(f"/api/add-company/lookup?ticker={ADD.lower()}")
    assert r.status_code == 200
    assert r.json() == {"symbol": ADD, "name": "Zeta Test, Inc.", "exchange": "NMS", "tracked": False}
    assert count_jobs(conn) == before


def test_lookup_unknown_ticker_is_404(client, source):
    source["src"] = FakeSource(found=False)
    r = client.get(f"/api/add-company/lookup?ticker={GONE}")
    assert r.status_code == 404
    assert "No US-listed company found" in r.json()["detail"]


def test_lookup_source_failure_gives_fixed_text_only(client, source):
    source["src"] = FakeSource(error=RuntimeError(f"rate limited for {SECRET}"))
    r = client.get(f"/api/add-company/lookup?ticker={ADD}")
    assert r.status_code == 502
    assert "rate-limiting" in r.json()["detail"]
    assert SECRET not in r.text


def test_lookup_rejects_a_bad_ticker(client, source):
    r = client.get("/api/add-company/lookup?ticker=NOT%20A%20TICKER!")
    assert r.status_code == 422


# --- start: the one write ----------------------------------------------------

def test_start_from_the_local_app_creates_a_job_and_launches_it(client, launcher, conn):
    r = client.post("/api/add-company/jobs", json={"ticker": ADD}, headers=LOCAL)
    assert r.status_code == 202
    body = r.json()
    assert body["symbol"] == ADD
    assert body["status"] == "queued"
    assert launcher.calls == [(ADD, body["job_id"])]


def test_start_refuses_a_foreign_origin_and_starts_nothing(client, launcher, conn):
    r = client.post("/api/add-company/jobs", json={"ticker": ADD},
                    headers={"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert r.status_code == 403
    assert launcher.calls == []
    assert count_jobs(conn) == 0


def test_start_refuses_a_request_with_no_origin(client, launcher, conn):
    r = client.post("/api/add-company/jobs", json={"ticker": ADD}, headers={"Content-Type": "application/json"})
    assert r.status_code == 403
    assert launcher.calls == []
    assert count_jobs(conn) == 0


def test_start_refuses_a_plain_text_body_even_from_the_local_app(client, launcher, conn):
    """A page can send a text/plain body without a preflight. It must not start anything."""
    r = client.post("/api/add-company/jobs", content=f'{{"ticker": "{ADD}"}}',
                    headers={"Origin": "http://localhost:5173", "Content-Type": "text/plain"})
    assert r.status_code in (415, 422)
    assert launcher.calls == []
    assert count_jobs(conn) == 0


def test_start_while_the_lock_is_held_is_busy_and_writes_nothing(client, launcher, conn):
    other = connect()
    try:
        hold_lock(other)
        r = client.post("/api/add-company/jobs", json={"ticker": ADD}, headers=LOCAL)
        assert r.status_code == 409
        assert "Try again in a few minutes" in r.json()["detail"]
        assert launcher.calls == []
        assert count_jobs(conn) == 0
    finally:
        release_lock(other)
        other.close()


def test_start_when_the_process_cannot_launch_marks_the_job_failed(client, conn):
    app.dependency_overrides[get_job_launcher] = lambda: FakeLauncher(error=OSError("no python"))
    try:
        r = client.post("/api/add-company/jobs", json={"ticker": ADD}, headers=LOCAL)
        assert r.status_code == 500
        row = conn.execute(
            "SELECT status FROM job_runs WHERE symbols && %s ORDER BY id DESC LIMIT 1", ([ADD],)
        ).fetchone()
        assert row[0] == "failed"
    finally:
        app.dependency_overrides.pop(get_job_launcher, None)


# --- status ------------------------------------------------------------------

def test_status_of_an_unknown_job_is_404(client):
    assert client.get("/api/add-company/jobs/999999999").status_code == 404


def test_fresh_job_with_no_lock_yet_is_queued(client, conn):
    job_id = insert_job(conn)
    assert client.get(f"/api/add-company/jobs/{job_id}").json()["status"] == "queued"


def test_job_holding_the_lock_is_running_with_its_step(client, conn):
    job_id = insert_job(conn, step="filings")
    other = connect()
    try:
        hold_lock(other)
        body = client.get(f"/api/add-company/jobs/{job_id}").json()
        assert body["status"] == "running"
        assert body["step"] == "filings"
        assert body["message"] == "Working on: filings"
    finally:
        release_lock(other)
        other.close()


def test_a_job_that_died_is_interrupted_not_running(client, conn):
    job_id = insert_job(conn, started_ago=timedelta(minutes=10))
    assert client.get(f"/api/add-company/jobs/{job_id}").json()["status"] == "interrupted"


def test_a_stale_heartbeat_is_interrupted_even_if_the_lock_is_held(client, conn):
    job_id = insert_job(conn, started_ago=timedelta(hours=1),
                        heartbeat=datetime.now(timezone.utc) - timedelta(minutes=30))
    other = connect()
    try:
        hold_lock(other)
        assert client.get(f"/api/add-company/jobs/{job_id}").json()["status"] == "interrupted"
    finally:
        release_lock(other)
        other.close()


def test_finished_job_with_a_gap_is_partial_with_the_report(client, conn):
    report = {"message": None, "companies": [{
        "symbol": ADD, "name": "Zeta", "verdict": "ADDED, WITH GAPS",
        "lines": [{"step": "filings", "status": "NONE", "text": "no 10-K or 10-Q"}]}]}
    job_id = insert_job(conn, status="success", report=report)
    body = client.get(f"/api/add-company/jobs/{job_id}").json()
    assert body["status"] == "partial"
    assert body["companies"][0]["verdict"] == "ADDED, WITH GAPS"
    assert body["companies"][0]["lines"][0]["text"] == "no 10-K or 10-Q"


def test_finished_job_that_added_nothing_is_failed(client, conn):
    report = {"companies": [{"symbol": ADD, "name": None, "verdict": "NOT ADDED", "lines": []}]}
    job_id = insert_job(conn, status="failed", report=report)
    assert client.get(f"/api/add-company/jobs/{job_id}").json()["status"] == "failed"


def test_finished_job_with_no_report_says_so(client, conn):
    job_id = insert_job(conn, status="success")
    body = client.get(f"/api/add-company/jobs/{job_id}").json()
    assert body["status"] == "failed"
    assert "without a report" in body["message"]


def test_a_clean_add_is_success(client, conn):
    report = {"companies": [{"symbol": ADD, "name": "Zeta", "verdict": "ADDED", "lines": []}]}
    job_id = insert_job(conn, status="success", report=report)
    assert client.get(f"/api/add-company/jobs/{job_id}").json()["status"] == "success"
