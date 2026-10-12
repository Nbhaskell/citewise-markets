# Decisions, gotchas, and known weak spots

A record of why things are the way they are, and what testing showed. Numbers are from October 2026 on six companies
(AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA). Most evaluations were small and hand-read, so treat them as spot checks, not
benchmarks.

## Decisions

| Decision | Why |
|---|---|
| One Postgres with TimescaleDB and pgvector | One database to run and back up instead of three. Plenty for this size. Moving to separate stores later is possible |
| Free prototype data sources behind interfaces | Lets us build without paying. The interfaces make a licensed feed a one-class swap |
| Local embeddings (`bge-small-en-v1.5`) | Free, private, no API key. Related passages scored about 0.8 and unrelated about 0.4 in a quick check |
| Local LLM through Ollama (Qwen3 8B) as the starting model | No paid API key was available. The `LLM` interface keeps Claude a drop-in later |
| Headlines only for news | The free feed has no article text. Enough for a mood score, not for deep analysis |
| Filings stored whole, then chunked | Keeps the original text so re-chunking or re-embedding never needs a re-download |
| Nightly job as a plain Python command, scheduled by Windows Task Scheduler | No extra services to run. Works for a personal dev machine. A hosted deployment would use a cron job or a cloud scheduler running the same command |
| Task runs only while logged in (interactive principal) | Avoids storing a Windows password. Docker Desktop and Ollama start at login anyway, and the job needs both |
| Missing prerequisites are skipped and flagged `partial`, not failed | One missing piece (Ollama down, no SEC contact) shouldn't block prices and news, but it shouldn't pass silently either |
| Postgres advisory lock for "one run at a time" | The database is already the shared source of truth, and the lock disappears automatically if the process dies |
| Backend in Python (FastAPI), not Node | All the data and AI code is Python, so the API calls it directly instead of through a second service. Node.js is still needed later, only for building the web screens |
| API is read-only and has no login yet | Four of the six wireframe screens need only reads, and it avoids handling passwords before there is a reason to. It listens on `127.0.0.1` and allows only the local web app's origin |
| One database connection per request | Simple and fast enough locally (a connect takes a few milliseconds on `127.0.0.1`). A connection pool is the upgrade if load ever matters |
| Migrations are append-only numbered SQL files | `db/migrate.py` applies each once. Never edit one that has been applied; add a new file |

## Gotchas we hit

| Problem | Cause and fix |
|---|---|
| Every database connection hung for about 60 seconds | On Windows, `localhost` resolves to IPv6 first, but the container only listens on IPv4 (`127.0.0.1`). Use `127.0.0.1` in `DATABASE_URL` |
| yfinance news returned an empty list for every ticker | Source was unusable, so headlines come from Google News RSS instead |
| SEC requests fail or get blocked | EDGAR requires a User-Agent with a name and contact email. Set `SEC_USER_AGENT`. Stay under 10 requests per second |
| Indexing 8 minutes of work showed nothing in the database | With psycopg, `with conn.transaction()` after an earlier query only creates a savepoint, not a commit. Call `conn.commit()` after each unit of work |
| 82% of NVIDIA's headlines were one site's auto-generated "Fund X bought N shares" posts | Excluded `marketbeat.com` in the Google News query (`EXCLUDED_SITES` in `google_news.py`) |
| Search tests failed intermittently, returning 1 result instead of 10 | Tests insert and delete vectors constantly. Dead entries in the HNSW vector index crowded out live results until a `VACUUM`. `tests/conftest.py` now vacuums first. In normal use autovacuum handles it |
| Python patch scripts wrote broken strings and regexes into files | Escapes like `\n` and `\b` were mangled by shell heredocs. Edit files directly, or build such characters explicitly |

## How the safety checks were calibrated

- **Relevance gate (`MIN_SCORE = 0.62`).** Across 16 test questions, unrelated ones topped out at 0.564 and relevant ones
  started at 0.685. The cutoff sits between them. It is tuned on only 16 questions, so very short or vague questions
  can land in the gap.
