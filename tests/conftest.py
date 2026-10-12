import psycopg
import pytest

from data.db import database_url


@pytest.fixture(scope="session", autouse=True)
def vacuum_vector_tables():
    """Tests insert and delete vectors constantly. Dead entries left in the vector index can crowd
    out live results and make search tests flaky, so clean up once before the session."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("VACUUM filing_chunks")
    yield
