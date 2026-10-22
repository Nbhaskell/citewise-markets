# Setup

Everything you need to install, load data, and run Citewise for Markets on your own PC. For what the project is and why it is built the way it is, see the [README](../README.md). Day-to-day running (the nightly refresh, adding and removing companies, backups) is in [OPERATIONS.md](OPERATIONS.md), and the API is in [API.md](API.md).

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

## The web app

The quickest way to start everything (database, an Ollama check, the API, and the web app, then open the browser):

```bash
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Docker Desktop and Ollama must already be open (the script checks both and says what's missing; Ollama only gets a
warning). Safe to run again: anything already running is left alone, and if something else is using the API or web
port it says so and doesn't touch it. Stop the API and web app with `powershell -File scripts\stop.ps1`. The database
keeps running on purpose, because the nightly refresh and backup need it (`docker compose stop` stops it too).

The dashboard lives in `web/`. To start the pieces yourself, start the API, then the app:

```bash
.venv\Scripts\python -m api
cd web
npm install        # first time only
npm run dev        # opens at http://localhost:5173
```

The dashboard shows the watchlist (price, daily change, one-month trend, news mood), a "What changed" card (counts and the
three biggest moves for the latest trading day, linking to the full page), the latest positive and negative
headlines, a data-freshness line that warns about stale data or a failed refresh, and a box for asking the copilot
questions with clickable numbered sources. Click a ticker to open its stock detail page: an interactive price chart
(1M to MAX), key stats, fundamentals (revenue, profit, margins, market value, P/E, each with its calculation and
source filings one click away, and cautions where a number could mislead), that company's news and SEC filings, and a
copilot limited to that company's data.
The What changed page (`/changes`) looks back over the latest trading day, 3, or 7, or "since last visit" (this browser
remembers the newest trading day it showed you; nothing is stored on the server), and lists new filings, big moves, and
notable headlines. A move counts when it is at least 3% and at least twice that company's own usual daily move; a day on
which most companies moved the same way is labeled market-wide; headlines beside a move are timing only, never a
reason. There is no AI summary on it.
The Copilot page (`/copilot`) is a full-page chat: pick which companies to search, see your recent questions (saved
in your browser), stop a slow answer, and retry a failed one. You can follow up ("and what about its risks?"): the
last three questions of the current topic are sent along so the copilot can work out what "its" means, and the page
shows an "Understood as" line with the standalone question it searched. Earlier answers are never used as evidence;
every answer is still written only from the stored sources. "Start a new topic" stops earlier questions being used. See [web/README.md](../web/README.md) for details, tests, and how its types are
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
| Check price, news and sentiment answers | `python -m ai.eval_market` | `--repeat 3`, `--show` (print every answer), `--held-out` (the 2026-10-16 cases, already run once; write fresh ones before the next fair score). Needs Ollama |
| Score headlines | `python -m ai.sentiment AAPL` | `--days 7` `--no-score` (summary only) |
| Fundamentals (revenue, profit, EPS, margins, market value, P/E) | `python -m data.fundamentals AAPL` | shows where each figure came from and any cautions |
| Refresh everything | `python -m jobs.refresh` | `--symbols AAPL` `--steps prices news filings fundamentals index sentiment` |
| Check freshness | `python -m jobs.refresh --status` | |
| Start the API | `python -m api` | docs at `http://127.0.0.1:8000/docs` |
| Start the web app | `cd web` then `npm run dev` | needs the API running; `npm test` for its tests |
| Run tests | `python -m pytest` | |
| Database shell | `docker exec -it stockmarket-db psql -U stockmarket` | |

Start and stop the database with `docker compose up -d` and `docker compose stop`. The data lives in a Docker volume
and survives restarts. The container has `restart: unless-stopped`, so it comes back by itself whenever Docker Desktop
starts (for example after a reboot); one you stopped with `docker compose stop` stays stopped.

If printing filing text fails with an encoding error in a Windows console, set `PYTHONIOENCODING=utf-8`.

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

