from datetime import date

import pytest

from ai.chunking import chunk_text
from ai.index_filings import index_filing
from data.db import connect

SYMBOL = "ZZIDX"
ACCESSION = "0-ZZIDX1"


def test_chunks_respect_size_and_track_sections():
    text = "\n".join(
        ["Part I", "Item 1.", "Business"]
        + [f"Business sentence number {i} about widgets." for i in range(60)]
        + ["Item 1A.", "Risk Factors"]
        + [f"Risk sentence number {i} about supply chains." for i in range(60)]
    )
    chunks = chunk_text(text, target=500, overlap=100)
    assert len(chunks) > 5
    assert all(len(c.text) <= 500 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].section == "Part I, Item 1"
    assert chunks[-1].section == "Part I, Item 1A"
    assert any(c.section == "Part I, Item 1" for c in chunks)


def test_chunks_overlap_and_cover_all_text():
    lines = [f"line {i:03d} " + "x" * 40 for i in range(100)]
    chunks = chunk_text("\n".join(lines), target=400, overlap=120)
    seen = set()
    for c in chunks:
        seen.update(c.text.splitlines())
    assert seen == set(lines)
    assert chunks[0].text.splitlines()[-1] in chunks[1].text.splitlines()


def test_overlap_never_pushes_a_chunk_past_target():
    lines = ["a" * 100, "b" * 100, "c" * 290, "d" * 100, "e" * 290, "f" * 100]
    chunks = chunk_text("\n".join(lines), target=300, overlap=150)
    assert all(len(c.text) <= 300 for c in chunks)
    assert {line for c in chunks for line in c.text.splitlines()} == set(lines)


def test_long_line_is_split_and_empty_text_gives_no_chunks():
    chunks = chunk_text("word " * 1000, target=300, overlap=50)
    assert len(chunks) > 10 and all(len(c.text) <= 300 for c in chunks)
    assert chunk_text("  \n\n ") == []


class FakeEmbedder:
    dim = 384

    def __init__(self, name):
        self.name = name
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        return [[1.0] + [0.0] * 383 for _ in texts]


@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Idx Co')", (SYMBOL,))
        c.execute(
            "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
            "VALUES (%s, %s, '1', '10-K', %s, 'https://x', %s)",
            (ACCESSION, SYMBOL, date(2026, 1, 1), "\n".join(f"Item 1.\nrow {i} " + "y" * 80 for i in range(40))),
        )
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM filings WHERE symbol = %s", (SYMBOL,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYMBOL,))
        c.commit()


def count(conn):
    return conn.execute("SELECT count(*) FROM filing_chunks WHERE accession_number = %s", (ACCESSION,)).fetchone()[0]


def test_index_is_idempotent_and_reindexes_on_model_change(conn):
    a = FakeEmbedder("model-a")
    n = index_filing(conn, a, ACCESSION)
    assert n > 1 and count(conn) == n
    assert index_filing(conn, a, ACCESSION) == 0 and a.calls == 1

    b = FakeEmbedder("model-b")
    assert index_filing(conn, b, ACCESSION) == n
    models = {r[0] for r in conn.execute("SELECT embedding_model FROM filing_chunks WHERE accession_number = %s", (ACCESSION,))}
    assert models == {"model-b"} and count(conn) == n
