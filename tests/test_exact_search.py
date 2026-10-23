"""Vector searches in the test suite are exact (see tests/conftest.py), and the HNSW index is still there for the app.

The suite turns off ordered index scans for the connections it opens, because the approximate index sometimes missed the synthetic test
vectors that other tests leave dead entries beside. Two things must stay true: the tests really do run that way, and the index itself
still exists and can answer a nearest-neighbour query, since nothing else in the suite would notice it going missing.

The second check must not depend on which plan the planner prefers. A first version asked it to plan the real search query (a join of three
tables) and asserted that the plan used the index; on GitHub's database, partway through the suite (about 16 companies, 34 filings, 165
chunks, with statistics) the planner chose an index-nested-loop and a sort instead, and the test failed with nothing wrong with the index.
So this one checks the catalog, checks that the search sorts by the operator the index serves, and asks the planner a question that has
one answer: with sequential scans and sorts switched off, can a plain nearest-neighbour query on the table only be answered by the index?
"""
import os

from ai.search import SEARCH_SQL
from data.db import connect


def test_the_suite_runs_its_searches_without_the_approximate_index():
    assert "enable_indexscan=off" in os.environ.get("PGOPTIONS", "").replace(" ", "")
    with connect() as c:
        assert c.execute("SHOW enable_indexscan").fetchone()[0] == "off"


def test_the_hnsw_index_exists_with_the_cosine_operator_class():
    with connect() as c:
        definition = c.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'filing_chunks_embedding_idx'").fetchone()
    assert definition, "the index filing_chunks_embedding_idx is missing"
    assert "USING hnsw" in definition[0] and "vector_cosine_ops" in definition[0], definition[0]


def test_the_search_sorts_by_the_operator_the_index_serves():
    # `<=>` is cosine distance, which the index's vector_cosine_ops class answers; a different operator would silently stop using it.
    assert "ORDER BY c.embedding <=> " in SEARCH_SQL


def test_a_nearest_neighbour_query_can_be_answered_by_the_index():
    query = "SELECT id FROM filing_chunks ORDER BY embedding <=> %(q)s::vector LIMIT 5"
    params = {"q": "[" + ",".join(["0"] * 383 + ["1"]) + "]"}
    with connect() as c:
        c.execute("SET enable_indexscan = on")  # the suite switches it off; this check asks whether the index could be used
        c.execute("SET enable_seqscan = off")
        c.execute("SET enable_sort = off")  # with both off, only an index that serves the ordering can produce the first rows
        plan = "\n".join(row[0] for row in c.execute("EXPLAIN " + query, params).fetchall())
    assert "filing_chunks_embedding_idx" in plan, plan
