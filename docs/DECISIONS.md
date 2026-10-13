# Decisions, gotchas, and known weak spots

A record of why things are the way they are, and what testing showed. Numbers are from October 2026 on six companies
(AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA). Most evaluations were small and hand-read, so treat them as spot checks, not
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
| Task runs only while logged in (interactive principal) | Avoids storing a Windows password. Docker Desktop and Ollama start at login anyway, and the job needs both |
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
| Quote pages and "X vs Y" pages are left out of the copilot's headlines | They are most of the neutral labels, say nothing new, and quote intraday prices that read like closing prices. The news panel is unchanged |
| Index and market-wide questions are refused | No index data is stored. Asked "What is the S&P 500 at?", the model answered "$217" from a filing's total-return chart (scaled from $100). Refusing is better than a confident wrong number |
| A cause hint is retried, then shown as a caution | The prompt alone didn't stop the model hedging ("may have influenced market sentiment"), so the code checks for it, retries once, and the reply carries a visible `cautions` entry if it persists |

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
  irrelevant. About two-thirds of labels are neutral, mostly quote pages and "X vs Y" comparison pages, so scores sit
  near zero. Consistency across re-runs was not measured.
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
  correctly, but the model repeats "$600" and the check flags it as not in the sources. Left as is: a spurious warning
  is the safer way to fail than trusting numbers a user supplies.
- **The cause check only looks for certain wording** ("due to", "may have contributed", "driven by"). A cause implied
  in other words would pass, and it only runs when the answer was given both prices and headlines.
- **Headlines in answers are shallow.** Titles only, the newest six (so usually all from one day, whatever period was
  asked about), some not really about the company (the model labels "irrelevant" only a few), and the labels are two
  thirds neutral. Answers repeat that, but a "Dating app Bumble is in talks to go private" headline can still appear
  under Nvidia.
- **Year-to-date and window figures use closing prices only,** from the free Yahoo feed. The latest day may be partial,
  and the 52-week range is of closes, not intraday highs and lows.
- **No fundamentals.** Market value, P/E, and analyst targets aren't stored. The copilot says they aren't available, but
  on a filings-route question the model sometimes answers uncited ("the sources don't include that").
- **The "If the question assumes a decline, it contradicts the data" sentence** showed up in a real answer, copied
  from the prompt rule. Harmless, but it is the model repeating its instructions.
- **Checked in a real browser:** a price question with a false premise, a sentiment question, an index question
  (refused), a reload (history restored, in the new shape), old saved answers (still showing), and a 375 px phone
  width. Dark mode only. The browser pane's own history was used, so these answers sit in that pane's saved history.
- **Search is vector-only.** A keyword (full-text) search was considered for exact-term lookups and not built.
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
- **The stock detail page has no AI signal or fundamentals.** Those need data and a model that don't exist. It shows what
  the stored data supports: prices, news mood, filings, and the filings copilot.
- **Duplicate headlines:** the free news feed can return the same title from different sources or links, so a headline
  can appear twice in a company's news list. Not deduplicated yet.
- **The chart shows daily closes only.** No volume bars, indicators, comparison between companies, or pinch-zoom.
  The latest day can be partial while the market is open.
- **Stock detail was checked in a real browser** (live NVIDIA and Tesla data, hover checks against database values,
  range switching, the page's copilot, the not-found page, a 375 px phone width), in dark mode only.
- **The dashboard was checked visually in dark mode at 780 px wide (single column) and by DOM and CSS checks at
  desktop width.** My screenshots of the two-column desktop layout were cropped by the preview pane, and light mode
  wasn't viewed. Look at both on a real screen.
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
- Filtering quote-page and comparison-page headlines out of sentiment scoring (the copilot already leaves them out of
  its headlines, but they still count in the labels and the dashboard)
- A proper evaluation set of questions with known answers
- Index and fundamentals data (S&P 500, P/E, market value) so those questions can be answered instead of refused
- A code rule for bare "What about Tesla?" follow-ups that carries the previous question's topic over
- Choosing headlines spread across the period asked about, not just the newest six
- Streaming answers, so the screen isn't blank for several seconds
