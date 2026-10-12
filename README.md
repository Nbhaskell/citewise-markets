# stockMarket

An AI stock market app, built bottom-up. So far the **data layer** and **AI layer** exist as command-line tools;
the backend API and the screens are not built yet.

What works today:

- Daily prices, news headlines, and SEC filings (10-K / 10-Q) stored in one Postgres database
- Semantic search over the filings
- A copilot that answers questions from the filings, with `[1]`-style citations, and a check that flags figures
  not found in the cited passages
- News headline sentiment (positive / negative / neutral / irrelevant) per company
- A nightly refresh job that keeps all of the above up to date (you register it once, see below)
- A read-only HTTP API (FastAPI) over all of it, for the web screens to use (see "The API" below)
- A web dashboard (React) with a watchlist, news panel, and copilot box (see "The web app" below)

Everything runs locally and costs nothing. The AI uses a local model through Ollama.

> **Prototype data only.** Yahoo Finance (prices) and Google News (headlines) are free, unofficial sources and are
> not licensed for a public product. Replace them with licensed feeds before any launch. SEC EDGAR is public and fine.
> The copilot summarizes public filings. It is not financial advice and it can be wrong.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and [docs/DECISIONS.md](docs/DECISIONS.md) for why
things are the way they are, including known weak spots.

## What you need

| Tool | Used for |
|---|---|
| Docker Desktop | Runs the database (Postgres 17 with TimescaleDB and pgvector) |
| Python | Developed on 3.14. Newer syntax (`X \| None`) means 3.10 or later is needed; other versions are untested |
| Ollama with `qwen3:latest` | The local AI model for the copilot and sentiment |
| Node.js (LTS) | Builds and runs the web app in `web/`. Install with `winget install OpenJS.NodeJS.LTS`, then open a new terminal |

## One-time setup

Commands are for Git Bash or PowerShell from the project folder. On Windows the virtual environment's Python is
`.venv\Scripts\python`; on macOS or Linux it is `.venv/bin/python`.

1. **Create your settings file.**
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   - Set `POSTGRES_PASSWORD` to a long random password, and put the same password inside `DATABASE_URL`.
   - Keep `127.0.0.1` in `DATABASE_URL`. Using `localhost` can hang for about a minute on Windows (see DECISIONS).
   - Set `SEC_USER_AGENT` to your name and a contact email. The SEC requires it on every request.

2. **Start the database.**
   ```bash
   docker compose up -d
   ```

3. **Install the Python packages.**
   ```bash
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

4. **Create the tables.**
   ```bash
   .venv\Scripts\python db/migrate.py
   ```

5. **Get the local AI model** (if you don't have it): install Ollama, then
   ```bash
   ollama pull qwen3:latest
   ```
   Keep the Ollama app running whenever you use the copilot or sentiment. The first embedding run also downloads
   a small embedding model (about 130 MB).

6. **Check everything works.**
   ```bash
   .venv\Scripts\python -m pytest
   ```
   The tests use the real database. They create and delete rows with `ZZ...` test tickers and leave your data alone.

## Loading data

Run these in order. Each is safe to re-run: existing rows are updated or skipped, not duplicated.

```bash
.venv\Scripts\python -m data.ingest AAPL MSFT NVDA GOOGL AMZN TSLA
.venv\Scripts\python -m data.ingest_news AAPL MSFT NVDA GOOGL AMZN TSLA
.venv\Scripts\python -m data.ingest_filings AAPL MSFT NVDA GOOGL AMZN TSLA
.venv\Scripts\python -m ai.index_filings
.venv\Scripts\python -m ai.sentiment AAPL MSFT NVDA GOOGL AMZN TSLA
```

Prices must come first, because they create the company records the other steps need. Indexing six companies' filings
takes about 8 minutes and scoring about 700 headlines takes about 2.5 minutes on an RTX 3080.

## Keeping data fresh (nightly job)

`python -m jobs.refresh` runs the whole pipeline for every active company in the database: recent prices, news,
new filings, embedding of any new filings, and sentiment for new headlines. A company or step that fails is
recorded and the rest still run. A normal run on six companies takes well under a minute when nothing big is new.

```bash
.venv\Scripts\python -m jobs.refresh --status     # recent runs and how fresh each company's data is
.venv\Scripts\python -m jobs.refresh              # run it now
.venv\Scripts\python -m jobs.refresh --symbols AAPL --steps news sentiment   # just part of it
```

Add a new company once with `python -m data.ingest TICKER` (prices create the company record), and the nightly job
picks it up from then on. Runs are logged to the `job_runs` table and to `logs/refresh.log`. Exit codes: 0 all good,
1 something failed or was skipped, 2 database unreachable, 3 another run already in progress.

**Schedule it** (one time, changes your Windows Task Scheduler):

```bash
powershell -ExecutionPolicy Bypass -File scripts\register_nightly_task.ps1 -Time 23:00
```

Remove it with `powershell -File scripts\unregister_nightly_task.ps1`. The task only runs while you are logged in,
and if the PC was off at the scheduled time it runs when you next log in. **Docker Desktop and Ollama must be running**
at that time. If Docker is down the run exits with code 2, and if Ollama is down only the sentiment step is skipped.

## The API

```bash
.venv\Scripts\python -m api
```

Serves `http://127.0.0.1:8000`. Open `http://127.0.0.1:8000/docs` for interactive documentation where you can try
every endpoint. The database must be running, and Ollama for the copilot.

