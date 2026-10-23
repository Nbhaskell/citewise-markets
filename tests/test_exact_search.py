"""Vector searches in the test suite are exact (see tests/conftest.py), and the HNSW index is still there for the app.

The suite turns off ordered index scans for the connections it opens, because the approximate index sometimes missed the synthetic test
vectors that other tests leave dead entries beside. Two things must stay true: the tests really do run that way, and the index itself
still exists and can answer the search query, since nothing else in the suite would notice it going missing.
"""
import os

from ai.search import SEARCH_SQL
from data.db import connect


def test_the_suite_runs_its_searches_without_the_approximate_index():
    assert "enable_indexscan=off" in os.environ.get("PGOPTIONS", "").replace(" ", "")
    with connect() as c:
        assert c.execute("SHOW enable_indexscan").fetchone()[0] == "off"


def test_the_hnsw_index_exists_and_the_search_query_can_use_it():
    params = {"q": "[" + ",".join(["0"] * 383 + ["1"]) + "]", "symbols": None, "forms": None, "limit": 5, "latest": False}
    with connect() as c:
        c.execute("SET enable_indexscan = on")
        c.execute("SET enable_seqscan = off")  # force the planner to use the index whenever it can, whatever the table's size
        plan = "\n".join(row[0] for row in c.execute("EXPLAIN " + SEARCH_SQL, params).fetchall())
    assert "filing_chunks_embedding_idx" in plan, plan
