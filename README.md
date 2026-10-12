# stockMarket

An AI stock market app, built bottom-up. So far the **data layer** and **AI layer** exist as command-line tools;
the backend API and the screens are not built yet.

What works today:

- Daily prices, news headlines, and SEC filings (10-K / 10-Q) stored in one Postgres database
- Semantic search over the filings
- A copilot that answers questions from the filings, with `[1]`-style citations, and a check that flags figures
  not found in the cited passages
- News headline sentiment (positive / negative / neutral / irrelevant) per company

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
| Node.js | Not needed yet. It's for the future web app |

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
db/          migrate.py and numbered SQL migrations (never edit one that has been applied)
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

## What is not built yet

- A nightly job that runs the whole pipeline automatically
- The backend API (accounts, portfolios, alerts) and the web and mobile screens
- A Claude (Anthropic API) implementation of the LLM interface
- A paid, licensed market data feed