| Endpoint | Returns |
|---|---|
| `GET /health` | Database and AI model status |
| `GET /api/status` | Nightly job history and how fresh each company's data is |
| `GET /api/stocks` | Every tracked company: latest price, daily change, news sentiment (the dashboard) |
| `GET /api/news?days=3&limit=30&sentiment=positive&sentiment=negative` | Latest headlines across all companies (filters: `symbol`, `sentiment`, `include_irrelevant`) |
| `GET /api/stocks/{symbol}` | One company, plus 52-week range and volume |
| `GET /api/stocks/{symbol}/prices?range=1M\|3M\|6M\|1Y\|5Y\|MAX` | Daily price bars for a chart |
| `GET /api/stocks/{symbol}/news?days=7&limit=30` | Headlines with sentiment labels (add `include_irrelevant=true` to see all) |
| `GET /api/stocks/{symbol}/filings` | Stored SEC filings and whether each is searchable |
| `GET /api/filings/search?q=...&symbol=AAPL&form=10-K&latest=true` | Matching filing passages with source links |
| `POST /api/copilot` with `{"question": "...", "symbols": ["NVDA"]}` | A cited answer from the filings |

The copilot can take several seconds, so show a loading state. Check `unverified_numbers` in its reply and warn
the user if it isn't empty.

**It is read-only and has no login.** It only listens on this computer (`127.0.0.1`) and only allows requests from
the local web app's address (`localhost:5173` or `:3000`). Don't expose it to a network until accounts exist.

## The web app

The dashboard lives in `web/`. Start the API, then the app:

```bash
.venv\Scripts\python -m api
cd web
npm install        # first time only
npm run dev        # opens at http://localhost:5173
```

It shows the watchlist (price, daily change, one-month trend, news mood), the latest positive and negative headlines,
a data-freshness line that warns about stale data or a failed refresh, and a box for asking the copilot questions
with clickable numbered sources. See [web/README.md](web/README.md) for details, tests, and how its types are
generated from the API.

## Command cheat sheet

| What | Command | Useful options |
|---|---|---|
| Daily prices | `python -m data.ingest AAPL` | `--period 1y` (also `1mo`, `5y`, `max`; default `5y`) |
| News headlines | `python -m data.ingest_news AAPL` | `--days 7` |
| SEC filings | `python -m data.ingest_filings AAPL` | `--forms 10-K,10-Q` `--limit 2` (newest per form) |
| Embed filings | `python -m ai.index_filings [AAPL ...]` | no symbols means every filing |
| Search filings | `python -m ai.search "supply chain risk" --symbol AAPL` | `--form 10-K` `--limit 5` `--latest` |
| Ask the copilot | `python -m ai.copilot "What are Nvidia's biggest risks?"` | `--symbol NVDA` `--no-expand` `--show-prompt` |
| Score headlines | `python -m ai.sentiment AAPL` | `--days 7` `--no-score` (summary only) |
| Refresh everything | `python -m jobs.refresh` | `--symbols AAPL` `--steps prices news filings index sentiment` |
| Check freshness | `python -m jobs.refresh --status` | |
| Start the API | `python -m api` | docs at `http://127.0.0.1:8000/docs` |
| Start the web app | `cd web` then `npm run dev` | needs the API running; `npm test` for its tests |
| Run tests | `python -m pytest` | |
| Database shell | `docker exec -it stockmarket-db psql -U stockmarket` | |

Start and stop the database with `docker compose up -d` and `docker compose stop`. The data lives in a Docker volume
and survives restarts.

If printing filing text fails with an encoding error in a Windows console, set `PYTHONIOENCODING=utf-8`.

## Project layout

```
data/        Ingest tools and data sources
  sources/     base.py (interfaces), yfinance_source.py, google_news.py, edgar.py
ai/          Chunking, embeddings, search, copilot, sentiment, and the LLM interface
api/         The FastAPI app (app.py), response shapes (schemas.py), SQL (queries.py), per-request setup (deps.py)
web/         The React web app (see web/README.md)
jobs/        The nightly refresh runner (refresh.py) and its status report (status.py)
db/          migrate.py and numbered SQL migrations (never edit one that has been applied)
scripts/     PowerShell scripts to schedule and unschedule the nightly job
logs/        refresh.log (git-ignored)
tests/       pytest tests (run against the real database with ZZ-prefixed test tickers)
docker-compose.yml   The database container
.env         Your private settings (git-ignored, never commit it)
```

## Settings (.env)

| Name | Needed | Meaning |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | yes | Database credentials used by Docker |
| `DATABASE_URL` | yes | How the Python tools connect. Must match the three above |
| `SEC_USER_AGENT` | for filings | "Your Name your@email.com", sent to sec.gov |
| `LLM_PROVIDER` | no | Defaults to `ollama`. No other provider exists yet |
| `OLLAMA_MODEL` | no | Defaults to `qwen3:latest` |
| `API_PORT` | no | Port for the API. Defaults to `8000` |
| `CORS_ORIGINS` | no | Comma-separated web app addresses the API accepts. Defaults to localhost on ports 5173 and 3000 |

## What is not built yet

- Failure alerts for the nightly job (today you check `--status` or the log)
- Accounts and login, portfolios, and alerts (the API so far is read-only)
- A natural-language stock screener and an "AI signal" (forecast) per stock, both shown in the wireframes
- More screens: stock detail with a price chart, a full copilot page, screener, portfolio, alerts and settings.
  Only the dashboard exists, and it leaves out the wireframe's market indices strip, portfolio value, and
  "AI daily brief" because no data or accounts sit behind them yet
- A mobile app, and anything for putting the app online
- A Claude (Anthropic API) implementation of the LLM interface
- A paid, licensed market data feed
