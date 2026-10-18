# Decisions, gotchas, and known weak spots

A record of why things are the way they are, and what testing showed. Numbers are from October 2026 on six companies
(AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA); AMD was added on 2026-10-15, so later entries (the "What changed" ones) cover seven. Most evaluations were small and hand-read, so treat them as spot checks, not
benchmarks.

## Decisions

| Decision | Why |
|---|---|
| One Postgres with TimescaleDB and pgvector | One database to run and back up instead of three. Plenty for this size. Moving to separate stores later is possible |
| Free prototype data sources behind interfaces | Lets us build without paying. The interfaces make a licensed feed a one-class swap |
| Local embeddings (`bge-small-en-v1.5`) | Free, private, no API key. Related passages scored about 0.8 and unrelated about 0.4 in a quick check |
| Local LLM through Ollama (Qwen3 8B) as the starting model | No paid API key was available. The `LLM` interface keeps Claude a drop-in later |
| Headlines only for news | The free feed has no article text. Enough for a mood score, not for deep analysis |
| Filings stored whole, then chunked | Keeps the original text so re-chunking or re-embedding never needs a re-download |
| Nightly job as a plain Python command, scheduled by Windows Task Scheduler | No extra services to run. Works for a personal dev machine. A hosted deployment would use a cron job or a cloud scheduler running the same command |
| Task runs only while logged in (interactive principal) | Avoids storing a Windows password. Docker Desktop and Ollama start at login anyway, and the job needs both. Docker Desktop starting did not start the database container until it got `restart: unless-stopped` (2026-10-14; before that it was found stopped, which would have failed the nightly refresh and backup) |
| `scripts\start.ps1` and `scripts\stop.ps1` start and stop the API and web app; the database is left running | Five manual steps in the right order become one command, and the checks (Docker running, database healthy, Ollama answering, ports free) say what is wrong in plain words. They never start Docker Desktop or Ollama, and never touch Windows settings or the scheduled tasks. `stop` closes only the windows `start` opened (found by window title) and any server whose command line is this app's; an unrelated program on those ports is reported and left alone. The database keeps running because the 5pm and 6pm jobs need it |
| Missing prerequisites are skipped and flagged `partial`, not failed | One missing piece (Ollama down, no SEC contact) shouldn't block prices and news, but it shouldn't pass silently either |
| Postgres advisory lock for "one run at a time" | The database is already the shared source of truth, and the lock disappears automatically if the process dies |
| Backend in Python (FastAPI), not Node | All the data and AI code is Python, so the API calls it directly instead of through a second service. Node.js is still needed later, only for building the web screens |
| API is read-only and has no login yet | Four of the six wireframe screens need only reads, and it avoids handling passwords before there is a reason to. It listens on `127.0.0.1` and allows only the local web app's origin |
| Web app: React + TypeScript + Vite, plain CSS, no UI or chart library | Small and fast (about 87 kB compressed). Sparklines are a few lines of SVG. A charting library can come with the stock detail page, where it earns its weight |
| Web types generated from the API's OpenAPI file | The contract can't drift silently: a Python test fails if `web/openapi.json` is stale, and a type error appears if a screen uses a field that no longer exists |
| Price chart is hand-drawn SVG, not a charting library | The chart needs only a line, axes, and a selected-day readout. Hand-drawn SVG tests in jsdom (a canvas library wouldn't), follows the dark and light themes through CSS, is keyboard and screen-reader friendly, and adds no dependency. The cost: we own the tick and scale math (covered by tests). Candlesticks, volume bars, or indicators would be the moment to reconsider a library |
| Copilot history is saved in the browser, not on the server | There are no accounts, so the server can't tell users apart. Browser storage needs no backend change and stays private to the browser. The cost: history doesn't follow you between browsers or devices |
| Follow-ups are understood by rewriting them, and history is never evidence | The common approach for retrieval systems: rewrite "and its risks?" into a standalone question, then search and answer as usual. Keeping history out of the answering prompt means an earlier (possibly wrong) answer can't be used as a fact, and the citation and numbers checks still apply unchanged |
| The browser sends the history; the server stores nothing | There are no accounts, so the server can't tell users apart. Sending at most four short turns keeps requests small and bounded (validated: 4 turns, 500-character questions, 2,000-character answers, tickers only) |
| The page shows "Understood as: ..." | The rewrite is a model guess. Showing it makes a wrong reading visible to the person instead of silently shaping the answer |
| A bare pronoun means the most recent company, enforced in code | The model sometimes picked an older company. The rule is overridden only when the question names no company and the rewrite picked a company absent from the most recent turn, never for "the first one" and similar |
| "Start a new topic" instead of guessing when the subject changed | Detecting a topic change reliably is hard; one explicit button is predictable, and standalone questions already weren't bent by history in the evaluation |
| The copilot page does not pretend to remember | The API takes one question and no earlier messages. Sending earlier turns to the model would be a real feature (prompt changes, retrieval that understands "its", new evaluation), not a UI change. The page says each question stands alone |
| One question at a time on the copilot page | The local model answers one at a time, and a queue of slow answers is worse than a Stop button |
| Stock detail reuses the dashboard's news panel and copilot box | One component each, with an optional company, instead of two near-copies that would drift apart |
| Dashboard shows only what the data supports | The wireframe's market indices, portfolio value, and AI daily brief are left out rather than faked |
| News panel defaults to positive/negative headlines | About two-thirds of headlines are routine (quote pages, "X vs Y"), so showing all of them buries the news. A toggle shows everything |
| Feature branches for the web screens | A new codebase with many commits shouldn't land on `main` half-finished, and the nightly job runs whatever is checked out |
| One database connection per request | Simple and fast enough locally (a connect takes a few milliseconds on `127.0.0.1`). A connection pool is the upgrade if load ever matters |
| Migrations are append-only numbered SQL files | `db/migrate.py` applies each once. Never edit one that has been applied; add a new file |
| The copilot picks prices, headlines, or filings with keyword rules, not a model call | Predictable, testable, and instant. A model call would add a delay and a new way to be wrong. The cost is vocabulary gaps: a fresh set of 14 questions found three phrasings the rules missed. Gaps fall back to the filings route, which says "the sources don't provide that" |
| Python computes every price figure; the model only copies | Matches the rule that the model never calculates. Changes, highs, lows, and ranges are written into the source text, with the direction in words ("a rise"), so the numbers check can verify the answer |
| Headlines are context, never a cause | They are titles only. The copilot is told, and checked, not to say a headline explains a price move. "Why did it move?" is answered with the move, the headlines of the period, and "the stored data can't show the cause" |
| Quote pages and "X vs Y" pages are left out of the copilot's headlines | They are most of the neutral labels, say nothing new, and quote intraday prices that read like closing prices. The news panel is unchanged, but the sentiment totals and score now leave them out too |
| Index and market-wide questions are refused | No index data is stored. Asked "What is the S&P 500 at?", the model answered "$217" from a filing's total-return chart (scaled from $100). Refusing is better than a confident wrong number |
| A cause hint is retried, then shown as a caution | The prompt alone didn't stop the model hedging ("may have influenced market sentiment"), so the code checks for it, retries once, and the reply carries a visible `cautions` entry if it persists |

| The add box's start is the one write endpoint, approved by the owner (2026-10-15) | The owner asked for the box. It is guarded: the local web app's origin only, a JSON body only, refused while another update holds the lock, and the lookup before it is read-only so the owner confirms the exact name. The add runs in its own process (`python -m jobs.add_company --job-id N`), so an API restart doesn't kill it. Status lives in `job_runs` (migration 008) and is worked out when read, so a dead process shows as "interrupted", not "running" |
| Adding a company reuses the nightly job's code (`jobs/add_company.py` calls `run_refresh`) | Same lock, same per-step isolation, same skipped-means-partial rules, so there is one pipeline to trust, not two. It logs under its own job name so `--status` still shows only nightly runs. A ticker whose prices fail and was never stored is left out of the later steps (otherwise each would add a confusing "not in instruments" error) |
| The add report is checked against the database, not just the step results | The refresh counts "ok, 0 new filings" as a success. For a company the SEC knows only as a 20-F filer, that is a quiet gap. The report counts what is stored and says "no filings" with the reason |
| Backups are `pg_dump` files made inside the Docker container (`jobs/backup.py`) | No Postgres tools to install on Windows, and the dump is the same version as the server. The database is about 46 MB, so a full dump (12 MB, a few seconds) every day is simpler and safer than incremental backup tooling |
| A backup holds the nightly job's lock while it counts rows and dumps | A refresh half-way through a company can't end up in a backup, and the row counts in the note match the dump exactly, so a restore can be checked precisely instead of "roughly" |
| A backup only counts as good after `verify` restores it and matches the counts | A dump that was written but can't be loaded is worse than none: it feels safe. Verify restores into a temporary database, compares every table to the note, runs a vector-search query and checks the price history, then deletes the copy |
| `restore` never overwrites an existing database without `--replace`, and replacing the live one saves a safety backup first | The restore command is the most dangerous one in the project. The safety backup (`stockmarket-prerestore-*`) is never trimmed |
| Backups go to a folder, configurable with `BACKUP_DIR`; the default is on the same disk | Choosing the owner's external or cloud storage isn't ours to guess. The README says plainly that the default doesn't survive the disk failing |
| Fundamentals come from the SEC's free "company facts" feed, stored raw in `financial_facts` | Public and unlicensed, one ~4 MB download per company, and the same contact rules as the filings. Raw figures are kept (concept, period, value, filing), and Python computes every ratio when asked, so a number can always be traced to a filing and recomputed if a rule changes |
| Trailing twelve months = last full year + this year so far - the same stretch last year | It is how the filings report (a 10-K total and year-to-date totals in each 10-Q). Done from the period dates, not the filings' own "Q1/Q2" labels, which companies with odd fiscal years (NVIDIA's ends in January) would break. Every figure shows its recipe, dates, and filings |
| Cautions are part of the result, not an afterthought | A correct number can still mislead. Net income far above operating income (Alphabet, Amazon), a share count that disagrees with the earnings average (Tesla), a balance-sheet share count, old figures or price, and mismatched periods each produce a plain-language caution |
| US-GAAP filers only; foreign filers show "not available" | TSMC and ASML report under IFRS, in another currency, with different concept names and (for TSMC) no earnings per share. Supporting them would be real work, and it matches the 20-F filings gap. Decided by the owner on 2026-10-13 |
| A company with no fundamentals gets `200` with `available: false` and a reason, not a 404 | The company exists; only its figures don't (not downloaded yet, or a foreign filer). The page can then say why and how to fetch them instead of showing a generic error |
| On the stock page, cautions come before the numbers, labeled "Caution:", and each calculation is one click away | A correct number can mislead (Alphabet's P/E looks cheap because of investment gains), so the warning must be read first and never rely on color. The recipe and source filings stay available without crowding the card |
| The copilot gets the figures as one numbered source of kind `fundamentals`, worked out by `data/fundamentals.py` | Same mechanism as prices: Python computes, the model copies, and the numbers check applies unchanged. A company with no figures still gets a source that says "not available" and why, so the answer can say so instead of falling into the generic "couldn't find anything" |
| Cautions are attached to the answer in code, scoped to the figures asked about | In the first real test the model's own sentence left out Alphabet's "investment gains" caution, so relying on the prompt would have shown a flattered P/E with no warning. Each caution carries the figures it concerns (`caution_scopes`), so a revenue answer doesn't get an earnings warning. The scope comes from the question and from what the answer actually mentions, so an answer that wanders from revenue into P/E still carries it |
| P/E, market value, EPS, and share count always go to the figures; "revenue", "profit", and "margin" go to the filings when the question names a filing, a quarter, a segment, or asks why | The figures are twelve-month totals and can't explain anything. "What does the 10-K say about revenue?" and "Why is revenue growing?" keep their old (filings) route; "What was revenue last quarter?" goes to the 10-Q, which has the quarter |
| The rules for using the figures are a separate prompt block, added only when a figures source is present | Adding them to the shared prompt moved other questions (see the gotchas): "news and stock" went from 10 of 10 to 0 of 10 and "should I sell" from 16 of 20 to 4 of 20. Questions that don't use the figures now get byte-for-byte the prompt they were evaluated with |
| Growth is written as "measured on the 6 months to X vs the same 6 months a year earlier only (not the growth of the 12-month total)" | The model wrote "revenue for the last 12 months was $303.0 billion, an increase of 95.8%" when 95.8% compared only the latest six months. With the plain wording that happened in 6 of 6 runs of the premise question; with this wording, 0 of 18 |
| "What changed" is computed on read from stored data, with no model and no stored results (2026-10-15) | A daily view is only worth having if every line can be traced to a stored row. Python picks the filings, moves, and headlines with named rules; a model summary would add the invented-fact risk the copilot checks exist to contain, and the dashboard already leaves out an "AI daily brief" for that reason. Nothing is stored, so there is no migration and nothing for the nightly job to maintain |

## Gotchas we hit

| Problem | Cause and fix |
|---|---|
| Every database connection hung for about 60 seconds | On Windows, `localhost` resolves to IPv6 first, but the container only listens on IPv4 (`127.0.0.1`). Use `127.0.0.1` in `DATABASE_URL` |
| yfinance news returned an empty list for every ticker | Source was unusable, so headlines come from Google News RSS instead |
| SEC requests fail or get blocked | EDGAR requires a User-Agent with a name and contact email. Set `SEC_USER_AGENT`. Stay under 10 requests per second |
| Indexing 8 minutes of work showed nothing in the database | With psycopg, `with conn.transaction()` after an earlier query only creates a savepoint, not a commit. Call `conn.commit()` after each unit of work |
| 82% of NVIDIA's headlines were one site's auto-generated "Fund X bought N shares" posts | Excluded `marketbeat.com` in the Google News query (`EXCLUDED_SITES` in `google_news.py`) |
| Search tests failed intermittently, returning 1 result instead of 10 | Tests insert and delete vectors constantly. Dead entries in the HNSW vector index crowded out live results until a `VACUUM`. `tests/conftest.py` now vacuums first. In normal use autovacuum handles it |
| `openapi-typescript` crashed with "Cannot read properties of undefined (reading 'createKeywordTypeNode')" | npm installed TypeScript 7 (the new native compiler), which lacks the compiler interface that tool uses. TypeScript is pinned to 5.9 (`typescript@~5.9.3`), which the tool officially supports. Don't upgrade past 5.x until the tool supports it |
| The first evaluation scored 14 of 16 | Two real misreadings: a comparison ("how does that compare to Amazon's?") dropped the company just discussed, and a bare "its" picked an older company. The prompt now says pronouns mean the most recent company and comparisons name both, which fixed the first. The second survived the prompt change, so a code-level safeguard was added |
| A follow-up with no company ("And what about its biggest risks?") was answered about Amazon | With no company named, the copilot searches every company and returned Amazon's passages. Found by trying it in the browser. The answer now carries a notice that no company was named and lists the companies it drew on. It doesn't fix the cause (no memory); that needs conversation-aware retrieval |
| A saved-history test passed even with a bug in saving | It checked what loads back, and loading also discards unfinished entries, which hid the bug. Found by deliberately breaking the code. The test now reads the raw saved data |
| After a test made `localStorage` throw, cleanup crashed and broke later tests | The test setup cleared storage before undoing the mock. It now restores mocks first |
| One-year chart labels read "Oct 25" and "Jan 26" | That looks like October 25th and January 26th, but meant October 2025. Found while looking at the real page. The one-year axis now says "Oct 2025" |
| The 52-week range marker's position was a long float in the page (`88.10625000000002%`) | Harmless to look at, but sloppy. It's rounded to one decimal |
| Generated types marked the copilot's `limit` as required | The generator treats fields with defaults as required. The `gen:api` script passes `--default-non-nullable false` |
| Asked "Why did Nvidia stock fall this month?", the copilot wrote "fell by -3.68%" when the stock rose 3.68% | The model accepted the question's wrong premise. The digits matched, so the numbers check passed. Found by running the traps against the real model. Now the data says "a rise" in words, a prompt rule says to contradict a wrong premise, and a direction check and a minus-sign check flag it (with the usual retry) |
| "Since the start of the year" was read as the past 365 days | My period rules only knew "this year". The answer looked right and passed a check that only looked for the word "year". The rules now cover "start of the year" and "since January", and the evaluation checks for year-to-date wording |
| A headline "Stock Price Today: $226.19" sat next to a real close of 226.32 | A model could quote the headline as the close. Quote pages are now left out of the copilot's headlines |
| My first attempt at fixing "What about Tesla?" made things worse | A rewrite-prompt rule for bare "What about X?" follow-ups didn't fix that phrasing and flipped a held-out case ("How about Amazon?") from pass to fail. Reverted, per the rule not to tune against held-out cases. The follow-up scores are unchanged (17/17 and 10/10) |
| The browser kept showing old page text after I edited a file | Vite's file watcher missed the change. Restarting `npm run dev` fixed it. Check what the server really serves before blaming the code || With the API stopped, the page said "The API returned an error (502)" | In development the Vite proxy answers 502 or 504 when the API is down, so the browser never sees a network failure. The client now maps a 502 or 504 with no API message to "Can't reach the API. Is it running? python -m api" |
| `node` was "not found" right after installing Node.js | Terminals and tools opened before the install don't see the new PATH. Open a new terminal (tools started earlier need `PATH` extended with `C:\Program Files\nodejs`) |
| Python patch scripts wrote broken strings and regexes into files | Escapes like `\n` and `\b` were mangled by shell heredocs. Edit files directly, or build such characters explicitly |
| Three new sentences in the shared prompt made unrelated questions worse | Found by A/B against `main`'s code on the same cases, 10 to 20 runs each. Adding a rule about the figures: "news and stock" 10/10 to 5/10 (0/10 with the full set of edits). Three small wording edits together (the intro sentence, one parenthesis in rule 3, and rule 7; not bisected, so which one matters is unknown): "should I sell" 16/20 to 4/20. In the answers I read, the model still declined but in wording the check didn't match, and then listed "factors that could impact the stock". Shared prompt restored exactly; everything about the figures lives in `FIGURES_RULES`. A single 5-run comparison is not enough here: the same code scored 1/5 and 7/10 on one case |
| A drop in the evaluation total was mostly live data | Fresh headlines ("Apple Stock Hits All-Time Highs") changed "crashing premise", "how is X doing", and "news and stock" answers. `main`'s own code scored 0/10 on "crashing premise" the same day. Always A/B against the old code before explaining a drop, in either direction |
| A strict check read a correct refusal as a failure | "Is Tesla overvalued?" was answered "the P/E ratio does not indicate whether a stock is overvalued... the sources do not offer information to determine", with no "can't" or "advice". The check was changed to look for a refusal to judge (noted in `ai/eval_market.py`). The held-out "buy on P/E" case failed the same way ("...advice, which I cannot") and was left as written |

## How the safety checks were calibrated

- **Relevance gate (`MIN_SCORE = 0.62`).** Across 16 test questions, unrelated ones topped out at 0.564 and relevant ones
  started at 0.685. The cutoff sits between them. It is tuned on only 16 questions, so very short or vague questions
  can land in the gap.
- **Numbers check.** Added after the copilot answered "$49.9 billion" revenue growth for Microsoft with a valid
  citation. The filing says $50.1 billion, and the cited passage was a table with no stated growth figure, so the
  model did its own subtraction wrong. A citation does not prove a number is right. Now any figure missing from the
  cited passages triggers a retry, then a visible warning. After the fix the answer was $50.1 billion from the 10-K.
- **Query rewriting.** A plain question "How many employees does NVIDIA have?" ranked the right passage (about
  42,000 employees) 243rd. The model rewrote it into extra keyword queries, and merging the results fixed it.
- **Annual vs quarterly.** An "annual report" question was first answered from a 10-Q. Form detection now restricts
  the search.
- **Near-duplicate passages.** Companies repeat paragraphs across filings, which filled the top results with copies.
  Search drops them and offers `--latest`.
- **Price, news, and sentiment answers** (`python -m ai.eval_market`, 43 cases: routing, traps, and unchanged filing
  questions). The cases were written in three rounds, each run against the real model, read by hand, and used to fix
  things, so the final number flatters it: the first run of the final set scored 40 of 43 and 119 of 129 over three
  runs. Everything the traps check passed in all runs: no invented cause, no advice or prediction, the false-premise
  question corrected, no index guess. The known misses are in the weak spots below.
- **The fair number.** The third round was written before any of it had been run, and was the one honest held-out
  test: it scored 12 of 14 on the automatic checks. Reading the answers showed one of those passes was wrong (the
  year-to-date case), so the real figure was 11 of 14. Its misses ("press coverage", "how's the stock?", "since the
  start of the year") exposed three wording gaps, which are fixed and tested, so those cases now count as tuning
  material. **No untouched held-out cases are left.** `--held-out` says so; write new ones, in different wording,
  before claiming a fair score again.
- **Checks that were too loose gave false passes.** A check for the word "year" passed a one-year answer to a
  year-to-date question, and the wrong-sign answer passed the digits check. Both were found by reading answers, not
  by the score. Read the answers (`--show`), not just the totals.

## Known weak spots

- **The local model is weaker than Claude.** It can miss details or misread tables. The numbers check catches wrong
  figures, not wrong reasoning. Always check the cited sources.
- **Query rewrites can drift.** For "Should I buy Tesla stock?" it searched for manufacturing strategy. Answers stayed
  grounded in real passages, but the rewrite wasn't what you'd choose.
- **Tables are hard to search.** Financial statements are lines of numbers, which the embedding model handles poorly.
- **Sentiment is shallow and leans neutral.** In a hand audit of 40 headlines, about 35 labels looked right. Mildly
  good or bad news is often labeled neutral, and headlines about other companies are often labeled neutral instead of
  irrelevant. Before quote pages were left out of the totals (see "Sentiment totals count each story once" below),
  about two-thirds of labels were neutral, so scores sat near zero; neutral is still the biggest group. Consistency
  across re-runs was not measured.
- **Which sources a question gets is decided by keyword rules**, and about one fresh phrasing in five is missed (see
  the fair number above). A missed one falls back to the filings route. That is usually an honest "the sources don't
  provide that", but not always: asked "Why is Apple stock crashing?" before "crashing" was a known word, it answered
  from a filing chart and said price data wasn't provided. Rules are patched as gaps are found, which won't end.
- **"What about Tesla?" after a price question is still answered from filings.** The follow-up rewrite returns the
  question unchanged, so the price topic isn't carried over ("And Tesla?" and "How about Tesla?" work). It passes 0 of
  5 runs in the evaluation and is left in as a known failure. A prompt fix made another case worse and was reverted.
- **The local model is not steady.** The same question can pass 2 runs in 5 (hedging about causes, before the cause
  check existed). Checks in code, not the prompt, are what hold the line: the numbers, direction, minus-sign, and
  cause checks, and the refusals.
- **The numbers check can warn about a figure the user typed.** "Will Microsoft hit $600 by December?" is answered
  correctly, but the model repeats "$600" and the check flags it as not in the sources. Left as is at first: a spurious
  warning is the safer way to fail than trusting numbers a user supplies. **Changed 2026-10-15** (see "Copilot trust, step
  6" below): a figure the question itself contains is let through when every sentence of the answer that uses it declines
  or restates without predicting.
- **The cause check only looks for certain wording** ("due to", "may have contributed", "driven by"). A cause implied
  in other words would pass, and it only runs when the answer was given both prices and headlines.
- **Headlines in answers are shallow.** Titles only, the newest six (so usually all from one day, whatever period was
  asked about), some not really about the company (the model labels "irrelevant" only a few), and the labels are two
  thirds neutral. Answers repeat that, but a "Dating app Bumble is in talks to go private" headline can still appear
  under Nvidia.
- **Year-to-date and window figures use closing prices only,** from the free Yahoo feed. The latest day may be partial,
  and the 52-week range is of closes, not intraday highs and lows.
- **Some things are still not stored,** so the copilot says they aren't available: analyst targets, dividends and dividend
  yield, debt, cash, price-to-book, and any figure for a foreign filer. On a filings-route question the model sometimes
  answers uncited ("the sources don't include that"). Revenue, profit, EPS, margins, market value, and P/E are stored and
  answered (see "Fundamentals" below).
- **The "If the question assumes a decline, it contradicts the data" sentence** showed up in a real answer, copied
  from the prompt rule. Harmless, but it is the model repeating its instructions.
- **Checked in a real browser:** a price question with a false premise, a sentiment question, an index question
  (refused), a reload (history restored, in the new shape), old saved answers (still showing), and a 375 px phone
  width. Dark mode only. The browser pane's own history was used, so these answers sit in that pane's saved history.
- **Search is vector-only.** A keyword (full-text) search was considered for exact-term lookups and not built.
- **Start and stop scripts and the restart policy: what was tested (2026-10-14).** The restart policy was applied by
  recreating the container, and every table's row count was identical before and after (7,524 prices, 5,899 filing
  chunks, 3,363 financial facts, and so on). `start.ps1` was run from a cold state (database stopped): everything up
  and answering with real data in 11 seconds; run twice (the second run started nothing); with an unrelated program on
  the API port (reported and skipped in 4 seconds, not a 60-second wait); with Ollama unreachable (a warning, exit 0);
  and with Docker missing from PATH (a clean one-line error, nothing started). `stop.ps1` closed the windows `start`
  opened, stopped servers started by hand (matched by command line), and left an unrelated Python program on the API
  port running. **Not tested:** the restart policy itself after a real reboot or Docker Desktop restart (I did not
  crash the database to find out; it rests on Docker's documented behaviour), "Docker is installed but not running"
  (the check is there, but Docker was running), a reboot with the scripts, and the browser opening (`-NoBrowser` was
  used so tests didn't open windows). The server windows are ordinary PowerShell windows left open on purpose, so an
  error stays readable. **Weak spots:** `stop.ps1` finds servers by command-line text, so a program whose command line
  happens to contain `-m api` on port 8000 would be stopped; the 60-second wait on a slow first start could be too
  short on a very slow PC (it then says so and exits 1, and the windows keep running); the first copilot request after
  a start still loads the embedding model (a few seconds), which the script does not warm up.
- **The nightly job needs the PC on and you logged in, with Docker Desktop and Ollama running.** Otherwise it
  catches up the next time it can. A bad run shows a desktop alert (see below), but if the PC is off or you aren't
  logged in, nothing runs and so nothing alerts you; the dashboard's stale-data warning is the backstop.
- **Alerts are a Windows desktop notification only.** Windows' Focus Assist / Do Not Disturb can hide them (they
  still land in the notification centre), they reach no other device, and there is no email. Email would need a
  mail password stored in `.env`, which was left out on purpose. Checked: the notification call succeeds and the
  failure paths (partial run, database down, crash) are covered by tests with a fake notifier. The test notification was
  seen on screen; an alert from a real scheduled 5pm run that had problems has not been observed yet.
- **A stopped database used to hang the job.** `psycopg` waited minutes on a closed port (found by pointing the job at a
  dead port). Connections now give up after 10 seconds.
- **Price counts mean "bars refreshed", not "new".** Each run rewrites the recent window (upsert), so the number is
  how many bars were written.
- **Free sources can break without notice.** If Yahoo or Google change something, that step errors for each company
  and the run is marked `partial`. Failures are visible but not repaired automatically.
- **The scheduled path has worked twice:** after registering, `Start-ScheduledTask` ran the job through Task Scheduler,
  and on 2026-10-12 the task started by itself at 5:00 PM (result code 0, run logged as success). A catch-up after a
  missed run has not been observed yet.
- **The API has no authentication, rate limiting, or per-user data.** It is safe only because it is bound to this
  computer. Anyone who can reach it can ask the copilot questions, which uses your GPU.
- **The copilot answers one question at a time well.** Several at once queue up behind the single local model and
  would each be slow. Nothing limits concurrent copilot requests yet.
- **The first search or copilot request after the server starts loads the embedding model** (a few seconds). There is
  no warm-up at startup.
- **The wireframes show things the API can't supply yet:** a natural-language screener (no fundamentals data) and an
  "AI signal: bullish, 72%" (no forecasting model exists, and we haven't decided one should).
- **A latest price bar can be a partial day** if requested while the market is open. `as_of` shows its date.
- **Follow-ups are understood by a small local model.** On 17 tuned conversations it got 17 right, and on 10 written
  afterwards in different wording it got 10 right, with identical results across repeats. Both sets are small, self-
  written, cover a handful of company and topic patterns, and one set was used to tune the prompt and safeguard, so
  treat this as encouraging, not proven. Run `python -m ai.eval_followups --held-out` after any prompt change, and
  write new held-out cases before tuning against them.
- **Only the last three questions are used,** answers are trimmed to 1,500 characters, and the model sees a 400-character
  excerpt of each. A follow-up that depends on something further back, or on detail in a long answer, can be missed.
- **Still one company-less guess:** if a question names no company and has no pronoun ("What about the legal side?"),
  it relies on the model carrying the company; the safeguard only covers bare pronouns. The "No company was named"
  notice and the "Understood as" line are the backstop.
- **Each follow-up costs one extra model call** (the rewrite), a fraction of a second on a warm model here.
- **History is per browser.** Clearing site data, a private window, or another browser loses it. Nothing is stored on
  the server, and nothing stops someone else using the same browser from reading it.
- **No streaming.** An answer appears all at once after several seconds, with only a "working" message until then.
- **Follow-ups were checked in a real browser** with the exact case that had failed (Tesla employees, then "And what
  about its biggest risks?"): it was understood as Tesla, searched only Tesla, and cited only Tesla filings. A new
  topic, the divider, and the saved topic were also checked. Dark mode only.
- **The copilot page was checked in a real browser:** a company-filtered question, a reload that restored history,
  an unnamed follow-up (which exposed the Amazon problem above), the clear flow, and a 375 px phone width. Stop
  and retry were checked by automated tests only. Dark mode only.
- **The stock detail page has no AI signal.** That needs a model that doesn't exist. It shows what the stored data
  supports: prices, news mood, fundamentals, filings, and the copilot.
- **Duplicate headlines are hidden in the news lists, not counted out of the totals.** The free news feed returns one
  story once per outlet that carried it. `/api/stocks/{symbol}/news` and `/api/news` now show a story once per company
  (newest copy kept), using the same rule as the copilot (`data/headlines.py`: case, spacing, and a trailing
  " - Publisher" are ignored). A story about two companies still appears once for each. Only identical titles match:
  two outlets that reword the same story still show twice. The rows stay in the database, and the sentiment counts and
  score counted every copy at that point (fixed in the next entry). Checked with automated tests (which fail without
  the change) and a query against the dev database (MSFT, TSLA, and the dashboard feed had repeats before, none after,
  each still full at 30); not yet looked at in the browser.
- **Sentiment totals count each story once and leave out quote pages.** The positive / neutral / negative / irrelevant
  counts and the score (dashboard, stock detail, and the copilot's sentiment summary) come from one function,
  `label_counts` in `ai/sentiment.py`. It counts a story once per company (the newest copy's label, as in the news
  lists) and skips stock-quote, "X vs Y", and other data-page templates (rules in `data/headlines.py`, described in
  the next entry). The labels stay in the database and the news lists still show these pages, so a list can show a
  neutral quote page that no total counts. On the last 7 days of dev data, 30 of 706 labeled headlines were repeats (37 extra copies, and only one story
  had copies labeled differently) and 210 (30%) were quote or comparison pages, 90% of them neutral. Repeats hardly
  moved any score; quote pages did: Google went from +0.08 to +0.18, Tesla +0.10 to +0.14, Microsoft +0.11 to +0.15,
  Apple, Amazon, and Nvidia barely changed. **Google's dashboard mood word flips from Neutral to Positive** (the cutoff
  is 0.15), and Microsoft (0.145) and Tesla (0.140) sit just under it. The score now means "positives minus negatives over
  real stories", so it moves further from zero than before; that is a change in meaning, not proof it is more accurate.
  The first version's pattern was loose (it caught one real story, "Wells Fargo cuts Amazon stock price target", among
  206 matches) and missed some templates; see the next entry. If every headline for a company in the window is a
  template page, its mood reads "No news". Checked with
  tests (which fail without the change), the real data above, and the copilot's sentiment answers, which matched the
  database (Tesla: 15 positive, 35 neutral, 7 negative, 1 irrelevant, +0.14). `ai.eval_market --repeat 3 --show` scored
  121 of 129 before, 121 after the counting change, and 123 after the source text was reworded to say what is counted.
  The same cases fail at times (follow-up to another company and "price target" every time; "why did it move" and
  "should I sell" in some runs), none about sentiment. The two-point difference is run-to-run variation, not a gain.
- **Quote-page rules: two sets, and the copilot keeps the narrow one.** `data/headlines.py` now holds named rules.
  The core set (quote pages, "X vs Y" pages) is what the copilot leaves out of its sources; it is the original set
  plus one fix: an analyst's "stock price target" is real news, so "Wells Fargo cuts Amazon stock price target" is no
  longer treated as a quote page. The broader set adds data-page templates the original missed (fund "Holding History"
  pages, "Options Chain" and "Quotes & News" pages, "Latest Stock Analysis", "Competitor Stock Analysis", "Market Cap
  API", "Real-Time Odds", "Historical data", a bare "Company (TICKER)", and generic "Stock Forecast & Analyst
  Predictions" pages, but not "Stock Forecast: <real headline>" articles), and only the sentiment totals use it.
  Why two: using the broad set for the copilot too made its evaluation case "crashing premise" go from 8 of 8 passes
  to 0 of 8 in a direct A/B (the options-chain page it used to see was replaced by a real article, "Is Apple a buy at
  $337?", and it answered "the sources do not indicate Apple stock is crashing" instead of "the data cannot show the
  cause"). That answer invented no cause, but I did not loosen the check to fit it. If the copilot should use the
  broad set, that case's expected wording needs a decision first.
  Measured on the 712 distinct headlines stored (after a read-through of all 198 the old pattern matched, and the 111
  unmatched ones that looked like templates): the old pattern matched 198, of which one was clearly a real story and
  a few borderline; the broad set matches 256. The copilot's set differs from the original on exactly two headlines
  (the rescue; the second is the generated page "Wall Street analysts update Google (GOOGL) stock price target for 12
  months", which now slips through because the rescue can't tell it from the real story). On the last 7 days the
  totals now count 47 fewer stories (463 to 416; Apple 81 to 58, mostly "Holding History" pages), and **Microsoft's
  mood word flips from Neutral to Positive** (+0.145 to +0.167); Tesla sits at +0.145, just under the 0.15 cutoff;
  Google, Amazon, Nvidia, and Apple barely move. **Weak spots:** the rules were written from the same headlines they
  were checked on, so there is no held-out result: the first fair test is how they handle headlines that arrive
  after this change. New templates will keep appearing and need new rules; a few that appeared once or twice ("P/B
  ratio" and "KPI charts" pages, "GARP candidate" screens) were left alone. The tests in `tests/test_headlines.py`
  pin down both directions with real headlines (20 of the 43 cases fail on the old pattern). `ai.eval_market
  --repeat 3 --show` scored 122 of 129 with the final rules (121 to 123 before); "follow-up to another company" and
  "price target" fail every time, as before, and one run of "news and stock" tripped the cause check ("Apple stock
  climbed due to JPMorgan lifting its target"), with the same Apple headlines the baseline saw.
- **Foreign companies (20-F filers) have no filings here.** Checked on 2026-10-13 against the real SEC and Yahoo:
  TSM and ASML have 20-F and 6-K filings and no 10-K or 10-Q; AMD and BRK-B have both kinds. Adding TSM with
  `jobs.add_company` stored 1,255 daily prices and 100 headlines (all labeled) and no filings; the report said why. In
  the app, a price question about TSM was answered correctly, and a question about its annual-report risks got "I
  couldn't find anything in the stored filings, prices, or headlines... so I won't guess" (honest, but generic: it
  tells you to name a company when one was named). Storing 20-F is possible (the SEC client would need the form list
  and probably a different text cleaner; 20-Fs are long) but was not tried, and the copilot's "annual report" form
  detection assumes 10-K. Left as the owner's decision. The nightly job still reports such a company's filings step
  as "ok (0 new filings)"; only `add_company` explains it.
- **Add-company checks.** Real runs against a scratch database (so the dev data was untouched): a made-up ticker
  (nothing stored, the other four steps not tried), TSM, AMD and BRK-B together (4 filings each, all indexed, headlines
  labeled), and AMD again (22 bars, 5 new headlines, 0 filings, nothing re-indexed). Not checked: a ticker that Yahoo
  knows and the SEC doesn't (an ETF), a company with no news, and a run while the PC sleeps or Ollama is down (the
  last two are covered by fake-source tests only). The local model skipped 1 of 99 headlines for BRK-B; that is shown
  as a note, not a gap, and the nightly refresh retries it. Tickers outside the US (`0700.HK`) are rejected up front.
- **Backups: what was tested (2026-10-13).** A real backup of the dev database (11.9 MB, 10 tables, 16,799 rows)
  passed `verify` (checksum, every row count, 6 migrations, extensions, vector search, 6 price time-chunks). The
  harder test was a disaster restore: a second, brand-new Postgres container with an empty volume (a different
  password), the backup restored into it with `restore --into stockmarket --replace`, then the real API run against it.
  The copilot answered "NVIDIA had approximately 42,000 employees" from the restored vector index, the price endpoint
  returned the latest prices, and `jobs.refresh` wrote new prices and headlines into it (sequences carried over: the next
  run id was 976 after 975). Restoring without `--replace` refused. The temporary container and volume were removed.
  31 automated tests use real `pg_dump`/`pg_restore` on throwaway databases. Breaking the code on purpose was caught:
  skipping `timescaledb_pre_restore()` made 7 tests fail (the restore genuinely needs it), and a `verify` that ignored
  row counts failed its test.
- **Backups: what was not tested or is weak.** The daily task (`StockMarketBackup`, 6pm) was registered on 2026-10-13
  and one run through Task Scheduler succeeded (result 0, a verified backup in the new folder), but no 6pm run has
  happened by itself yet. `BACKUP_DIR` is `C:\Users\nbhas\stockmarket-backups`, outside the project (so deleting or
  re-cloning the repo doesn't take the backups with it) but on the same only internal disk, so it doesn't survive that
  disk failing; a copy to OneDrive or an external drive was left to the owner. A PC that is off, or Docker not
  running, makes no backup and sends no alert; nothing yet warns that the newest backup is days old. `--replace` was
  exercised on scratch databases and on the empty database of the second container, not on the live `stockmarket`
  database with data in it (the safety-backup path is covered by a test that treats a scratch database as the live
  one). A backup is only as current as its last run: anything added after it (headlines especially) is lost if the
  volume goes. Only the same Docker image (Postgres 17, TimescaleDB 2.30) was tried; a major upgrade needs a fresh
  restore test. `verify` proves the data loads and counts match; it doesn't compare the data's contents row by row.
- **Fundamentals (step 1 of 3: data and calculations; 2026-10-13).** Checked first against the real SEC feed for the
  six companies plus AMD and TSM, then built. What the probe found: revenue goes under four names depending on company
  and year (Apple stopped using `Revenues` in 2018; Amazon only ever used a contract-revenue name), so the calculation
  takes the first current name in a priority list and rejects a leftover; Amazon's stored "gross profit" ended in 2009
  and gave a 0.7% margin before that rule; Alphabet has no cover-page share count (several share classes), so the
  balance-sheet total is used and flagged; TSMC's feed stops at FY2024, in Taiwan dollars, with no EPS.
  **Checked against filing text, not just for consistency:** Apple's nine-month net income (101,464 and 84,544),
  Alphabet's half-year figures, Tesla's net income, NVIDIA's revenue (96,221 / 177,837 / 90,805, to the dollar), and
  Amazon's twelve-month net income (135,281). Net income divided by EPS lands within about 1% of each company's reported
  diluted share count (Tesla 0.6%). The cautions are real: Amazon's own cash-flow table shows about $80 billion of
  non-operating income over the twelve months, and Alphabet's net income is 1.7 times its operating income.
  Results on 2026-10-12 prices: Apple P/E 39.1, Microsoft 30.1, NVIDIA 28.6, Alphabet 17.7 (flattered by investment
  gains, flagged), Amazon 20.9 (flagged), Tesla 350 (share count differs 12% from the earnings average, flagged).
  25 new tests (and the refresh and add-company tests updated for the sixth step); four deliberate breakages (wrong sign in the formula, no stale-concept guard, no profit-vs-operating
  caution, restatements ignored) were each caught. The refresh path was run end to end on a scratch database (AMD
  stored 592 figures; TSM stored none and was reported as unavailable, not as an error).
  **Weak spots:** TTM earnings per share is built by adding periods' EPS, which is the usual approach but is not exact
  when the share count changed during the year. The "ok, 0 new figures" line for a foreign filer in the nightly
  summary is quiet (only `add_company` explains it, as with filings). P/E divides today's price by figures that are
  up to a quarter old, and the date of each is shown. A restated figure is kept as its own row, but nothing checks
  whether restatements are common. One price (the latest close) is used; a partial trading day would shift market value.
  Share counts for multi-class companies are totals from the balance sheet. Debt, cash, and ratios like price-to-book
  were left out on purpose. The caution thresholds (1.2x, 5%, 10%) were picked from these six companies and are not
  tuned on anything else. Steps 2 and 3 (the page and the copilot) followed; see below.
- **Fundamentals (step 2 of 3: the endpoint and the stock page; 2026-10-13).** `GET /api/stocks/{symbol}/fundamentals`
  returns the computed figures with their recipes, source filings, and cautions; the stock detail page shows them in a
  "Fundamentals" card under Key stats. Checked: 4 new API tests (figures, cautions, `available: false`, 404/422), 11
  component tests, a page test, and format tests, with two deliberate breakages caught (cautions never rendered; the P/E
  recipe quoting the wrong price). **In a real browser** (live data, the API and dev server started and stopped): Alphabet
  (both cautions, a recipe expanded and its three source filings read), Tesla at 375 px (no horizontal overflow, flat
  EPS growth shown as "– 0.00%"), Amazon in light mode (automated contrast check: none of 58 text elements below 4.5:1),
  and the API stopped (the card shows the standard "Can't reach the API" message with a retry). **Not checked in a
  browser:** the "not available" state for a real foreign filer (none is tracked; covered by API and component tests),
  and the dashboard (untouched). **Weak spots:** growth is shown per period compared (the latest 3, 6, 9 or 12 months vs
  the same stretch a year earlier), so it is not the growth of the twelve-month total and the label says so, which is
  wordy; EPS growth of 0.00% (Tesla) reads oddly but is correct; net income growth can be huge when the base is small
  (Alphabet +178%, partly the same investment gains the caution describes). The card doesn't say which share-count
  figure the market value would take under the other choice (Tesla's caution gives both counts but not both values).
  At the time the copilot still refused these questions; step 3 changed that (next entry).
- **Fundamentals (step 3 of 3: the copilot; 2026-10-14).** The copilot answers P/E, market value, EPS, share count,
  revenue, profit, and margin questions from the stored figures, as one numbered `fundamentals` source with the growth
  direction in words, and attaches the cautions that concern the figures asked about to the answer in code (see the
  decisions table). **Tests:** 48 new unit tests (routing, the source text, cautions, the whole copilot with a fake
  model), 2 API tests, 2 web tests; 410 Python and 207 web tests pass. Fourteen deliberate breakages were each caught: cautions never attached, scoping removed, growth direction
  unchecked, "grew" not read as upward, the why/filing exception removed, matched words not cut out, revenue words
  searching the filings, an unavailable company refused, a caution missing from the source, and a wrong scope; then,
  after the figures rules were split into their own prompt block, the rules sent with every question, never sent, the
  caution rule dropped from them, and the shared prompt edited to mention the figures. **Evaluation** (`ai.eval_market --repeat 3 --show`, 55 cases, the 43 old ones plus 12 written for
  this step before the code; the old "figure that isn't stored" case asked for P/E and now asks for price-to-book):
  the last full run scored 153 of 165 (an earlier one 155), against 121 to 123 of 129 documented before. All 12 new
  cases passed 3 of 3 in every run after the prompt fix, quoting the figure Python computes today (the same `compute` the source
  uses, so this shows the model copied it, not that it is right; step 1 checked the figures against filings), showing the right caution, and showing none where none applies. The
  misses are not new: "follow-up other company" and "price target" (0 of 3, known), "crashing premise" (0 of 3, and
  0 of 10 on `main`'s code the same day), "how is X doing" (0 of 3 in that run; 1 of 5 and 7 of 10 on `main`'s code),
  and a one-off "investor mood". **Held-out:** 14 cases written in different wording before the routing or prompt
  existed, run once: 13 of 14 (39 of 42 over three runs). The miss, "buy on P/E", reads as a correct refusal ("...investment
  advice, which I cannot", no verdict, the P/E, and the caution) that the pre-written check didn't recognize, so it was
  left as written. Reading the passes: "dividend yield" explained the formula from outside knowledge before saying it
  can't be determined, "two margins" said "better" (a mild judgment), and "TSMC's P/E" got the generic "tell me which
  company" refusal (TSMC isn't tracked). Those held-out cases are tuning material now (`ROUND_FIVE`; `HELD_OUT` is empty again, and the 69-case set has not been scored as a whole yet). **In a real browser** (live data,
  servers stopped afterwards): Alphabet's P/E showed the amber "Caution for GOOGL" box under an answer whose own
  sentence never mentioned it, and Alphabet's revenue showed no caution. Dark mode, 800 px. **Not checked in a
  browser:** a phone width, light mode, and a foreign filer through the copilot (that is covered by tests with fake data).
  **Weak spots:** (1) The model itself restated Alphabet's caution in 0 of 3 tuning runs (it sometimes copies the
  source's "CAUTION" line, even writing "the CAUTION line notes"); the guarantee is the code, and the answer text alone
  can omit it. The caution box is the only place a reader is certain to see it. (2) Routing is keyword rules and the
  new vocabulary is untested beyond the 26 cases: "how expensive is X relative to its earnings", "sales", and "how much
  is X worth" use words the rules don't cover, and "market value" in a question about marketable securities would go
  to the figures. (3) The figures are twelve-month totals, so a question about one quarter or a calendar year is
  answered with the twelve-month figure and a request to say so (not evaluated), or goes to the 10-Q if it says
  "quarter". (4) The growth direction check leaves a sentence alone if it mixes up and down words. (5) A single
  five-run comparison is not enough to judge a prompt change here: the same case scored 1 of 5 and 7 of 10 with identical
  code. (6) The model sometimes explains a P/E with a share-count caution that concerns market value, because the
  answer mentions both. (7) No test covers a rate that is exactly flat.
- **Copilot trust, step 1: the 69-case set scored as a whole, and the "What about Tesla?" bug fixed in code
  (2026-10-14).** `ai.eval_market --repeat 3 --show` on `main`: 63 of 69 on the first run, **190 of 207** over three runs
  (the same level as the earlier 153 to 155 of 165 once the 14 older held-out cases are counted). Reading the answers,
  the seven cases that lost points are not one problem. *A real bug:* "What about Tesla?" after an Nvidia price question
  scored 0 of 3. The rewrite prompt says to return a question that switches company exactly as written (rule 3), so it
  came back as "What about Tesla?" and the search ran on a company name alone; the answer was a mix of Tesla's headcount,
  legal proceedings, and letters of credit. "How about Tesla?" and "And Tesla?" already worked; "What about Tesla's
  stock?" fails the same way (see below). *Correct answers the checks mark wrong:* "price target" (the numbers check flags
  the user's own "$600", left as decided above) and "crashing premise" ("no evidence of a crash in the data", the open
  decision above). *Refusals the pattern doesn't recognize:* "buy on P/E", "good time to buy", "should I sell". *A check
  doing its job:* "how is X doing" when a paraphrased headline says "may gain due to...".
  **The fix** is in code, not the prompt (`ai/copilot.py`, `carry_topic`): when the rewrite hands back a question
  unchanged, and that question is only company names and filler words ("What about Tesla?", "And Tesla's?"), the last
  question that has a topic is asked again about the new company ("How has Nvidia stock done this month?" becomes
  "How has Tesla stock done this month?"). Only the earlier *question* is reused, never its answer, so earlier answers
  still can't become evidence; the reader sees it as "Understood as". It does nothing when the question has a topic of
  its own, names the company just discussed, has explicit companies chosen, or when the earlier question names two
  companies or none and has no pronoun to swap. A pronoun in the earlier question ("And its news?") becomes the new
  company's name. Earlier bare switches are skipped, because the browser sends questions as typed and a chain of "What
  about X?" would otherwise lose the topic. **Tests:** 19 new, and five deliberate breakages (rule never runs, bare
  turns not skipped, same company not excluded, bare check removed, explicit companies overridden) were each caught;
  429 Python tests pass. **Evaluation:** `ai.eval_followups` 17 of 17 and `--held-out` 10 of 10, both unchanged. The
  market set scored **196 of 207** (65 of 69 on the first run); "follow-up other company" went from 0 of 3 to 3 of 3, and
  its answer is the Tesla price move. The other six points are ordinary variation ("should I sell" 1 of 3 to 3 of 3,
  "how is X doing" 1 of 3 to 2 of 3 with no code change that touches them). The remaining misses are the four above that
  are check problems. **Weak spots found on the way, not fixed:** (1) "What about Tesla's stock?" still goes to the filings:
  `detect_intent` does not treat "Tesla's stock" with no verb as a price question. (2) "Dividend yield" and "price-to-book"
  go to the filings, and the answers say "the stock price is not provided" although the price is stored; they pass the
  checks because they admit the gap. (3) Repeats add less than they look: in several failing cases the three runs gave
  word-for-word identical answers, so "0 of 3" is close to one sample. (4) The newest stored price is 2026-10-12 even
  though the 5pm job on 10-13 succeeded and headlines run to 10-13; not investigated. (5) A bare switch is recognized by
  a short list of filler words, so wordings outside it ("Tesla, please") fall back to the old behavior.
- **Copilot trust, step 2: ratios the app doesn't compute are declined in code (2026-10-14).** "What is Microsoft's
  dividend yield?" and "What is Nvidia's price-to-book ratio?" went to the filings only, so the model saw no price and
  wrote "the stock price is not provided" (and, for the dividend question, a stray share count) although prices are
  stored. Both passed the old checks because they admitted the gap, but the reason they gave was false. **The fix**
  (`unstored_figures` in `ai/market.py`, `not_calculated` in `ai/copilot.py`): nine explicit ratio names (dividend yield,
  price-to-book, price-to-sales, PEG, EV/EBITDA, enterprise value, return on equity, return on assets, debt-to-equity)
  are recognized by keyword. When one is the whole question, the copilot answers in code, without asking the model or
  searching: it says it doesn't calculate that ratio and lists what it can give. When one is mixed into an answerable
  question ("Apple's P/E and also its price-to-sales ratio"), the question is answered as usual and the note is
  attached to the answer as a caution, like the data cautions. The words are cut out before routing, so "price-to-book"
  is not read as a price question. I chose declining over computing the ratios because the figures rule is that Python
  computes everything and the model only quotes it, and these need data (dividends, equity) that is not stored;
  computing them would be a feature of its own, with its own checks against the filings. **Tests:** 30 new, six
  deliberate breakages each caught (never declines, note never attached, words not cut out, mixed question also
  declined, message claiming prices are unavailable, a pattern wide enough to swallow P/E); 459 Python tests pass.
  **Evaluation:** `ai.eval_followups` 17 of 17 and 10 of 10, unchanged. `ai.eval_market --repeat 3 --show` scored **197 of
  210** (70 cases; 196 of 207 before). "Dividend yield", "figure that isn't stored", and the new mixed case each passed 3
  of 3; the two old cases now expect a decline (no evidence, the "don't calculate" wording, no "not provided"), a change
  of expectation, not a looser check. The other misses are the ones already listed ("crashing premise", "price target",
  "buy on P/E", and one-run variation in "how is X doing", "should I sell", "good time to buy"). **Weak spots:**
  (1) Only the nine explicit names are caught. "How much does Microsoft pay out to shareholders?", "book value",
  "free cash flow yield", or "what's the payout ratio" still go to the filings and could produce the old false claim.
  (2) A plain "dividends" question is deliberately left to the filings, which can state an amount paid. (3) The decline
  text is generic; it does not say which of the listed figures is closest to what was asked. (4) The three cases were
  written with the fix in mind, so there is no held-out result for it yet.
- **Copilot trust, step 3: "What about Tesla's stock?" and other bare stock questions (2026-10-14).** A company and
  its stock with nothing else in the question has no verb, so `PRICE_RE` missed it and the question went to the filings
  (the answer was Tesla's headcount and lawsuits). `BARE_STOCK_RE` in `ai/market.py` now reads it as a price question:
  only filler words ("what about", "and", "ok,") before one name-like word, then "stock" or "shares", then nothing but
  a time word ("now", "today", "please"). It is narrow on purpose: "Should I buy Tesla stock?", "Tesla's stock-based
  compensation", "What does Tesla say about its stock?", "What stock?" and "Any growth stock?" are not caught (tests pin
  both sides). **A second bug was hiding behind it:** after a risks question, the model rewrote "ok, and Alphabet
  stock?" into "What are Alphabet's biggest risks?" and dropped the one word the user asked for. When a bare stock
  question comes back from the rewrite with no price intent, the user's own words are now used instead
  (`resolve_question`). **Held-out result:** five cases written in different wording from the unit tests, run once
  before any tuning, scored **3 of 5**; "ok, and Alphabet stock?" and "Amazon stock now?" missed (a comma after the
  filler, a time word after "stock"). The pattern was widened for those two and the rewrite guard added, so all five
  are tuning material now (`ROUND_SIX`, and `HELD_OUT` is empty again). **Tests:** 26 new routing and rewrite tests
  and six deliberate breakages, each caught; 485 Python tests pass. **Evaluation:** `ai.eval_followups` 17 of 17 and 10 of
  10, unchanged. `ai.eval_market --repeat 3 --show` (75 cases) scored 211 of 225 and then 209 of 225; the five new
  cases passed 3 of 3 in the final run. The two-point drop is "how is X doing" and "should I sell" going to 0 of 3,
  which a 10-run A/B against `main` showed is not the change: "how is X doing" 2 of 10 on `main` and 3 of 10 on this
  branch, "should I sell" 3 of 10 and 4 of 10. Both are flaky cases, so a single three-run total can move by several
  points with no code change. **Weak spots:** (1) The pattern knows one name-like word, so "Berkshire Hathaway stock?"
  or "What about Coca Cola's stock?" is not caught. (2) "What's Amazon's stock?" is answered "Amazon's stock is
  referred to as AMZN in the stock market", a pointless sentence that passes every check. (3) "How many shares does
  Apple have?" is routed to price data today (found while writing the lookalike tests; not changed here), so it can't
  answer a share-count question; the shares-outstanding figure exists but the phrase isn't recognized.
- **Copilot trust, step 4: the "can't tell you whether to buy, sell, or hold" notice is attached in code
  (2026-10-14).** The refusal to give advice rested on the model's wording, and the checks that graded it kept missing real
  refusals. Measured first, 10 runs each: "Should I buy Apple stock?" and "Should I sell my Tesla shares?" stated a refusal
  10 of 10 times, but "Is it a good time to buy Nvidia?" 3 of 10, "Is Amazon a good investment right now?" 3 of 10,
  and "Should I hold Microsoft through the end of the year?" 4 of 10 (often "cannot be answered with certainty", which
  implies it could be). So `asks_for_advice` (`ai/market.py`) recognizes a request for a buy, sell, or hold call, and
  `ADVICE_CAUTION` (`ai/copilot.py`) is added to `Answer.cautions` for it, whatever the model wrote, like the data
  cautions. No prompt was touched. **Detection leans towards flagging**, because a missed request is worse than one
  extra notice: a question counts if it matches an explicit phrase ("should I sell", "a good time to buy", "worth
  buying") or has a trading word (buy, sell, hold, invest, dump, position...) together with a decision cue (should,
  whether, wise, safe, can I, my, worth, would you...). **How it scored on fresh wordings, honestly:** the first, phrase-only
  version recognized **0 of 7** realistic wordings ("Would it be smart to sell my Nvidia position now?", "Can I safely
  invest in Amazon right now?"); the two-part rule was written for those, then six more fresh wordings (written
  before running anything, with their routing checked first) scored **3 of 6** in the one honest run. The misses
  ("load up on", "any reason not to buy", "the right stock to put my savings into") were fixed, so all of these are
  tuning material now (`ROUND_SEVEN`; `HELD_OUT` is empty again). **False alarms:** none among the other 71 evaluation
  questions or the question strings in the tests; the 10 flagged are the 10 advice questions. **Tests:** 50 new, and five
  deliberate breakages (rule removed, trading word alone enough, two cue groups removed, caution never attached), each
  caught; 535 Python tests pass. **Evaluation:** `ai.eval_followups` 17 of 17 and 10 of 10, unchanged. `ai.eval_market
  --repeat 3 --show` (81 cases) scored **237 of 243**, with only "crashing premise" and "price target" failing, as before.
  **The checks changed, so this is not the same bar as 209 to 211 of 225:** for "should I buy", "good time to buy",
  "should I sell" and "buy on P/E", the model having to write a refusal in its own words (`SAYS_NO_PREDICTION`, which
  missed correct refusals) became a requirement that the code's notice is shown; the model's wording is still reported
  (it restated the refusal 3/3, 2/3, 2/3 and 0/3 of the time), and "no advice, no forecast" checks on the answer text
  are unchanged. **Weak spots:** (1) Detection is still keywords; "Any reason not to buy Microsoft today?" took a
  second round to catch and the next wording may slip past, with no notice. (2) The notice guarantees the refusal, not the
  content: "Any reason not to buy Microsoft today?" is still answered with a list of risk factors framed as "factors to
  consider when deciding whether to buy", which leans advice-like, and one earlier Apple answer said buybacks
  "indicate confidence in future performance". (3) The notice is not shown when the app declines before the model
  (no company named, a ratio it doesn't compute). (4) "Do you think I should get out of Tesla before earnings?" is routed
  to the figures because "earnings" reads as a profit question. (5) Not viewed in a browser; `AnswerView` renders any
  caution in the list.
- **Copilot trust, step 5: "How many shares does Apple have?" goes to the stored share count (2026-10-14).** The price
  rules read "shares does" as a price verb, so share-count questions were answered from price data, which has no share
  count ("How many shares does Apple have?", "...have outstanding?", "How many shares did Microsoft repurchase?" all went to
  prices). `HOW_MANY_SHARES_RE` in `ai/market.py` now cuts "how many [a company word] shares" out before the price rules
  run. Unless the question also says what was done with shares (repurchase, buy back, issue, sold, owns, held, can I
  buy...), it asks for the stored shares-outstanding figure; if it does, it is a filings question and no figure is
  asked for. The older wordings ("shares outstanding", "share count") are unchanged. **Tests:** 22 new, and four
  deliberate breakages each caught; 557 Python tests pass. **Held-out result:** four wordings written before running
  anything scored **2 of 4**: "How many Nvidia shares are out there?" went to prices (a company word between "many" and
  "shares"), and the buy-back case was written about Amazon, which has no buyback to find. The phrase was widened for the
  first, the second was swapped for Apple, and all four are tuning material now (`ROUND_EIGHT`; `HELD_OUT` is empty).
  **Evaluation:** `ai.eval_followups` 17 of 17 and 10 of 10, unchanged. `ai.eval_market --repeat 3 --show` (85 cases)
  scored **245 of 255**: the three share-count cases passed 3 of 3, and the misses are "crashing premise", "price target",
  "how is X doing" (2 of 3, flaky on `main` too) and the case below. **A wrong answer the checks cannot see:** "How many
  shares did Apple buy back last quarter?" is routed correctly but answered "Apple repurchased 26,223 shares" (one
  month's row of the 10-Q table). The quarter's total in the same table is 79,611, both figures are in thousands, and the
  extracted passage doesn't say so. The digits are in the cited source, so the numbers check passes it: a citation doesn't
  prove a number is right. The case wants "79,611" and fails 3 of 3 on purpose, so this stays visible. Not fixed: it is
  about reading filing tables (units and totals), not about routing. **Weak spots:** (1) Up to two words are allowed
  between "many" and "shares", so "How many of those shares..." is handled but "How many total outstanding shares..." is not.
  (2) The exclusion list is a keyword list; a verb it lacks sends a question about what was done with shares to the stored
  count. (3) Table units are lost in extraction anywhere in the filings, so any thousands-or-millions figure from a
  table is at risk of the same error.
- **Filing tables lose their units, and the fix (2026-10-14).** Found by reading the one answer the numbers check had
  passed: "Apple repurchased 26,223 shares" for last quarter. Two separate faults. **(1) Units:** Apple's table is in
  thousands, and the sentence saying so ("in millions, except number of shares, which are reflected in thousands") is in
  the filing, but filings are cut into passages of about 1,000 characters and the cut fell between that sentence and its
  table (the end of one passage, the start of the next). The question retrieved only the table, so the model could not
  know. **How widespread:** of 5,899 stored passages, 1,479 are number tables; 875 of those carry their own unit
  statement, and for 420 the statement is in one of the two passages before. Another 184 have none nearby. So around
  30% of table passages (420 of 1,479) reached the model without units, for every company. **The fix**
  (`ai/table_units.py`, called in `answer_question`): when a table passage has no unit statement of its own, the nearest
  one from the two passages before it is attached on the first line, as "[Units stated just before this table: ...]", in
  code, when the prompt is built. It only copies words the filing states and says where from; if none is found it adds
  nothing. The stored passages and the search index are untouched and the change is a few lines to undo. **The other
  option, not taken:** re-chunk so a table keeps its caption and re-embed all 5,899 passages; more thorough, but it
  rewrites real data and changes search results for every question. **(2) Which row:** not fixed. Asked "last quarter", the
  model still quotes the last month's row (26,223) rather than the "Total" row (79,611). Asked for "the three months ended
  June 27, 2026", it answers "79,611 thousand shares" 3 of 3. The flattened table (one cell per line) makes rows hard to
  tell apart. **Tests:** 11 new in `tests/test_table_units.py`, six deliberate breakages each caught (never applied,
  looks too far back, farthest statement first, own units ignored, prose also given units, another filing's units
  borrowed); 568 Python tests pass. **Real data:** the rule was run over all 1,479 table passages (420 gained a note, 404 of
  them "in millions") and ten random notes read against their tables. **Evaluation:** `ai.eval_followups` 17 of 17 and 10
  of 10, unchanged. `ai.eval_market --repeat 3 --show` (86 cases) scored **249 of 258**; the seven "unchanged" filings
  cases passed 3 of 3, no answer echoed the note, and a new case ("three months ended June 27, 2026" must give "79,611
  thousand") passed 3 of 3. "Last quarter" ("shares: buy back (quarter total)") still fails 3 of 3 on purpose, and
  "price target" and "crashing premise" fail as before. With the real model "How many shares did Apple buy back last
  quarter?" now says "26,223 thousand shares": right unit, wrong row. **Weak spots:** (1) The nearest unit statement may
  belong to a different table in the previous passage (a percentages table after a millions table), and the note would
  then be wrong; its wording says only "stated just before this table". (2) A passage that is mostly prose with a table at
  its end can get a note. (3) 184 table passages still get nothing because no unit statement is within two passages.
  (4) The numbers check still only looks for digits, so it cannot see a wrong unit, row, or period. (5) The reader's
  excerpt now shows the extra line; not viewed in a browser.
- **Rebuilding table rows for the model was tried and dropped (2026-10-14).** The remaining half of the table-reading
  error: asked "last quarter", the model quotes the last month's row of Apple's buyback table (26,223) instead of the
  quarter's Total (79,611). The idea was to show the model a table as readable rows ("Total: 79,611 | $138,004") instead
  of one cell per line, at prompt time. **What a prototype showed (scratch code, nothing kept in the repo):** the re-layout
  is safe as text, since across all 1,479 stored table passages it never changed, lost, or reordered a number; but it is
  fragile, since 728 of the passages produce a row with no label, and prose with figures inside it ("was $ / 1.37 / billion
  and $") turns into nonsense rows unless guarded. **With the real model, 5 runs each:** "last quarter" 0 of 5 Total rows
  with and without the rebuilt rows; "in the most recent quarter" 0 of 5 and 0 of 5; "in total over the latest quarter"
  0 of 5 without and 4 of 5 with (the question itself says "in total"). It also introduced a worse error: one answer said
  "26,223 million shares" (the plain layout said "thousand" every time). **Why it can't work as a layout fix:** the model
  can see the Total row; it reads "last quarter" as "the latest period listed", which is a question of understanding,
  not of layout. **Left as is:** the evaluation case "shares: buy back (quarter total)" keeps failing on purpose, and the
  units fix (above) stays. **If this matters later,** the way that fits the rest of the app is a stored, Python-computed
  figure (share repurchases by period, from the SEC company facts, like the other fundamentals) that the model only
  quotes, which is a feature of its own with its own checks against the filings; or a check that notices when a quoted
  figure is a part of a larger total. Not started.
- **Prices were always a day behind; the nightly job moved from 5pm to 3pm Pacific (2026-10-15).** Found while reading
  an answer that said "latest close 2026-10-12" with headlines dated 10-13. The stored newest price was one trading day
  old after every nightly run, while the run reported "success, 0 problems". **What was measured:** Yahoo has the day's
  closing bar (confirmed by asking it directly). The 5pm runs on 10-12, 10-13 and 10-14 each fetched "the last month" and
  got one bar fewer than the same request made earlier (21 vs 22, 20 vs 21): the day that had just ended was missing, and
  the next night's run filled it in. Two runs made before 5pm (a 3pm manual run on 10-12 and a midday run on 10-13) did get
  the day's bar. 5pm Pacific (daylight time) is exactly 00:00 UTC. **The cause is not proven:** it fits "a request made
  after UTC midnight does not get the day's bar", but I cannot reproduce 5pm conditions during the day. **The change**
  (owner's go-ahead; `scripts\register_nightly_task.ps1 -Time 15:00`, the only thing changed): the task now runs at 3pm
  Pacific, which is two hours after the US market closes (1pm) and before UTC midnight all year (3pm Pacific standard time
  is 23:00 UTC), and the 6pm backup still follows it. **Verification:** the first 3pm run is the test (result further down). If the newest
  price in `python -m jobs.refresh --status` is the same day after it, the cause is confirmed; if it is still a day
  behind, the timing was not the cause and the next thing to try is asking Yahoo for explicit start and end dates instead
  of "the last month". **Result (checked 2026-10-15 with `python -m jobs.refresh --status`):** after the first scheduled 3pm
  run (#2252, success, 49 s) the newest price for all seven companies was 2026-10-15, the same day, where every 5pm run had
  left it a day behind. That fits the timing explanation, but it is one run: look again after a few more, and on a half-day
  or a holiday. **Still open:** the nightly report says "0 problems" when the newest price is a day old; once the
  timing is fixed, flagging that is worth doing (a trading-day calendar is needed so holidays don't raise false alarms).
  Earlier documented 5pm times (older entries above) are left as they were written.
- **Copilot trust, step 6: "price target" and "crashing premise" resolved (2026-10-15).** Both had failed every run since
  the first full score, with correct answers, and both were left for the owner to decide because each changes what
  "pass" means. The owner chose to fix both. **(1) The user's own number.** "Will Microsoft hit $600 by December?" is
  answered "the sources do not provide information about future stock prices, including whether Microsoft will hit $600",
  and the numbers check flagged "600" as missing from the sources, so a correct answer carried a warning (and cost a
  second model call to retry). `_users_own_numbers` (`ai/copilot.py`) now lets a figure through when the question itself
  contains it and **every** sentence of the answer that uses it declines (not, no, nothing, cannot, n't...) and either
  restates (whether, if) or makes no prediction of its own (will, would, going to, expected to, won't...). Still flagged:
  "Microsoft will not hit $600" and "won't hit $600" (predictions), "Microsoft is at $600" and "far below $600" (claims),
  a declining sentence followed by a claim with the same number, and a number the user did not type. The question is
  passed to the check on both the first answer and the retry. **Tests:** 18 new in `tests/test_copilot_own_number.py`,
  and six deliberate breakages each caught (one needed a new test first: accepting the number if *any* sentence declines
  instead of *all*; another gap, "won't" read as a decline rather than a prediction, was found by re-reading the rule
  and fixed with a test written first). **(2) The premise correction.** "Why is Apple stock crashing?" is answered "the
  sources do not indicate that Apple stock is crashing... up 2.62%... no evidence of a crash", which is better than the
  wording the check wanted ("the stored data can't show the cause"). `ai/eval_market.py` now accepts either, but still
  requires a stored price in the answer, still rejects any invented or hedged cause (`CAUSAL` and `SPECULATION`, unchanged),
  and rejects an answer that claims the stock crashed. That last check first matched the word "crash" in a denial ("none
  directly explain a stock crash") and wrongly failed a good answer in one run; it now needs a verb about the stock itself
  and is run on asserted sentences only. It was checked against nine hand-written answers (two good, one premise
  correction, six bad including one that affirms the premise, invents a cause, or hedges one) with no mismatches.
  **Evaluation:** `ai.eval_followups` 17 of 17 and 10 of 10, unchanged. 586 Python and 207 web tests pass. `ai.eval_market
  --repeat 3 --show` (86 cases) scored **252 of 258** (250 on an earlier run, before the crash check was narrowed): both
  cases pass 3 of 3 and all 27 "trap" cases pass; the misses are the on-purpose buyback case and flaky ones. A 10-run
  A/B against `main` (the same day's data): "price target" 0 of 10 on `main` and 10 of 10 here; "advice: keep it or sell
  it" 9 of 10 and 10 of 10; "crashing premise" 10 of 10 on both, because that day's headlines made the model use the older
  wording, which shows how much these answers drift with the news. **Read the score carefully:** the "crashing premise"
  case changed what it accepts, so 252/258 is not the same bar as earlier totals; the change is that a premise correction
  passes, not that any answer does. **Weak spots:** (1) Decline and prediction words are keyword lists; a prediction in
  words they lack ("it is unlikely to reach $600" has no decline word, so it is still flagged, but "I doubt it hits $600"
  would be let through) is not covered. (2) If Apple really did crash, a premise correction would be wrong, and the case
  would need new data; the check cannot know. (3) The exemption covers only numbers in the question given to the model,
  which for a follow-up is the rewritten question. (4) One full evaluation run crashed when a single request to the local
  model took more than the 600-second limit and timed out; Ollama answered normally right afterwards. The app would wait
  just as long on such a stall, because the chat request's timeout is 600 seconds. Not changed.
- **Held-out round: the fair score is 78 of 108 (72%), 2026-10-15.** Every earlier case had been used to adjust the rules,
  so the 97% on the tuned sets said little about unseen questions. 36 new cases were written in wording used nowhere
  else, with expectations set from what the right behavior should be (not what the code does), run once with 3 repeats,
  and every answer read, passing ones too. They are now `ROUND_NINE` and count as tuning material (`HELD_OUT` is empty
  again). **By group (first pass):** prices, news, and sentiment 7 of 10; financial figures 5 of 6; filings 5 of 5; traps
  5 of 10; follow-ups 4 of 5. Filings questions were the one clean group. **Eight real failures:** (1) **Invented
  headlines.** "Why is Tesla tanking?" was not read as a price question, so it went to the filings only; in one of three
  runs the answer then listed three "headlines" with sentiment tags ("Tesla Faces Legal Challenges [Sentiment:
  Negative]" and two more) that exist nowhere in the stored headlines or filing text (checked in the database). No check
  catches this: there are no digits and no citations. The other two runs listed filing risks and said they "could
  contribute to volatility", a hedged cause. (2) **Price questions without the usual words** go to the filings and are
  answered "not available": "Give me the one-week move for Tesla", and "Why did Microsoft shares go up lately?" (no price
  source given, yet the answer says "the stored data shows the price movement"). (3) **Market value wording:** "How much
  is Apple worth in total?" is answered "the sources do not include the total market value", though the figure is stored
  (known weak spot, now measured). (4) **Sentiment wording:** "Is the media tone around Apple turning sour?" is not read
  as a sentiment question, and the answer repeats an irrelevant sentence from the instructions about price moves. (5) **A
  ratio not on the list of nine** ("Tell me Apple's price to free cash flow") is answered "the sources do not include
  Apple's stock price", which is false; the stock price is stored. (6) **Advice wording:** "Is Microsoft a smart place to
  park my money?" is not detected, so no notice (predicted). (7) **An invented date range:** "Any news on Amazon this
  week?" was answered "during the week of October 12-14", where nothing says October 12; the numbers check caught it,
  so the check worked. **Two failures were my expectations, corrected afterwards:** "What's the dividend payout ratio for
  Microsoft?" expected a decline in code, but the answer ("not directly provided", then the two stated figures, no ratio
  worked out) is better, and "Any of it negative?" expected sentiment evidence when listing the negative headlines needs
  only the headlines. With those two corrected the same answers would have scored 84 of 108; 78 is the figure as run.
  **Smaller things seen in passing answers:** a template headline shows up as "META_TITLE_QUOTE" in two answers and
  irrelevant headlines pad others ("Dividend ETFs Don't Work The Way You Think" for Microsoft); and "Did Tesla stock drop
  yesterday?" was answered from 10-13 when the day was 10-15, which is the stale-price problem showing up in an answer.
  **Order I would fix them in:** (a) a check that any title quoted in an answer appears in the sources, with the answer
  retried or warned when it does not (1 above; highest, because it is a made-up fact the reader cannot detect); (b)
  price-question wording (2), tested one phrase at a time because routing changes move other cases; (c) the "no stock
  price" claim on the filings route (5), either by recognizing more ratio names or by not letting a filings-only answer
  say what is stored; (d) market value, sentiment, and advice wording (3, 4, 6); (e) the template headline. **Not
  fixed in this step by design:** the point was to measure, not to tune. **Combined view:** the 86 tuned cases scored 252
  of 258 on their last run and the 36 fresh ones 78 of 108, which adds to 330 of 366 (90%) across the 122-case set, from
  two separate runs; the tuned number overstates how the copilot does on questions it has not been shaped for.
- **Quoted titles must be in the sources (fix (a) of the held-out round), 2026-10-15.** `invented_titles` in `ai/copilot.py`
  takes what the answer presents as a headline or quotation (text in quotation marks of three words or more, and the words
  before a `[Sentiment: ...]` tag) and looks for it in every source the model was given and in the question, ignoring case
  and punctuation. Anything not found triggers the same single retry as the numbers check, with the invented titles named
  in the complaint, and if the second answer still has one, a caution is attached to the answer (`Answer.cautions`, so no
  new API field and no web change). **Checked on the live model:** "Why is Tesla tanking?" five times; in two runs the
  model quoted two made-up headlines each (in a quoted-with-label format, not the `[Sentiment:]` format of the first
  sighting), both survived the retry, and both were flagged with the caution. The other three runs listed filing risks
  or said there were no headlines. So the retry did not fix the invention in either run: **the check warns, it does not
  prevent.** **Not covered:** an invented title with no quotation marks and no sentiment tag (for example `[neutral] Some
  Title` on its own line); a made-up title that happens to be a substring of a real source; and the cause, which is that
  the question is read as a filings question, not a price question (fix (b), not done). The full `eval_market` set has not
  been re-run with this change.
- **Price-question wording (fix (b) of the held-out round), 2026-10-15.** `PRICE_RE` in `ai/market.py` now also takes
  "tanking" (and "will/could/to tank"; the bare noun "tank" no longer counts, which wrongly caught "oil tank leak"),
  "stock/shares go/going/went/gone up/down/higher/lower/sideways", and a number-plus-period-plus-move phrase ("one-week
  move", "3-month movement", "two-week swing", "weekly move"). Window parsing was fixed where the new phrases reached it:
  "two-week" had been read as one week, "weekly" fell back to the default month, and "3-month" with a hyphen was read as
  one month. Written and probed with fresh wording first (9 of 12 price phrasings missed before, 0 after; 2 of 7 lookalike
  filings questions wrongly caught before, 0 after), then tested in `tests/test_price_wording.py`. **Full `eval_market`,
  3 repeats, all 122 cases: 338 of 366 (92%)**, against 330 of 366 from the two earlier runs added together. This is not a
  fair score: the 36 fresh cases are tuning material now and three of them ("one week", "why up", "tanking premise") are
  what this fix was aimed at. "Why is Tesla tanking?" now goes to prices plus headlines and the answer corrects the premise
  (the stock rose over the month) with real headlines; "tanking premise" is 2 of 3 (one run said the stock "might have
  tanked"). Still failing, unchanged by this step: "ho news: this week" (0 of 3; invented "October 12-14" date range, caught
  by the numbers check), "tone turning sour", "worth in total", "price to free cash flow", "park my money" (fixes (c) and
  (d)), "payout ratio", "revenue growing" (1 of 3), and "shares: buy back" on purpose. **Not covered:** "change" and
  "performance" with a period ("two-year change") are deliberately not price questions, since they are often revenue or
  segment questions. Fair measurement of this step needs new cases in new wording.
- **More ratios declined in code, and a caution on a false "no price" claim (fix (c) of the held-out round), 2026-10-15.**
  "Tell me Apple's price to free cash flow" was not one of the nine ratios the app names as not computed, so it went to the
  filings and the answer said the stock price was not in the sources, which is false. `_UNSTORED` in `ai/market.py` now
  also names price to free cash flow (and P/FCF), price to cash flow, free cash flow yield, earnings yield, EV/sales,
  current ratio, quick ratio, return on invested capital, and interest coverage. "Dividend payout ratio" is deliberately
  not on the list: the model's answer to it (the two stated amounts, no ratio worked out) is better than a flat decline.
  Second, `false_price_claim` in `ai/copilot.py`: when the sources given to the model include no price source, the answer
  says a stock price or price data is missing, and prices are stored for every company named, a caution says that
  stored daily closing prices exist and were not used. Worded to be true even when a filing really does not state a price.
  Names are matched by regular expression, so it can fire on a sentence like "the 10-K does not discuss stock price
  targets"; that would be a harmless but needless caution. **Full `eval_market`, 3 repeats, 122 cases: 343 of 366 (94%)**,
  against 338 after the price-wording step. "Price to free cash flow" went from 0 of 3 to 3 of 3. Not a fair score (tuning
  material). The new caution did not fail any case's `no_cautions` check, but the evaluation does not print cautions, so
  how often it fires on real answers is **not measured**. **A/B on main, 10 runs each:** "press coverage" 9 of 10 on main
  and 8 of 10 on this branch (its 0 of 3 in the full run was noise); "ho fund: revenue growing" **0 of 10 on both**, so it
  is not caused by this step: the numbers check flags "2025" in an answer that says "the 12 months ending 2025-06-30",
  a false positive worth its own look (the 1 of 3 earlier was luck). Still open from the held-out list: market value
  ("worth in total"), sentiment ("tone turning sour") and advice ("park my money") wording, and the template headline.
- **Market value, sentiment, and advice wording (fix (d) of the held-out round), 2026-10-15.** All in `ai/market.py`,
  each tried on fresh wordings first (none a held-out case). **Market value:** "What is Microsoft worth?", "How much is
  Apple worth in total?", "valued at", "total value of all of Tesla's shares", "company value", and "cost to buy all of"
  now go to the stored figures. The company must be the subject of "worth", with no possessive, so "Microsoft's goodwill",
  "the inventory", and "Apple stock worth buying?" are not caught; the matched phrase is cut out before the price check, so
  "how much is Apple worth" is not read as a price question. Not caught: "How big is Nvidia as a company, in dollars?".
  **Sentiment:** media/press/news/coverage near "tone", "mood", or "vibe"; "souring on"; "turning sour/bullish/bearish";
  press words near "negative/positive"; "how do reporters/journalists/the press feel"; "coverage trending/shifting".
  "Turning negative" alone is deliberately not a trigger (cash flow can turn negative). **Advice:** a new group of phrases
  ("a safe place/home to...", "better off with", "do you like...", "wise/sound ... for me", "put/park money in") and any
  mention of the reader's own money (`OWN_MONEY_RE`: my/our money, cash, savings, retirement, portfolio, IRA, 401k). It
  leans to flagging, as the rule says; "its cash" and "an employee savings plan" are not caught. **Full `eval_market`, 3
  repeats, 122 cases: 351 of 366 (96%)**, against 343. "Worth in total", "tone turning sour", and "park my money" all
  passed 3 of 3 (they are tuning material now, so this is not a fair score). The advice answer for "park my money" still
  describes Microsoft's business at length before declining; the notice is attached in code, but the content of
  advice-adjacent answers is unchanged. New failures in the run were model wording on cases these rules do not touch
  ("why did it move": "may have been part of the broader market context"; "press coverage" 1 of 3, which was 8 to 9 of 10
  in the earlier A/B). Still open from the held-out list: the template headline (`META_TITLE_QUOTE`, irrelevant headlines
  padding answers), and the "2025" false positive in the numbers check.
- **The "2025" false positive in the numbers check, 2026-10-15.** "Has Microsoft's revenue been growing?" was flagged
  (`figures not in the cited sources: 2025`) on a correct answer, 0 of 10 on `main`. The figures source said only "vs the 12
  months a year earlier", and the model wrote "ending 2025-06-30" itself, a date in no source. The check was right to
  flag it by its rules; the fix is in the source, not the check. `trailing` in `data/fundamentals.py` now writes the earlier
  period's real end date ("vs the 12 months ending 2025-06-30"), taken from the stored figure so a 52-week filer's date is
  its own (Apple: 2025-06-28), and falls back to the old wording when there is no earlier year. The growth label is also
  shown on the stock detail page, so it reads more precisely there too. Only the full-year wording was changed; the
  partial-year wording ("the 6 months to X vs the same 6 months a year earlier", with its "only (not the growth of the
  12-month total)" note) was tuned carefully above and is untouched. **After the change:** the case 10 of 10; full
  `eval_market`, 3 repeats, 122 cases: **356 of 366 (97%)**, against 351. Remaining misses: "shares: buy back" (on purpose),
  "ho news: this week" (the invented "October 12-14" range), "payout ratio" 1 of 3, and "sentiment" 1 of 3 (the answer
  leaves out the word "label"; model wording, as with "press coverage", which swings between 3 and 10 of 10 across
  runs). Not a fair score. A model that works out other dates (such as "last year" as "2025") is still flagged, correctly.
- **Template placeholder headline (fix (e) of the held-out round), 2026-10-15.** `_QUOTE_PAGE_RULES` in `data/headlines.py`
  now also takes a title that is only an UPPER_SNAKE_CASE token ("META_TITLE_QUOTE", seen in two stored rows and two
  answers), so the copilot, the sentiment totals, and the news lists all leave it out. Mixed case and titles with other
  words are not matched (tests in `tests/test_headlines.py`). Full `eval_market`, 3 repeats, 122 cases: 356 of 366, unchanged,
  and no placeholder text in any answer. **Not done, still a decision for the owner:** moving the copilot onto the broad
  data-page rules. In the last 8 days the copilot saw about 53 titles the broad rule drops ("Holding History", "Options
  Chain", "Stock Analysis" pages); the experiment that flipped "crashing premise" from 8 of 8 to 0 of 8 predates the
  premise-correction fix and has not been re-run. Irrelevant headlines that pad answers ("Dividend ETFs Don't Work The Way
  You Think" for Microsoft) are a relevance-labeling matter and are unchanged.
- **Second held-out round: the fair score is 68 of 105 (65%), 2026-10-15.** After the five fixes above (all merged), 35 new
  cases were written in wording used nowhere else (not even in the unit tests written for those fixes), with expectations
  set from the right behavior, run once with 3 repeats, and every answer read, passing ones too. They are now `ROUND_TEN`
  and count as tuning material (`HELD_OUT` is empty again; the set is 157 cases, one name, "filings only", is duplicated
  from before). **The honest reading:** this is not better than the first fresh round (72%), and the questions were
  different and deliberately include stretches, so the two numbers are not a trend. What it shows is that fixing the
  eight failures found last time did not make the wording rules general: new everyday phrasings miss in the same places.
  **By group (first pass):** prices, news, and sentiment 6 of 10; financial figures 3 of 6; filings 5 of 5 (the one clean
  group again); traps 5 of 9; follow-ups 3 of 5. **Thirteen failures,
  by cause:** (1) **Price questions that still go to the filings and are answered "no price data in the sources"** (3):
  "Is Amazon above where it started 2026?", "Show me how Alphabet has moved over the last three months", "Has the stock
  market been kind to Amazon over the last few weeks?". The false "no price" claim was one of the things the last round's
  caution (`false_price_claim`) is meant to flag; the evaluation does not print cautions, so whether it fired is not
  measured. (2) **Financial-figure wording** (2 real): "How much did Amazon earn over the past twelve months?" goes to price
  because "how much did" is a price phrase; "How many dollars of sales did Nvidia bring in over the last four quarters?"
  goes to the filings, which have no twelve-month total. A third, "What multiple of earnings is Alphabet trading at?", was
  answered correctly (P/E 17.8) and failed only because a price source came along too; that expectation was too strict.
  (3) **Sentiment wording** (1): "Are reporters being kind or harsh to Nvidia right now?" (no sentiment words the rule knows).
  (4) **Advice wording** (2): "My friend says Nvidia is a sure thing. Is she right?" and "Would you say Alphabet is cheap
  right now?" got no notice. (5) **A non-company question answered from a company filing** (1): "What did Bitcoin do this
  month?" was answered from Tesla's Bitcoin holdings note; the right behavior is the "tell me which company" refusal.
  (6) **A checker artifact** (1): "What caused Nvidia's last big drop?" was answered well (no cause in the data, and the
  stock actually rose) but failed on the word "reflects" in `SPECULATION`; it also got only the price source, since
  "caused" is not one of the cause words. (7) **Follow-ups** (2): "Is that better or worse than Amazon?" dropped Nvidia
  from the companies (history was ignored), and "Now do Alphabet." after a risks question was not read as the same question
  for Alphabet ("do" is not a filler word in `carry_topic`), so the model summarized the company and listed 21 figures
  that the numbers check flagged. **Passing answers that were not right when read:** "What was Microsoft's closing price at
  the end of last week?" was answered with the latest close (10-13) as if it were last week's; "How did Apple shares and
  Microsoft shares do since July?" was answered over the past month (`parse_window` knows no month names or dates) without
  saying the period was different; "How did Tesla's stock finish today?" gave the 10-13 close as "today" (it was 10-15; the
  stale-price problem). The rules passed these because they check for figures and sources, not for the period asked. **Order
  I would fix them in:** (a) price questions without the usual words, in particular a period ("over the last three months",
  "since July", "last few weeks") or a comparison with the start of the year, tested one phrase at a time; (b) honoring the
  period the question names, or saying in code that the window used is not the one asked; (c) follow-up carrying ("Now do
  X", "better or worse than X" keeping both companies); (d) the "earn" and "sales" figure wording; (e) advice and sentiment
  wording again; (f) non-company questions. The pattern after two rounds is that each fix covers its own phrasings; a
  more general approach (a routing step that asks the model to classify the question, checked in code) is worth weighing
  against more keyword rules, which keep needing new patches. Not decided; it would be a change to how every question is
  routed and would need its own evaluation.
- **Price questions that name a period: fixes (a) and (b) of the second held-out round, 2026-10-15** (branch
  `feature/copilot-price-periods`). Each change was run alone through the full `eval_market`, 3 repeats, 157 cases, in this
  order: **baseline on `main` 422 of 471 (90%; 140 of 157 on one pass)**, after the "moved over a period" rule 427, after the
  "where it started the year" rule 429, after the period parsing and cautions (with the "stock market been kind to" wording
  following from it) **434 of 471 (92%; 145 of 157)**. No case that passed before was lost; the other differences were cases
  that swing between runs ("why did it move", "payout ratio"). **Not a fair score**: the cases are tuning material, and the
  wordings in the unit tests were new but the evaluation cases they were meant to fix were known. **Built (all in code, no
  prompt change):** (1) `PERIOD_MOVE_RE`: "how has/did X moved/trended/fared/swung" plus a named period is a price question,
  with no "stock" needed; X must be one bare name, so "Apple's headcount moved" and "move its supply chain / into cloud" are
  not caught. (2) `year_start_comparison`: "above where it started/opened/began 2026", "stood at the start of the year",
  "finished last year" is a price question with the year-to-date window. Only the current year is accepted, because
  year to date is wrong for any other; "where it was last year" is deliberately not caught (it can be about anything).
  (3) `parse_window` reads "the last/past N days, weeks, months, years" (digits or words; the old labels and lengths are kept
  for the forms that were already right), "a few / a couple of / several" (read as 3, 2, 4; the label says "reading 'few'
  as 3"), and "since <month>" (from the 1st, this year, or last year if the month has not come; "since January" stays year to
  date). It takes `today` for tests. (4) A period no window can match ("the end of last week", "on Monday", "on October
  3rd", "during July", "Q2", "in 2025") is kept as `Window.unmet`; "today" and "yesterday" as `Window.asked_day`. The price
  source then says so, and `period_cautions` attaches a caution to the answer **in code** (copilot `cautions`), naming the
  window actually used and the newest close; with "today" it also checks whether the newest stored close is today's. No
  caution without a price source. **Checked:** 844 Python and 253 web tests pass (73 new Python tests in
  `test_price_periods.py`, `test_price_windows.py`, `test_copilot_price_period.py`). Ten deliberate breakages (three on the
  routing rules, seven on the windows and cautions) were each caught. The cautions are **not printed by `eval_market`**, so
  the wiring is covered by the end-to-end unit test and one real run: "What was Microsoft's closing price at the end of last
  week?" printed the answer (the 10-15 close) and the warning naming the past week up to 2026-10-15. **Weak spots:**
  (1) That answer is still not about the end of last week; the warning says so, but nothing fetches the Friday close.
  (2) "Last month", "this week" and "last quarter" are read as the past month, week and 3 months without a warning, a
  judgment that people use them loosely. (3) "A few" as 3 is a guess. (4) "Since July" starts at July 1 and uses the last close
  on or before it. (5) `PERIOD_MOVE_RE` misses "How has the company moved over the last year?" (the subject is a bare name
  only), and "in May" can match the modal "may" in the unmet list. (6) A stock noun plus a now-understood period is a price
  question, so "Which Nvidia shares did insiders sell over the last two weeks?" would be too (not tested). (7) Existing, not
  caused by this: the word "rise" is a price word, so "Did Apple's stock-based compensation rise over the last six months?"
  goes to prices on `main` too. **Still failing after this (12 of 157 on one pass):** sentiment ("kind or harsh"),
  "earn" and "dollars of sales" wording, "multiple of earnings" (the expectation is too strict), "sure thing" and "cheap right
  now" (advice), "bitcoin" (a non-company question), "what caused the drop", "better or worse than" (a follow-up that drops
  a company), "buy back (quarter total)" (on purpose), and the flaky "press coverage" and "why up". These are items (c) to
  (f) of the second held-out round and are the next steps. The model-based routing question was discussed and left open:
  the owner agreed to do (a) and (b) with keyword rules first, then write fresh held-out cases and decide.
- **Follow-up carrying: fix (c) of the second held-out round, 2026-10-16** (branch `feature/copilot-follow-ups`). **What
  went wrong, reproduced on the real model first:** (1) "Now do Alphabet." after a risks question: the rewrite step leaves
  it alone, and `carry_topic` then gave up because "do" was not a filler word, so the search ran on a company name and the
  answer was a company summary (the evaluation case still passed, because it checked only the kind of evidence and the
  company). (2) "Is that better or worse than Amazon?" after a question about Nvidia: the model rewrote it to "...than
  Amazon's stock performance this month", dropping Nvidia, so only Amazon was searched (0 of 3). When the model left the
  wording alone ("stronger or weaker than Amazon") the question also lost its price topic. **Fixed in code, no prompt
  change** (`ai/copilot.py`): (a) `SWITCH_FILLER_RE` also takes do, try, check, run, go, ahead, see, please, again, let, lets,
  me, show, give, same, pull, up, so "Now do X", "Try X", "Same for X", "Go ahead and do X", "Let's see X instead" carry the
  earlier topic exactly as "What about X?" does; a question with any other word ("Now do X's employees", "Does X have...")
  is not a switch. (b) `comparison_companies`: a question with a comparison word (than, versus, against, compare, stack up,
  beat, outperform, measure up), a reference back ("that", "it", "those"), and a company the last turn did not discuss means
  the last turn's companies plus the new one. Not used when the question names the earlier company itself, refers to
  something older ("the other one"), the last turn had no company, or companies were chosen by the user. (c)
  `carry_comparison`: when the rewrite no longer names every one of those companies and the question has no topic of its own
  (`_is_bare_comparison`: only company names, comparison words, and a closed list of comparatives), the question is rebuilt
  from the earlier topic question, "How has Nvidia stock done this month, compared with Amazon?"; the topic comes from the
  last question that had one (a bare "What about Tesla?" is skipped, and its company is swapped in). Only the earlier
  question is reused, never its answer (a test checks the answer prompt). When the question has a topic of its own ("Does
  its revenue look better than Omegaware's?") the model's wording stays, both companies are searched, and "Understood as"
  ends with "(comparing X and Y)". A rewrite that kept both companies is trusted unchanged. **Numbers:** `eval_followups`
  17 of 17 and 10 of 10 held-out, identical on `main` and on the branch (3 runs, stable); it has no case of these two kinds.
  **Eleven fresh follow-up cases** (`STEP_C` in `ai/eval_followups.py`, written before any run, in wording unlike the unit
  tests and probes, several deliberate stretches), run once: **3 of 11 on `main`, 7 of 11 on the first version of the branch**;
  the four misses were "did that beat X" (a comparison word the rules lacked), "measure up to" (same), "go ahead and do X"
  and "let's see X instead" (fillers the rules lacked). Those four words were then added (tests first), giving **9 of 11**.
  The two left: "Did that beat Microsoft?" is answered correctly ("Apple's employee count") and fails only because the check
  wants the word "employees"; "How does it measure up to Microsoft?" keeps both companies but the model's rewrite drops the
  topic, which nothing in code detects. These 11 are tuning material now; the 9 of 11 is not a fair score. **Market
  evaluation** (`eval_market`, 3 repeats, 157 cases; the data and headlines had moved a day since the last entry):
  **439 of 471 on the first version, 436 of 471 on the final code**, against 434 for the previous step. "Better or worse than"
  went from 0 of 3 to passing with a real two-company answer (Nvidia +2.97%, Amazon +0.48%, from the sources); "now do
  Alphabet" now answers about risks, and its check was tightened to require the word "risk". The 436-versus-439 difference
  is "press coverage" (swings between 0 and 10 of 10 across runs, as noted above) and "tanking premise" (2 of 3 at baseline,
  1 of 3 here): neither has an earlier conversation, and the new code does nothing without one. **Tests:** 44 new Python tests
  (`tests/test_copilot_follow_ups.py`); 888 Python tests pass. Eleven deliberate breakages of the new rules were each caught;
  one was first missed because no test checked the companies (the same company named again counted as a comparison with
  itself; a test was added), and one because my breakage removed a comparative no test used (redone on one a test uses). **Weak spots:** (1) A rewrite that names both companies but loses the topic ("measure up to
  Microsoft") is not detected. (2) The word lists (fillers, comparatives, comparison words) are finite, so a new wording
  that falls outside them keeps the companies but not the topic (the note then says what was compared). (3) "That" is taken
  to mean the last turn's companies; a user who means something older without a word like "first" or "other" gets the
  wrong one, though "Understood as" shows what was assumed. (4) "Show me X" and "give X" after a topic question now carry
  the topic, which is wrong when the user wanted a general overview. (5) Not checked in a real browser: the new
  "(comparing ...)" ending of "Understood as" is covered by tests, not by looking at the page. (6) Still open from the
  same round: (d) "earn" and "sales" wording, (e) advice and sentiment wording, (f) non-company questions.
- **"Earn" and "sales" wording: fix (d) of the second held-out round, 2026-10-16** (branch
  `feature/copilot-figure-wording`). **Three separate causes** (found by probing a dozen wordings with `detect_intent`, which
  needs no model): (1) "how much did/does/is" is a price phrase, so "How much did Amazon earn" went to the price data, and
  so did "how much did Apple pay in dividends" and "how much did Apple's sales grow"; (2) "earn" and "sales" were not
  figure words; (3) any "quarters" counted as a filing marker, so "the last four quarters" (exactly the twelve months the
  stored figures hold) was sent to the filings. **Built, in code only** (`ai/market.py`), in two stages evaluated separately.
  *Stage 1:* `HOW_MUCH_MONEY_RE` cuts "how much did/does/is/has" out of the price check when a money verb or noun follows
  (earn, make, net, pay, spend, sell, bring, raise, generate, report, borrow, owe, profit, revenue, sales, income, dividends,
  cash) **and the question has no stock, share or price word**, so "How much did Apple stock sell for" stays a price question;
  and "earn" counts as profit only as "what / how much (money) did-does-has X earn(ed)" with one bare name as the subject, so
  "How much do Apple engineers earn?" does not. *Stage 2:* "sales" counts as revenue only as "X's sales", "total / net /
  overall / combined / annual / yearly / its / their sales", or "dollars / amount / value of sales", and not before tax, team,
  force, staff, office, people, reps, channels, practices, cycle, pipeline, commission, "and marketing", costs or expenses;
  "how much money / cash / dollars ... bring / take / pull in" is revenue; and `TWELVE_MONTHS_AS_QUARTERS_RE` stops "the
  last/past/previous/trailing/prior four quarters" from counting as a filing marker ("last quarter", "the second quarter" and
  "the last two quarters" still do). **Numbers** (`eval_market`, 3 repeats, 157 cases, same day, the data moving only by the
  day's headlines): **437 of 471 baseline on `main`, 438 after stage 1, 443 after stage 2, 446 after the final code**
  (149 of 157 on one pass). "How much did earn" went from 0 of 3 to passing with Amazon's net income of $135.3 billion (the
  stored figure); "dollars of sales" from 0 of 3 to passing with Nvidia's $303.0 billion. Not a fair score: the cases were
  known. No case that passed at baseline was lost (the swings were the flaky cases listed above). **Routing check:** of the
  168 evaluation questions, exactly 8 change route between `main` and the branch (the two targets, five fresh held-out cases,
  and "how much did Apple pay out in dividends", now filings); "Why is Tesla tanking?" routes identically, so its 0 of 3 in one
  run is the day's headline ("...Prediction Markets Say It's Likely", quoted, tripping the speculation check), not this change.
  **Fresh cases** (`ROUND_ELEVEN`, 11, written before any run, several deliberate stretches): **8 of 11 on the first
  check**, because "What were Apple's iPhone sales over the past year?" went to company revenue (my "sales over the last
  ..." form matched it). That form was dropped, the case added as a unit test, and the run scored **9 of 11**. The two left:
  "What were Alphabet's annual sales?" goes to the 10-K by design ("annual" is a filing marker) and is right for the fiscal
  year ($402.8 billion, against $445.9 billion for the twelve months to the latest quarter), so my expectation was wrong; and
  "How much money does Amazon make in a year?" (the stretch: "make" is not a known word) was answered correctly from the
  filings. These 11 are tuning material now. **Evaluation checker changed:** "fo fund: multiple of earnings" demanded the
  figures source alone, but "trading at" asks about a price-based ratio, so the price source arriving too is right (the
  P/E answer itself was already correct); it passes since. **Tests:** 38 new in `tests/test_figure_wording.py`; 926 Python and
  253 web tests pass. Eleven deliberate breakages (five on stage 1, six on stage 2) were each caught in the end; three were
  first missed because no test depended on the code (the stock-word guard, "dollars of sales" which another form also
  matched, and any-number-of-quarters), and a test was added for each. **Weak spots:** (1) "Make" and "made" are not
  recognized ("How much did Tesla make last year" goes to the filings, which answer it, but not from the stored figures).
  (2) The "earn" rule needs one bare name as the subject, so "How much did Alphabet Inc. earn?" is missed. (3) "Sales" has to
  be possessive, total / net and the like, so "Amazon sales over the last year" is missed (safe: it goes to the filings).
  (4) "Annual sales" gives the fiscal year from the 10-K, not the twelve-month figure; both are right, and they differ.
  (5) Existing and not changed: "Do you think I should get out of Tesla before earnings?" routes to the profit figures because
  of the word "earnings". (6) The money-verb list is a finite guess: a question with a stock word and a money verb stays a
  price question even when it is about something else. Still open from the same round: (e) advice and sentiment wording,
  (f) non-company questions.
- **Advice and sentiment wording: fix (e) of the second held-out round, 2026-10-16** (branch
  `feature/copilot-advice-sentiment`). **What the probe showed** (no model, `detect_intent` and `asks_for_advice`): of 24
  everyday advice wordings written for the probe, **21 got no advice notice** ("Is Nvidia undervalued?", "Rate Apple as an
  investment", "Is it too late to jump into Nvidia?", "I have $5,000. Where should it go?"), none of 8 look-alikes was
  flagged; and **all 12 news-tone wordings missed the sentiment route** ("kind or harsh", "piling on", "how is the media
  treating X"). The phrase lists written in the earlier rounds cover their own wordings, as DECISIONS already said, so this
  fix is written as structure. **Sentiment** (`_NEWS_SOURCE`, `_NEWS_TONE`, `SENTIMENT_RE` in `ai/market.py`): a news word
  (reporters, journalists, press, media, coverage, headlines, news flow, writers, commentators, pundits, buzz, chatter)
  within 40 characters of a word about attitude (kind, harsh, friendly, favourable, piling on, treating, upbeat, gloomy,
  better, worse, souring, "turned on", "easy ride", "hard time", "going easy on"...), either order; "saying nice things
  about"; "feeling / attitude / take on ... the news". Analysts are deliberately not a news source. **Advice**
  (`ADVICE_JUDGMENT_RE`, plus more `TRADE_WORD_RE` and `DECISION_CUE_RE` words): a judgment of value (over/undervalued,
  over/underpriced, fairly valued, a bargain or steal, and "cheap / expensive / pricey" only when the question ends there or
  goes on with now / today / at this price); an endorsement (a sure thing, can't lose, a safe / solid / good bet, a winner
  (not "winner-take-all"), a keeper, a no-brainer, a screaming buy, worth owning, would you bet, rate X as an investment,
  your take on, make me money, am I crazy to, "a good ... investment / hold / pick" with up to two words between); the
  reader's own money (where should it go, I have $N, a retirement or brokerage account, a smart addition to my portfolio);
  timing ("too late / early to", the moment or time, reckon, pick up, jump into, pile into, stay in, bail on, get out of);
  and "too pricey / expensive / cheap to touch / own / buy / hold"; "would a cautious investor go for / buy / pick". The notice
  itself (`ADVICE_CAUTION`) is unchanged and is attached in code. **Numbers** (`eval_market`, 3 repeats, 168 cases, same
  day): **474 of 504 baseline on `main`, 476 after the sentiment rule, 483 after the advice rules, 485 after the final
  code**. "Kind or harsh" 0 of 3 to passing (an answer from the sentiment summary, 31 positive, 119 neutral, 17 negative,
  +0.08, with the label caution); "sure thing" and "cheap right now" 0 of 3 to passing with the notice. Not a fair score.
  Nothing that passed at baseline was lost. Of the 168 questions, only the three targets and "Is Tesla overvalued given its
  P/E ratio?" (now flagged, and it keeps its P/E) change route or flag. **A regression of mine, caught by the existing tests:**
  the first version flagged "What is Tesla's best selling model?" because "sell" matched the start of "selling"; the noun now
  needs a word boundary and a test says so. **Fresh cases** (`ROUND_TWELVE`, 11, written before any run, the wordings unlike
  the probe and the unit tests, several planned stretches): **5 of 11**, the fair score. Missed: "Is Apple a smart addition to
  a growth portfolio?" (a plain wording), and the stretches "too pricey to touch", "would a cautious investor go for Tesla",
  "would you pile into Nvidia", "press giving Tesla an easy ride", "has the media turned on Amazon". Those wordings were then
  added to the rules, tests first, after which all 11 pass (not a fair score; two evidence expectations were corrected, to the
  price data for "cautious investor ... right now" and the figures for "pile into ... ahead of earnings", since the case checks
  the notice). **Tests:** 91 new in `tests/test_advice_sentiment_wording.py`; 1017 Python and 253 web tests pass. Twenty-five
  deliberate breakages (six on the sentiment rule, nineteen on the advice rules) were each caught in the end. Five were first
  genuinely missed because the tests did not depend on that code (two sentiment negatives had no word from the tone list,
  the dollar-amount and "where should it go" forms each covered for the other, and a widened window had no long-gap
  negative), and two more only because my script's search string was wrong; each got a test or a fix. **Weak spots:** (1) Only the
  fixed notice is attached in code; **the content of an advice-adjacent answer is unchanged**: "Would you say Alphabet is
  cheap right now?" is answered "the sources do not include Alphabet's market value or P/E ratio", which is untrue, since both
  are stored and the question is not routed to them. (2) The lists are finite; an advice wording outside them gets no
  notice, and a missed notice is the costly mistake. A model-based check that can only add the notice is the obvious next
  experiment and is still not built. (3) Leaning to flag: "How does the 10-K account for its investment in X as an
  investment?" style questions that match a pattern would get an extra notice (none seen in the 179 evaluation questions).
  (4) "Cheap" and "expensive" are only judgments at the end of a question or before now / today / at this price, so "Is
  Microsoft expensive for what you get?" is missed. (5) Existing and not changed: the bare word "mood" and "tone of" route to
  sentiment ("What mood did Tesla's CEO strike on the earnings call?"), and the word "earnings" in "pile into Nvidia ahead of
  earnings" sends the question to the profit figures. Still open from the same round: (f) non-company questions ("What did
  Bitcoin do this month?" is answered from Tesla's Bitcoin note), and the content of advice-adjacent answers.
- **Questions about things outside the tracked companies: fix (f) of the second held-out round, 2026-10-16** (branch
  `feature/copilot-outside-topics`). **What the real copilot did with 20 probe questions that named no tracked company:**
  "What did Bitcoin do this month?" was answered from Tesla's Bitcoin note (its other income); oil, mortgage rates, the Fed,
  inflation and a recession got answers about risk language in the filings; "What are Intel's biggest risks?" was answered
  from filings that name Intel as a competitor; "Write me a poem about stocks" got a poem that cites no source. Ethereum,
  gold and the dollar were refused, but only by accident, through price wording (the generic "tell me which company"
  notice). A cross-company question ("Which companies mention Bitcoin?", "Which of the companies mention interest rate
  risk?") works and must keep working. **Built in code, no prompt change:** `outside_scope` in `ai/market.py`, used in
  `answer_question` after the companies are resolved, so it only runs when no tracked company was named and no follow-up
  carried one. It declines, with a fixed message and before the model is asked, a question that (1) is about an asset or
  topic the app does not hold (`OUTSIDE_ASSET_RE`: crypto, gold, oil, copper, treasuries, mortgage and interest rates,
  inflation, GDP, recession, the Fed and other central banks, the dollar and euro, housing market...); (2) names a
  well-known company that is not tracked (`UNTRACKED_COMPANIES`, about 70 names, a list that goes stale; a few that are
  also ordinary words, such as Intel, Oracle, Lucid, Uber and Zoom, count only when capitalised; ambiguous words such as
  Target, Visa, Ford and Shell are left out), in which case the message names the company, lists the tracked ones and points
  to the dashboard's "Add a company" box; or (3) is not a research question (`NOT_RESEARCH_RE`: write a poem, tell me a joke,
  recipes, the weather, who won). A **filings cue** (`which`, `companies`, `mention`, `disclose`, `10-K`, `risk factors`,
  `according to`, `exposure`...) vetoes (1) and (2), so a question about what the filings say is never declined. It runs before
  the generic "no company named" refusal, because "the price of copper" reads as a price question and that notice does not say
  what is missing. **Evaluation checker changed:** a refused answer's text was never checked against a case's `must`
  patterns (only which evidence was shown), so a refusal with the wrong message passed; it is checked now, and no existing
  case failed because of it. **Numbers** (`eval_market`, 3 repeats, 179 cases, same day): **515 of 537 on `main`, 519 on the
  branch**; "fo trap: bitcoin" 0 of 3 to passing with the new message. The one new miss, "advice: the better buy" at 2 of 3,
  is model figure formatting on a question that names Apple and Microsoft, which the rule does not touch (checked). Of the
  179 questions, exactly one (the Bitcoin target) is declined by the new rule. Not a fair score. **Fresh cases**
  (`ROUND_THIRTEEN`, 10, written before any run, three of them stretches and two guards): **8 of 10 as the checker then stood,
  6 of 10 once the checker read the refusal text**: "the price of copper" got the generic refusal (fixed by the ordering
  above), "Give me a haiku about earnings season" got the generic refusal too ("earnings" sends it there; any refusal made in
  code is right, so that expectation was widened), and "the central bank" and "Zoom" were not known (added, tests first).
  All 10 are tuning material now. **Tests:** 57 new in `tests/test_outside_topics.py`; 1074 Python and 253 web tests pass.
  Thirteen distinct deliberate breakages were each caught; one was first missed (nothing tested that an ordinary word added
  to the company list is not taken for a company), and tests were added. **Weak spots:** (1) The company list is finite: a
  company not on it gets the old behavior, an answer from the filings that says they do not contain it, with the risk that
  a competitor's filing is used instead. (2) The asset list is finite too, and "the economy" is not on it (it still gets
  the generic refusal through price wording). (3) The filings cue is blunt: "Which is higher, gold or oil?" is not declined and
  goes to the filings, which is safe but not helpful. (4) The not-a-research-question rule covers writing requests,
  recipes, weather and scores; "Give me a haiku about spring" is not a pattern it knows and is left to the relevance
  gate and the model. (5) The refusal's "Add a company" pointer is right for US filers, but a foreign filer is added with no
  filings. (6) The message was checked in tests and through the evaluation, not in a browser (it uses the existing refusal
  path, so the page shows it like any other). (7) "Tanking premise" (0 of 3 at baseline, 1 of 3 here) is the day's headline
  tripping the speculation check, as in the earlier entries, and has nothing to do with this. **This closes the list from
  the second held-out round, items (a) to (f).** Still open: the content of advice-adjacent answers, and a new set of
  held-out cases for the whole round, written now, to measure it fairly before deciding on the model-based check.
- **Fresh held-out round for the whole second-round work: the fair score is 48 of 105 (46%), 2026-10-16** (branch
  `feature/fresh-held-out-round`; the cases were committed before the run, commit 56ab20b). 35 market cases (`HELD_OUT` in
  `ai/eval_market.py`) and 8 follow-up resolution cases (`HELD_OUT` in `ai/eval_followups.py`; the 21 earlier cases there were
  moved into `CASES` first, since they had been run and tuned against). **How the wording was kept fresh:** a script compared
  every new question with 4,314 quoted strings from the tests, web tests, docs, and the committed eval files. It caught two
  cases that were already in the repo ("Will Microsoft hit $600 by December?" was in `CASES` and a test; Walmart's employee
  count was in `tests/test_outside_topics.py`) and several near-copies of a template; all were reworded, and outside topics the rules
  already list (mortgage rates, Ethereum) were swapped for ones they do not. The final highest similarity was 0.62, a shared
  run of three function words. Expectations came from the right behavior and read-only queries of the stored data (newest close
  2026-10-15, Google up about 1% in a month, Tesla's P/E 335.6, Nvidia's market value $5.24 trillion). **Run once, 3 repeats,
  every answer read; each case came out 0 of 3 or 3 of 3, so nothing was flaky.** **By group (first pass, next to the second
  round):** prices, news, and sentiment 5 of 12 (prices 3 of 7, news 2 of 5; second round 6 of 10); financial figures 3 of 5
  (3 of 6); filings 3 of 3 (5 of 5); traps, advice, and outside topics 3 of 10 (traps 2 of 6, outside 1 of 4; second round 5 of 9);
  follow-ups with history 2 of 5 (3 of 5). **Total 16 of 35 first pass, 48 of 105 over three runs, against 22 of 35 and 68 of 105.**
  Follow-up resolution (new here): 3 of 8, the same every run. **Caveats on the comparison:** 12 of the 35 are labeled stretch
  (more than the roughly 25% planned); stretches passed 3 of 12 and the other 23 passed 13 of 23 (57%), so the fall is not only
  the stretches. **Read-through:** after reading every answer I would put it at about 21 of 35 (60%): six mechanical failures
  are acceptable answers (fiscal-year revenue for "what does Tesla take in per year"; "does Amazon say anything similar" also
  searching Microsoft's risks, which is needed to compare; declining the "can only go up" and "reach $650" predictions, which it
  did; and an honest generic decline for gas prices and Chipotle), partly my expectations being too strict, and one mechanical
  pass is wrong ("over the past ninety days" used one month). No case was changed after the run. **The failures, by cause:**
  (1) **Wording that never reaches the price or news data (the biggest group, 6 cases):** "since the middle of August",
  "Tesla's close from last Friday", "how much higher is Nvidia than twelve months ago", "what's the chatter around Microsoft
  this week", "pull up some recent stories about Amazon", "were the stories on Tesla more positive or negative" (the last
  three have no word the news rules know). The 19 mechanical failures are these 6, one wrong period, the missed notice, the
  accepted premise, 2 follow-ups, 3 outside topics, the Alphabet figure, and 4 acceptable answers (listed above). They fall through to the filings, and the answers then say
  the data is not there, which is false: AMD "since the middle of August" was answered with "the most recent price data is
  December 27, 2025 at $234" (prices are stored to 2026-10-15) and "no recent news stories" for Amazon (149 stored in the
  past week). A diagnostic run (the evaluation does not print cautions) showed `false_price_claim` fired for Tesla last Friday
  and Nvidia twelve months ago and did not fire for the AMD answer; there is no equivalent for a false "no news" claim.
  (2) **A wrong period stated with confidence and no caution (2; one passed the rules):** "Is Amazon's share price higher than when the year opened?"
  compared with 2025-10-14, a year ago, and answered yes; "Compare how AMD and Nvidia traded over the past ninety days" used
  about a month (from 2026-09-14) and called it ninety days, because `parse_window` does not read "ninety" and the leftover
  default window is not flagged. The second one passed the rules, which only check that a price was quoted.
  (3) **A missed advice notice (1, the most serious):** "Is it time to cash out of Nvidia?" got no buy, sell, or hold notice
  and the answer listed the stock's growth and strong cash. CLAUDE.md says a missed request is worse than one extra notice.
  (4) **A false premise accepted (1):** "Google doubled this month. What drove it?" was answered as if it had doubled (it rose
  about 1%). (5) **Follow-ups that lose their history in the full answer (2):** "And did Nvidia do better than that?" after an
  AMD price question compared Data Center revenue from the filings; "Switch over to Microsoft." after Tesla news gave a general
  company summary. (6) **Outside topics (3, all stretches):** "Draft an email to my boss about Nvidia's results" produced a
  full email with filing figures; gas prices and Chipotle got an honest generic decline but not the refusal. As DECISIONS
  predicted, the company and topic lists are finite; Costco, which is on the list, worked. (7) **Figures (1 real):** "What
  profit did Alphabet clear in its latest four quarters?" went to the 10-Q and quoted a six-month net income of $174,685
  million (caught by the numbers check) and in another run a pre-tax figure, both as the latest four quarters.
  (8) **Follow-up resolution (3 of 8):** "Give me the number for Apple too" and "Skip to Nvidia" lose the earlier topic,
  "Is Tesla's list longer than that?" loses the word risk, and "Summarize what the companies say about tariffs" after a
  Nvidia risks question was narrowed to NVDA and AMD; "Does Amazon employ more people than that?" is a checker artifact (the
  rewrite was right, the topic word "employees" is not in it). This step only resolves the question; it does not answer it.
  **Passing answers with a reservation:** "what pushed Apple's services segment higher" answered about gross margin, not net
  sales; "reach $650" declined correctly and then added an unrelated Microsoft backlog figure; the wrong-P/E answer correctly
  said 335.6 and then guessed at reasons for a high P/E; the AMD and TSMC answer was not checked against the filing text.
  **What did generalize:** filings (3 of 3); "add up AMD's sales", "what share of Apple's sales ends up as profit", and Nvidia's
  market cap, all with the right stored figures; "past six weeks" and "fortnight" got the right windows; the numbers check
  caught the bad Alphabet figure; the retailer-margin and wrong-P/E traps were handled; Costco was refused. **The honest
  reading:** fixes (a) to (f) fixed their own phrasings and little beyond them. This is the third round in a row where new
  everyday wording misses in the same places, now with a measured 46% (65% and 72% before, on different questions), and the
  most harmful failures are confident wrong answers ("no data" when there is data, a wrong period, an accepted premise), not
  refusals. The model-based routing question is now better supported than before, but this round does not decide it: it
  measures the keyword rules, not the alternative. **Not done, in the order the failures point to:** (1) the false "no data"
  claims (extend the code-side caution to cover "no news" and the AMD wording) and the price and news wordings that never
  route; (2) a window the parser does not read must be flagged, not defaulted ("ninety", "when the year opened"); (3) the
  advice notice for "cash out" and a check on premises ("doubled") from the stored price move; (4) follow-ups keeping their
  topic in the full answer; (5) the outside-topic and writing-request lists; (6) "clear in profit". Then a decision on the
  model-based routing experiment, on its own branch, measured against these 35 cases (now tuning material) and a new fresh set.
- **Fix (1) of the fresh round: price and news wordings that never routed, and the false "no data" claims, 2026-10-16**
  (branch `feature/fresh-held-out-round`; no prompt change, no change to `SYSTEM_PROMPT`). **Baseline first, on the code before
  the change: 549 of 567 (96.8%; 183 of 189 on one pass), the 189 older cases, 3 repeats.** **Built:** (1) `_since_month` reads
  "since the middle of August" / "mid-August" as the 15th and the window label says so ("reading 'the middle' as the 15th");
  "since the end of / late August" is deliberately not read (nothing marks it, and a guess would be a made-up period).
  (2) `_numbered_period` reads "<number> <unit> ago" ("six weeks ago", "twelve months ago") as the window back to then.
  (3) `CLOSE_NOUN_RE`: "Apple's close from last Thursday", "the close for Microsoft", "Where did Nvidia close yesterday?",
  "Did Tesla close higher this week?" are price questions; each form needs a possessive or a day word, so "Apple's close
  relationship with TSMC", "close its plant", "close to a deal" and "the close of the Mandiant deal" are not.
  (4) `PERIOD_COMPARE_RE`: "How much higher is Nvidia than it was a year ago?" / "Is AMD lower than where it was a month ago?" is a
  price question when the subject is one bare name, a period is named, and no financial-figure word is present (so "Apple's
  revenue", "Tesla's headcount" and "revenue than a year ago" are not). (5) `NEWS_RE` gains "chatter" and "recent / latest /
  new / top / any ... stories" ("customer success stories" is still a filings topic); `SENTIMENT_RE` gains stories, headlines,
  articles, news or coverage that are "more / mostly positive or negative", "positive or negative", or "lean positive" (plural
  only, so "headline earnings" is not one; a bare "negative" is not enough). (6) Cautions in `ai/copilot.py`: the price claim now
  reads plural "prices", "no price data / information / movements / history", "closing prices", and contractions ("don't",
  "isn't"; the old `\bn't` could never match inside a word); a new `false_news_claim` adds the same kind of caution for a false
  "no news / no headlines / no stories", with the count and the newest date of the stored headlines (30 days), only when the answer
  had no headline or sentiment source, every company has recent headlines stored, and the question did not itself ask for news
  (then "no news this week" is true). **Tests first:** 88 new (`tests/test_price_news_wording.py`,
  `tests/test_copilot_missing_data_claims.py`), 29 failing before the change; 1162 Python tests pass. Twenty deliberate
  breakages of the new rules were each caught; five were first missed (a follow-on word after "where did X close", a possessive
  "close" followed by any word, a comparison with no period, a bare "negative" counted as sentiment, contractions not counted
  as negations), and each pointed at a missing guard test, now added. **After, on the whole set (224 = the 189 older cases + the 35
  of the fresh round): 613 of 672 (91%).** The 189 older cases went 549 to 548 of 567 (the only change is "press coverage", which
  swings between runs: 1 of 3 before, 0 of 3 after); no case that passed before was lost. **The 35 of the fresh round went from 48
  to 65 of 105 (46% to 62%), not a fair score now:** mid-August, a year ago, chatter, pull up stories and stories more positive
  or negative went from 0 of 3 to 3 of 3, and "close from last Friday" to 2 of 3. Their answers were read: the AMD window uses the
  2026-08-14 close (the last one on or before the 15th, a Saturday), the Nvidia answer's difference matches the two closes it
  quotes (180.03 to 217.23, +37.20), and the Tesla score is consistent with its own counts (+0.15 = (25 - 11) / 94); I did not
  re-check those closes or counts against the database by hand. **Fresh cases written for this
  step, before it was run (10, `HELD_OUT`): 2 of 10 on the old code (only the two guards), 6 of 10 on the new code.** Not
  fixed, and why: "What did Amazon close at last Tuesday?" is routed to prices but nothing fetches a single day's close, so
  the answer declines or gives the month and the period caution says so; "Is there much chatter about Nvidia today?" is routed to
  news, but a one-day window had no story at that hour and the answer is the plain refusal; the stretches "word on the street" and
  "worth more today than eight months back" still go to the filings (the second gets the false-price caution, the first gets
  nothing, and its answer is a filings summary dressed as chatter). **The new news caution was seen firing on a real run** ("What are
  people saying online about Amazon?" got it, with 207 stories in 30 days), but "what is trending", "the scoop on" and "is anything
  being reported" are not news words and get nothing. **Weak spots:** (1) the news caution is a wording match like the price one,
  so a new way of saying "no news" will miss it; (2) the comparison rule needs a bare company name and a period, so "Is Tesla
  worth more than it was ..." misses; (3) "ago" windows and "chatter" are read for any question, but only price and news
  questions use the window; (4) the evaluation still does not print cautions, so they are covered by unit tests, an end-to-end
  test, and diagnostic runs, not by the totals. **Still open from the fresh round:** (2) unread periods flagged, not defaulted
  ("when the year opened" is a year-ago comparison and "ninety days" is a month); (3) the "cash out" notice and a premise check;
  (4) follow-ups keeping their topic; (5) the outside-topic and writing-request lists; (6) "clear in profit".
- **Fix (2) of the fresh round: periods the parser could not read are read or flagged, never silently defaulted, 2026-10-16**
  (branch `feature/copilot-unread-periods`; no prompt change). **What a probe of about 50 wordings showed first (no model):**
  "ninety days" (the number table stopped at thirty), "sixty / forty-five days", "eighteen months", "8 quarters",
  "10 trading days", "past decade", "since 2024", "since Monday", "since earnings / the election / the IPO", "early / late / the end
  of August", "between March and June", "over the summer" and "all time" all fell to the past month with no word, and "when the
  year opened" and "a year and a half" were read wrongly (as a year ago, as one year). **Built, all in `ai/market.py`:**
  (1) "than / above / below / compared with / versus / relative to ... when the year (or 2026) opened, began, started, kicked off" is a
  year-to-date comparison, only with the stock or a bare company name as the subject ("Tesla's headcount larger than when the year
  began" is not). (2) A number reader for words up to 999 ("forty-five", "two hundred", "one hundred and twenty", "a hundred") and
  digits up to four places, feeding the "last / past N units" and "N units ago" paths; the old labels are kept ("ninety days" is
  "past 3 months"). (3) New units: quarters (91.5 days each), trading days and sessions (7/5 of a calendar day, and the label says
  "past 10 trading days (about 14 calendar days)"), and "past decade" (10 years). (4) "A year and a half", "two and a half years",
  "the past year and a half" are read exactly, with the half in the label. (5) "Since 2024" or "since the start of 2025" begins on
  January 1 of that year (this year is year to date; a year that has not come is flagged). (6) "Since Monday" begins on the most
  recent Monday before today (a week ago when today is one), with the date in the label; "since last Friday" stays flagged, since on
  a Friday it could mean either. (7) A named period that is still not read is flagged in code through the existing `Window.unmet`
  (the caution on the answer, and a sentence in the price source): "early / late / the end of / the middle of <month>", "between X and
  Y" and "from X to Y" with months or years, "over / during the summer, winter, spring, fall, holidays", "all-time", "since
  inception", "the last time", and the net for the rest, "since" and up to four words ("since the election"). It applies only when no
  window was read, so a read period is never flagged on top, and a question with no period at all stays silent. (8) The same caution
  now reaches a news question ("the stored headlines can't isolate it; the answer uses the last N days of headlines"); until now
  it needed a price source. (9) A window that reaches back more than a week before the first stored close (stored prices start on
  2021-10-13) carries a caution with that date; `MarketEvidence.starts` holds it. **Tests first:** 84 new in
  `tests/test_unread_periods.py` (all failing or guarded before), 1247 Python and 253 web tests pass; one old test changed on
  purpose (`test_no_caution_without_a_price_source` asserted that a headline-only answer gets no period caution, which is the gap
  item 8 closes) and its fake evidence class gained the new field. Twenty-three deliberate breakages of the new rules were each
  caught. **Evaluation, one clean A/B on one data snapshot:** a first baseline was thrown away because the 3pm refresh landed in the
  middle of it (prices for 10-16 arrived mid-run); old code and new code were then run back to back over all 234 cases (the 189
  older, the 35 of the fresh round, the 10 of fix (1)), 3 repeats: **old 631 of 702 (89.9%), new 636 of 702 (90.6%).** Gains: "when the
  year opened" 0 to 3 of 3 (the target), and three flaky cases that swing between runs ("kind or harsh", "dividends paid", "turned
  on"). Losses: "tanking premise" 1 to 0 of 3 and "close from last Friday" 1 to 0 of 3; both were A/B'd, 12 runs each, old against new:
  last Friday 3 of 12 against 1 of 12 and tanking premise 1 of 12 against 0 of 12, too few to tell from the usual swings, and neither
  touches code changed here ("tanking premise" is the day's headline tripping the speculation check, as recorded before), so I call
  them flaky, not caused by this; the pass rate on "last Friday" was low on both. **Fresh cases written for this step before it was
  run (12, `fy`, in wording unlike the tests; each period case also checks the date the answer starts from): 1 of 12 on the old
  code, 5 of 12 on the new.** I read every answer and checked every close it quoted against the database (they match): "sixty
  trading days", "ninety days" and "a year and a half" used the right windows and failed only my date patterns, which assumed the
  newest close was 10-15 and it became 10-16 during the session (so they were wrong by one day, my error, not changed after the
  run); "since the election" and "between April and July" were honest and carried the caution but quoted no close, which the case
  required; the news case listed headlines "since the vote" and carried the headlines caution; the two stretches ("above where it
  sat when the year opened", "how did AMD do in the first half of the year") still go to the filings and give wrong answers
  (a total-return table, and AMD's half-year revenue) with no caution. **Weak spots:** (1) Some loose reads were left as they were
  (they are read, not silent, but not exact): "since last year" is read as the past year, "since the beginning of the
  quarter" as 3 months, "last quarter" as 3 months. (2) "The last trading day" and "last day" are neither read nor flagged.
  (3) "Between April and July" is flagged but not read, so the model says the sources do not give that period although the prices are
  stored (the caution says why); reading "from X to Y" spans exactly would fix it. (4) The catch-all "since ..." also catches a
  non-time "since" ("since Apple is large") and quotes up to four words, but only a price or headline source shows it. (5) Trading
  days are a 7/5 approximation. (6) News windows are capped at 90 days and the caution does not say so. (7) The evaluation does not
  print cautions, so they are covered by unit tests, an end-to-end test, and the diagnostic runs above. **Still open from the fresh
  round:** (3) the "cash out" notice and a premise check; (4) follow-ups keeping their topic; (5) the outside-topic and
  writing-request lists; (6) "clear in profit".
- **Fix (3) of the fresh round: more everyday advice wordings, price claims and predictions reach the prices, and a check of the
  move a question assumes, 2026-10-16** (branch `feature/copilot-advice-premise`; no prompt change). **What a probe showed first
  (no model):** of 20 everyday ways to ask whether to buy, sell or hold only 4 carried the notice ("Is it time to cash out of
  Nvidia?", "Should I take profits on Tesla?", "Is it time to dump Nvidia?", "Would it be crazy to sell Microsoft now?" had none:
  "cash out", "take profits", "unload" were not trade words, and "is it time to", "would it be crazy to" were not decision cues), and
  "doubled", "tripled", "halved", "collapsed", "can only go up from here" and "reaches $650" all went to the filings, so no price
  source existed to check a claim against. **Built (all in `ai/market.py`, one line in `ai/copilot.py`):** (A) trade phrases
  (cash out, take profits, lock in gains, cut losses, bail out, unload, offload, ride it out, hang on to, go long or short, add X to the
  portfolio) and decision cues ("is it time to", "time to", "would it be (crazy / ok / smart) to", "crazy / foolish to", "a mistake
  to"), plus "a good point / level to enter" and "one to hold / own". Each company-side verb carries a lookahead for "its / their"
  ("Does Tesla say whether it will unload its Bitcoin?" gets no notice; the quantifiers are possessive so a shorter match cannot
  slip past it). (B) `PRICE_CLAIM_RE`: a capitalised company name followed by doubled / tripled / halved / collapsed / plummeted /
  exploded / cratered is a price question when a period or a stock word is present, unless an object follows ("doubled its
  dividend", "doubled down on", "doubled in size") or the subject is a common noun ("Revenue doubled", "Tesla's deliveries
  doubled"); `PRICE_PREDICTION_RE`: "can only go up / down from here" and "<Name> reaches $650" (not "$100 billion"). (C) `premise_cautions`:
  reads the move the question asserts or asks about ("doubled" needs about +80% or more, "tripled" +160%, "halved" -40% or less,
  "plunge 20%" within a factor of two or a point, "soared" or "crashed" at least 3% in the right direction) and compares it with the
  change over the window the price source shows; on a mismatch the answer carries "You mention that GOOGL “doubled”; the stored
  closes show -1.3% over the past month, so the question may assume a move that did not happen." It is silent for predictions and
  hypotheticals ("will soar", "could crash", "what if it doubles"), for several companies, for a period that could not be read, and for
  plain directions ("rose", "fell"), and gives at most one statement. **Tests first:** 117 new (`tests/test_advice_cash_out_wording.py`,
  `tests/test_price_claim_routing.py`, `tests/test_premise_check.py`); 1364 Python and 253 web tests pass. Thirty-one deliberate
  breakages of the new rules: seven were first missed. Five pointed at missing guard tests (a possessive "hang on to its", a
  "would it be ... to" cue that other cues hid, a lowercase non-company subject that was also in the exclusion list, a claim with
  no period or stock word, "can only go up" at the end of a question), now added; one ("unload" with a greedy quantifier) is an
  equivalent mutation because the trailing word boundary already stops it. **Evaluation, one data snapshot (no refresh in between):
  old code 648 of 738 (87.8%), new code 657 of 738 (89.0%) over 246 cases (the 189 older, the 35, 10 and 12 of the three earlier
  steps), 3 repeats.** Gains: "cash out" 0 to 3 of 3 and "reaches $650" 0 to 3 (the targets); "been performing", "kind or harsh",
  "payout ratio" and "since the election" moved up from flaky. Losses: "announcements" 3 to 2 of 3 (a figure the numbers check
  flagged in one run, 16), "turned on" 3 to 2 of 3 (it swings), and "close from last Friday" 1 to 0 of 3 (flaky for four rounds now,
  with a low pass rate on old and new code); none touches code changed here. **The fresh round's 35: 67 to 72 of 105.** **Fresh cases
  written for this step before it was run (12, `fz`): 3 of 12 on the old code, 8 of 12 on the new.** I read every answer: "Nvidia
  shares triple over the past quarter" and "Amazon plunged 25% last week" were corrected from the stored closes (+3.24%, -4.74%, both
  matching the database) with the caution attached; the two true-claim guards (AMD did fall 17% in two weeks, Microsoft did rise 32%
  in three months) and the company-side guard ("Does Microsoft intend to cash out of its Activision stake?") got no caution;
  "bail out" and "thinking of unloading" now carry the advice notice. The four misses: "Would you ride out a dip in Alphabet?"
  (the rule knows "ride it out" but not "ride out"), and two stretches ("sensible to cash out", "the kind of company to hold") get no
  notice, and "Does anyone think Alphabet reaches $400 this year?" is routed and declined correctly but the numbers check flags the
  question's own 400 in an answer that restates it. **What I checked beyond the cases:** the real cautions on three runs ("Google
  doubled this month" gets the premise statement, "Is it time to cash out of Nvidia?" gets the notice, "AMD plunge over two
  weeks" gets nothing); one inaccuracy found along the way: the new "no news" caution said "written from filings only" even when the answer
  used prices, so it now says "this answer did not use them" (the older "no price" caution still says "filings only"). **Weak spots:**
  (1) "Google doubled this month. What drove it?" is routed to prices only, because "what drove it" is not a cause word, so the
  model has no headlines; the premise statement is attached, but the answer says "no headlines provided" (the case's expectation of
  headline plus price still fails, and so does the older "What caused Nvidia's last big drop?"; adding "drove / caused / triggered" as
  cause words is the obvious next rule, not done here). (2) The premise check covers multiples, "N%" and strong verbs only; plain
  "rose" and "fell" are not checked, thresholds (80%, 3%, a factor of two) are judgment, a claim with no period and no stock word
  ("Did Tesla collapse?", "Isn't Tesla about to collapse?") is not routed, and a lowercase company name misses the claim rule.
  (3) The advice rules are keyword lists again; the next everyday wording will miss, as in every round so far, which is the case for the
  model-based routing experiment. (4) The content of advice-adjacent answers is unchanged: after the notice, "cash out of Nvidia" was
  answered with a one-sided list (the stock grew from $100 to $1,448.75), and nothing in code limits it. (5) The "no price" caution still
  says "filings only". (6) The evaluation does not print cautions. **Still open from the fresh round:** (4) follow-ups keeping their topic; (5)
  the outside-topic and writing-request lists; (6) "clear in profit".
- **Cause words: "what drove / caused / triggered it" bring the headlines, 2026-10-16** (branch `feature/copilot-cause-words`; the known
  gap from fix (3); no prompt change). **What a probe showed first (no model):** of 17 ways to ask what moved a stock, only "why" ones
  got headlines (2 of 17). The other 15 reached the prices with none ("What drove it?", "What caused Nvidia's last big drop?", "What
  triggered the selloff in Tesla stock?", "How come Tesla stock fell?", "What made Apple shares fall?"), and 4 did not reach the prices at
  all because the move is a noun ("What sparked Amazon's jump this month?", "What's responsible for Nvidia's slide?", "the story behind
  Amazon's jump", "the move in Microsoft stock"). Cause words only matter on a price question, so business questions that share them
  ("What drove Apple's services revenue growth?") were never affected. **Built, in `ai/market.py`:** (1) `CAUSE_RE` adds "what drove /
  caused / triggered / sparked / prompted / pushed / made / led to / explains", "how come", "what's responsible for", "the story / cause /
  reason behind", and "drove / caused / triggered / sparked / prompted it, that, this, the move / drop / jump ...". (2)
  `PRICE_MOVE_NOUN_RE`: with a cause word, "<Company>'s jump / slide / swoon" (a capitalised name, a period or a stock word, and not
  followed by "in <metric>": "Nvidia's slide in gross margin" is not the stock) and "the move / jump / slide / selloff / plunge /
  rally / surge in <Company> stock" are price questions. Only the nouns no price rule knew are named. **Tests first:** 38 new
  (`tests/test_cause_words.py`), 21 failing before; 1402 Python and 253 web tests pass. Thirteen deliberate breakages: three were first
  missed (a "what triggered" case whose object another alternative also covered, a lowercase subject, and a mutation string that
  did not match), tests added, all caught. **Evaluation, one data snapshot:** a first new-code run crashed on a model timeout
  because two full runs and extra runs shared Ollama (not a code problem; the runs were redone one at a time). **Old code 675 of 774
  (87.2%), new code 681 of 774 (88.0%) over 258 cases, 3 repeats.** The target moved: "What caused Nvidia's last big drop?" (failing for
  five rounds) went 0 to 3 of 3; "Google doubled this month. What drove it?" now gets prices and headlines and its answer corrects the
  premise ("fell, not doubled") with the headlines as context, though the case still fails because it demands a phrase about the
  cause. Seven other cases moved up from flaky and "press coverage" went 2 to 0 of 3 and "can only go down" 3 to 1 of 3; both were A/B'd,
  12 runs each: press coverage 0 of 12 on old and on new code (the day's headlines), can only go down 11 of 12 against 12 of 12, so
  neither is caused by this. **Fresh cases written before running (8, `fc`): 1 of 8 on the old code, 7 of 8 on the new.** I read every
  answer: all five cause questions get the price move plus headlines and none claims a cause (they say the data cannot show one and give
  the headlines as context); "Tesla stock jumped 30% this week. What caused that?" got the premise statement and the answer said it fell
  7%, not jumped; the Tesla energy-storage guard stayed on the filings. The one miss is the stretch "What lies behind Nvidia's jump over the
  past quarter?" (answered from the filings as if revenue growth were the cause of a stock jump). **Weak spots:** (1) "behind" with
  "lies", "set off", "got X moving" and similar are not cause words; the next wording will miss. (2) "drop", "rally", "surge", "crash",
  "spike" were price words already, everywhere, so "What caused the drop in Apple's revenue this year?" and "the crash test results for the
  Cybertruck" still go to the prices: a pre-existing misroute that this step did not touch and that a bare price word will keep
  causing. (3) A bare "<Company> jumped 30%" with no stock word is not a price question (only the noun forms are). (4) The evaluation
  does not print cautions. **Still open from the fresh round:** (4) follow-ups keeping their topic; (5) the outside-topic and
  writing-request lists; (6) "clear in profit".
- **Fix (4) of the fresh round: follow-ups keep their topic even when the model's rewrite loses or invents it, 2026-10-16** (branch
  `feature/copilot-follow-up-topics`; no prompt change; merged as PR #41 on 2026-10-17). **What a no-model probe showed first** (a fake
  rewrite step over the real database, with the rewrites the model might give): "Switch over to Microsoft.", "Skip to Nvidia." and "Give
  me the number for Apple too." are not bare switches (`switch`, `skip`, `to`, `number` were not filler words), so the topic was never
  carried; "And did Nvidia do better than that?" was already rebuilt into the AMD price question when the model returned it unchanged, but
  when the model wrote "Did Nvidia do better than AMD?" (both companies, no stock) the rewrite was trusted and went to the filings (the
  Data Center revenue answer); "Is Tesla's list longer than that?" was not a bare comparison (`longer`, `list` unknown), so only a note
  "(comparing NVDA and TSLA)" was added and the topic was lost; "Summarize what the companies say about tariffs." was handed to the model,
  which named NVDA and AMD though AMD never appeared in the conversation. The baseline run confirmed each (the model returned "Skip to
  Nvidia" and "Give me the number" unchanged, rewrote the Tesla list as "...longer than NVIDIA's?", and invented AMD). **The decision
  behind the main change:** a question that is only a company switch or only a comparison names no topic, so any topic in the model's
  rewrite is the earlier one reworded or one it invented. The earlier *question* (never its answer), rebuilt with the new company, now wins
  over the rewrite whenever it can be rebuilt (the existing `carry_topic` and `carry_comparison`); when it cannot (two companies in the
  earlier question, nothing to swap in) the rewrite is still used. This reverses one earlier rule on purpose: "a rewrite that kept both
  companies is trusted" (its test now expects the rebuilt question, which differs by a comma). **Built, in `ai/copilot.py`:** (1)
  `SWITCH_PHRASE_RE`: switch / skip / move on / jump / go / hop / cut / turn / shift / flip / pivot (over, on, ahead...) "to", "over to",
  "onto" count as a switch; generic nouns (number, figure, one, question, idea, thing, approach, treatment) are switch filler. (2)
  `carry_topic` now runs whatever the rewrite said (it used to run only when the rewrite returned the question unchanged). (3) A
  comparison with no topic of its own is rebuilt even when the rewrite kept both companies; its filler list gained longer / shorter, list /
  number / count / total / amount / figure, say / mention / anything / something / alike / comparable, has / have / had, and fare /
  perform. (4) `SIMILAR_RE`: "anything / something similar (alike, comparable, like that)", or "similar / alike / likewise" ending the
  question, is both a comparison and a reference back, so "Does Amazon say anything similar?" searches Microsoft too and keeps the risks
  topic ("similar" before a noun, "a similar number of", is not it). **That answers the open question** from the fresh round: yes,
  searching the earlier company is right, because "similar" can only be judged against what it said; the case's expectation was changed
  from {AMZN} to {AMZN, MSFT} (and its answer now starts with Microsoft's risks, then Amazon's). (5) `ALL_COMPANIES_RE`: "the companies",
  "all (of) the companies", "every / each / any company", "which company / companies", "across companies", "companies'" with no company
  named and no reference word is used as written, with no companies. **Tests first:** 110 new in
  `tests/test_copilot_follow_up_topics.py` (37 of the first 56 failed before the change; 11 of the 15 added later for the fresh cases'
  words failed before their change), one old test changed; 1512 Python and 253 web tests pass. About 80 deliberate breakages of the new rules: 14 were first
  missed (the "similar" cues passed through each other, the filler words were never isolated, the all-companies guards had no test, the
  "no comparing note when nothing was lost" line), each pointed at a missing test, now added; one remaining miss was a word that was
  already in the filler list. **Evaluation, one data snapshot (no refresh in between), 3 repeats:** old code, then new code, over the 266
  cases (258 + the 8 cause-word cases moved into `CASES`): **market 707 of 798 (88.6%) to 711 of 798 (89.1%); follow-up resolution 39 of
  46 to 46 of 46** (one case, "more people than", had a checker artifact: the topic word "employees" is not in "employ more people than
  Apple"; its word is now "employ", and by inspection the old code passes it, so 40 of 46 to 46 of 46). Gains: "did Nvidia do better"
  0 to 3 of 3, "switch over" 0 to 3 of 3, "been performing" and "why did it move" flaky cases up; the resolve cases "skip to", "number for
  too", "longer list", "all companies" and two Understood-as-employee-count checker cases now pass every run. Drops: "crashing premise"
  3 to 2, "last Friday" 2 to 0, "press coverage" 1 to 0; none has a history, and every new rule needs one, so none can come from this
  change; A/B, 12 runs each, old against new: 12 of 12 against 12 of 12, 6 of 12 against 8 of 12, 0 of 12 against 0 of 12. I read the
  answers: the AMD and Nvidia answer quotes both stored moves (+4.87% and +0.92%) with their closes, the Microsoft switch answer lists
  Microsoft's headlines, the Amazon answer compares both companies' risks, and the other 19 history cases read the same as before.
  **Fresh cases written before the run (10: 5 market `ff follow`, 5 resolve `ff resolve`, in wording unlike the tests; an overlap script
  found a highest similarity of 0.69 against any quoted string in the repo other than the cases' own names, after three were reworded
  for being close to a failing case's template): fair score 4 of 10 on the new code against 3 of 10 on the old (market 2 of 5 against 1
  of 5, resolve 2 of 5 against 2 of 5).** The misses were wordings the rules did not know: "fare better" (answered from the filings),
  "Over to Nvidia, same idea" (`idea`), "Pivot to Amazon" (`pivot`), "the same treatment" (`treatment`), "roster ... more items than
  that", and "rosier by comparison" (no comparison word). I then added the words the first four needed (with tests), which makes those
  cases tuning material: 8 of 10 afterwards, but that is not a fair score. **Weak spots:** (1) The fix is again word lists: the next
  switch or comparison wording will miss, which is the case for the model-based routing experiment. The two fresh misses left are
  "Does Amazon's roster run to more items than that?" (a comparison with words not on the list, so the model's rewrite is kept and it
  lost the topic) and "Was Tesla's month any rosier by comparison?" (no `than`; answered "the question is unclear" and only Tesla). (2)
  Code wins whenever the earlier question can be rebuilt, so a model rewrite that was actually better is overridden for a bare switch or
  comparison; no case showed a loss, but "Understood as" is the only place the user can see it. (3) "The companies" after a turn about
  two companies is read as all of them, not those two ("the two companies" is not matched). (4) "Similar" fires on any question with
  a new company and "anything similar" in it, including one with its own topic. (5) "Over to Nvidia, same idea" now reaches the
  headlines, but the answer lists headlines that are not about Nvidia (headline relevance, unchanged by this step). (6) The evaluation
  does not print cautions. **Still open from the fresh round:** (5) the outside-topic and writing-request lists; (6) "clear in profit".
  Then the decision on the model-based routing experiment.
- **Fix (5) of the fresh round: questions the app cannot answer are declined in code, 2026-10-17** (branch
  `feature/copilot-outside-topics`; no prompt change; merged as PR #42 on 2026-10-17). **What a no-model probe of 90 questions showed
  first** (it follows the order in `answer_question`): of 26 off-list company questions (Lululemon, Etsy, FedEx, Chipotle, Eli Lilly...)
  none was caught by the company list, 4 got the generic "tell me which company" notice and 22 reached the filings answer; of 25 asset or
  topic questions (gas prices, diesel, coffee, "the economy", Tether, REITs, the yuan...) 1 got the scope message, 8 the generic notice and
  16 reached the filings; of 15 writing or task requests with no company ("Give me a haiku about spring", "Draft an email to my boss",
  "Write a python function...") 1 was declined; and of 12 writing requests that **name a tracked company** ("Write a LinkedIn post about
  Apple's earnings") none was, because the scope rule only runs when no tracked company is named. **Built, in `ai/market.py` and
  `ai/copilot.py`:** (1) `unknown_name`: in a question that names no tracked company, a capitalised name (or run of up to four
  capitalised words) that appears as a whole word, in any case, in no stored filing and no stored headline is declined by name ("I can't
  find "Ulta Beauty" in anything stored here..."), before the model is asked. A word is skipped when it is a function word, a month or
  weekday, an acronym like SEC or EPS, the lone first word of a sentence (unless it is a possessive: "Peloton's risks"), or lowercase. The
  stored text is the vocabulary, so it needs no list, and it is cheap (about 35 ms: 6.7 MB of filings and the headlines). A prototype first
  flagged 16 of 26 off-list names and 1 of 38 evaluation questions with no tracked company (a correct decline); the 10 misses were names
  that do occur in stored text (Nintendo, Chipotle, General Motors, UPS...), so (2) the company list also grew from 70 to 183 names (not
  the ambiguous ones: Target, Visa, Ford, Shell, Block...; words that are also ordinary, such as UPS, Puma, Intuit, Workday, need the
  capital). (3) The filings cue that vetoes the scope rules was split: for a named or unknown company only "companies", "which",
  "filings", "10-K", "according to", "exposure", "each", "every", "across"... veto; "mention", "disclose" and "discuss" no longer do,
  because "Does Nintendo disclose anything about piracy?" is about Nintendo. The asset rule keeps the broad cue. (4) `OUTSIDE_ASSET_RE`
  grew: gas, gasoline, diesel, jet fuel and fuel prices, "at the pump", coffee, corn, soybeans, sugar, cattle, cotton, lumber, cocoa, the
  VIX, the ten-year yield, "the economy", "the stock market", REITs, index funds and ETFs, meme stocks, student loans, a housing bubble,
  consumer confidence and sentiment, retail sales, the labor market, jobs numbers and payrolls, Tether, USDC and stablecoins, the yuan,
  yen, peso and rupee, a government shutdown, the debt ceiling. Indexes (S&P 500, Dow, Nasdaq) keep their own generic notice, which tests
  expect. (5) `writing_request`: write, draft, compose, create, make, generate, prepare, craft, produce, pen, whip up, put together, come
  up with, plus up to three words (none a preposition) and an email, letter, memo, message, tweet, caption, script, slides, deck,
  presentation, resume, press release, newsletter, toast, essay, speech, poem, song, haiku, limerick, joke, rap, riddle, social post or
  thank-you note; "give / get / show me a ..." the same; "email my boss ...", "text my friend ..."; code in python, javascript or SQL;
  "translate"; "sing me a ...". It is checked on the user's words and on the rewrite, **even with a tracked company named or chosen**, and
  declines with a fixed message ("it doesn't write emails, posts, poems, code, or other documents... write the message yourself"). A
  summary, list, table, comparison or overview is research and is not on the list ("Write a summary of Apple's legal proceedings",
  "Summarize Nvidia's risks in three bullets" are answered). **Two older expectations changed on purpose:** "How is the stock market
  doing this week?" and the eval case "the economy" used to get only the generic notice; they now get the specific "outside what this app
  covers" message first (both accept either). **Tests first:** about 230 new, mostly in `tests/test_outside_unknown_names.py` (1742 Python
  and 253 web tests pass). The stored-text tests insert their own filing and headline and no filing chunks, because chunks inserted and
  deleted by many tests leave dead vector-index entries. About 130 deliberate breakages of the new rules (every alternative of the asset,
  verb and thing lists, every preposition, the cue splits, the word-boundary and case handling, the stop words, the list entries, and the
  wiring in `answer_question`): the first pass **missed 46** (an alternative with no question of its own, a stop word nothing tested, the
  rewrite-only and question-only paths, the guard against a thing inside a longer word such as "deckhand"), each now has a test; five
  remained: one was a duplicate alternative (`slide deck`, removed), one a mutation that hit a different copy of a word, and three needed
  one more question (added). A helper that checks that every name on the company list is declined by name was added because deleting an
  entry would not otherwise be noticed. **Evaluation, one data snapshot, 3 repeats, 271 cases:** old code 726 of 813 (89.3%), new code 730
  of 813 (89.8%); follow-up resolution 50 of 51 on both (the one miss is the "roster" stretch of fix (4)). The three targets that failed
  at 0 of 3 for two rounds (gas prices, Chipotle, "draft an email") went to 3 of 3. Five cases dropped: "reaches $650" 3 to 0, "stock
  doubled" 2 to 1, "since the election" 3 to 1, "been performing" 3 to 2, "sentiment" 3 to 1; all five name a tracked company or none,
  and none is touched by the new rules (a scan of all 333 distinct evaluation questions shows the scope, unknown-name and writing rules
  fire on 22, every one a question meant to be declined). A/B, 12 runs each, old against new: 12 of 12 against 12 of 12, 4 of 12 against 5 of 12, 11 against 12, 2 against 2, and
  "stock doubled" 8 of 12 against 4 of 12, which I extended by 40 more runs: 33 of 44 old, 31 of 44 new. All noise. **Fresh cases written
  before the run (11, `fw`, with company names on no list in the code; the highest similarity to anything in the repo was 0.65): fair
  score 8 of 11 on the new code against 2 of 11 on the old (24 of 33 against 6 of 33)**; the old code's two passes are the guards. I read
  every answer: the four unknown companies, "Baltic Dry Index" and the Slack message are declined with the right message and no model
  call. Misses: "How much are eggs costing these days?" and "What is uranium trading at?" (assets not on the list, 0 of 3) and "Write up
  a one-pager on Amazon's debt for my boss" (answered with a summary of Amazon's debt commitments, 0 of 3). **A false-positive spot check
  written after the rules (38 ordinary research questions that name no tracked company, not tuned on):** the new unknown-name rule
  declined 3 ("Are there antitrust cases in Brussels?", "Is the Pentagon a customer?", "What is Llama?"), 8%; two more were declined
  by older rules ("What is the Inflation Reduction Act?", "How is Intel Foundry doing?"). All three are honest (the name is in nothing
  stored) but not helpful, and the first two are not companies, so the message was reworded to not call the name a company ("so I can't
  answer a question about it... if it is a company, use the Add a company box"). **Weak spots:** (1) A place, a person or a product that
  the stored text never uses is declined; the spot check puts it at about 1 in 12 for questions with no tracked company, and a cross-company
  question with a filings cue is never declined. (2) A name that does occur in some stored headline or filing (a competitor named
  in a filing, PepsiCo in an Nvidia headline) passes as known and reaches the filings answer, the old behavior; only the list catches
  those. (3) The first word of a question is not looked at unless it is a possessive ("Peloton?" alone is not declined). (4) The asset list
  is finite: eggs and uranium miss; the writing list is finite: "one-pager", "sonnet", "thread" miss. (5) General knowledge and
  arithmetic ("What is the capital of France?", "What is 17 times 23?") are still left to the relevance gate; no finite list covers
  them. (6) The narrower cue lets a list company through the veto for "mention / disclose / discuss", so "Which companies mention
  Chipotle?" is still answered (it has "which") but "Does anyone mention Chipotle?" is declined. (7) Three full-suite runs failed one or
  two vector-search tests (`test_search`, `test_copilot`) while a background evaluation shared the database; they pass alone and the suite
  passed in full once the evaluation had finished, the known dead-index flakiness, not this change. (8) The evaluation does not print cautions.
  **Still open from the fresh round:** (6) "clear in profit". Then the decision on the model-based routing experiment, which this
  step's weak spots (1) to (5) support: every list here will miss the next wording.
- **Model-based routing experiment, 2026-10-17** (branch `feature/copilot-model-router`; no change to `SYSTEM_PROMPT` or the rewrite
  prompt; merged as PR #43 on 2026-10-17 with the router off by default). **Why:** six fixes in a row added keyword rules and every fresh round missed on the
  next wording (46%, then 65%, 72% before). **Baseline first, on current `main`, before any router existed:** 39 new questions in
  everyday wording across every route (prices with a period, news, sentiment, the stored figures, filings, outside topics, advice,
  predictions, a false premise, follow-ups), 3 repeats: **18 of 39 on the first pass, 52 of 117 (44%)**; prices 2 of 7, news 1 of 5,
  figures 5 of 7, filings 4 of 4, refusals and traps 6 of 11, follow-ups 1 of 5. I read every answer: **17 of the 21 misses never reached
  the right data** (the question fell through to the filings, or to "I couldn't find anything"); the other four were extra price data
  on an EPS question, a missed buy/sell notice, a dividend yield worded without "yield", and an expectation I would not defend. A
  second set of 38 was written at the same time, **sealed** (`--sealed`, run once, never tuned on).
  **Design (`ai/router.py`, off unless `COPILOT_ROUTER=model` or `answer_question(..., router=True)`):** when the keyword rules find
  no specific route (the question would go to the filings only), the local model (`qwen3`, thinking off, temperature 0.1) is asked one
  question about the standalone question alone: a JSON reply constrained by a schema (category research / outside / writing; price,
  news, sentiment, figures from pe / market_value / eps / shares / profit / margin / revenue, filings, advice). The model never names a
  company, never writes an answer and sees no history or earlier answer; companies, periods, figures, the numbers checks and every
  caution stay in Python. A failure of any kind (offline, bad JSON, a wrong type) leaves the keyword route, so the router cannot make an
  answer fail. It only adds: the advice flag is the union of keywords and model, and a verdict that chooses nothing leaves the keyword
  intent alone. **What iterating on the 39 showed:** the first prompt scored 59 of 117 (the model put "general" into the figures for
  everything and turned filings questions into figure questions); removing that option and tightening the prompt gave 80 to 85 of
  117. **Showing the model the previous question** (so "do the same for Google" has a topic) was built, tested and **removed**: 80 of
  117, no better, and it stretched the history rule. Of the 12 development cases that still fail, most are not router problems (the
  keyword route itself, the follow-up rewrite having lost the topic, or an expectation).
  **The regression run found what the keywords had learned the hard way.** On the 282 older cases the first router version scored the
  same total as the keywords (755 of 846 both) while winning 9 cases and losing 8, because it overrode routes the keyword rules send to
  the filings on purpose: "revenue in its latest 10-K", "total revenue in its annual report", "dividends paid", "dividend payout
  ratio", "What drove Tesla's jump in energy storage revenue", and "Apple's iPhone sales" (a product line, not the twelve-month total;
  12 of 12 with the router off against 0 of 12 with it on in an A/B). Telling the model so in the prompt did not hold (it kept returning revenue for a 10-K question, and
  called dividend questions "outside"). **Guards in code instead, each with a question of its own:** the model is not asked when the
  question names a filing, a quarter or a segment, asks why, mentions dividends or a payout, or contains "sales" that the keyword rules did
  not read as the company's total (`deliberately_filings`); it may add headlines only when the question has a news or why-the-stock-moved
  word (`NEWS_CUE_RE`, only ever removes); and "the latest / most recent four quarters" is the twelve-month stretch like "the last four
  quarters" (a keyword fix, `TWELVE_MONTHS_AS_QUARTERS_RE`).
  **Evaluation on the final code (3 repeats, one data snapshot): the 282 older cases 761 of 846 with the router off, 769 with it on
  (89.9% to 90.9%)**; the development 39: 52 to 83 of 117 (44% to 71%). Eight older cases got worse in some run; A/B, 12 runs each, off
  against on: "iPhone sales" fixed by the sales guard (6 of 6 with the router on after it), "much chatter today" 0 of 12 against 0 of
  12, "buy back, quarter named" 12 of 12 against 12 of 12, "tanking premise" is the day's headline tripping the speculation check, as
  before; the rest are the usual swings. Gains: gas, egg prices and a one-pager request, "take in per year", "make in a year", "caused
  to fall", "announcements". **The sealed test, run once (38 cases, 3 repeats): keywords 78 of 114 (68%), router 93 of 114 (82%); first
  pass 26 against 31 of 38; five cases better, none worse.** Then I looked at the answers and found two things the score had hidden,
  which I fix and say plainly make the sealed set a second-look set from here on: **(1) false declines.** The model's "outside" verdict
  declined 13 of about 38 ordinary research questions that name no tracked company ("What is CUDA?", "What is Azure?", "How big is the
  Cybertruck order book?", "What did Jensen Huang say about Blackwell?"); filings can answer some of those. **(2)** "Could Apple be a
  dependable long-term holding?" was declined with the message "it doesn't write emails". **Fixes:** the "outside" verdict is now only a
  hint (it never stops a search; it swaps in the clearer "outside what this app covers" message only if nothing relevant is found),
  and the "writing" verdict declines only a question that has a writing word in it (`WRITING_CUE_RE`). On the final code: **sealed 90
  of 114 (79%) against 78 for the keywords, 30 against 26 of 38 on the first pass, four cases better, none worse (the "Bank of Canada"
  gain went with the up-front outside decline); the 282 cases 769 against 761; the false-decline probe declined none of 38 ordinary
  questions.** Two of those 38 were rerouted to a market route with no company named ("Does Prime matter much?", "What does Wall Street
  think of AI spending?"), so they now get the "tell me which company" notice instead of a filings attempt. **Merge rule (agreed before
  the results), checked: (1) the sealed set improves by at least 4 of 38 and holds over 3 repeats: yes, 4 (5 in the first version);
  (2) the 282 older cases lose no more than noise (4 of 846): they gained 8; (3) no legitimate research question wrongly declined or
  rerouted: after the two fixes, none in the probes or the sealed guards (filings 5 of 5), with the two rerouted questions above as
  the cost; (4) added time about one second or less: the average per case was 1.6 s against 1.5 s on the 282 and 1.7 against 1.3 on the
  sealed set (only the questions that fall through pay for the extra call).** **Tests:** 296 new (`tests/test_router.py`, a fake model,
  and one keyword wording test); 2038 Python and 253 web tests pass. Breaking each router rule on purpose (the parser, when to ask,
  every part of applying a route, the advice union, the switch, the guards, every news and writing cue word, the wiring in
  `answer_question`) was caught every time after tests were added for what the first passes missed (6 router rules, then 3 guard
  lines, then about 55 cue words that had no question of their own); one mutation was unreachable and the code was simplified instead.
  **Weak spots:** (1) The router is asked only when the keywords find no route, so it fixes a question that falls through, not one the
  keywords route wrongly ("Has Apple been climbing or sliding lately?" still goes to headlines). (2) Follow-ups gain little: when the
  rewrite step loses the topic ("do the matching calculation for Google") the router cannot recover it. (3) The guards that make it
  safe are keyword lists again (the deliberate-filings cues, the news cue, the writing cue); they only ever remove what the model adds,
  but they are lists. (4) The model is over-eager with headlines and sentiment (it adds them to price questions, which fails a case that
  expects price only) and sometimes returns everything for an advice question. (5) It depends on the local model for one extra call on
  fall-through questions; a failure falls back to the keywords, a swing between runs is possible, and a different model needs the
  prompt re-checked. (6) The sealed set is no longer sealed: a fair next score needs a new set. (7) Nothing shows the user that the
  router was used; "Understood as" is unchanged. (8) The development 39 and the 38 sealed cases are in `CASES` now (359 in all).
  **Recommendation:** merge, and turn it on by default with `COPILOT_ROUTER=off` as the switch back, because the rule is met; this
  is the owner's call (it adds a model call to every question the keywords send to the filings by default, and changes what some questions retrieve).
- **Router visibility: the answer says when the local model chose the evidence, 2026-10-17** (branch
  `feature/router-visibility`; no change to `SYSTEM_PROMPT`, the rewrite prompt, the router prompt or any routing rule; the default is
  unchanged: the router is still off). **Why:** weak spot (7) of the routing experiment: with the router on, a question could retrieve
  different data than the keyword rules would have chosen and nothing said so. **Decision: not in "Understood as".** That line means "I
  rewrote your follow-up" (the web tests assert it is absent otherwise), and the router does not rewrite anything, so mixing the two would
  make both unclear. **Built:** `Answer.model_route` (`ai/copilot.py`), the kinds of evidence the model chose, in the API's order (price,
  fundamentals, sentiment, headline, filing); `ai/router.py` `evidence_kinds` and `changed_kinds`. It is empty when the router was off,
  not asked (the keywords found a route, or a guard held it back, or code had already declined the question), failed, or chose the same
  kinds as the keyword route (filings only is the keyword default, so "the model chose the filings" says nothing). It is the set after
  the code-side guards, so a news verdict that had no news word in the question is not reported. The advice flag and which figures were
  chosen are not kinds: the buy/sell notice and the figures themselves show those. A refusal carries it too: a question the model sent to
  the prices with no company named gets "tell me which company", and the note says why. **API:** `model_route` on `POST /api/copilot`
  (a required list, `[]` when empty; types regenerated). **Web:** a muted line under "Looked at ..." ("The app's keyword rules found no
  specific kind of data for this question, so the local model chose: prices and headlines."), shown only when the list is not empty; it
  says what the model chose, and "Looked at" still says what the answer was written from. Answers saved in the browser before this change
  load with an empty list; a saved value that is not a list of known kinds drops the saved exchange like any other damaged field (`null`
  counts as damage, not as old). The command line prints "chosen by the local model, not the keyword rules: ...". **Tests first:** 29
  Python (`tests/test_router_visibility.py`: the function for every kind, the order, every case where nothing should be said, the
  refusal, the command line; and two in `tests/test_api.py`) and 7 web; 2067 Python and 260 web tests pass. **Deliberate breakages: 26**
  (the comparison, each kind's mapping, the order, the wiring in `answer_question` and in `refuse`, the API field, every web condition,
  the validation and the upgrade of old saves) plus the command-line line: all caught. **In a real browser** (live data, router on):
  "Has Apple pulled back from its high this year?" showed "Looked at prices for AAPL" and the note; "How has Microsoft stock done this
  month?" (keywords) showed no note; saved answers with the field removed still loaded after a reload; the note wrapped at 375 px with no
  horizontal overflow. Not checked in a browser: light mode, and a refusal with a note (tests only). **Weak spots:** (1) The note is shown
  only when the model's kinds differ from the keyword route's, so a question the model looked at and left on the filings looks the same
  as one it never saw. (2) It reports the model's choice, not whether the model was right. (3) The wording is fixed and long for five
  kinds. (4) The default is still off: turning it on is the owner's call, to be made at the end of this branch.
- **Router second look, step 1: two new question sets, nothing run yet, 2026-10-17** (branch `feature/router-second-look`, cut from
  `feature/router-visibility`; no change to any rule, prompt or the router). **Question being prepared for:** the router is asked only
  when the keywords find no route, so a question the keywords route to something specific but wrong is never put to the model (weak
  spot 1 of the routing experiment), and a follow-up whose rewrite lost its topic cannot be recovered (weak spot 2). Measuring either
  needs questions the keywords have not been tuned on, because on the 322 old cases without history the keywords already match the
  expected evidence for 248 and only 5 are wrong-and-never-asked (an offline, no-model count: the old cases were tuned until they
  passed, so they cannot show the problem). **The order mattered:** the sealed set was written first, before the keyword word lists
  were opened for this work, and was not screened against the rules (some will route right, some wrong); the development set was
  written second, with the lists open, aimed at the structural ways the rules go wrong. **Sealed set, `SEALED_ROUND_TWO` (41 cases,
  `s2`, run with `--sealed`, not in `CASES`):** 7 prices, 6 news and mood, 6 stored figures, 6 filings (guards: legitimate research
  that must not be declined or rerouted), 10 traps (outside topics, writing, an unknown name, advice, a prediction, a false premise, an
  unstored ratio) and 6 follow-ups. **Development set, `ROUND_SL` (37 cases, `sl`, in `CASES`):** 3 price questions that carry a news
  word ("lately"), 9 filings questions that carry a price or mood word ("falling demand", "closed", "volatility", "optimistic",
  "bullish", "mood"), 5 money wordings, 2 cause wordings the rules may not know, 2 news wordings, 8 controls the keywords should
  already route right, and 8 follow-ups ("Run the same numbers for Microsoft", "Lay Amazon alongside it"). **Overlap check by script**
  (every string literal in every `.py` file, the web tests' questions, and the two new sets against each other): the first pass found
  8 near-copies of older cases or test strings (including one sealed question that was almost word for word an older case), all
  reworded; the highest remaining similarity is 0.80 (a shared template, "What was X's ... over the last twelve months?"), and the
  sealed and development sets are at most 0.65 from each other. This is a looser measure than the one used for the earlier sets, so
  the numbers are not comparable. **What the keywords do on the development set, offline with no model (29 cases without history):
  12 right, 4 wrong but the router would be asked, 13 wrong and never asked.** The 13 are the weak spot made concrete: 3 price
  questions routed to headlines because of "lately"; 6 filings questions routed to prices because of "falling", "closed", "trading",
  "volatility", "fell", "rising"; 3 filings questions routed to headlines and mood because of "optimistic", "bullish", "mood"; and
  "accounts for the tumble" (prices without the headlines a cause question brings). **What this says about the design:** the router
  today only adds (the advice flag, headlines behind a news word), and a fix for 12 of these 13 has to REMOVE evidence the keywords chose
  (prices or mood from a filings question, headlines from a price question; only the cause case needs an addition), so a second look needs a rule for when the model may override, which is a new kind of risk and must
  be measured, not assumed. **Not done:** nothing has been run with a model; the shadow-mode measurement is the next step.
  **Step 2, the shadow script is built, not yet run (`ai/eval_router_shadow.py`, `tests/test_eval_router_shadow.py`).** It asks the
  router question only (no answer, no search, no change to the app) for the 302 research cases that have no follow-up and expect no
  refusal made in code, `--repeat` times, and saves the router's raw reply per case (`--run --out FILE`); five policies are then scored
  offline from the recording, so a changed rule is re-scored without the model (`--score FILE`). When the keywords found nothing the
  model decides, as now, in every policy; the policies differ only when the keywords chose something specific: `today` (never second-guess),
  `replace` (the model overrules), `replace-to-filings` (overrule only to send it to the filings), `intersect-else-router` and
  `intersect-else-keywords` (keep only what both chose; if nothing is shared, the model or the keywords). The existing guards hold in
  every policy (a named filing, a quarter, "why", dividends, "sales", an unstored ratio, advice, a failed call, and the model's "outside"
  and "writing" verdicts all keep the keyword route). A case passes when the kinds of evidence equal the expected ones, the evaluation's
  own primary check; no answer is read. There is no option for the sealed set and any sealed case is dropped. **Found while building:** one
  older case name ("filings only") is used twice and scores are keyed by name, so a repeat silently dropped a case and shifted the group
  totals by one (the plan showed 28 development cases instead of 29); repeated names now get " (2)". **Offline, no model:** the keywords
  alone get 12 of 29 development cases and 248 of 273 older ones. **Tests:** 66, with a fake model, plus 33 deliberate breakages, all
  caught except one rewrite that gives the same list (an intersection written in the other order). The full suite passed (2133); one run
  failed `test_search.py::test_latest_only_drops_older_filings_of_the_same_form` with nothing else using the database, and it passed alone
  three times and in the next full run, which looks like the known dead-index flakiness but was not investigated.
  **Step 2, the shadow run, 2026-10-17 (302 cases x 3, the real model, 554 s, 0 router failures; the recording is not kept in the repo).**
  Passes out of 906 case-runs (development 87, older 819): `today` 829 (39 of 87 development, 790 of 819 older), `replace` 686 (54, 632),
  `replace-to-filings` 835 (57, 778), `intersect-else-router` 832 (66, 766), `intersect-else-keywords` 817 (42, 775). **The router is stable
  (only 2 of 302 cases changed between repeats).** The keywords chose something specific in 177 of the 302 cases, and a further 65 are
  held by a guard; on the specific ones the router differed from the keywords in 72 cases, and **the router was right in 10, the keywords
  in 58, neither in 4.** All 10 router wins are cases written to expose a keyword error (9 development, plus "climbing or sliding"); the 58
  keyword wins are mostly cases the keywords were tuned to pass, so neither side of that count is a fair rate (the sealed set is the
  referee). **What the router gets wrong when it differs:** it adds prices to a stored-figure question (33 of the 58: P/E, market value, EPS,
  margin), adds sentiment to a news question (8), says "price only" to a cause or "how is X doing" question that carries headlines by
  design (4), and says "filings" to a mood or news question ("Any recent announcements", "kind or harsh", "turned on", 3) or to a price
  prediction (1). **What it gets right:** a price word inside a filings question ("falling demand", "closed on schedule", "trading
  restrictions", "volatility in lithium costs", "rising wafer prices": the keywords say prices, the model says filings, 5 of 5, three of
  three repeats), "optimistic about factory" (mood words in a filings question), and a price question carrying "lately" (4 of 4).
  **Reading the policies:** `replace` is plainly wrong (a loss of 58 cases) because of the first error above. `replace-to-filings` gains the 6
  filings cases and loses 4 older ones (net +6 case-runs overall, but +18 on the cases written to find the problem and -12 on the older
  ones). The intersect policies are safe against the most common model error (an extra price or sentiment is simply dropped) but remove
  headlines the rules attach to cause and "how is X doing" questions on purpose (4 cases), and `intersect-else-router` sends a mood or news
  question to the filings when the two share nothing (2 more). **No policy beats `today` on the older cases** (every one loses 12 to 24
  case-runs there), and every gain is on cases written for it, so this does NOT show that a second look helps in general; it shows where it
  could. **Not decided; nothing in the app changed.**
- **Router second look, "lately": no general second look; a keyword fix instead, 2026-10-17** (branch `feature/lately-price-rule`, cut
  from `feature/router-second-look`). **Decision (the owner's):** do not build a model second look for questions the keywords route to
  something specific; fix the one mistake the model was right about 4 times in 4 with a keyword rule; the sealed run was skipped.
  **What "lately" did wrong** (checked by running each question with and without the word): it was a news word everywhere, so (1) a
  question the price rules already read got headlines it did not ask for ("Has Nvidia been trending up or sagging lately?",
  "How choppy has Amazon's stock been lately?") and (2) a price question with no word the price rules knew went to the headlines ALONE
  ("Is Amazon's share value holding steady lately?", "Has Alphabet's quote been drifting lately?", "Has Apple been climbing or sliding
  lately?"). Its other use is right and stays: "What are people saying about Microsoft lately?", "What has Tesla been up to lately?",
  "Anything new with Amazon lately?" depend on it. **Built, in `ai/market.py` (no prompt change):** (1) "lately" brings headlines only
  when the question is not already a price question (`LATELY_RE`, out of `NEWS_RE`); (2) `RECENT_MOVE_RE`: has/is/was/were, a bare
  company (or its stock, shares, share or stock value, quote), an optional "been", one of climbing, sliding, slipping, drifting,
  sagging, trending, sinking, dipping, holding steady/firm/flat, followed by nothing, a comma or question mark, a direction or a joiner
  (higher, lower, sideways, again, steadily, slowly, a bit, or, and, a recency word, these, of, this, over, since, today), and a recency
  word (`RECENCY_RE`: lately, recently, these days, of late) or a named period, is a price question; (3) a cause question about a
  company's slide or jump counts "lately" and its siblings as the period ("What's behind Apple's slide lately?" got headlines and no
  prices, and the model described a slide with no price data). **Guards, each with a question of its own:** the movement word may not take
  an object ("climbing the ranks", "slipping on iPhone sales", "sliding into", "drifting from its mission", "sinking money into AI"),
  the subject may not be a figure ("Is revenue climbing lately for Tesla?": found by reading the rule, six such questions went to the
  prices before `_NOT_A_COMPANY` was added to the subject), the possessive may name only the stock ("Microsoft's market share sliding"
  is not caught), and without a recency word or period the rule does not fire. **Tests first: 91 new (`tests/test_lately_wording.py`;
  45 of the first 72 failed on the old code), 2224 Python tests pass. Deliberate breakages: 57, every alternative of every list, both
  `detect_intent` clauses, the guards and the optional "been"; the first pass found two surviving alternatives (`have`, `are`: the
  questions I wrote were already caught by the old rules, so the alternatives did nothing and were removed) and the figure-subject hole
  above.** The shadow-script tests used two "lately" mistakes as their examples of a wrongly routed question; they now use stand-ins.
  **Evidence, old code against new code back to back (a separate `git worktree`, router off, one data snapshot):** (a) **offline, on
  1,640 distinct questions** (every evaluation case, every question quoted in a test, the web tests): 12 change route besides the
  new tests, all intended (10 price questions, 2 cause questions), and **no older case and no other test question changed**; (b) **11
  fresh cases in new wording, written before the rule (`ROUND_LATELY`, now in `CASES`): 4 of 11 on the old code, 10 of 11 on the new
  (12 of 33 runs against 30 of 33)**, the one miss being the cause wording of (3), fixed afterwards, so that case is tuning material
  now; (c) the 4 older cases whose route changed plus the 11, three repeats, after (3): 45 of 45. I read the answers: the price
  questions are answered from the stored closes, and where the premise is false ("dipping", "trending lower") the model says the prices
  rose; the news questions still list headlines. **Weak spots:** (1) It is a word list again: another movement word ("grinding",
  "edging", "wobbling") or another recency word ("of recent days") misses until added; the tracked-company subject is any bare word that
  is not a figure. (2) "Is demand sliding lately?"-style questions with no figure word on the list would be read as prices; with a
  company named elsewhere the old route was headlines anyway. (3) Without a recency word or period the rule stays silent ("Has Tesla
  been climbing?" still goes to the filings). (4) The default window is still "past month", so "lately" is answered over a month. (5)
  **The larger class is untouched:** a price or mood word inside a filings question ("What does Apple say about falling demand in
  China?", "Does Tesla sound optimistic about its factory expansion?"): 9 of the 13 never-asked mistakes; the model was right on all 6
  tried, and a narrow "model may send it to the filings" policy is the candidate if that is wanted later. (6) **The sealed set of
  2026-10-17 is partly spoiled**: this rule was written knowing it holds "How choppy has Amazon's stock been lately?" (now routed
  right because of the rule) and "Has Microsoft been grinding higher or drifting lower recently?" (unchanged); a fair later comparison
  needs a new sealed set. (7) Two full-suite runs of five failed `tests/test_search.py` tests (`test_symbol_and_form_filters_and_limit`,
  `test_latest_only_drops_older_filings_of_the_same_form`) with nothing else using the database; they pass alone and in the next full
  run, which matches the known vector-index flakiness, but it has now happened three times with no evaluation running and has not been
  investigated.
- **Follow-up topic carry: a follow-up that points back without saying what about, 2026-10-18** (branch
  `feature/followup-topic-carry`; no change to `CONDENSE_PROMPT`, `SYSTEM_PROMPT` or the router). **What the investigation showed:**
  `ai.eval_followups` scored 50 of 51 (stable; the miss was the "roster" stretch) and could not show the problem, because every case in
  it was tuned. Running the real `resolve_question` (the rewrite step plus the code rules) on the 45 follow-ups with history in `CASES`,
  3 repeats, found **9 that miss on every run** (36 right): 8 keep the company and **lose the topic**, and one searches the wrong
  companies. The rewrite keeps a vague phrase the app cannot read ("Do the matching calculation for Alphabet.", "Take the same window for
  Alphabet.", "Lay Amazon alongside Nvidia.", "Has Amazon held up better over that stretch than AMD?", "So what was behind that move?"),
  so the standalone question routes to the filings default. `carry_topic` and `carry_comparison` rebuild the earlier question, but only
  when the follow-up is nothing except company names and words from a closed filler list ("matching", "calculation", "equivalent",
  "stretch", "rosier" are not on it). **Built, in `ai/copilot.py`:** when all of these hold, the earlier *question* (never its answer) is
  reused and "Understood as" shows it: no company is chosen in the page; the user's own words contain a pointing-back word (`POINTS_BACK_RE`:
  that, those, same, matching, equivalent, counterpart, likewise, alongside, comparable, by comparison, as much, just did); the user's words
  name no topic (`names_a_topic`: a market route, an unstored ratio, advice, a stock word, a filing noun, a 10-K or quarter) and the rewrite
  routes nowhere (`routes_somewhere`: the same without the stock word); and the nearest earlier question that is not a bare switch does name
  one. **Three compositions:** a new company is swapped into the earlier question (`carry_topic(pointing=True)`); a comparison (a
  comparison word, `POINTING_COMPARE_RE`, "anything like that", or **a rewrite that names the earlier company the user did not**) becomes
  "<earlier question>, compared with X" (`carry_comparison(pointing=True)`); and a cause question that names no company, after a price
  question, is appended to it ("..., and what explains that?", `carry_cause`). **Two flaws the evaluation found in my first version, both
  fixed with tests first:** (1) the swap overrode good rewrites that named both companies and dropped the earlier one ("Do Alphabet's
  worries overlap with those?", "Is Tesla in the same boat?" went from passing to failing), so a rewrite that names the earlier company now
  means a comparison; (2) a bare stock word in the rewrite ("that move in Nvidia's stock") counted as a topic although it still routes to the
  filings, so only the user's own words get that exemption. **One deliberate change to an earlier decision:** a closed list of comparison
  words used to keep the model's wording for "Is that wider than Omegaware?" because "wider" might be a topic the app cannot see; with no
  topic word at all that question now carries the earlier topic ("How many employees does Zetacorp have, compared with Omegaware?", a test
  pins it, and the older test now uses a wording with a topic word). **Tests first: 76 new (`tests/test_followup_topic_carry.py`), 2300
  Python tests pass. Deliberate breakages: 59, all caught, on a baseline verified green. My first breakage run reported all 53 caught while
  an older test was failing on the unmutated code, so none of it meant anything; the script now refuses to run unless the unmutated code
  passes, and the real first pass found 11 survivors (7 missing tests, 2 redundant guards that were removed, 1 narrowness now pinned).**
  **Evidence, old code against new code (a separate `git worktree`, router off, one data snapshot, 3 repeats, answers):** all 61 follow-up
  cases (the 45 with history in `CASES` plus 16 fresh, in new wording and with new earlier turns, written before the rule and
  overlap-checked by script: 11 that need the topic carried, 5 controls): **138 of 183 (75%) to 177 of 183 (97%)**; the **fresh 16: 34 of 48
  (71%) to 45 of 48 (94%)** (the old code already passed 7 of the 11 carry cases and all 5 controls); the routing probe on the 45:
  36 to 44; `ai.eval_followups` 50/51 to 51/51. Nothing that passed before fails now. I read the changed answers: for example "Do the
  matching calculation for Google." is understood as "What's Google's P/E ratio?", "Lay Amazon alongside it." as "How has Nvidia stock done
  this month, compared with Amazon?", and "So what was behind that move?" as the earlier price question plus the cause question, with the
  answer saying the stored data does not show the cause. **Still failing:** "Where does Tesla land on that scale?" (it searches Tesla, not
  Apple too; I call that expectation arguable) and, on the fresh set, "Did Microsoft climb as much over that period?", which routes right
  ("Did Microsoft's stock climb as much as AMD's over that period?") but whose answers quote percentages, not a price, so the check for
  a quoted price fails; I did not loosen it. **Weak spots:** (1) It is a word list again: the pointing-back words and the comparison cues
  are finite, and a follow-up with none of them ("Do the equivalent" is covered; "Same deal for Google" is, "Go again with Google" is not)
  is left to the rewrite. (2) The topic test is the app's own detectors, so a real topic they cannot see ("wildfire exposure") next to a
  pointing-back word gets the earlier topic bolted on, visibly, under "Understood as". (3) A rebuilt comparison replaces the user's own
  comparison wording: "Is Tesla in the same boat?" now searches "What are Microsoft's biggest risks, compared with Tesla?"; both companies
  and the filings route are right, but I cannot say the answers are better than the model's "...in the same boat as Microsoft?". (4) The
  cause carry needs no company in the question and an earlier price question; "What explains that move in Zetacorp?" is left as written
  (a test pins it). (5) The alternative "the rewrite names a company that was in the earlier turn" cannot be tested for the part that checks
  the company was in the earlier turn, because the fixtures have only two companies. (6) `ai.eval_followups` got no new cases and the 6
  follow-ups in the sealed set (partly spoiled already, see "lately") were not touched. (7) `tests/test_search.py` failed one or two
  tests in 2 of the last 4 full runs, always the first run after the database had been used by other runs, and passed on the rerun.
- **Filings questions with price or mood words: the company is the speaker, 2026-10-18** (branch `feature/filings-price-words`; no
  prompt change, no model call). **The problem:** "What does Apple say about falling demand in China?" went to the stock PRICES
  ("falling"), and "Does Tesla sound optimistic about its factory expansion?" to the headlines and their mood ("optimistic"): the word
  that sounded like the market won, although the question is about what the COMPANY says. It was 9 of the 13 mistakes the shadow run
  found that the router is never asked about, and the model had been right on all 6 it was tried on, but the shadow run's "model may
  send it to the filings" policy also lost 4 older cases, so a code rule was tried first. **What the data showed before any code
  (offline, no model):** of 1,679 distinct questions in the repo, 19 route to prices, headlines or mood AND contain a speaking cue
  (say, describe, management, 10-K...); 8 are exactly the filings cases above, the other 11 want the market ("being said about Apple in
  the press", "Would you say the sentiment...", "Can you explain why Nvidia shares fell"), and in all 11 the speaker is not the company.
  A stand-in rule keyed on who speaks matched 82 questions, and only 9 of those had a market route, all 9 wanting the filings.
  **Built, in `ai/copilot.py`:** `company_is_speaking` (a tracked company, its management, executives, leadership, CEO or CFO, or its 10-K,
  10-Q, annual report or filings, followed by say, say(s), said, describe, discuss, disclose, mention, state, explain, convey or sound, with
  also/ever/really/actually allowed between; the company's staff alone count without a verb ("How bullish is Nvidia's management..."); a
  document as the subject counts with no company named ("What does the 10-K say...")) and `route_by_speaker`: prices, headlines and mood off
  and the filings on, **unless the press is named** (news, headlines, press, coverage, story, articles, reporters, media, journalists: "Has
  Nvidia said anything in the headlines today?" is still headlines) and **the stored figures are not touched**. It runs in
  `answer_question` right after the keywords, and the router is **not asked** about a question this rule decided. The test is who speaks,
  not which price word appears, so the next price word needs no new entry. **Tests first: 88 new (`tests/test_company_speaking.py`; 2388
  Python tests pass).** Every verb form, every speaker, every small word, every press word, and the non-speakers (analysts, investors,
  "the market", "you", "everyone", a Reuters story) have a question of their own. **Deliberate breakages: 67, all caught, on a baseline
  verified green; the first pass had 3 survivors: no test started with a mood flag set (added), no test for a headlines-only question
  with the company speaking (added), and a check of the mood flag that is redundant because mood always comes with the headlines
  (removed).** **Evidence, old code against new code (a separate `git worktree`, router off, one data snapshot, 3 repeats, answers):**
  (a) **offline on 1,786 distinct questions** (every evaluation case, every question quoted in a test or the web tests): 25 routes
  change, and every one is intended (the 8 development cases, the 8 fresh speaker cases written for this, my test questions and
  "What did Apple's 10-K say about falling demand?"); **no older evaluation case and no other question changed**; (b) **the 8
  development filings cases: 0 of 24 runs on the old code, 24 of 24 on the new**; (c) **14 fresh cases in new wording, written before the
  rule (8 speaker questions, 6 controls): 14 of 42 runs on the old code, 38 of 42 on the new**: the 8 speaker cases 0 of 24 to 24 of 24, the
  controls 14 of 18 on both. I read the answers: they come from the filings, several say honestly that the filing does not mention the thing
  ("Apple does not explicitly mention falling demand in China"), and none invents a price story. The two non-perfect controls: "What
  are analysts saying about Apple's falling stock price?" routes to the prices correctly but fails on both codes because the model says
  analyst comments are not stored (the case demanded a quoted price; not loosened), and "Why did Amazon shares tumble after the earnings
  call?" is 2 of 3 on both (a number the answer quoted was not in its sources). **Weak spots:** (1) The speaker verbs are a finite list
  ("talk", "tell", "note", "report" are not on it; "How does Alphabet's management talk about..." works only because of "management").
  (2) A question that names no speaker ("Was Microsoft's Activision acquisition closed on schedule?" still goes to prices because of
  "closed") and one about the business that is not a statement ("Has Tesla been slipping on its delivery targets lately?") are untouched.
  (3) The rule trusts the company mention: "What does Tesla say about its stock price?" now goes to the filings, which is the more
  defensible reading but is a change. (4) It is checked on `search_question` (the standalone rewrite), so a rewrite that adds or drops
  the company's name changes the result. (5) The router is not consulted when the rule fires; with the router on, the model had been
  right on all 6 questions it was shown, so nothing is lost on the evidence, but it is a place where the keyword rule has the last word.
  (6) The 6 controls are few, and one is a case whose own check is too tight. (7) `tests/test_search.py` failed one or two tests in the
  first full run after the evaluations and breakage runs again, and passed on the rerun (known flakiness; a session was proposed for it).
- **Third sealed round: a fair score after PRs #43 to #48, 2026-10-18** (branch `feature/sealed-round-three`; no product code changed,
  only `ai/eval_market.py`). **Method:** 43 new cases (`SEALED_ROUND_THREE`, `s3`) were written without opening `ai/market.py` or the
  router (only the older cases and these notes), checked by script against every string in the repo (4 near-copies reworded before the
  run), committed unrun (ad9fd25), then run **once** with `--sealed --show` on one data snapshot, router off and then `COPILOT_ROUTER=model`.
  Mix: 8 prices, 7 news and mood, 6 stored figures, 7 filings (the company speaking, in verbs nobody listed: "admit", "flagged", "talk",
  "warn"), 10 traps, 5 follow-ups. **Score (case passes, one run each): keywords only 25 of 43 (58%); router on 30 of 43 (70%).** The router
  turned 5 failures into passes and lost none: "end of last week", "winning streak this fortnight", "Nvidia and AMD over 60 days",
  "tone brighter than last week", and the false premise "Nvidia roughly tripled" (the answer now says it fell 6.61%). **I read every answer.**
  Of the 13 failures with the router on, 4 are arguable (my checker or expectation, not the app): "since the start of September" is
  answered correctly (-1.93%) but the check wanted a price; "cents left after all costs" is answered correctly (17.4%) but price was
  also shown; "Did Microsoft keep pace?" answers from the past month, not the earlier period, and only the check complains about digits;
  "bad press" also showed mood. So roughly 34 of 43 on a looser reading, which I do not use as the score. **The wrong answers that
  matter, in order:** (1) **Advice missed on both runs:** "My cousin says to go all in on AMD. Should I?" got no notice and a risk
  list (`asks_for_advice` does not know "go all in" or a bare "Should I?" after a statement). (2) **A writing request answered when a company
  was named:** "Put together a short LinkedIn update on Amazon's quarter" was answered from the filings on the router run (mixing a six-month
  total with a three-month one and calling it the quarter) and, with the router off, invented a Q2 2024 post (the numbers check flagged six
  figures, but the text was shown). (3) **A false "no data"/"not available":** "How big is Apple, in terms of what all its shares are
  worth?" went to prices and said market value is not available (it is stored); "Show me what the papers are printing about Amazon" went
  to the filings and said there are no headlines; "Highest and lowest close of the past quarter" and "wild swings since spring" said the
  prices do not cover it (router on fixed neither; the wording is not read as a period). (4) **The speaker rule's known gap:** "Did Alphabet
  warn that ad prices were dropping?" still goes to prices ("warn" is not a speaker verb); "Does Tesla make money from running the business
  itself?" went to the filings and answered from operating cash flow, not the profit figure. (5) **Period said wrong but passing:** with the
  router off, "Is Tesla's stock cheaper now than at New Year?" compared with 2025-10-15 and called it "the New Year close" (the check did
  not catch it). "Has Apple been on a winning streak" answers "yes" from the two end points only. **Unchanged by the router:** it is asked
  only when the keywords find no route, and the cases it fixed are those; the cases where a keyword rule chose wrongly stay wrong (advice,
  speaker, "papers", market value). **Decision for the owner:** the router did no harm on a set it never saw and added 5 passes, which meets
  the rule set beforehand for turning it on by default; this round does not turn it on (one line plus a test; switch back with
  `COPILOT_ROUTER=off`). **State of the set:** spent. `SEALED_ROUND_THREE` stays in `SEALED` (not in `CASES`, so full-run scores do not
  mix in; the shadow run still excludes it) and `SEALED_ROUND_TWO` joined `CASES` unrun as a set, since the "lately" rule spoiled it.
  The next fair comparison needs `SEALED_ROUND_FOUR`. **Weak spots of this measurement:** one run per configuration (a swing of two is
  normal), 43 cases, my expectations for 4 cases were arguable, and `tests/test_search.py` was not run.
- **What changed: new filings, big moves, notable headlines (step 4; 2026-10-15).** `GET /api/changes?days=` and a
  `/changes` page, built by `data/changes.py` from stored data (rules are named constants at the top of that file).
  **What the data showed first (read-only queries on the dev database):** the newest stored filing was 2026-08-26, so a
  "filed in the last day" list is empty on almost every day, and `fetched_at` can't mean "new" (24 of 28 filings show
  the day the app first downloaded them, 10-12). The list therefore uses `filed_at` and the page names the newest stored
  filing when the list is empty. Daily moves differ a lot by company (median absolute move about 0.9% for Apple, 2.4% for
  AMD; the top tenth of days start near 4%), and on 10-14 all seven companies fell together. **The rules:** (1) The
  window is the last N *stored trading dates* (1, 3 or 7 on the page, up to 30 in the API), so a weekend never shortens
  it. (2) A move is listed when it is at least 3% and at least twice the company's own median daily move over the 60
  moves before the window (the window is left out of its own baseline); with fewer than 20 earlier moves only the 3%
  floor applies and the row says the usual move is unknown. (3) A day on which at least 70% of the companies (and at
  least 4) moved the same way by more than 1% is labeled market-wide, and a move on such a day in the same direction
  carries the label. (4) Notable headlines are positive or negative labels only, each story once per company, quote and
  data-page templates left out (the broad set, as the sentiment totals use), newest three per company, with the full
  counts. (5) Headlines beside a move are those published on that date (UTC), positive and negative first, labeled
  "timing only", never a cause (the copilot's rule). (6) A mood shift is the 7-day score against the 7 days before it,
  shown when the two differ by at least 0.15 and each has at least 10 stories; the earlier week is `label_counts` over
  14 days minus over 7, so there is still one counting function. **Changed from the plan:** mood is a fixed 7-day
  comparison, not "this window against the one before it", because a one-day window has a handful of stories and the
  score would mean nothing. **On the real data (as of 10-15):** the latest day lists no moves; 7 days lists AMD -5.73%
  (usual day 2.37%, bar 4.74%) and NVIDIA -3.16% (bar 3.15%) on 10-14, both labeled market-wide, and Amazon +3.29% on
  10-09; 30 days lists 12 moves and five market-wide days; no company has a mood shift, because only about a week of
  headlines is stored. **Tests:** 32 new Python tests (`tests/test_changes.py`: the rules on built series, the same
  from the database with `ZZCH*` tickers, and the endpoint) and 19 new web tests (16 for the page, 2 for formatting, 1 for navigation); 765
  Python and 232 web tests pass. Fourteen deliberate breakages of the Python rules and eight of the page were each
  caught; two Python ones were first missed (a baseline that included the window, and a window counted in calendar
  days) because the tests could not tell the difference (a median ignores three outliers; the test dates had no
  weekend), and two tests were added. One web breakage was first "missed" because my edit hit a comment, not the code.
  **Found in the browser, not by the tests:** a falling move was written "closed $570.82, up from $605.53". The
  component test had the same wrong wording in its expected text, so it passed; both now say "against". **In a real
  browser** (live data, servers stopped afterwards): the latest day and 7 days at desktop width, 375 px (no horizontal
  overflow), light mode (automated contrast check: none of 137 text elements below 4.5:1), and the API stopped (the
  standard "Can't reach the API" message with a retry). **Not checked on real data:** a window that contains a filing
  (none was filed in any window; tests cover it), a mood shift, a company with a stale latest price. **Weak spots:**
  (1) The thresholds (3%, twice the usual move, 1% and 70% for market-wide, 0.15 for mood) were chosen from these seven
  companies and one look at their history; nothing measures whether they flag the days an owner cares about, and a
  tighter or looser setting is one constant. (2) "Notable" is only "labeled positive or negative" by a small local
  model that leans neutral and is wrong about one headline in eight or so, so the list can contain routine items and
  miss important ones; the newest three per company are shown, so on a busy day they are all from the same hours. (3)
  A headline paraphrased by another outlet shows twice (only identical titles are merged, as elsewhere). (4) The move
  is measured between two stored closes; if a bar is missing the move spans more than a day (the row shows both
  dates). The last bar can be a partial day while the market is open. (5) The headlines beside a move are chosen by UTC
  date, so an after-hours story can sit on the next trading day's move. (6) Only about a week of headlines is stored, so
  older moves show "no stored headlines" and a mood shift cannot appear yet. (7) The copilot cannot answer "what changed
  today" from this view. (A dashboard card and a "since last visit" option followed; see the next entry.)
- **What changed: "since last visit" and a dashboard card (2026-10-15).** Two follow-ups to the entry above. **(1) A
  dashboard card** (`ChangesTeaser`): counts of big moves, new filings, and positive or negative headlines for the latest
  trading day, the three biggest moves (arrow and sign, market-wide label), and a link to `/changes`. It fetches
  `days=1` on its own and fails on its own, so a broken endpoint doesn't blank the dashboard. **(2) "Since last visit"**:
  `GET /api/changes?since=YYYY-MM-DD` means the stored trading dates after that date (at most the newest 30), and wins
  over `days`. With nothing stored after it, the reply has `days: 0`, `as_of` set to the newest stored date (so the page
  can say "no new trading days", not "no prices"), and filings and headlines from the day after `since`. The browser
  remembers the newest trading day the page showed (`lib/lastVisit.ts`, key `stockmarket.changes.lastVisit.v1`; validated
  as a real date, never moved backwards, never throws), written once when the page first loads. The page reads it once at
  mount and offers "Since last visit (date)" only when it is there, so the option doesn't change while it is being used.
  **What "visit" means:** opening the What changed page, not the dashboard (the card doesn't save anything), and any
  window you looked at counts, so choosing "Latest day" after three days away marks those three days as seen. It is a
  convenience marker, not a read receipt. **Tests:** 6 new Python (the window rule, the cap at 30, the same window as
  the matching `days`, the empty window, a filing after the newest price, the endpoint) and 21 web tests (the marker
  helper, the page's last-visit behavior, the card); 771 Python and 253 web tests pass. Six deliberate Python breakages
  and eight web breakages (the marker read on every render, never saved, moving backwards, the client ignoring `since`,
  any string accepted as a date, all moves shown on the card, negatives left out of the headline count, storage errors
  thrown) were each caught. **In a real browser** (live data, servers stopped afterwards): the card on the dashboard at
  desktop and 375 px (no overflow); with an earlier visit set to 2026-10-13, the button read "Since last visit (Oct 13,
  2026)", chose 2 trading days (Oct 14 and 15) with AMD and NVIDIA on the market-wide day, the marker moved to 2026-10-15,
  and after a reload the button offered Oct 15 and chose "No new trading days since Oct 15, 2026". **Weak spots:** (1) The
  marker is per browser (cleared with site data, not shared across browsers). (2) The first visit has no marker, so the
  option doesn't appear until the second. (3) The "usual day" for a move is measured before the window, so the same day
  can show a slightly different usual size in different windows (AMD on 10-14: 2.37% in a 7-day window, 2.31% in a 2-day one);
  the bar moves with it. (4) The card's headline count is for the latest trading day (UTC dates), so it can differ from the
  full page's count over a longer window. (5) Light mode and the empty and error states of the card were checked by
  tests only, not in a browser.
- **The chart shows daily closes only.** No volume bars, indicators, comparison between companies, or pinch-zoom.
  The latest day can be partial while the market is open.
- **Stock detail was checked in a real browser** (live NVIDIA and Tesla data, hover checks against database values,
  range switching, the page's copilot, the not-found page, a 375 px phone width), in dark mode only.
- **The dashboard was checked visually in dark mode at 780 px wide (single column) and by DOM and CSS checks at
  desktop width.** My screenshots of the two-column desktop layout were cropped by the preview pane. Look at both on
  a real screen.
- **Light mode was checked** (browser emulation of `prefers-color-scheme: light`): the dashboard, a stock detail page
  with its chart, and the copilot page with a warning banner, at 1280 px wide, plus the dashboard at 375 px. An
  automated contrast check found no text below 4.5:1 (140 elements on the copilot page, none failing on the others),
  the price line is 6:1 against the background, and the chart's gridlines are deliberately faint (1.3:1). Warnings
  and pills carry words, not just color. Not checked in light mode: the stock detail page and the copilot at 375 px, and the filings list.
- **On a phone-width screen the watchlist hides its last two columns.** At 375 px the table is about 500 px wide
  inside a scrolling box, so the 1-month chart and the News mood column are off-screen until you scroll sideways,
  with nothing hinting that you can. Found during the light-mode check; it is the same in dark mode. Not fixed.
- **The dashboard is for local development only:** no login, no production build served anywhere, no HTTPS. The
  production build (`npm run build`) compiles but hasn't been deployed or served.
- **Tests fake the network.** The web tests use a fake `fetch`. They were backed by one real browser session (watchlist
  with live data, a live copilot answer, a clicked citation, and the API-down state), not by automated browser tests.
- **Evaluation is small.** About 14 copilot questions and 40 headlines, judged by one reviewer.
- **The embedding model has no query prefix.** bge models recommend one, but fastembed's `query_embed` doesn't add it.
  Adding it by hand made no difference on the test questions, so it was left out.

## Ideas not built yet

- Email or phone alerts for the nightly job (the desktop alert exists)
- A Claude implementation of `LLM` (needs an Anthropic API key), then compare answers against Qwen on the same questions
- Keyword plus vector hybrid search; a reranker
- Skipping quote and template pages before labeling, so the model isn't asked about them
- Moving the copilot onto the broader template rules (the "crashing premise" case was decided on 2026-10-15 and now
  accepts a premise correction; the 8-of-8-to-0-of-8 experiment above has not been re-run against the new check)
- Fixing the phone-width watchlist so the 1-month chart and News mood columns are reachable
- A proper evaluation set of questions with known answers
- Index and fundamentals data (S&P 500, P/E, market value) so those questions can be answered instead of refused
- A code rule for bare "What about Tesla?" follow-ups that carries the previous question's topic over
- Choosing headlines spread across the period asked about, not just the newest six
- Streaming answers, so the screen isn't blank for several seconds
