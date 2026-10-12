"""Chunk stored filings and embed them into filing_chunks for semantic search.

Usage: python -m ai.index_filings [AAPL MSFT ...]   (no symbols = every filing)
Filings already indexed with the current model are skipped; others are re-indexed.
"""
import argparse
import sys
import time

import psycopg

from data.db import connect

from .chunking import chunk_text
from .embeddings import Embedder, FastEmbedder

INSERT_CHUNK = (
    "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
    "VALUES (%s, %s, %s, %s, %s::vector, %s)"
)


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def index_filing(conn: psycopg.Connection, embedder: Embedder, accession: str) -> int:
    """Returns the number of chunks written, or 0 if already indexed with this model."""
    symbol, form, filed_at, period, text = conn.execute(
        "SELECT symbol, form, filed_at, period_of_report, text FROM filings WHERE accession_number = %s",
        (accession,),
    ).fetchone()
    done = conn.execute(
        "SELECT count(*) FROM filing_chunks WHERE accession_number = %s AND embedding_model = %s",
        (accession, embedder.name),
    ).fetchone()[0]
    if done:
        return 0

    chunks = chunk_text(text)
    header = f"{symbol} {form} filed {filed_at}" + (f" for period ending {period}" if period else "")
    inputs = [f"{header}. {c.section or ''}\n{c.text}" for c in chunks]
    vectors = embedder.embed_documents(inputs)

    with conn.transaction():
        conn.execute("DELETE FROM filing_chunks WHERE accession_number = %s", (accession,))
        with conn.cursor() as cur:
            cur.executemany(
                INSERT_CHUNK,
                [
                    (accession, c.index, c.section, c.text, vector_literal(v), embedder.name)
                    for c, v in zip(chunks, vectors)
                ],
            )
    conn.commit()  # make each filing's chunks durable and visible right away
    return len(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="*")
    args = parser.parse_args(argv)
    symbols = [s.upper() for s in args.symbols]

    embedder = FastEmbedder()
    failures = 0
    with connect() as conn:
        rows = conn.execute(
            "SELECT accession_number, symbol, form, filed_at FROM filings "
            "WHERE (%s::text[] = '{}' OR symbol = ANY(%s)) ORDER BY symbol, filed_at DESC",
            (symbols, symbols),
        ).fetchall()
        for accession, symbol, form, filed_at in rows:
            started = time.time()
            try:
                n = index_filing(conn, embedder, accession)
                status = f"{n} chunks in {time.time() - started:.0f}s" if n else "already indexed"
                print(f"{symbol} {form} {filed_at}: {status}", flush=True)
            except Exception as exc:
                failures += 1
                conn.rollback()
                print(f"{symbol} {form} {filed_at}: FAILED - {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
