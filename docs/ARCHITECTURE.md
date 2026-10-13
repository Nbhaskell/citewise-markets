# Architecture

The app is built in layers, bottom-up. Each layer only depends on the ones below it.

```
Client apps        (partly built) web dashboard: web/. Not built: other screens, mobile app, notifications, admin
Backend services   (partly built) read-only API: api/. Not built: accounts, portfolios, alerts, broker API
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
| `job_runs` | One row per nightly refresh: status (running, success, partial, failed) and per-step results as JSON |
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
question (+ earlier turns, optional) -> copilot.py: resolve_question: rewrite a follow-up into a standalone question (LLM)
         -> find companies -> rewrite into extra searches (LLM)
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

### Follow-up questions

`answer_question` takes optional earlier turns (`Turn`: question, answer, companies). They are used in exactly one
place, `condense_question`, which asks the model to rewrite the latest question so it stands alone ("And its risks?"
becomes "What are Tesla's biggest risks?"). From then on the standalone question is what gets searched and answered;
**the history never reaches the prompt that writes the answer**, so an earlier answer can't be used as evidence (a
test checks this). Around the rewrite:

- chosen companies always win; otherwise companies come from the standalone question;
- if the question names no company, has a bare pronoun ("its", "that"), and the rewrite picked a company that was not
  in the most recent turn, the code overrides the model with the most recent company and says "(assuming X)",
  unless the question deliberately goes back ("the first one", "the other");
- a rewrite that is empty, too short, over 300 characters, or fails falls back to the original question;
- the reply carries `interpreted_question` (null when the question was used as written) so the screen can show it.

`ai/eval_followups.py` measures this against 27 conversations (see DECISIONS for results).

### Copilot safety behaviors

- Answers only from retrieved passages, with `[n]` citations. Citations to passages that don't exist are removed.
- **Relevance gate:** if the best passage scores below `MIN_SCORE` (0.62), it answers "I couldn't find..." without
  calling the model.
- **Numbers check:** every figure in an answer must appear in the cited passages (or their headers). If not, it asks
  the model once to rewrite using only quoted figures, and if that fails it prints a warning.
- It refuses buy/sell/hold advice and price predictions. It adds a "not financial advice" note.
- "Annual report" or "10-K" restricts the search to 10-Ks, and "quarter" or "10-Q" restricts it to 10-Qs.

## Nightly refresh (`jobs/`)

`python -m jobs.refresh` walks every active company through five steps, in order:

```
prices -> news -> filings -> index (embed new filings) -> sentiment (score new headlines)
```

- **Isolation:** each (step, company) runs in its own try/except. A failure is recorded and the run continues.
- **Status:** `success` if everything ran, `partial` if anything failed or was skipped, `failed` if every unit failed.
  Exit code 0 only for `success`, so Task Scheduler's "Last Run Result" is meaningful.
- **Alerts:** a run that ends `partial` or `failed`, can't reach the database, or crashes shows a Windows toast
  notification (`jobs/notify.py`, via PowerShell, no extra software or accounts). A run that finds another run in
  progress does not alert. A notification that can't be shown is logged and never affects the job. Database
  connections time out after 10 seconds, so a stopped Docker fails fast instead of hanging.
- **Skips, not failures, for missing prerequisites:** no `SEC_USER_AGENT` skips filings, Ollama not answering skips
  sentiment, and an embedding model that won't load skips indexing. The run is marked `partial` so it isn't silent.
- **Incremental prices:** asks for just enough history to cover the gap since the last stored day (1 month, 3 months,
  and so on, up to the full 5 years for a new company). Prices are upserted, so overlap is harmless.
- **No overlap:** a Postgres advisory lock stops two runs at once; the second exits with code 3. The lock is released
  even if the run crashes.
- **Dependencies are injected** through a `Deps` dataclass, so tests swap in fakes for every outside service.
- **Observability:** the `job_runs` table, `logs/refresh.log`, and `python -m jobs.refresh --status` (recent runs and
  per-company freshness: last price, newest headline, newest filing, filings indexed, unscored headlines).
- **Scheduling:** `scripts/register_nightly_task.ps1` creates a Windows Task Scheduler task (daily, runs when you
  are logged in, catches up after a missed time, never overlaps, 2-hour limit). It is not registered automatically.

## Read-only API (`api/`)

A FastAPI app that exposes the stored data and the AI tools as JSON, for the web screens. It runs in the same
Python process space as the AI code, so the copilot and search are plain function calls, not a second service.

| File | Role |
|---|---|
| `api/app.py` | Routes. Plain (non-async) endpoints, which FastAPI runs in a thread pool, matching the synchronous database driver |
| `api/schemas.py` | The response and request shapes. These are the contract with the screens and drive `/docs` |
| `api/queries.py` | The SQL for each endpoint |
| `api/deps.py` | Per-request database connection, the embedder and chat model (loaded once, on first use), CORS settings |

- **Fakes in tests:** the embedder, chat model, and sentiment model name are FastAPI dependencies, so tests replace
  them via `app.dependency_overrides`. The tests use the real database with `ZZAPI` seed data.
- **Sentiment model:** headline labels are reported for the currently configured chat model (`LLM_PROVIDER`), so a
  later Claude run doesn't mix with Qwen's labels.
- **Price ranges** end at the latest stored bar, not today, so weekends and holidays never give an empty chart.
- **Validation:** tickers must look like tickers, ranges and limits are bounded, questions are 3 to 500 characters.
  Unknown companies return 404, a model that isn't running returns 503.
- **News feed:** `GET /api/news` returns recent headlines across all active companies, optionally filtered by
  company and sentiment label; each row carries the company it was labeled for.
- **Screens the API can support:** dashboard, stock detail (except an AI signal), and copilot chat. Not covered: screener,
  portfolio, alerts and settings, because the data or accounts behind them don't exist yet.

## Web app (`web/`)

React 19 and TypeScript, built with Vite. It only talks to the API; it never touches the database or the AI code.

```
Dashboard page (/)
  FreshnessBar   <- /api/status, /health        data age, failed refreshes, AI model offline
  Watchlist      <- /api/stocks, /prices        price, change, 1-month sparkline, news mood
  NewsPanel      <- /api/news                   latest positive/negative headlines (toggle for all)
  CopilotBox     -> POST /api/copilot           cited answer, clickable sources, warnings

