# CLAUDE.md

Guidance for Claude Code when working in this repo. For setup and commands see [README.md](README.md); for design and
history see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

## What this is

An AI stock market app, built bottom-up. Built so far: the data layer (`data/`, `db/`), the AI layer (`ai/`), a nightly
refresh job (`jobs/`, scheduled in Windows Task Scheduler for 5pm Pacific), a read-only FastAPI backend (`api/`), and a
React web app (`web/`) with three screens: dashboard, stock detail, and a full-page copilot that understands follow-ups. Not built: accounts and
login, portfolios, alerts, a screener, a Claude (Anthropic API) provider, and anything that puts it online. See the
README's "What is not built yet" for the current list.

## Working with the owner

The owner is building this step by step and is not a professional developer, so explain things plainly.

- **After each technical step**, end with a short "in plain terms" summary written so a 12-year-old could follow it
  (simple analogies, no jargon). Skip it for anything that isn't a technical step: commits, pushes, pulls, branch cleanup, and reviewing or catching up on past work.
- **At the start of each step**, say whether it deserves a feature branch and why. Small docs changes can go straight to
  `main`.
- **Ask before you commit, push, or open a pull request.** The owner merges pull requests themselves on GitHub; once
  they say it's merged, verify it, then clean up (switch to `main`, pull, delete the branch locally and on GitHub).
- **Report faithfully.** Say what was verified and how, what wasn't, and what is still weak. Test things for real
  (a browser, the live API) and look for ways to make a test fail; several real bugs here were found that way.
- **Check before big or irreversible actions** (installing software, changing Windows settings, deleting data), and
  never touch secrets: `.env` is private and the SEC contact email in it is only ever sent to sec.gov.
- **Don't store notes about the owner outside this repo** (no separate memory files); anything worth keeping goes in
  these docs where the owner can see and edit it.
- **Keep an eye on plan limits.** Long sessions use more of the owner's usage allowance, so when a session gets long
  (the context window passes about 60-70%), say so and suggest a fresh one at a natural boundary.

## Run and test

- Python: the virtual environment at `.venv` (`.venv/Scripts/python` on Windows). Run tools as modules, from the
  repo root, for example `python -m ai.copilot "question"`.
- Database: `docker compose up -d`, then `python db/migrate.py`.
- Tests: `python -m pytest`. They use the **real** dev database with `ZZ`-prefixed test tickers and clean up after
  themselves. The database container must be running. Run the suite before committing.
- Ollama (with `qwen3:latest`) must be running for the copilot and sentiment.
- Web app: `cd web`, then `npm install` (first time), `npm test`, `npm run typecheck`, `npm run build`. To see it,
  start `python -m api` and `npm run dev` (port 5173).
- Before a commit, run all of them: `python -m pytest`, and `npm run typecheck` plus `npm test` in `web/`.

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
- **Stay on the local model for now.** The owner can't pay for API usage, so don't propose or start a Claude provider;
  keep using `qwen3` through Ollama.
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
- **API (`api/`):** keep it read-only and bound to `127.0.0.1` until accounts exist. Don't add write endpoints, widen
  CORS, or bind to `0.0.0.0` without being asked. Keep response shapes in `schemas.py` stable, since the screens
  depend on them, and keep copilot answers passing through the `unverified_numbers` field. Tests override the
  embedder, chat model, and sentiment model via `app.dependency_overrides`; don't load real models in tests.
  Stop any server you start for a manual check.
- **Web app (`web/`):** its types are generated, never hand-copied. After changing an endpoint or response shape, run
  `python -m api.export_openapi` then `npm run gen:api` in `web/` (the Python contract test fails otherwise). Keep
  TypeScript on 5.x (see DECISIONS). Never use `dangerouslySetInnerHTML` or render API text as HTML, and run any
  outside URL through `safeHttpUrl`. Keep warnings visible (stale data, failed refresh, offline model,
  `unverified_numbers`) and never rely on color alone. Run `npm run typecheck` and `npm test` before committing.
  Node.js lives in `C:\Program Files\nodejs`; add it to `PATH` if a tool can't find `node`. Stop any dev servers you
  start (ports 5173 and 8000).
- **Copilot follow-ups:** earlier turns may only be used to understand the latest question (`condense_question`). Never
  put them in the prompt that writes the answer, or an earlier answer could become evidence; a test guards this. Keep
  showing "Understood as", keep the "No company was named" notice, and validate anything read back from
  `localStorage`. After changing the rewrite prompt or the pronoun safeguard, run `python -m ai.eval_followups` (needs
  Ollama) and `--held-out`; don't tune against the held-out cases, add fresh ones instead.
- **Branches:** do new feature work on a `feature/...` branch and tell the user when a step warrants one. The nightly job
  runs whatever code is checked out, so don't leave half-finished work checked out at 5pm.
- **Scheduling is the user's call:** don't run `scripts/register_nightly_task.ps1` (it changes Windows Task Scheduler)
  without being asked.

## Conventions

- Small tools: each ingest or AI command is a module with a `main()` and `argparse`, is idempotent, and logs
  failures instead of crashing the whole run.
- New behavior gets tests that use fake sources, fake embedders, and fake LLMs, so most tests need no network and no
  model.
- Keep docs honest: when an evaluation or limitation changes, update [docs/DECISIONS.md](docs/DECISIONS.md).
