# CLAUDE.md

Guidance for Claude Code when working in this repo. For setup and commands see [README.md](README.md); for design and
history see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

## What this is

An AI stock market app, built bottom-up. The data layer (`data/`, `db/`) and AI layer (`ai/`) are built as
command-line tools. The nightly job, backend API, and screens are not built.

## Run and test

- Python: the virtual environment at `.venv` (`.venv/Scripts/python` on Windows). Run tools as modules, from the
  repo root, for example `python -m ai.copilot "question"`.
- Database: `docker compose up -d`, then `python db/migrate.py`.
- Tests: `python -m pytest`. They use the **real** dev database with `ZZ`-prefixed test tickers and clean up after
  themselves. The database container must be running. Run the suite before committing.
- Ollama (with `qwen3:latest`) must be running for the copilot and sentiment.

## Rules

- **Secrets:** never commit or print `.env`, passwords, or API keys. Don't paste secrets into chat or logs.
  `SEC_USER_AGENT` holds a real contact email: only ever send it to sec.gov.
- **Database host:** use `127.0.0.1`, never `localhost` (on Windows, `localhost` hangs about 60 seconds).
- **Migrations:** append-only. To change the schema add the next numbered file in `db/migrations/`. Never edit one
  that has been applied. The embedding column is `vector(384)`; a different model size needs a migration and a
  full re-index.
- **Commits in psycopg:** `with conn.transaction()` after an earlier query is only a savepoint. Call `conn.commit()`
  after each unit of work.
- **Interfaces:** keep data sources behind the protocols in `data/sources/base.py`, embedders behind `Embedder`, and
  chat models behind `LLM` in `ai/llm.py`. Don't call a provider directly from the copilot or ingest code.
- **Free sources are prototype-only.** Yahoo Finance and Google News aren't licensed for a public product. Don't
  build features that assume they stay.
- **Don't claim untested things work.** Only a local `OllamaLLM` exists. There is no Claude provider until one is
  written and run against a real key.
- **Verify AI output against its sources.** A citation doesn't prove a number is right. Keep the numbers check and
  the relevance gate in the copilot, and don't loosen them to make answers look better.
- **No investment advice.** The copilot must keep refusing buy/sell/hold recommendations and keep the disclaimer.
- **Tests that touch vectors:** `tests/conftest.py` vacuums `filing_chunks` first because dead index entries made
  search tests flaky. Keep that.
- **Windows console:** set `PYTHONIOENCODING=utf-8` when printing filing text. Edit files with the editor tools,
  not shell heredocs that carry escape sequences (`\n`, `\b`), which have corrupted files before.
- **Commits and pushes:** only when the user asks. The GitHub repo is private.

- **Nightly job (`jobs/refresh.py`):** keep each (step, company) isolated so one failure never stops the run, keep
  the advisory lock, and keep missing prerequisites as skipped-and-`partial`, never silent successes. Tests for it
  inject fakes through `Deps` and set the job name to `test_refresh` so they never touch real run history.
- **Scheduling is the user's call:** don't run `scripts/register_nightly_task.ps1` (it changes Windows Task Scheduler)
  without being asked.

## Conventions

- Small tools: each ingest or AI command is a module with a `main()` and `argparse`, is idempotent, and logs
  failures instead of crashing the whole run.
- New behavior gets tests that use fake sources, fake embedders, and fake LLMs, so most tests need no network and no
  model.
- Keep docs honest: when an evaluation or limitation changes, update [docs/DECISIONS.md](docs/DECISIONS.md).
