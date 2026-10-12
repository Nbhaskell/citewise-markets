from datetime import date

import pytest

from ai.index_filings import vector_literal
from ai.search import search_filings
from data.db import connect

SYMBOLS = ("ZZSA", "ZZSB")


def axis(i, weight=1.0):
    """A 384-dim vector pointing mostly along axis i (so we control cosine similarity)."""
    v = [0.0] * 384
    v[i] = weight
    v[(i + 1) % 384] = 1.0 - weight
    return v


class FakeEmbedder:
    name = "fake"
    dim = 384

    def __init__(self, vec):
        self._vec = vec

    def embed_query(self, text):
        return self._vec


@pytest.fixture
def conn():
    with connect() as c:
        for sym in SYMBOLS:
            c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, %s)", (sym, sym))
        filings = [
            ("0-SA-OLD", "ZZSA", "10-K", date(2024, 1, 1)),
            ("0-SA-NEW", "ZZSA", "10-K", date(2025, 1, 1)),
            ("0-SA-Q", "ZZSA", "10-Q", date(2025, 6, 1)),
            ("0-SB-NEW", "ZZSB", "10-K", date(2025, 1, 1)),
        ]
        for acc, sym, form, filed in filings:
            c.execute(
                "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                "VALUES (%s, %s, '1', %s, %s, 'https://x', 't')", (acc, sym, form, filed))
        chunks = [  # (accession, index, section, text, vector)
            ("0-SA-OLD", 0, "Item 1A", "old risk text", axis(0)),
            ("0-SA-NEW", 0, "Item 1A", "new risk text", axis(0)),
            ("0-SA-NEW", 1, "Item 7", "new revenue text", axis(5)),
            ("0-SA-Q", 0, "Item 2", "quarter text", axis(0, 0.5)),
            ("0-SB-NEW", 0, "Item 1A", "other company risk", axis(0)),
        ]
        for acc, i, sec, text, vec in chunks:
            c.execute(
                "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
                "VALUES (%s, %s, %s, %s, %s::vector, 'fake')", (acc, i, sec, text, vector_literal(vec)))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM filings WHERE symbol = ANY(%s)", (list(SYMBOLS),))
        c.execute("DELETE FROM instruments WHERE symbol = ANY(%s)", (list(SYMBOLS),))
        c.commit()


def run(conn, vec, **kw):
    return search_filings(conn, FakeEmbedder(vec), "q", **kw)


def test_ranks_by_similarity_and_scores_are_cosine(conn):
    results = run(conn, axis(5), symbols=["ZZSA"], limit=2)
    assert results[0].text == "new revenue text" and results[0].score == pytest.approx(1.0, abs=1e-4)
    assert results[0].score > results[1].score
    assert results[0].section == "Item 7" and results[0].filed_at == date(2025, 1, 1)


def test_symbol_and_form_filters_and_limit(conn):
    assert {r.symbol for r in run(conn, axis(0), symbols=["zzsb"], limit=10)} == {"ZZSB"}
    assert {r.form for r in run(conn, axis(0), symbols=["ZZSA"], forms=["10-Q"], limit=10)} == {"10-Q"}
    assert len(run(conn, axis(0), symbols=["ZZSA"], limit=2)) == 2


def test_latest_only_drops_older_filings_of_the_same_form(conn):
    texts = {r.text for r in run(conn, axis(0), symbols=["ZZSA"], limit=10, latest_only=True)}
    assert "old risk text" not in texts
    assert {"new risk text", "new revenue text", "quarter text"} <= texts


def test_empty_query_rejected(conn):
    with pytest.raises(ValueError):
        search_filings(conn, FakeEmbedder(axis(0)), "   ")
