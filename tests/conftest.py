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


@pytest.fixture(scope="session", autouse=True)
def vacuum_vector_tables():
    """Tests insert and delete vectors constantly. Dead entries left in the vector index can crowd
    out live results and make search tests flaky, so clean up once before the session."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("VACUUM filing_chunks")
    yield
