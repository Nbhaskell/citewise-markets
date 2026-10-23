# CLAUDE.md

Guidance for Claude Code when working in this repo. For setup and commands see [docs/SETUP.md](docs/SETUP.md) and [docs/OPERATIONS.md](docs/OPERATIONS.md) (the [README](README.md) is the overview); for design and
history see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

## What this is

Citewise for Markets (the GitHub repo is `citewise-markets`; the local folder, the Docker container and the PowerShell window titles keep the old name `stockMarket`): an AI stock market research app, built bottom-up. Built so far: the data layer (`data/`, `db/`), the AI layer (`ai/`), a nightly
refresh job (`jobs/`, scheduled in Windows Task Scheduler for 3pm Pacific), a FastAPI backend (`api/`) that is read-only except for starting an add and removing a company, and a
React web app (`web/`) with four screens: dashboard (with a small "What changed" card), stock detail, "What changed"
(`/changes`), and a full-page copilot that understands follow-ups
and answers from filings, daily prices, and news headlines. Not built: accounts and
login, portfolios, a screener, fundamentals for foreign (20-F) filers, backups
kept anywhere but this PC's disk, email or phone alerts, a Claude (Anthropic API) provider, and anything that puts it online. See the
README's "The full list of what is not built" for the current list.

## Current direction

The owner uses this privately, on their own PC, for **daily research on companies**, and holds no stocks. So skip
accounts, login, portfolios, holdings, and putting it online; none of that is wanted now. The blow-by-blow history
(dates, PR numbers, scores per round) lives in [docs/DECISIONS.md](docs/DECISIONS.md); this section is the state of
play and the standing guidance.

1. **Adding and removing companies: built.** `python -m jobs.add_company TICKER` and an "Add a company" box on the
   dashboard; `python -m jobs.remove_company TICKER` and an on/off tracking switch beside every company (with an "Are you
   sure?"). These are the only two write endpoints the API has (`POST` add-start and `POST /api/remove-company`, both
   approved by the owner; there is no third: switching a removed company back on runs the existing add). Removal sets
   `instruments.active = false` and deletes nothing; a purge is not built and would need a backup first. A foreign 20-F
   filer (TSM) is added with prices and headlines but no filings; whether to also store 20-F is an open decision for the
   owner. DECISIONS: "Removing a company", "Tracking switches".
2. **Database backups: built** as `python -m jobs.backup` (backup, list, verify, restore), scheduled daily at 6pm in Windows
   Task Scheduler (`StockMarketBackup`) into `BACKUP_DIR`. The folder is on the only internal disk, so it does not survive
   the disk failing; an occasional copy to OneDrive or a USB drive is the owner's call. No "newest backup is old" warning yet.
3. **Fundamentals: built** (P/E, market value, revenue, margins, EPS): SEC "company facts" stored in `financial_facts`,
   ratios computed on read in `data/fundamentals.py`, `GET /api/stocks/{symbol}/fundamentals`, a Fundamentals card on the
   stock page, and the copilot quoting the figures as a numbered source of kind `fundamentals` with cautions attached in
   code. US-GAAP filers only. Python computes every ratio; the model only quotes it. A screener can't exist without these.
