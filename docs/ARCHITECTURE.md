# Architecture

The app is built in layers, bottom-up. Each layer only depends on the ones below it.

```
Client apps        (not built)   web app, mobile app, notifications, admin
Backend services   (not built)   accounts, portfolios, alerts, optional broker API
AI layer           (built)       embeddings, search, copilot, sentiment      -> ai/
Data layer         (built)       prices, news, filings, one Postgres DB      -> data/, db/
```

## Data layer

One Postgres 17 container (`docker-compose.yml`) with two extensions: **TimescaleDB** for time-series prices and
**pgvector** for embeddings. One database replaces what the original design drew as three boxes (relational,
time-series, vector store).

Tables, created by the numbered files in `db/migrations/`:

| Table | Holds |
|---|---|
| `instruments` | One row per company: ticker, name, sector, SEC CIK |
| `prices_daily` | Daily OHLCV bars. A TimescaleDB hypertable keyed by (symbol, date) |
| `ingestion_runs` | A diary of every price pull, including failures |
| `filings` | Full text of 10-K and 10-Q filings, one row per SEC accession number |
| `filing_chunks` | Filing text cut into about 1,200-character passages, each with a 384-number embedding |
| `news_articles`, `news_article_symbols` | Headlines (no article bodies) and which company each belongs to |
| `news_sentiment` | One label per (article, company, model) |
| `schema_migrations` | Which migrations have been applied |

### Data sources (swappable)

Each source implements an interface in `data/sources/base.py`, so replacing one means writing one class and changing
nothing downstream.

| Need | Today | Licensed for a product? |
|---|---|---|
| Prices, company info | `YFinanceSource` (Yahoo Finance via `yfinance`) | No: replace before launch |
| Headlines | `GoogleNewsSource` (public RSS feed, headlines only) | No: replace before launch |
| Filings | `EdgarClient` (SEC EDGAR) | Yes. Needs `SEC_USER_AGENT` and stays under 10 requests per second |

## AI layer

```
filings text -> chunking.py -> embeddings.py -> filing_chunks (pgvector)
                                                      |
question -> copilot.py: find companies -> rewrite the question into extra searches (LLM)
         -> search.py (vector search, merged by reciprocal rank, near-duplicates dropped)
         -> relevance gate -> LLM answers from the passages with [n] citations
         -> citations and numbers check (one retry on failure) -> answer
headlines -> sentiment.py -> LLM labels in batches (strict JSON) -> news_sentiment
```

| Piece | File | Notes |
|---|---|---|
| Chunker | `ai/chunking.py` | About 1,200 characters with overlap. Labels each chunk with its Part and Item (for example "Part I, Item 1A") |
| Embedder | `ai/embeddings.py` | Local `BAAI/bge-small-en-v1.5` through fastembed. The vector column is fixed at 384 dimensions |
| Indexer | `ai/index_filings.py` | Commits per filing. Skips filings already indexed with the current model |
| Search | `ai/search.py` | Cosine similarity with an HNSW index. Filters by ticker and form. `latest_only` keeps the newest filing of each form |
| LLM interface | `ai/llm.py` | `generate(system, user, json_schema=None)`. Only `OllamaLLM` (Qwen3) exists. Pick with `LLM_PROVIDER` |
| Copilot | `ai/copilot.py` | See the safety behaviors below |
| Sentiment | `ai/sentiment.py` | Labels each headline from an investor's view of one company |

### Copilot safety behaviors

- Answers only from retrieved passages, with `[n]` citations. Citations to passages that don't exist are removed.
- **Relevance gate:** if the best passage scores below `MIN_SCORE` (0.62), it answers "I couldn't find..." without
  calling the model.
- **Numbers check:** every figure in an answer must appear in the cited passages (or their headers). If not, it asks
  the model once to rewrite using only quoted figures, and if that fails it prints a warning.
- It refuses buy/sell/hold advice and price predictions. It adds a "not financial advice" note.
- "Annual report" or "10-K" restricts the search to 10-Ks, and "quarter" or "10-Q" restricts it to 10-Qs.

## Swappable pieces at a glance

| To change... | Write... | Edit... |
|---|---|---|
| Price or news source | a class matching `PriceSource` or `NewsSource` | the ingest command that constructs it |
| Embedding model | a class matching `Embedder` | `ai/embeddings.py`. A model with a different vector size needs a new migration and a full re-index |
| Chat model (for example Claude) | a class matching `LLM` | `get_llm()` in `ai/llm.py` |

## Not built yet

Nightly refresh job, backend API, web and mobile screens, a Claude implementation of `LLM`, and a licensed data feed.
