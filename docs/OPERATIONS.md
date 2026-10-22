# Operations

Running Citewise for Markets day to day: the nightly refresh, adding and removing companies, the question log, and backups. First-time installation is in [SETUP.md](SETUP.md); the design behind the job is in [ARCHITECTURE.md](ARCHITECTURE.md).

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

**Remove a company** (stop tracking it) with a command, or with the on/off switch beside it in the dashboard's watchlist (or in
its page header), which asks "Are you sure?" first. A removed company moves to a dimmed "Not tracked" list under the watchlist;
switching it back on there runs the same update as the Add box (a few minutes) and moves it back:

```bash
.venv\Scripts\python -m jobs.remove_company TSM
```

Nothing is deleted. The company is switched off, so it leaves the dashboard, the nightly refresh, "What changed", and the
copilot, but its prices, filings, headlines, and figures stay stored. `python -m jobs.add_company TSM` brings it back with
that history. It uses the same lock as the nightly job (exit code 3 while a refresh is running); exit code 1 means the
ticker is not tracked (never added, or already removed).

Runs are logged to the `job_runs` table and to `logs/refresh.log`. Exit codes: 0 all good,
1 something failed or was skipped, 2 database unreachable, 3 another run already in progress, 4 the job crashed.
Exit codes 1, 2 and 4 also pop up a Windows desktop alert, so you hear about a bad night without checking. Test that
alerts reach you with `.venv\Scripts\python -m jobs.notify`. Add `--no-alert` to a manual run to silence them.

**Schedule it** (one time, changes your Windows Task Scheduler):

```bash
powershell -ExecutionPolicy Bypass -File scripts\register_nightly_task.ps1 -Time 15:00
```

Use 3pm (Pacific). Yahoo left out the day's closing price when the job ran at 5pm, so the stored prices stayed a day
behind; see "Prices were always a day behind" in `docs/DECISIONS.md`.

Remove it with `powershell -File scripts\unregister_nightly_task.ps1`. The task only runs while you are logged in,
and if the PC was off at the scheduled time it runs when you next log in. **Docker Desktop and Ollama must be running**
at that time. If Docker is down the run exits with code 2, and if Ollama is down only the sentiment step is skipped.

## Your questions

Every question you ask the copilot in the web app is appended, with its answer, to `logs/copilot_questions.jsonl` on this PC
(git-ignored; it is not sent anywhere, is not in the database backups, and keeps no source text). Questions can contain personal
context, so `COPILOT_LOG=off` in `.env` turns it off. To read it and see which answers look like misses (refused, "the sources do
not provide", nothing cited, unverified numbers):

```bash
.venv\Scripts\python -m ai.review_questions                 # the last 20
.venv\Scripts\python -m ai.review_questions --flagged       # only the ones that look like misses
.venv\Scripts\python -m ai.review_questions --since 2026-10-19 --full
```

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

**Schedule it** (one time, changes your Windows Task Scheduler; default 6pm, after the 3pm refresh):

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