4. **"What changed": built** (`/changes`, `GET /api/changes`, `data/changes.py`, a dashboard card, a per-browser "since last
   visit" marker). Computed on read, no AI summary, nothing stored. Not built: copilot questions about it.
5. **Copilot trust: ongoing.** Everything below is done in code, not in the prompt (DECISIONS: "Copilot trust, steps 1 to 6"
   and the rounds after it): follow-ups that name only another company keep the earlier topic; ratios the app doesn't
   compute are declined; a request for a buy, sell or hold call always carries `ADVICE_CAUTION`; questions about things
   outside the tracked companies and requests to write something are declined with a fixed message; named periods are
   read exactly or flagged by a caution; a false premise (or a false "no price data" / "no news") gets a code-side note;
   a lowercase ticker and "hows / whats" typing variants are read. A local-model **router** (`ai/router.py`) is asked only
   when the keywords find no specific route, and was turned on by default on 2026-10-19 (`COPILOT_ROUTER=off` switches it
   off).

   **How to read the scores.** The routing rules are word lists, and every list has missed on the next wording. Held-out
   rounds, each written in new wording and run once before any tuning, scored 72% and 65% (the first two) and 46% on the
   fresh round after them (a deliberately harder set). The sealed rounds scored, with the router on, 70%, 79% and 78%
   (keywords only: 58%, 66%, 65%); once a round has been run its cases are tuning material and join `CASES`. The agreed
   stopping rule (stop tuning keywords at 85 to 90 percent on two rounds in a row, or when most failures are arguable) is
   **not met**, and `SEALED` is spent: write a new sealed set (`--sealed`) before any fair comparison. Scores from different
   steps are not the same bar, because some checks changed. DECISIONS holds the per-round numbers and the worst misses.

   **Known open items:** named outlets ("the Wall Street Journal"), "since spring" as a period, a company's later mention
   turning the prices off ("shares fell after Marketco warned"), a price word in a question with no speaker, a speaker
   verb not on the list, and the follow-up "Where does Tesla land on that scale?". The router does not fix a question the
   keywords route wrongly, and a shadow run found no policy for letting the model second-guess a keyword route (DECISIONS:
   "Router second look, step 2"), so there is no second look. **Do not retry rebuilding table rows for the model**: it was
   tried and dropped (DECISIONS, 2026-10-14), and "shares: buy back (quarter total)" fails on purpose. The newest stored
   price being a day old looks fixed by moving the nightly task to 3pm; keep checking `python -m jobs.refresh --status`.

## When the repo goes public

The repo is private now (the README's CI badge shows 404 until it is public). **Remind the owner of this list as soon as they
say the repo is going public, or ask about making it public.** Visibility, settings and uploads on GitHub are the owner's
steps; walk them through each one, and never change repository settings without being asked.

1. Change the visibility (Settings, General, Danger zone).
2. Upload `docs/images/social-preview.png` (Settings, General, Social preview, Edit). GitHub offers this only on a public
   repo, or on a private one that had an image before.
3. Protect `main` (Settings, Rules or Branches): require a pull request and the three CI checks ("Python tests",
   "Web app checks", "Secret scan").
4. Turn on secret scanning with push protection, and Dependabot alerts (Settings, Advanced Security).
5. Turn on "Automatically delete head branches" (Settings, General).
6. Check that the README CI badge now shows the real status.
7. Still open: the demo video link in the README, a "how this relates" section for each README (needs the owner's RAG
   project description), and whether the case study mentions that it was built with Claude Code.

## Working with the owner

The owner is building this step by step and is not a professional developer, so explain things plainly.

- **"In plain terms" summary: only after a technical step.** A technical step is one where code, tests, evaluations,
  data, or settings were built, changed, run, or debugged. End that turn with a short "in plain terms" paragraph written
  so a 12-year-old could follow it (simple analogies, no jargon). **Never** add it after commits, pushes, pull requests,
  merges, pulls, creating or deleting branches, reading or catching up on past work, or answering a question about the
  project. If one turn does both (a fix, then a commit), the summary covers the fix and is written before the commit.
- **At the start of each step**, say whether it deserves a feature branch and why. Small docs changes can go straight to
  `main`.
- **Ask before you commit, push, or open a pull request, in two questions (owner chose this on 2026-10-19):** first the
  commit alone (say plainly that nothing is pushed), then, after the commit, the push and the pull request together as one
  question. Never push or open a PR on the strength of the commit approval, and never offer all three in one question. A
  push on its own (a backup of a branch with no PR) is a separate request from the owner. The owner merges pull requests themselves on GitHub; once
  they say it's merged, verify it, then clean up (switch to `main`, pull, delete the branch locally and on GitHub).
- **Report faithfully.** Say what was verified and how, what wasn't, and what is still weak. Test things for real
  (a browser, the live API) and look for ways to make a test fail; several real bugs here were found that way.
- **Check before big or irreversible actions** (installing software, changing Windows settings, deleting data), and
  never touch secrets: `.env` is private and the SEC contact email in it is only ever sent to sec.gov.
- **Don't store notes about the owner outside this repo** (no separate memory files); anything worth keeping goes in
  these docs where the owner can see and edit it.

## Run and test

- Python: the virtual environment at `.venv` (`.venv/Scripts/python` on Windows). Run tools as modules, from the
  repo root, for example `python -m ai.copilot "question"`.
- Database: `docker compose up -d`, then `python db/migrate.py`.
- Tests: `python -m pytest`. They use the **real** dev database with `ZZ`-prefixed test tickers and clean up after
  themselves. The database container must be running. Run the suite before committing.
- Ollama (with `qwen3:latest`) must be running for the copilot and sentiment.
- Web app: `cd web`, then `npm install` (first time), `npm test`, `npm run typecheck`, `npm run build`. To see it,
  start `python -m api` and `npm run dev` (port 5173), or run `scripts\start.ps1` (database, Ollama check, API, and
  web app in their own windows) and `scripts\stop.ps1` afterwards. Don't leave servers running.
- Before a commit, run all of them: `python -m ruff check .`, `python -m pytest`, and `npm run typecheck` plus `npm test` in `web/`.
  Ruff is configured in `pyproject.toml` (errors, pyflakes and bugbear only; line length, import sorting and modernising rules are off
  on purpose) and is also a step in CI. Do not run `ruff --fix` blindly: its "unused import" fix would have deleted `MAX_DAYS` from
  `api/queries.py`, which `api/app.py` reads back as `queries.CHANGES_MAX_DAYS`. Fix each finding by hand, or `# noqa` it with the reason.
  **Vector searches in the tests are exact, not through the HNSW index** (`tests/conftest.py` sets `PGOPTIONS=-c enable_indexscan=off`
  for every connection the tests open; the app is not affected). Before this, two different tests (`test_filing_search_skips_a_removed_
  company_even_when_asked_for_it_by_name` and `test_comparison_retrieves_from_each_company`) failed in 2 of 6 runs of the test files up
  to and including `test_remove_company.py`, because the approximate index sometimes missed a synthetic test vector among 10,000 real
  chunks and dead entries; with the setting, 10 of 10 such runs passed. `tests/test_exact_search.py` checks that the setting stays on and
  that the HNSW index still exists (in the catalog, with the cosine operator class), that the search sorts by the operator it serves, and
  that a plain nearest-neighbour query can be answered by it. A new search test should not expect the index to behave; if you want to
  test the index path, set `enable_indexscan = on` on that connection deliberately. **Never assert which plan the planner chooses for a
  query that joins tables**: that depends on the table statistics, and an earlier version of that test (asking for the plan of the real
  three-table search) passed on the dev database and every earlier CI run, then failed on `main` when the CI database held about 16 companies, 34
  filings and 165 chunks with statistics. Check the catalog, or ask a question with one answer (sequential scans and sorts switched off).
- Baseline as of 2026-10-23: 3011 Python tests (run on `feature/title-length-test`) and 303 web tests (run on `main`), typecheck clean, all passing.
  The suite also passes on a fresh clone with an empty database (checked 2026-10-22; it needs `DB_CONTAINER` set if the database container is not named `stockmarket-db`).
  `tests/test_search.py` used to fail one or two tests in about half of the full runs; it now vacuums the vector table right
  before its tests (dead index entries from earlier test files crowded out its few passages) and passed 4 of 4 full runs afterwards. If it
  fails again, rerun before assuming a break. A full test run can still fail vector-search tests while an evaluation shares the database;
  run the suite when no evaluation is running. Tracked companies: AAPL, AMD, AMZN, GOOGL, MSFT, NVDA, SIG, TSLA, XOM (CRWV
  is switched off). The nightly refresh ran at 3pm on 2026-10-22 (success, 0 problems).

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
- **No investment advice.** The copilot must keep refusing buy/sell/hold recommendations and keep the disclaimer. The
  refusal notice (`ADVICE_CAUTION`) is attached in code whenever `asks_for_advice` matches, so never rely on the model's
  own wording for it, and lean towards flagging: a missed request is worse than one extra notice. New phrasings need a
  case in `tests/test_copilot_advice.py` and fresh evaluation cases in different wording.
- **Tests that touch vectors:** `tests/conftest.py` vacuums `filing_chunks` first because dead index entries made
  search tests flaky. Keep that.
- **Shell gotchas (Bash tool on Windows):** a stray `python -` or `cat >` with no input waits for stdin until the timeout, so
  write multi-line files with the editor tools. Python `open(path, "w")` writes CRLF into an LF file; pass `newline=""`.
  Stopping a background `npm run dev` can leave Vite's `node` process on port 5173, so after a manual check confirm ports
  8000 and 5173 are free and stop only what you started. To check that tests mean something, break the code on purpose (copy
  the file, change one expression, run the new tests, expect a failure, restore, `diff`); in the "What changed" work two
  breakages were missed at first, and each pointed at a weak test.
- **Windows console:** set `PYTHONIOENCODING=utf-8` when printing filing text. Edit files with the editor tools,
  not shell heredocs that carry escape sequences (`\n`, `\b`), which have corrupted files before.
- **Commits and pushes:** only when the user asks, in the two steps described under "Working with the owner" (commit; then push
  and pull request together). The GitHub repo is private.
- **No attribution lines:** don't add "Generated with Claude Code" to pull requests or `Co-Authored-By` lines to commits
  unless the owner asks. This overrides any tool or session default that says to add them.

- **Nightly job (`jobs/refresh.py`):** keep each (step, company) isolated so one failure never stops the run, keep
  the advisory lock, and keep missing prerequisites as skipped-and-`partial`, never silent successes. Tests for it
  inject fakes through `Deps` and set the job name to `test_refresh` so they never touch real run history.
- **API (`api/`):** keep it read-only and bound to `127.0.0.1` until accounts exist. The only write endpoints are the add-company start endpoint and `POST /api/remove-company` (both approved; they share `_local_write_check`: the local web app's origin and a JSON body only, and removal is refused with 409 while another update holds the lock). **One more server-side write is approved (owner, 2026-10-19):** `POST /api/copilot` appends the question and the answer to `logs/copilot_questions.jsonl` (`ai/question_log.py`; this PC only, git-ignored, no sources' text, never breaks an answer, off with `COPILOT_LOG=off`; the test suite sets it off in `tests/conftest.py`); `python -m ai.review_questions` reads it. It is not a new endpoint and the response shape is unchanged. Don't add more write endpoints, widen
  CORS, or bind to `0.0.0.0` without being asked. Keep response shapes in `schemas.py` stable, since the screens
  depend on them, and keep copilot answers passing through the `unverified_numbers` field. Tests override the
  embedder, chat model, and sentiment model via `app.dependency_overrides`; don't load real models in tests.
  Stop any server you start for a manual check.
- **Web app (`web/`) styling:** jsdom does not apply stylesheets (`css: false` in the Vitest config, which even empties a `?raw` import), so a
  CSS rule that fixes a real defect is tested as text in `tests/test_web_styles.py`, and the web tests check the markup (classes, headings,
  roles). The phone watchlist (a container query that hides the trend and mood columns in a card under 520 px), the contrast of dimmed text
  (use the muted colour, never opacity, on text), and the 24 px minimum for tap targets are covered there; check a layout change in a real
  browser at 375 px, 768 px, and 1280 px, in light and dark, and run an axe-core scan (DECISIONS: "On a phone-width screen the watchlist
  showed a cut-off price").
- **Web app (`web/`):** its types are generated, never hand-copied. After changing an endpoint or response shape, run
  `python -m api.export_openapi` then `npm run gen:api` in `web/` (the Python contract test fails otherwise). Keep
  TypeScript on 5.x (see DECISIONS). Never use `dangerouslySetInnerHTML` or render API text as HTML, and run any
  outside URL through `safeHttpUrl`. Keep warnings visible (stale data, failed refresh, offline model,
  `unverified_numbers`) and never rely on color alone. Run `npm run typecheck` and `npm test` before committing.
  Node.js lives in `C:\Program Files\nodejs`; add it to `PATH` if a tool can't find `node`. Stop any dev servers you
  start (ports 5173 and 8000). If the browser shows old text after you edit a file, check what Vite serves
  (`curl http://localhost:5173/src/...`) and restart `npm run dev`; its file watcher has missed edits.
- **Copilot follow-ups (`ai/followups.py`; the checks on the model's answer are in `ai/answer_checks.py`, company names in
  `ai/companies.py`, and `answer_question` stays in `ai/copilot.py`):** earlier turns may only be used to understand the latest question (`condense_question`). Never
  put them in the prompt that writes the answer, or an earlier answer could become evidence; a test guards this. Keep
  showing "Understood as", keep the "No company was named" notice, and validate anything read back from
  `localStorage`. After changing the rewrite prompt or the pronoun safeguard, run `python -m ai.eval_followups` (needs
  Ollama) and `--held-out`; don't tune against the held-out cases, add fresh ones instead. **A follow-up that points back without a
  topic** ("Do the matching calculation for Google.", "Lay Amazon alongside it.", "What explains that?") is rebuilt from the earlier
  *question* in code when the user's words name no topic and the rewrite routes nowhere (`POINTS_BACK_RE`, `names_a_topic`,
  `routes_somewhere`, `carry_topic`, `carry_comparison`, `carry_cause`; DECISIONS: "Follow-up topic carry"); keep it visible under
  "Understood as" and keep it out of the answer prompt. Measure a change to it with the real `resolve_question`, not only
  `ai.eval_followups` (every case in that eval was tuned): the 45 follow-ups with history in `CASES` plus fresh ones, old against new.
  A breakage script that reports everything caught is meaningless unless the unmutated code is verified green first.
- **Copilot market data (`ai/market/`: `topics`, `advice`, `scope`, `intent`, `windows`, `premise` and `evidence`):** prices, headlines, and sentiment reach the model only as numbered sources, with
  every figure computed in Python (the model never calculates) and the direction written in words. Keep the numbers,
  direction, minus-sign, and cause checks, the "no company named" and index refusals, and the rule that headlines never
  explain a price move. Before changing the prompt, `detect_intent`, or `parse_window`, run `python -m ai.eval_market
  --repeat 3 --show` (needs Ollama) and read the answers, not just the totals; checks that are too loose give false
  passes. The cases live in `ai/eval_cases/` (`CASES`, `HELD_OUT`, `SEALED` are assembled in its `__init__.py`; the runner is
  `ai/eval_market.py`). `HELD_OUT` is empty; the 35 of the fresh round, the 10, 12 and 12 of fixes (1) to (3), the 8 of the cause-word step and
  the 5 of fix (4) and the 11 of fix (5) are in `CASES` (282 with the older ones). All of them are tuning
  material from now on, so write fresh cases in different wording before claiming a fair score, and don't tune against
  held-out cases once run. Before the fundamentals step, three runs scored about 121 to 123 of 129;
  after it, 153 to 155 of 165 on the same 43 cases plus 12 new ones (the 14 held-out cases that were then run, 13 passing,
  are now in `CASES` too, so the set is 69; scored whole on 2026-10-14: 190 of 207, then 196 of 207 after the follow-up fix). A swing of two is normal model
  variation, and a case that drops to 0 of 3 is not: A/B it against the old code (a `git worktree` of `main`, 10 to 20
  runs, since 5 is not enough) before explaining it away. Headlines change daily, so some cases drift on their own.
  **Never edit `SYSTEM_PROMPT` for a new feature**: even three small wording edits moved unrelated cases ("should I
  sell" 16/20 to 4/20); add a conditional block like `FIGURES_RULES` instead.
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
  runs whatever code is checked out, so don't leave half-finished work checked out at 3pm.
- **Removing companies (`jobs/remove_company.py`):** removal is switching `instruments.active` off, never a delete. Anything that lists
  or looks up tracked companies must filter on `active` (`api.queries.tracked_symbols`, `stock_rows`, `data.changes`, `ai.search`,
  `company_mentions`, the copilot's `tracked` list); a new query that lists companies needs the same filter and a case in
  `tests/test_remove_company.py`. The removal takes the shared refresh lock. A purge that deletes rows is a separate, unbuilt
  decision for the owner.
- **Adding companies (`jobs/add_company.py`):** it reuses `run_refresh` (same lock, same isolation) under its own job
  name, `add_company`, and its report is checked against what is stored, not just the step results. Keep "no filings",
  "skipped", and "failed" visible as gaps; never let a ticker that wasn't stored read as OK. Tests set `ADD_JOB` to
  `test_add_company`, use `ZZADD`/`ZZADE` tickers, and inject fakes through `Deps`.
- **Backups (`jobs/backup.py`):** a backup counts as good only after `verify` has restored it and matched every table's
  row count. Keep the TimescaleDB steps in `restore_into` (`timescaledb_pre_restore()` before `pg_restore`, `post_restore()`
  after; without them the restore fails), keep sharing the refresh lock, and keep `restore` from overwriting an existing
  database without `--replace` and a safety backup. Only files named exactly `stockmarket-<date>-<time>.dump` are ever
  trimmed. Tests use real `pg_dump`/`pg_restore` on throwaway `zz_backup_*` databases, never the dev data.
- **Fundamentals (`data/fundamentals.py`, `data/ingest_fundamentals.py`):** store raw SEC figures, never ratios; Python
  computes everything on read. Trailing-twelve-month figures are last full year + this year so far - the same stretch
  last year, and every figure carries its recipe, dates, and filings. Keep the cautions (net income far above operating
  income, a share count that disagrees with the earnings average, a balance-sheet share count, old figures or price,
  mismatched periods); a correct number can still mislead. Keep rejecting a leftover concept (Amazon's 2009 gross
  profit). Figures are checked against the filing text, not just for self-consistency. Tests use fake SEC data and
  `ZZFUN`.
- **Model router (`ai/router.py`, switched by `COPILOT_ROUTER`; ON by default since 2026-10-19, `COPILOT_ROUTER=off` turns it off; the test suite sets it off in `tests/conftest.py`):** the model only picks among the routes that already exist, from
  the standalone question alone (never history or an earlier answer), asked only when the keywords found no specific route and
  none of the guards (`deliberately_filings`: a filing, quarter, segment, "why", dividends, "sales" the keywords did not read) says
  the keyword route was deliberate. It may add, never remove, a notice; its "outside" verdict is a hint, its "writing" verdict needs
  a writing word, and its headlines need a news word. Any failure leaves the keyword route. When it changes what is retrieved the
  answer must say so (`Answer.model_route`, the API's `model_route`, the "local model chose" line); keep that visible, and keep it out
  of "Understood as", which means a rewritten follow-up. Before changing its prompt or a guard,
  run `python -m ai.eval_market --repeat 3` with `COPILOT_ROUTER=off` and with it on (the default; set `=model` to be explicit) on one data snapshot, read the answers, and
  A/B every case that drops; a new fair comparison needs a new `SEALED` set run once with `--sealed`.
- **Questions the app cannot answer (`ai/market/scope.py`: `outside_scope`, `unknown_name`, `writing_request`; used in
  `answer_question`):** declined in code, before the model, with a fixed message. A request to write something is declined
  even when a tracked company is named; the other rules run only when none is named or chosen, and a filings cue ("which
  companies", "10-K", "according to") keeps a research question answerable. A decline must say truthfully what is missing ("I can't
  find X in anything stored"); never decline a summary, list or table request. The company and asset lists are finite: add a
  phrasing as a test first, with a question of its own for every alternative (breaking each alternative on purpose found 46
  untested ones). Tests that need stored text insert their own filing and headline and no filing chunks.
- **Copilot fundamentals (`ai/market/evidence.py`, `ai/copilot.py`):** the figures reach the model only as one numbered source
  (kind `fundamentals`), every number from `data/fundamentals.py`, growth direction in words and checked like a price
  move. **Cautions are attached to the answer in code** (`relevant_cautions` into `Answer.cautions`), scoped to the
  figures the question or the answer is about; never leave them to the model, which dropped Alphabet's "investment
  gains" caution in its own sentence. A new caution in `data/fundamentals.py` needs its scope tags (`add_caution`).
  "Revenue" and "profit" words go to the filings instead when the question names a filing, a quarter, a segment, or asks
  why; P/E, market value, and EPS always go to the figures. Same eval rules as the market data above: new cases in
  different wording before changing routing or the prompt, and read the answers.
- **What changed (`data/changes.py`, `api/queries.changes`):** every rule is a named constant at the top of `data/changes.py`;
  keep the calculation in Python and the endpoint read-only, with no model call. A big move is measured against the
  company's own usual day (baseline excludes the window), a market-wide day is labeled, filings use `filed_at` and never
  `fetched_at`, and headlines beside a move are timing only, never a cause. Mood comes from `label_counts` (don't add
  another counting query). `build_changes` takes the mood counts as a function so `data/` doesn't import `ai/`. Tests:
  `tests/test_changes.py` (`ZZCH*` tickers) `web/src/pages/ChangesPage.test.tsx`, and `web/src/components/ChangesTeaser.test.tsx`. The last-visit marker is
  validated like other `localStorage` reads (`web/src/lib/lastVisit.ts`).
- **Scheduling is the user's call:** don't run `scripts/register_nightly_task.ps1` or `scripts/register_backup_task.ps1`
  (they change Windows Task Scheduler) without being asked.

## Conventions

- Small tools: each ingest or AI command is a module with a `main()` and `argparse`, is idempotent, and logs
  failures instead of crashing the whole run.
- New behavior gets tests that use fake sources, fake embedders, and fake LLMs, so most tests need no network and no
  model.
- Keep docs honest: when an evaluation or limitation changes, update [docs/DECISIONS.md](docs/DECISIONS.md).
- **Dependencies and CI.** `requirements.in` lists the packages the project asks for; `requirements.txt` is the exact `pip freeze` of a
  working environment, and CI installs from it. To add or upgrade a package: change `requirements.in`, install it into a new virtual
  environment, run the full test suite, then replace `requirements.txt` with that environment's freeze. `.github/workflows/ci.yml` runs
  the Python tests (against a throwaway TimescaleDB started with the repo's own `docker-compose.yml`, no Ollama, no model downloads)
  and the web typecheck, tests, and build, plus a gitleaks scan of the whole git history (the "Secret scan" job; the image is pinned in
  the workflow). `.gitleaks.toml` allowlists only the two browser-storage key names in `web/src/lib/conversation.ts`, with
  `condition = "AND"`: gitleaks combines an allowlist's `paths` and `regexes` with OR by default, which silently ignored every
  generic-key finding in that file until a planted secret showed it. Test any change to that file by planting made-up secrets in a scratch
  folder and checking they are still reported. A test must never depend on text that happens to be in the dev database: CI starts empty,
  so a test that needs a stored name or headline inserts its own (four tests had to be fixed for this). Check a workflow change with
  `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`.
