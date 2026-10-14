# stockMarket

An AI stock market app, built bottom-up and used privately on one PC for company research. The **data layer**, the
**AI layer**, a nightly refresh job, a read-only API, and a web app (dashboard, stock detail, copilot) all exist.

What works today:

- Daily prices, news headlines, and SEC filings (10-K / 10-Q) stored in one Postgres database
- Semantic search over the filings
- A copilot that answers questions from the filings, the stored daily prices, the company's financial figures
  (revenue, profit, margins, market value, P/E), and news headlines (with their sentiment labels), with `[1]`-style
  citations. It flags figures not found in the cited sources and moves described the wrong way, shows a caution
  whenever a figure it quotes can mislead (Alphabet's P/E is flattered by investment gains), and it can't say why a
  price moved, predict prices, or give advice
- News headline sentiment (positive / negative / neutral / irrelevant) per company
- A nightly refresh job that keeps all of the above up to date (you register it once, see below)
- A read-only HTTP API (FastAPI) over all of it, for the web screens to use (see "The API" below)
- A web app (React): a dashboard, a stock detail page (price chart, stats, fundamentals, news, filings, a copilot for
  that company), and a full-page copilot with saved history (see "The web app" below)

Everything runs locally and costs nothing. The AI uses a local model through Ollama.

> **Prototype data only.** Yahoo Finance (prices) and Google News (headlines) are free, unofficial sources and are
> not licensed for a public product. Replace them with licensed feeds before any launch. SEC EDGAR is public and fine.
> The copilot summarizes stored public filings, prices, financial figures, and headlines. It is not financial advice and it can be wrong.

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
.venv\Scripts\python -m data.ingest_fundamentals AAPL MSFT NVDA GOOGL AMZN TSLA
.venv\Scripts\python -m ai.index_filings
.venv\Scripts\python -m ai.sentiment AAPL MSFT NVDA GOOGL AMZN TSLA
```

Prices must come first, because they create the company records the other steps need. Indexing six companies' filings
takes about 8 minutes and scoring about 700 headlines takes about 2.5 minutes on an RTX 3080.

## Keeping data fresh (nightly job)

`python -m jobs.refresh` runs the whole pipeline for every active company in the database: recent prices, news,
new filings, reported figures from the SEC (revenue, profit, earnings per share, share counts), embedding of any new
filings, and sentiment for new headlines. A company or step that fails is
recorded and the rest still run. A normal run on six companies takes well under a minute when nothing big is new.

```bash
.venv\Scripts\python -m jobs.refresh --status     # recent runs and how fresh each company's data is
.venv\Scripts\python -m jobs.refresh              # run it now
.venv\Scripts\python -m jobs.refresh --symbols AAPL --steps news sentiment   # just part of it
```

**Add a company** with one command, then the nightly job keeps it fresh from then on:

```bash
.venv\Scripts\python -m jobs.add_company TSM       # one or more tickers; repeating one just brings it up to date
```

It runs all six steps for that ticker (needs Docker and Ollama running; takes a minute or two, longer for a company
with several big filings to index) and prints a per-step report ending in ADDED, ADDED WITH GAPS, or NOT ADDED. Only
US-listed tickers work; write a share class with a dash (`BRK-B`, and `brk.b` is tidied to that). **Foreign companies
that file a 20-F instead of a 10-K (TSM, ASML) are added with prices, headlines, and sentiment, but no filings:** the
app stores only 10-K and 10-Q, so the report says so and the copilot can't answer filing questions for them. It uses the
same lock as the nightly job, so it refuses to run while a refresh is in progress (exit code 3). Runs show in
`job_runs` as `add_company`, not in `--status`. Same exit codes as above, except 1 also means "added with gaps".
(`python -m data.ingest TICKER` still works for prices alone.)

Runs are logged to the `job_runs` table and to `logs/refresh.log`. Exit codes: 0 all good,
1 something failed or was skipped, 2 database unreachable, 3 another run already in progress, 4 the job crashed.
Exit codes 1, 2 and 4 also pop up a Windows desktop alert, so you hear about a bad night without checking. Test that
alerts reach you with `.venv\Scripts\python -m jobs.notify`. Add `--no-alert` to a manual run to silence them.

**Schedule it** (one time, changes your Windows Task Scheduler):

```bash
powershell -ExecutionPolicy Bypass -File scripts\register_nightly_task.ps1 -Time 23:00
```

Remove it with `powershell -File scripts\unregister_nightly_task.ps1`. The task only runs while you are logged in,
and if the PC was off at the scheduled time it runs when you next log in. **Docker Desktop and Ollama must be running**
at that time. If Docker is down the run exits with code 2, and if Ollama is down only the sentiment step is skipped.

## Backups

Everything lives in one Docker volume, and nothing else keeps a copy. Prices and filings can be downloaded again, but
**news headlines can't** (the free feed only returns recent items) and re-labeling them costs model time. So:

```bash
.venv\Scripts\python -m jobs.backup                 # take a backup now (about 12 MB, a few seconds)
.venv\Scripts\python -m jobs.backup list            # what exists, newest first
.venv\Scripts\python -m jobs.backup verify          # prove the newest one restores (uses a temporary database)
```

A backup is a `.dump` file plus a `.json` note (checksum, row counts) in the `backups` folder (git-ignored), or in
`BACKUP_DIR` if you set it in `.env`. **The default folder is on the same disk as the database**, so it protects
against a deleted volume or a bad migration, not against the disk dying: point `BACKUP_DIR` at a synced or external
drive for that. The newest 30 automatic backups are kept. It waits for a running nightly refresh to finish first, and
`verify` restores into a temporary database, compares every table's row count with the note, checks the search index and
price history work, then deletes the copy. Your live database is not touched. A failed backup shows a desktop alert.

**Schedule it** (one time, changes your Windows Task Scheduler; default 6pm, after the 5pm refresh):

```bash
powershell -ExecutionPolicy Bypass -File scripts\register_backup_task.ps1
powershell -File scripts\unregister_backup_task.ps1          # to remove it
```

**If the database is lost** (volume deleted, new PC): start a fresh database, then restore the newest backup into it.

```bash
docker compose up -d                                          # creates an empty database
.venv\Scripts\python -m jobs.backup list                      # pick a file
.venv\Scripts\python -m jobs.backup restore backups\stockmarket-YYYYMMDD-HHMMSS.dump --into stockmarket --replace
.venv\Scripts\python -m jobs.backup verify backups\stockmarket-YYYYMMDD-HHMMSS.dump
```

`restore` refuses to touch a database that already exists unless you add `--replace`, and replacing a database that has
data first saves it as `stockmarket-prerestore-....dump` (never deleted automatically). To look at a backup without
risk, restore it under another name (`--into stockmarket_old`). Stop the API and any running job first; `--replace`
closes their connections. After restoring, run `jobs.refresh` to catch up on anything newer than the backup.
Backups hold prices, filings, and headlines only (no passwords). They need the same Docker image; a newer Postgres
major version would need a fresh restore test.

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
| `GET /api/stocks/{symbol}/fundamentals` | Revenue, profit, EPS, margins, market value, and P/E from the SEC filings, each with how it was built, its source filings, and cautions. `available` is false for a company with no figures |
| `GET /api/stocks/{symbol}/filings` | Stored SEC filings and whether each is searchable |
| `GET /api/filings/search?q=...&symbol=AAPL&form=10-K&latest=true` | Matching filing passages with source links |
| `POST /api/copilot` with `{"question": "...", "symbols": ["NVDA"], "history": [...]}` | A cited answer from filings, prices, financial figures, and headlines. Each source has a `kind` (`filing`, `price`, `fundamentals`, `headline`, or `sentiment`). `history` (optional, up to 4 earlier question and answer pairs) only helps understand a follow-up; the reply's `interpreted_question` says how it was read |

The copilot can take several seconds, so show a loading state. Check `unverified_numbers` and `cautions` in its reply
and show them to the user if they aren't empty.

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

The dashboard shows the watchlist (price, daily change, one-month trend, news mood), the latest positive and negative
headlines, a data-freshness line that warns about stale data or a failed refresh, and a box for asking the copilot
questions with clickable numbered sources. Click a ticker to open its stock detail page: an interactive price chart
(1M to MAX), key stats, fundamentals (revenue, profit, margins, market value, P/E, each with its calculation and
source filings one click away, and cautions where a number could mislead), that company's news and SEC filings, and a
copilot limited to that company's data.
The Copilot page (`/copilot`) is a full-page chat: pick which companies to search, see your recent questions (saved
in your browser), stop a slow answer, and retry a failed one. You can follow up ("and what about its risks?"): the
last three questions of the current topic are sent along so the copilot can work out what "its" means, and the page
shows an "Understood as" line with the standalone question it searched. Earlier answers are never used as evidence;
every answer is still written only from the stored sources. "Start a new topic" stops earlier questions being used. See [web/README.md](web/README.md) for details, tests, and how its types are
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
| See the price and headline evidence | `python -m ai.market NVDA "How has Nvidia stock done this year?"` | `--model` picks whose sentiment labels to use |
| Check follow-up understanding | `python -m ai.eval_followups` | `--repeat 3` for stability, `--held-out` for the untuned cases. Needs Ollama |
| Check price, news and sentiment answers | `python -m ai.eval_market` | `--repeat 3`, `--show` (print every answer), `--held-out` (none left right now). Needs Ollama |
| Score headlines | `python -m ai.sentiment AAPL` | `--days 7` `--no-score` (summary only) |
| Fundamentals (revenue, profit, EPS, margins, market value, P/E) | `python -m data.fundamentals AAPL` | shows where each figure came from and any cautions |
| Refresh everything | `python -m jobs.refresh` | `--symbols AAPL` `--steps prices news filings fundamentals index sentiment` |
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
jobs/        The nightly refresh (refresh.py), its status report (status.py), adding companies (add_company.py), backups (backup.py)
db/          migrate.py and numbered SQL migrations (never edit one that has been applied)
scripts/     PowerShell scripts to schedule and unschedule the nightly job and the backup
logs/        refresh.log, backup.log (git-ignored)
backups/     Database backups (git-ignored; created on first backup)
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
| `BACKUP_DIR` | no | Where backups are written. Defaults to the `backups` folder in the project |
| `DB_CONTAINER` | no | Name of the database container the backup runs `pg_dump` in. Defaults to `stockmarket-db` |
| `API_PORT` | no | Port for the API. Defaults to `8000` |
| `CORS_ORIGINS` | no | Comma-separated web app addresses the API accepts. Defaults to localhost on ports 5173 and 3000 |

## What is not built yet

- Adding a company from the app (today it is one command, `python -m jobs.add_company`; see "Keeping data fresh")
- Filings for foreign companies that file a 20-F (only 10-K and 10-Q are stored)
- Fundamentals for foreign filers (TSM, ASML): they report under another accounting standard, so they have no stored
  figures, and the copilot says so. Also not stored: dividends, debt, cash, price-to-book, and analyst targets
- Index data (S&P 500 level), so the copilot can answer those instead of refusing
- Backups on a second disk or off this PC (they go to `BACKUP_DIR`; you have to point it somewhere safe), and an alert
  when no backup has happened for days (a PC that is off sends none)
- Accounts and login, portfolios, and alerts (the API so far is read-only)
- A natural-language stock screener and an "AI signal" (forecast) per stock, both shown in the wireframes
- More screens: screener, portfolio, alerts and settings. Only the dashboard, stock detail, and copilot exist.
- Conversation history that follows a user between devices (it's saved per browser; there are no accounts)
- The wireframe's market indices strip, portfolio value, and "AI daily brief" on the dashboard, because no data or
  accounts sit behind them yet
- A mobile app, and anything for putting the app online
- A Claude (Anthropic API) implementation of the LLM interface
- A paid, licensed market data feed
