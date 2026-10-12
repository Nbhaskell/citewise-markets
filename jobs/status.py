"""Show recent refresh runs and how fresh each company's data is."""
import psycopg


def print_status(conn: psycopg.Connection, embedder_name: str, llm_name: str) -> None:
    print("Recent runs (your local time):")
    runs = conn.execute(
        "SELECT id, started_at, status, extract(epoch FROM finished_at - started_at)::int, "
        "       (SELECT count(*) FROM jsonb_array_elements(coalesce(details, '[]'::jsonb)) d WHERE d->>'status' <> 'ok') "
        "FROM job_runs WHERE job = 'nightly_refresh' ORDER BY started_at DESC LIMIT 5"
    ).fetchall()
    if not runs:
        print("  none yet")
    for run_id, started, status, secs, problems in runs:
        took = f"{secs}s" if secs is not None else "unfinished"
        print(f"  #{run_id}  {started.astimezone():%Y-%m-%d %H:%M}  {status:<8} {took:<10} {problems} problem(s)")

    print("\nData freshness:")
    print(f"  {'':<6} {'last price':<11} {'newest headline':<17} {'newest filing':<14} {'indexed':<9} unscored headlines")
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
    for symbol, price, news, filing, indexed, total, unscored in rows:
        news_text = f"{news.astimezone():%Y-%m-%d %H:%M}" if news else "-"
        print(f"  {symbol:<6} {str(price or '-'):<11} {news_text:<17} {str(filing or '-'):<14} {indexed}/{total:<7} {unscored}")
