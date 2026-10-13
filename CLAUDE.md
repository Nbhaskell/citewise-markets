# CLAUDE.md

Guidance for Claude Code when working in this repo. For setup and commands see [README.md](README.md); for design and
history see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

## What this is

An AI stock market app, built bottom-up. Built so far: the data layer (`data/`, `db/`), the AI layer (`ai/`), a nightly
refresh job (`jobs/`, scheduled in Windows Task Scheduler for 5pm Pacific), a read-only FastAPI backend (`api/`), and a
React web app (`web/`) with three screens: dashboard, stock detail, and a full-page copilot that understands follow-ups
and answers from filings, daily prices, and news headlines. Not built: accounts and
login, portfolios, a screener, fundamentals data (P/E, market value, revenue), adding a company from the app, backups
kept anywhere but this PC's disk, email or phone alerts, a Claude (Anthropic API) provider, and anything that puts it online. See the
README's "What is not built yet" for the current list.

## Current direction

The owner uses this privately, on their own PC, for **daily research on companies**, and holds no stocks. So skip
accounts, login, portfolios, holdings, and putting it online; none of that is wanted now. Roughly in the order to do
them (the owner hasn't confirmed the order):

1. **Easier adding of companies.** Done as a command: `python -m jobs.add_company TICKER` (all five steps, then a
   per-step report). Later: an "Add company" box in the web app, which needs the first write endpoint and a
   background job. That is a deliberate exception to the read-only API rule: confirm it with the owner first and keep
   it bound to `127.0.0.1`. Checked on a real foreign filer (TSM): the SEC has 20-F for it and no 10-K or 10-Q, so it
   is added with no filings and the report says so. Whether to also store 20-F is an open decision for the owner.
2. **Database backups.** Built as `python -m jobs.backup` (backup, list, verify, restore); the restore was tested into
   a brand-new empty Postgres. Not yet scheduled (the owner decides; `scripts/register_backup_task.ps1` exists) and the
   default folder is on the same disk, so the owner should set `BACKUP_DIR` to a drive that survives this one failing.
3. **Fundamentals** (P/E, market value, revenue, margins). The copilot refuses these questions today, and a screener
   can't exist without them. SEC EDGAR's structured company data is the likely source (public, so no licensing
   problem); that has not been checked yet. Python computes every ratio and the model only quotes it as a numbered
   source.
4. **A daily "what changed" view** (new filings, big moves, notable headlines) from data already stored.
5. **Copilot trust.** "Follow-up to another company" and "price target" fail in `ai.eval_market` every time, and the
   evaluation set is small.

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
  start (ports 5173 and 8000). If the browser shows old text after you edit a file, check what Vite serves
  (`curl http://localhost:5173/src/...`) and restart `npm run dev`; its file watcher has missed edits.
- **Copilot follow-ups:** earlier turns may only be used to understand the latest question (`condense_question`). Never
  put them in the prompt that writes the answer, or an earlier answer could become evidence; a test guards this. Keep
  showing "Understood as", keep the "No company was named" notice, and validate anything read back from
  `localStorage`. After changing the rewrite prompt or the pronoun safeguard, run `python -m ai.eval_followups` (needs
  Ollama) and `--held-out`; don't tune against the held-out cases, add fresh ones instead.
- **Copilot market data (`ai/market.py`):** prices, headlines, and sentiment reach the model only as numbered sources, with
  every figure computed in Python (the model never calculates) and the direction written in words. Keep the numbers,
  direction, minus-sign, and cause checks, the "no company named" and index refusals, and the rule that headlines never
  explain a price move. Before changing the prompt, `detect_intent`, or `parse_window`, run `python -m ai.eval_market
  --repeat 3 --show` (needs Ollama) and read the answers, not just the totals; checks that are too loose give false
  passes. `HELD_OUT` in that file is empty on purpose: write fresh cases in different wording before claiming a fair
  score, and don't tune against them once run. Over three runs it scores about 121 to 123 of 129; a swing of two is
  normal model variation, and a case that drops to 0 of 3 is not (A/B it with the old code before explaining it away).
  Don't change the follow-up rewrite prompt without running
  `ai.eval_followups` and `--held-out` (a change for "What about X?" once made it worse and was reverted).
- **Headline rules and sentiment totals (`data/headlines.py`, `ai/sentiment.py`):** "the same headline" (`title_key`) and
  "a quote page" are defined once. `is_quote_page` is the narrow set the copilot uses; `is_template_page` is the broader
  set only the sentiment totals use. Don't point the copilot at the broad set without first deciding what to do about
  the "crashing premise" eval case, which dropped from 8 of 8 passes to 0 of 8 when it was tried; don't loosen the
  check to fit. Totals and score come only from `label_counts` (each story once per company, templates left out), and
  the API news lists show each story once; don't add another counting query. The rules were written from the same
  headlines they are tested on, so new templates need a new rule plus a case in `tests/test_headlines.py`.
- **Branches:** do new feature work on a `feature/...` branch and tell the user when a step warrants one. The nightly job
  runs whatever code is checked out, so don't leave half-finished work checked out at 5pm.
- **Adding companies (`jobs/add_company.py`):** it reuses `run_refresh` (same lock, same isolation) under its own job
  name, `add_company`, and its report is checked against what is stored, not just the step results. Keep "no filings",
  "skipped", and "failed" visible as gaps; never let a ticker that wasn't stored read as OK. Tests set `ADD_JOB` to
  `test_add_company`, use `ZZADD`/`ZZADE` tickers, and inject fakes through `Deps`.
- **Backups (`jobs/backup.py`):** a backup counts as good only after `verify` has restored it and matched every table's
  row count. Keep the TimescaleDB steps in `restore_into` (`timescaledb_pre_restore()` before `pg_restore`, `post_restore()`
  after; without them the restore fails), keep sharing the refresh lock, and keep `restore` from overwriting an existing
  database without `--replace` and a safety backup. Only files named exactly `stockmarket-<date>-<time>.dump` are ever
  trimmed. Tests use real `pg_dump`/`pg_restore` on throwaway `zz_backup_*` databases, never the dev data.
- **Scheduling is the user's call:** don't run `scripts/register_nightly_task.ps1` or `scripts/register_backup_task.ps1`
  (they change Windows Task Scheduler) without being asked.

## Conventions

- Small tools: each ingest or AI command is a module with a `main()` and `argparse`, is idempotent, and logs
  failures instead of crashing the whole run.
- New behavior gets tests that use fake sources, fake embedders, and fake LLMs, so most tests need no network and no
  model.
- Keep docs honest: when an evaluation or limitation changes, update [docs/DECISIONS.md](docs/DECISIONS.md).
