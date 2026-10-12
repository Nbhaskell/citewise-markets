"""Recent refresh runs and how fresh each company's data is. Used by `--status` and the API."""
import psycopg


def recent_runs(conn: psycopg.Connection, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT id, started_at, finished_at, status, "
        "       (SELECT count(*) FROM jsonb_array_elements(coalesce(details, '[]'::jsonb)) d WHERE d->>'status' <> 'ok') "
        "FROM job_runs WHERE job = 'nightly_refresh' ORDER BY started_at DESC LIMIT %s",
        (limit,),
    ).fetchall()
    return [
        {"id": r[0], "started_at": r[1], "finished_at": r[2], "status": r[3], "problems": r[4]} for r in rows
    ]


def freshness(conn: psycopg.Connection, embedder_name: str, llm_name: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.symbol,
               (SELECT max(ts) FROM prices_daily p WHERE p.symbol = i.symbol),
               (SELECT max(a.published_at) FROM news_articles a JOIN news_article_symbols s ON s.article_id = a.id
                 WHERE s.symbol = i.symbol),
               (SELECT max(filed_at) FROM filings f WHERE f.symbol = i.symbol),
               (SELECT count(*) FROM filings f WHERE f.symbol = i.symbol AND EXISTS
                 (SELECT 1 FROM filing_chunks c WHERE c.accession_number = f.accession_number AND c.embedding_model = %(emb)s)),
               (SELECT count(*) FROM filings f WHERE f.symbol = i.symbol),
               (SELECT count(*) FROM news_article_symbols s WHERE s.symbol = i.symbol AND NOT EXISTS
                 (SELECT 1 FROM news_sentiment n WHERE n.article_id = s.article_id AND n.symbol = s.symbol AND n.model = %(llm)s))
        FROM instruments i WHERE i.active ORDER BY i.symbol
        """,
        {"emb": embedder_name, "llm": llm_name},
    ).fetchall()
    keys = ("symbol", "last_price_date", "newest_headline_at", "newest_filing_date",
            "filings_indexed", "filings_total", "unscored_headlines")
    return [dict(zip(keys, r)) for r in rows]


def print_status(conn: psycopg.Connection, embedder_name: str, llm_name: str) -> None:
    print("Recent runs (your local time):")
    runs = recent_runs(conn)
    if not runs:
        print("  none yet")
    for r in runs:
        secs = int((r["finished_at"] - r["started_at"]).total_seconds()) if r["finished_at"] else None
        took = f"{secs}s" if secs is not None else "unfinished"
        print(f"  #{r['id']}  {r['started_at'].astimezone():%Y-%m-%d %H:%M}  {r['status']:<8} {took:<10} {r['problems']} problem(s)")

    print("\nData freshness:")
    print(f"  {'':<6} {'last price':<11} {'newest headline':<17} {'newest filing':<14} {'indexed':<9} unscored headlines")
    for f in freshness(conn, embedder_name, llm_name):
        news = f["newest_headline_at"]
        news_text = f"{news.astimezone():%Y-%m-%d %H:%M}" if news else "-"
        indexed = f"{f['filings_indexed']}/{f['filings_total']}"
        print(f"  {f['symbol']:<6} {str(f['last_price_date'] or '-'):<11} {news_text:<17} "
              f"{str(f['newest_filing_date'] or '-'):<14} {indexed:<9} {f['unscored_headlines']}")
