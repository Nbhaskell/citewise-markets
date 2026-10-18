# CLAUDE.md

Guidance for Claude Code when working in this repo. For setup and commands see [README.md](README.md); for design and
history see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

## What this is

An AI stock market app, built bottom-up. Built so far: the data layer (`data/`, `db/`), the AI layer (`ai/`), a nightly
refresh job (`jobs/`, scheduled in Windows Task Scheduler for 3pm Pacific), a FastAPI backend (`api/`) that is read-only except for starting an add, and a
React web app (`web/`) with four screens: dashboard (with a small "What changed" card), stock detail, "What changed"
(`/changes`), and a full-page copilot that understands follow-ups
and answers from filings, daily prices, and news headlines. Not built: accounts and
login, portfolios, a screener, fundamentals for foreign (20-F) filers, adding a company from the app, backups
kept anywhere but this PC's disk, email or phone alerts, a Claude (Anthropic API) provider, and anything that puts it online. See the
README's "What is not built yet" for the current list.

## Current direction

The owner uses this privately, on their own PC, for **daily research on companies**, and holds no stocks. So skip
accounts, login, portfolios, holdings, and putting it online; none of that is wanted now. Roughly in the order to do
them (the owner hasn't confirmed the order):

1. **Easier adding of companies.** Done as a command (`python -m jobs.add_company TICKER`) and as an "Add a company"
   box on the dashboard (lookup, confirm, then a background add with progress). The box's start endpoint is the one
   approved write exception to the read-only API rule (owner approved 2026-10-15); it is bound to `127.0.0.1`, accepts
   only the local web app's origin and JSON, and is refused while another update holds the lock. Removing a company is
   not built. Checked on a real foreign filer (TSM): the SEC has 20-F for it and no 10-K or 10-Q, so it
   is added with no filings and the report says so. Whether to also store 20-F is an open decision for the owner.
2. **Database backups.** Built as `python -m jobs.backup` (backup, list, verify, restore); the restore was tested into
   a brand-new empty Postgres. Scheduled daily at 6pm in Windows Task Scheduler (`StockMarketBackup`, registered
   2026-10-13 at the owner's request), writing to `C:\Users\nbhas\stockmarket-backups` via `BACKUP_DIR` in `.env`.
   That folder is outside the project but still on the only internal disk (`C:`), so it does not survive the disk
   failing; an occasional copy to OneDrive or a USB drive is the owner's call. No "newest backup is old" warning yet.
3. **Fundamentals** (P/E, market value, revenue, margins), in three steps the owner approved on 2026-10-13: (1) data
   and calculations, built: SEC "company facts" stored in `financial_facts`, ratios computed in `data/fundamentals.py`,
   a nightly `fundamentals` step; (2) built: `GET /api/stocks/{symbol}/fundamentals` and a "Fundamentals" card on the
   stock detail page (`web/src/components/Fundamentals.tsx`); (3) built: the copilot answers P/E, market value,
   EPS, revenue, profit, and margin questions from the figures as a numbered source of kind `fundamentals`
   (`ai/market.py`), and attaches the relevant cautions to the answer in code. US-GAAP filers only; foreign filers show "not available".
   Python computes every ratio and the model only quotes it as a numbered source. A screener can't exist without these.
4. **A daily "what changed" view** (new filings, big moves, notable headlines) from data already stored. Built on
   (`/changes`, `GET /api/changes`, `data/changes.py`; see DECISIONS "What changed"), with a "since last visit" option
   (a per-browser marker) and a dashboard card. No AI summary, computed on read, nothing stored. Not built: copilot
   questions about it.
5. **Copilot trust.** In progress; the history is in DECISIONS.md ("Copilot trust, steps 1 to 6"). Built, all in code and
   not in the prompt: a follow-up that only names another company keeps the earlier topic (`carry_topic`); ratios the app
   doesn't compute are declined (`unstored_figures`); "Tesla's stock" with nothing else is a price question
   (`BARE_STOCK_RE`); "how many shares does X have" goes to the stored share count (`HOW_MANY_SHARES_RE`); a request for a
   buy, sell, or hold call always carries a fixed notice (`asks_for_advice`, `ADVICE_CAUTION`); a table passage that lost
   its unit sentence to the cut between passages gets it back at prompt time (`ai/table_units.py`); and a figure the
   question itself contains is not flagged as unverified when the answer only declines or restates (`_users_own_numbers`).
   Two held-out rounds, each written in new wording and run once before any tuning: the first (36 cases) scored 78 of 108
   (72%), the second (35 cases, after five fixes from the first) **68 of 105 (65%)**, which is the honest number (DECISIONS:
   "Held-out round" and "Second held-out round"). The five fixes from the first round are merged: quoted titles must be
   in the sources (`invented_titles`, a warning, it does not prevent the invention), more price wordings, more ratios
   declined and a caution on a false "no price" claim (`false_price_claim`), market-value, sentiment and advice wordings,
   the earlier year's real date in the growth label, and a placeholder headline rule. The second round shows the wording
   rules are not general: new everyday phrasings miss in the same places (a period in a price question, "earn" and
   "sales", "Now do X" follow-ups, a few advice phrasings, a non-company question answered from a filing), and some
   passing answers use the wrong period without saying so. The set was 157 cases then (189 after fix (f)); all are tuning material now, and the full
   run scored 356 of 366 before the second round. Also failing: "shares: buy back (quarter total)" on purpose (a real
   wrong answer: one month's row, not the Total; rebuilding rows was tried and dropped, see DECISIONS, so don't retry it),
   and flaky cases ("news and stock", "press coverage", "sentiment", "how is X doing") that swing between runs on the same
   code. Scores from different steps are not the same bar, because some checks changed. Not done: the fixes the second
   round points to, in the order DECISIONS gives (price questions with a period first), whether to weigh a model-based
   routing step against more keyword rules, and the content of advice-adjacent answers. (The fresh held-out round that measured
   fixes (a) to (f) is done; see below.) (The newest-stored-price-a-day-old problem looks fixed by moving the nightly task to 3pm: the 2026-10-15 run
   left every price on the same day. It is one run, so keep checking `python -m jobs.refresh --status`.)

   **Next up (as of 2026-10-15): this step.** Order from DECISIONS ("Second held-out round"). Done (PR #32, merged
   2026-10-15): (a) price questions that name a period or compare with the start of
   the year, and (b) reading more periods (numbers, "a few weeks", "since July") and saying in code, as a caution, when
   the period asked cannot be matched or "today" has no close (DECISIONS: "Price questions that name a period"; 422 of 471
   before, 434 after, tuning material, not a fair score). Done (PR #33, merged 2026-10-16): (c) follow-up carrying ("Now
   do X", "better or worse than X" keeping both companies; DECISIONS: "Follow-up carrying"; 436 of 471 on the market
   evaluation; 11 fresh follow-up cases went 3 of 11 on `main` to 7 of 11, 9 of 11 after adding the words they missed, now
   tuning material). Done (PR #34, merged 2026-10-16): (d) "earn" and "sales" wording (DECISIONS: "'Earn' and 'sales'
   wording"; 437 of 471 before, 446 after; 11 fresh cases 8 of 11, 9 of 11 after one fix, now tuning material). Done (PR #35,
   merged 2026-10-16): (e) advice and sentiment wording (DECISIONS: "Advice and sentiment wording"; 474 of 504 before, 485 after; 11 fresh cases 5 of 11, then all 11 after adding their wordings, now
   tuning material). Done (PR #36, merged 2026-10-16): (f) questions about things outside the tracked companies
   (DECISIONS: "Questions about things outside the tracked companies"; 515 of 537 before, 519 after; 10 fresh cases 6 of 10
   once the checker read refusal text, now tuning material). **That closes items (a) to (f).**

   **Fresh held-out round for the whole second-round work: run 2026-10-16, fair score 48 of 105 (46%)** (branch
   `feature/fresh-held-out-round`; the 35 market and 8 follow-up resolution cases were committed, 56ab20b, before the run;
   DECISIONS: "Fresh held-out round"). The second round scored 68 of 105 (65%) on different questions, and 12 of these 35 were
   deliberate stretches (3 of 12 passed; the other 23 passed 13), so the numbers are not a trend; about 21 of 35 (60%) after
   reading every answer and counting six arguable expectations. By group (first pass): prices, news, and sentiment 5 of 12,
   figures 3 of 5, filings 3 of 3, traps, advice, and outside topics 3 of 10, follow-ups 2 of 5; follow-up resolution 3 of 8.
   The worst failures are confident wrong answers, not refusals: a false "no price data" or "no news" (the code-side caution
   fired for some and not others), a wrong period stated as the one asked ("when the year opened", "ninety days"), a missed
   advice notice ("cash out"), and a false premise accepted ("Google doubled"). **Those 35 cases have been run, so
   they are tuning material from now on (they are in `CASES`).** **Fix (1) is merged (PR #37, 2026-10-16;
   DECISIONS: "Fix (1) of the fresh round"):** the since-mid-month, "N units ago", "close", "higher than it was ... ago",
   "chatter" and "stories" wordings now route, and a false "no news" claim carries a caution like the price one; the 189 older
   cases went 549 to 548 of 567 (a flaky case), the fresh round's 35 went 48 to 65 of 105, and 10 fresh cases went 2 to 6 of 10.
   **Fix (2) is merged (PR #38, 2026-10-16; DECISIONS: "Fix (2) of the fresh round"):** "ninety days", quarters, trading days, "since 2024", "since Monday", "a year and a half" and "when the year
   opened" are read exactly, and every other named period that is not read is flagged by a caution (prices and headlines) instead
   of defaulting silently; a window past the first stored close says so. A clean old-against-new run on 234 cases went 631 to 636
   of 702; 12 fresh cases went 1 to 5.
   **Fix (3) is merged (PR #39, 2026-10-16; DECISIONS: "Fix (3) of the fresh round"):** "cash out", "take profits", "unload", "is it time to", "would it be crazy to" and the like now carry the
   advice notice (with company-side guards), "Google doubled" and "can only go up" reach the prices, and a new code-side premise
   statement quotes the stored move when the question assumes one that did not happen. A clean old-against-new run on 246 cases went
   648 to 657 of 738; 12 fresh cases went 3 to 8.
   **The cause-word gap from fix (3) is merged (PR #40, 2026-10-16; DECISIONS: "Cause words"):** "what drove / caused / triggered it", "how come" and "what's responsible for" bring the headlines to a price question, and
   "<Company>'s jump / slide" or "the move in <Company> stock" with a cause word reaches the prices. A clean old-against-new run on 258
   cases went 675 to 681 of 774; 8 fresh cases went 1 to 7.
   **Fix (4) is merged (PR #41, 2026-10-17; DECISIONS: "Fix (4) of the fresh round"):** a
   question that is only a company switch ("Skip to Nvidia.", "Switch over to Microsoft.", "Give me the number for Apple too.") or only
   a comparison ("Is Tesla's list longer than that?", "Does Amazon say anything similar?", "Did Microsoft fare better than that?") names
   no topic, so the earlier question rebuilt with the new company now wins over the model's rewrite (it used to be trusted when it named
   both companies); "similar" searches the earlier company too; "the companies" / "which company" with no company named is used as written.
   One clean old-against-new run on 266 cases went 707 to 711 of 798; follow-up resolution 39 (40 after a checker fix) to 46 of 46; 10 fresh
   cases (fair score) went 3 to 4 of 10, 8 of 10 after adding the words they missed (now tuning material). The next wording will miss
   again: these are still word lists.
   **Fix (5) is merged (PR #42, 2026-10-17; DECISIONS: "Fix (5) of the fresh round"):** a
   question that names no tracked company and contains a capitalised name found in no stored filing or headline is declined by name
   (`unknown_name`, so no company list is needed for it); the company list grew from 70 to 183 names; more outside assets (gas, diesel,
   crops, "the economy", REITs, stablecoins, more currencies); and a request to write an email, post, poem, code, slides or a translation
   is declined **even when a tracked company is named** (`writing_request`; summaries, lists and tables are research and stay answerable).
   One clean old-against-new run on 271 cases went 726 to 730 of 813 (gas prices, Chipotle and "draft an email" 0 to 3 of 3); 11 fresh
   cases (fair score) went 2 to 8 of 11. A false-positive spot check of 38 ordinary questions with no tracked company found 3 wrongly
   declined (Brussels, the Pentagon, Llama: names in nothing stored). Eggs, uranium and "write up a one-pager" still miss.
   **Model-based routing experiment is merged (PR #43, 2026-10-17, router OFF by default; DECISIONS: "Model-based
   routing experiment"):** when the keywords find no specific route, the local model is asked one JSON question (`ai/router.py`: which
   kinds of stored data does this question need; research / outside / writing) and can only add to the keyword route; it never names a
   company or writes an answer, and any failure leaves the keywords. It is off unless `COPILOT_ROUTER=model` (or `router=True`).
   Guards in code keep it from overriding the keyword rules' deliberate filings routes ("10-K", "why", dividends, "iPhone sales"), from
   adding headlines to a non-news question, and from declining anything that has no writing word in it; its "outside" verdict is only
   a hint. **Router visibility is built on `feature/router-visibility` (2026-10-17, DECISIONS: "Router visibility"):** the answer carries
   `model_route` (the kinds of evidence the model chose; empty when the keywords decided, the router was off or failed, or it chose
   what the keywords had), and the page shows a muted "the local model chose: ..." line under "Looked at ..."; "Understood as" is
   unchanged. Results: a fresh 39-question baseline of 44% (52 of 117) went to 71% on the same cases (those are now development
   material); on the 282 older cases 761 to 769 of 846; the sealed 38 (run once) 78 to 93 of 114 on the first version, 90 on the final,
   after two false declines found by reading the answers made it a second-look set. The merge rule set beforehand is met. **Next:** the
   owner decides whether to turn it on by default (a one-line change plus a test; the switch back is `COPILOT_ROUTER=off`); "clear
   in profit" is covered by the router when it is on (a fresh set will tell). The router does not fix a question the keywords route wrongly, or a follow-up whose
   rewrite lost its topic. Every keyword list so far has missed on the next wording, so write a new sealed set (`SEALED`, `--sealed`)
   before the next fair comparison. All earlier fresh cases are in `CASES` (359 market, plus the 37-case development set `ROUND_SL`
   = 396; 51 follow-up resolution), so `HELD_OUT` is empty. **`SEALED` now holds 41 UNRUN cases (`SEALED_ROUND_TWO`, written
   2026-10-17 on `feature/router-second-look`, DECISIONS: "Router second look, step 1") for the next fair comparison: run it once
   with `--sealed`, at the end, and never tune on it.** An offline check on the development set found 13 of 29 non-follow-up cases
   routed wrongly by the keywords and never put to the router; 12 of them need evidence REMOVED, which the router does not do.

## Working with the owner

The owner is building this step by step and is not a professional developer, so explain things plainly.

- **"In plain terms" summary: only after a technical step.** A technical step is one where code, tests, evaluations,
  data, or settings were built, changed, run, or debugged. End that turn with a short "in plain terms" paragraph written
  so a 12-year-old could follow it (simple analogies, no jargon). **Never** add it after commits, pushes, pull requests,
  merges, pulls, creating or deleting branches, reading or catching up on past work, or answering a question about the
  project. If one turn does both (a fix, then a commit), the summary covers the fix and is written before the commit.
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
- Before a commit, run all of them: `python -m pytest`, and `npm run typecheck` plus `npm test` in `web/`.
- Baseline as of 2026-10-17 (on `feature/router-visibility`, after PR #43's 2038 and 253): 2067 Python tests, 260 web tests,
  all passing. A full test run can fail one or two vector-search tests while an evaluation shares the database;
  run the suite when no evaluation is running. Tracked companies: AAPL, AMD, AMZN, GOOGL, MSFT, NVDA, TSLA. The nightly
  refresh ran at 3pm on 2026-10-16 (success, 0 problems).

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
- **Commits and pushes:** only when the user asks. The GitHub repo is private.
- **No attribution lines:** don't add "Generated with Claude Code" to pull requests or `Co-Authored-By` lines to commits
  unless the owner asks. This overrides any tool or session default that says to add them.

- **Nightly job (`jobs/refresh.py`):** keep each (step, company) isolated so one failure never stops the run, keep
  the advisory lock, and keep missing prerequisites as skipped-and-`partial`, never silent successes. Tests for it
  inject fakes through `Deps` and set the job name to `test_refresh` so they never touch real run history.
- **API (`api/`):** keep it read-only and bound to `127.0.0.1` until accounts exist. The only write is the add-company start endpoint (approved). Don't add more write endpoints, widen
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
  passes. `HELD_OUT` in that file is empty; the 35 of the fresh round, the 10, 12 and 12 of fixes (1) to (3), the 8 of the cause-word step and
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
- **Model router (`ai/router.py`, switched by `COPILOT_ROUTER`):** the model only picks among the routes that already exist, from
  the standalone question alone (never history or an earlier answer), asked only when the keywords found no specific route and
  none of the guards (`deliberately_filings`: a filing, quarter, segment, "why", dividends, "sales" the keywords did not read) says
  the keyword route was deliberate. It may add, never remove, a notice; its "outside" verdict is a hint, its "writing" verdict needs
  a writing word, and its headlines need a news word. Any failure leaves the keyword route. When it changes what is retrieved the
  answer must say so (`Answer.model_route`, the API's `model_route`, the "local model chose" line); keep that visible, and keep it out
  of "Understood as", which means a rewritten follow-up. Before changing its prompt or a guard,
  run `python -m ai.eval_market --repeat 3` with `COPILOT_ROUTER=off` and with `=model` on one data snapshot, read the answers, and
  A/B every case that drops; a new fair comparison needs a new `SEALED` set run once with `--sealed`.
- **Questions the app cannot answer (`ai/market.py`: `outside_scope`, `unknown_name`, `writing_request`; used in
  `answer_question`):** declined in code, before the model, with a fixed message. A request to write something is declined
  even when a tracked company is named; the other rules run only when none is named or chosen, and a filings cue ("which
  companies", "10-K", "according to") keeps a research question answerable. A decline must say truthfully what is missing ("I can't
  find X in anything stored"); never decline a summary, list or table request. The company and asset lists are finite: add a
  phrasing as a test first, with a question of its own for every alternative (breaking each alternative on purpose found 46
  untested ones). Tests that need stored text insert their own filing and headline and no filing chunks.
- **Copilot fundamentals (`ai/market.py`, `ai/copilot.py`):** the figures reach the model only as one numbered source
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
