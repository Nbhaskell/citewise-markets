import os

import psycopg
import pytest

from data.db import database_url

# The model router is on by default (DECISIONS: "Router on by default"). Tests use scripted models that expect exactly the calls they
# were written for, so the suite switches it off; tests of the router itself pass `router=True` or set the variable themselves.
os.environ["COPILOT_ROUTER"] = "off"
# The question log (DECISIONS: "Question log") is on by default; the suite must never add its test questions to the real file. The tests of
# the log itself switch it on with a temporary file.
os.environ["COPILOT_LOG"] = "off"
# Vector searches in the tests are exact, not through the approximate HNSW index. The tests use synthetic one-hot vectors that sit far from
# real embeddings, and the shared dev table also holds thousands of real chunks and the dead entries other tests leave behind, so the
# index sometimes missed a test chunk (two different tests, in about 1 full run in 3, on 2026-10-23). What these tests check is the SQL
# (the company, form and "active" filters, the ordering), which is the same either way. HNSW has no bitmap scan, so turning off ordered
# index scans is what keeps a query off it. libpq reads PGOPTIONS for every connection the tests open; the app itself is not affected.
# tests/test_exact_search.py checks that this stays on and that the index itself still exists and can be used.
os.environ["PGOPTIONS"] = (os.environ.get("PGOPTIONS", "") + " -c enable_indexscan=off").strip()


@pytest.fixture(scope="session", autouse=True)
def vacuum_vector_tables():
    """Tests insert and delete vectors constantly. Dead entries left in the vector index can crowd
    out live results and make search tests flaky, so clean up once before the session."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("VACUUM filing_chunks")
    yield