- **Numbers check.** Added after the copilot answered "$49.9 billion" revenue growth for Microsoft with a valid
  citation. The filing says $50.1 billion, and the cited passage was a table with no stated growth figure, so the
  model did its own subtraction wrong. A citation does not prove a number is right. Now any figure missing from the
  cited passages triggers a retry, then a visible warning. After the fix the answer was $50.1 billion from the 10-K.
- **Query rewriting.** A plain question "How many employees does NVIDIA have?" ranked the right passage (about
  42,000 employees) 243rd. The model rewrote it into extra keyword queries, and merging the results fixed it.
- **Annual vs quarterly.** An "annual report" question was first answered from a 10-Q. Form detection now restricts
  the search.
- **Near-duplicate passages.** Companies repeat paragraphs across filings, which filled the top results with copies.
  Search drops them and offers `--latest`.

## Known weak spots

- **The local model is weaker than Claude.** It can miss details or misread tables. The numbers check catches wrong
  figures, not wrong reasoning. Always check the cited sources.
- **Query rewrites can drift.** For "Should I buy Tesla stock?" it searched for manufacturing strategy. Answers stayed
  grounded in real passages, but the rewrite wasn't what you'd choose.
- **Tables are hard to search.** Financial statements are lines of numbers, which the embedding model handles poorly.
- **Sentiment is shallow and leans neutral.** In a hand audit of 40 headlines, about 35 labels looked right. Mildly
  good or bad news is often labeled neutral, and headlines about other companies are often labeled neutral instead of
  irrelevant. About two-thirds of labels are neutral, mostly quote pages and "X vs Y" comparison pages, so scores sit
  near zero. Consistency across re-runs was not measured.
- **The copilot reads filings only.** It does not use prices, news, or sentiment yet.
- **Search is vector-only.** A keyword (full-text) search was considered for exact-term lookups and not built.
- **The nightly job needs the PC on and you logged in, with Docker Desktop and Ollama running.** Otherwise it
  catches up the next time it can. Nothing alerts you if it fails; you'd see it in `--status` or the log.
- **Price counts mean "bars refreshed", not "new".** Each run rewrites the recent window (upsert), so the number is
  how many bars were written.
- **Free sources can break without notice.** If Yahoo or Google change something, that step errors for each company
  and the run is marked `partial`. Failures are visible but not repaired automatically.
- **The scheduled path was tested once:** after registering, `Start-ScheduledTask` ran the job through Task Scheduler
  (result code 0, run logged as success). A run at the scheduled clock time, and a catch-up after a missed run,
  have not been observed yet.
- **The API has no authentication, rate limiting, or per-user data.** It is safe only because it is bound to this
  computer. Anyone who can reach it can ask the copilot questions, which uses your GPU.
- **The copilot answers one question at a time well.** Several at once queue up behind the single local model and
  would each be slow. Nothing limits concurrent copilot requests yet.
- **The first search or copilot request after the server starts loads the embedding model** (a few seconds). There is
  no warm-up at startup.
- **The wireframes show things the API can't supply yet:** a natural-language screener (no fundamentals data) and an
  "AI signal: bullish, 72%" (no forecasting model exists, and we haven't decided one should).
- **A latest price bar can be a partial day** if requested while the market is open. `as_of` shows its date.
- **Evaluation is small.** About 14 copilot questions and 40 headlines, judged by one reviewer.
- **The embedding model has no query prefix.** bge models recommend one, but fastembed's `query_embed` doesn't add it.
  Adding it by hand made no difference on the test questions, so it was left out.

## Ideas not built yet

- Failure alerts for the nightly job (email or desktop notification)
- A Claude implementation of `LLM` (needs an Anthropic API key), then compare answers against Qwen on the same questions
- Keyword plus vector hybrid search; a reranker
- Filtering quote-page and comparison-page headlines out of sentiment
- A proper evaluation set of questions with known answers
