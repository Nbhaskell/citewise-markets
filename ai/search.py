"""Semantic search over embedded SEC filings.

Usage: python -m ai.search "What are Apple's biggest risks?" [--symbol AAPL] [--form 10-K] [--limit 5] [--latest]
"""
import argparse
import sys
from dataclasses import dataclass
from datetime import date
from typing import Optional

import psycopg

from data.db import connect

from .embeddings import Embedder, FastEmbedder
from .index_filings import vector_literal

SEARCH_SQL = """
SELECT c.id, c.accession_number, f.symbol, f.form, f.filed_at, f.period_of_report, f.url,
       c.section, c.text, 1 - (c.embedding <=> %(q)s::vector) AS score
FROM filing_chunks c
JOIN filings f ON f.accession_number = c.accession_number
WHERE (%(symbols)s::text[] IS NULL OR f.symbol = ANY(%(symbols)s))
  AND (%(forms)s::text[] IS NULL OR f.form = ANY(%(forms)s))
  AND (NOT %(latest)s OR f.filed_at = (
        SELECT max(f2.filed_at) FROM filings f2 WHERE f2.symbol = f.symbol AND f2.form = f.form))
ORDER BY c.embedding <=> %(q)s::vector
LIMIT %(limit)s
"""


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    accession_number: str
    symbol: str
    form: str
    filed_at: date
    period_of_report: Optional[date]
    url: str
    section: Optional[str]
    text: str
    score: float  # cosine similarity, higher is closer


def search_filings(
    conn: psycopg.Connection,
    embedder: Embedder,
    query: str,
    symbols: Optional[list[str]] = None,
    forms: Optional[list[str]] = None,
    limit: int = 5,
    latest_only: bool = False,
) -> list[SearchResult]:
    """Top `limit` passages for `query`. latest_only keeps only the newest filing of each form per company."""
    if not query.strip():
        raise ValueError("query is empty")
    params = {
        "q": vector_literal(embedder.embed_query(query)),
        "symbols": [s.upper() for s in symbols] if symbols else None,
        "forms": forms or None,
        "limit": limit,
        "latest": latest_only,
    }
    with conn.transaction():
        # Filters are applied after the vector index, so let the index keep scanning
        # until it has enough matching rows instead of returning too few.
        conn.execute("SET LOCAL hnsw.iterative_scan = 'relaxed_order'")
        rows = conn.execute(SEARCH_SQL, params).fetchall()
    conn.commit()
    return [SearchResult(*row[:9], float(row[9])) for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query")
    parser.add_argument("--symbol", action="append", help="repeat to search several tickers")
    parser.add_argument("--form", action="append", help="e.g. 10-K or 10-Q; repeatable")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--latest", action="store_true", help="only the newest filing of each form")
    args = parser.parse_args(argv)

    embedder = FastEmbedder()
    with connect() as conn:
        results = search_filings(conn, embedder, args.query, args.symbol, args.form, args.limit, args.latest)
    for i, r in enumerate(results, 1):
        snippet = " ".join(r.text.split())[:300]
        print(f"{i}. [{r.score:.3f}] {r.symbol} {r.form} filed {r.filed_at} | {r.section or '-'}")
        print(f"   {snippet}")
        print(f"   {r.url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