Copilot page (/copilot)
  CompanyFilter      <- /api/stocks             pick up to 5 companies, or none for all
  ConversationView   -> POST /api/copilot       one message per question, each with its own AnswerView
  Composer                                      Enter sends; the button becomes Stop while waiting
  useConversation    localStorage               newest 20 finished questions, validated on load

Stock detail page (/stocks/:symbol)
  header + KeyStats  <- /api/stocks/{symbol}    price, change, 52-week range bar, volume, sector, news mood
  PriceHistory       <- /api/stocks/{symbol}/prices?range=   PriceChart (SVG) with 1M, 3M, 6M, 1Y, 5Y, MAX
  NewsPanel (symbol) <- /api/news?symbol=       that company's headlines over 7 days
  FilingsList        <- /api/stocks/{symbol}/filings         forms, dates, searchable badge, SEC links
  CopilotBox (symbol) -> POST /api/copilot      every question limited to this company
```

- **Types come from the API.** `api/export_openapi.py` writes `web/openapi.json`; `npm run gen:api` turns it into
  `src/api/schema.d.ts`. A Python test fails if the committed `openapi.json` is stale.
- **Dev connection:** Vite proxies `/api` and `/health` to `127.0.0.1:8000`, so the browser sees a single origin. The
  API's CORS list (`localhost:5173` and `:3000`) is the backstop for any other setup.
- **Each panel loads and fails on its own**, with its own error and retry, so one broken endpoint doesn't blank the page.
- **Safety in the UI:** API text is rendered as React text, never HTML. Links from outside data go through
  `safeHttpUrl` (http and https only). Every price change has an arrow and sign, not only a color.
- **Price chart:** hand-drawn SVG sized to its container. The scale, tick, and path math are pure functions in
  `src/lib/chart.ts`. The selected day is shown in a text readout (hover, touch, or arrow keys), which doubles as the
  accessible description. While a new range loads the old chart stays, dimmed, and its labels follow the data it was
  given, so they never mismatch.
- **Copilot conversation:** `useConversation` keeps a list of exchanges (pending, done, error, stopped), each tagged
  with a topic. `buildHistory` picks the newest three finished, non-refused answers from the current topic to send
  with a new question, and the topic number is saved under its own key. It allows one
  in flight at a time, checking a ref that updates instantly as well as state, so two sends in the same instant
  can't both go through. History persists in `localStorage` under a versioned key. Only finished exchanges are
  saved, loaded entries are validated field by field, and a blocked or full storage is reported, never thrown.
  `AnswerView` is the one place an answer is rendered (dashboard box, stock page, and copilot page), and gives its
  source elements unique ids so many answers can share a page.
- **Routing:** `/`, `/stocks/:symbol`, and `/copilot` (React Router), with a main navigation that marks the current page. An unknown ticker (the API's 404) gets a "not tracked" page
  with the command to add it, and a malformed one is rejected before any request is made.
- **Tests:** Vitest with Testing Library against a fake `fetch`. They cover each panel's loading, empty, error, and
  warning states, plus the client's error messages.

## Swappable pieces at a glance

| To change... | Write... | Edit... |
|---|---|---|
| Price or news source | a class matching `PriceSource` or `NewsSource` | the ingest command that constructs it |
| Embedding model | a class matching `Embedder` | `ai/embeddings.py`. A model with a different vector size needs a new migration and a full re-index |
| Chat model (for example Claude) | a class matching `LLM` | `get_llm()` in `ai/llm.py` |

## Not built yet

Accounts and login, portfolios, alerts, the screener and AI-signal endpoints,
the remaining web screens, a mobile app, a Claude implementation of `LLM`, and a licensed data feed.
