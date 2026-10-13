"""Back up the database to a file you can restore from, and prove that a backup works.

Usage:
  python -m jobs.backup                       take a backup now, then trim old ones (keeps the newest 30)
  python -m jobs.backup list                  show the backups, newest first
  python -m jobs.backup verify [FILE]         restore a backup (default: the newest) into a temporary database,
                                              check it against what was recorded at backup time, then delete the copy
  python -m jobs.backup restore FILE --into NAME [--replace]
                                              restore into database NAME. Without --replace it refuses if NAME exists.
                                              With --replace it first takes a safety backup of the current database.

Backups go to the `backups` folder in this project, or BACKUP_DIR from .env (point it somewhere that survives this
disk failing, e.g. a synced or external drive). Each backup is a .dump file plus a .json note of its checksum and row
counts. The dump is made by pg_dump inside the Docker container, so Docker Desktop must be running.
A backup waits for a running nightly refresh to finish (it shares its lock), so it never captures a half-written run.

Exit code 0 = ok, 1 = a check failed, 2 = the database or Docker is unreachable, 3 = a refresh kept the database busy,
4 = the command itself failed or crashed. Exit codes 2 and 4 on a backup also show a Windows desktop alert
(pass --no-alert to turn that off).
"""
import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from data.db import ROOT, database_url, get_setting

from .notify import send_notification
from .refresh import LOCK_KEY

log = logging.getLogger("backup")

DEFAULT_KEEP = 30
DUMP_RE = re.compile(r"^stockmarket-(prerestore-)?\d{8}-\d{6}\.dump$")
AUTO_RE = re.compile(r"^stockmarket-\d{8}-\d{6}\.dump$")  # only these are ever trimmed; safety backups are kept
DB_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class BackupError(Exception):
    """Something went wrong that the message explains (exit code 4)."""


class Unreachable(Exception):
    """The database or Docker can't be reached (exit code 2)."""


class Busy(Exception):
    """A refresh held the database lock for the whole wait (exit code 3)."""


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


# ---- settings and plumbing ----

def backup_dir() -> Path:
    return Path(get_setting("BACKUP_DIR") or ROOT / "backups")


def container() -> str:
    return get_setting("DB_CONTAINER") or "stockmarket-db"


def live_db() -> str:
    return conninfo_to_dict(database_url())["dbname"]


def db_user() -> str:
    return conninfo_to_dict(database_url())["user"]


def connect_to(db: str, autocommit: bool = False) -> psycopg.Connection:
    try:
        return psycopg.connect(make_conninfo(database_url(), dbname=db), autocommit=autocommit, connect_timeout=10)
    except psycopg.OperationalError as exc:
        raise Unreachable(f"can't reach database '{db}' (is Docker Desktop running?): {exc}") from exc


def docker(args: list[str], stdin: Optional[Path] = None, stdout: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run a command inside the database container. Output goes to `stdout` (a file) if given, else it is captured."""
    cmd = ["docker", "exec", "-i", container(), *args]
    fin = open(stdin, "rb") if stdin else subprocess.DEVNULL
    fout = open(stdout, "wb") if stdout else subprocess.PIPE
    try:
        return subprocess.run(cmd, stdin=fin, stdout=fout, stderr=subprocess.PIPE, timeout=3600)
    except FileNotFoundError as exc:
        raise Unreachable("the `docker` command wasn't found (is Docker Desktop installed and running?)") from exc
    finally:
        for f in (fin, fout):
            if hasattr(f, "close"):
                f.close()


def psql(db: str, statement: str) -> None:
    r = docker(["psql", "-U", db_user(), "-d", db, "-v", "ON_ERROR_STOP=1", "-Atq", "-c", statement])
    if r.returncode != 0:
        raise BackupError(f"psql failed in '{db}': {r.stderr.decode(errors='replace').strip()[-400:]}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def table_counts(conn: psycopg.Connection) -> dict[str, int]:
    names = [r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY 1")]
    return {n: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(n))).fetchone()[0] for n in names}


def manifest_path(dump: Path) -> Path:
    return dump.with_suffix(".json")


# ---- backup ----

def take_backup(db: Optional[str] = None, directory: Optional[Path] = None, wait: float = 900,
                label: str = "", now: Optional[datetime] = None) -> Path:
    """Dump `db` (default: the live database) into the backup folder and return the file's path.

    Holds the refresh job's lock for the whole dump so no run is half-written in it. Raises Busy if it can't get the
    lock within `wait` seconds, Unreachable if the database or Docker is down, BackupError if the dump is unusable."""
    db = db or live_db()
    directory = directory or backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    final = directory / f"stockmarket-{label}{stamp}.dump"
    partial = directory / f".{final.name}.partial"

    with connect_to(db) as conn:
        deadline = time.monotonic() + wait
        while not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
            if time.monotonic() >= deadline:
                raise Busy("a refresh has held the database for the whole wait; try again later")
            log.info("a refresh is running; waiting for it to finish before backing up...")
            time.sleep(10)
        try:
            counts = table_counts(conn)
            migrations = [r[0] for r in conn.execute("SELECT name FROM schema_migrations ORDER BY name")]
            version = conn.execute("SHOW server_version").fetchone()[0]
            result = docker(["pg_dump", "-U", db_user(), "-Fc", db], stdout=partial)
            if result.returncode != 0:
                raise BackupError(f"pg_dump failed: {result.stderr.decode(errors='replace').strip()[-400:]}")
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        finally:
            conn.rollback()
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
            conn.commit()

    listing = docker(["pg_restore", "--list"], stdin=partial)  # does the file parse as a dump at all?
    if listing.returncode != 0 or b"TABLE DATA" not in listing.stdout:
        partial.unlink(missing_ok=True)
        raise BackupError("the dump was written but can't be read back as a database dump; it was discarded")
    partial.replace(final)
    manifest_path(final).write_text(json.dumps({
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": db, "postgres": version, "bytes": final.stat().st_size, "sha256": sha256_of(final),
        "migrations": migrations, "tables": counts,
    }, indent=2), encoding="utf-8")
    log.info("backup written: %s (%.1f MB, %d tables, %s rows)", final, final.stat().st_size / 1e6, len(counts),
             f"{sum(counts.values()):,}")
    return final


def trim(directory: Path, keep: int) -> list[Path]:
    """Delete the oldest automatic backups beyond `keep`. Only files named exactly like ours are ever touched."""
    autos = sorted((p for p in directory.iterdir() if p.is_file() and AUTO_RE.match(p.name)), reverse=True)
    removed = []
    for old in autos[keep:]:
        old.unlink()
        manifest_path(old).unlink(missing_ok=True)
        removed.append(old)
        log.info("removed old backup %s", old.name)
    return removed


def list_backups(directory: Path) -> list[Path]:
    return sorted((p for p in directory.iterdir() if p.is_file() and DUMP_RE.match(p.name)), reverse=True) \
        if directory.exists() else []


# ---- restore and verify ----

def database_exists(name: str) -> bool:
    with connect_to("postgres", autocommit=True) as c:
        return c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is not None


def drop_database(name: str) -> None:
    with connect_to("postgres", autocommit=True) as c:
        c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def restore_into(dump: Path, name: str) -> None:
    """Create database `name` and load `dump` into it, using TimescaleDB's required before/after steps.
    On any failure the half-built database is dropped. The database must not already exist."""
    with connect_to("postgres", autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        psql(name, "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT timescaledb_pre_restore();")
        r = docker(["pg_restore", "-U", db_user(), "-d", name, "--no-owner"], stdin=dump)
        if r.returncode != 0:
            raise BackupError(f"pg_restore failed: {r.stderr.decode(errors='replace').strip()[-600:]}")
        psql(name, "SELECT timescaledb_post_restore();")
    except BaseException:
        drop_database(name)
        raise


def load_manifest(dump: Path) -> dict:
    path = manifest_path(dump)
    if not path.exists():
        raise BackupError(f"{path.name} is missing, so there is nothing to check {dump.name} against")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_backup(dump: Path, temp_name: Optional[str] = None) -> list[Check]:
    """Restore `dump` into a temporary database and compare it with the manifest written at backup time."""
    manifest = load_manifest(dump)
    checks = [Check("file checksum", sha256_of(dump) == manifest["sha256"],
                    "matches the note written at backup time" if sha256_of(dump) == manifest["sha256"]
                    else "the file has changed since it was written (damaged?)")]
    if not checks[0].ok:
        return checks
    name = temp_name or f"restore_check_{datetime.now():%Y%m%d%H%M%S}"
    restore_into(dump, name)
    try:
        with connect_to(name) as conn:
            counts = table_counts(conn)
            expected = manifest["tables"]
            diffs = [f"{t}: {counts.get(t)} restored vs {n} backed up" for t, n in expected.items() if counts.get(t) != n]
            diffs += [f"{t}: unexpected extra table" for t in counts if t not in expected]
            checks.append(Check("row counts", not diffs, f"all {len(expected)} tables match ({sum(expected.values()):,} rows)"
                                if not diffs else "; ".join(diffs)))
            migrations = [r[0] for r in conn.execute("SELECT name FROM schema_migrations ORDER BY name")]
            checks.append(Check("schema version", migrations == manifest["migrations"],
                                f"{len(migrations)} migrations, latest {migrations[-1] if migrations else '-'}"))
            ext = {r[0] for r in conn.execute("SELECT extname FROM pg_extension")}
            checks.append(Check("extensions", {"timescaledb", "vector"} <= ext, "timescaledb and vector present"
                                if {"timescaledb", "vector"} <= ext else f"missing from {sorted(ext)}"))
            if expected.get("filing_chunks"):  # the search index must really work, not just hold rows
                hits = conn.execute(
                    "SELECT count(*) FROM (SELECT id FROM filing_chunks ORDER BY embedding <=> "
                    "(SELECT embedding FROM filing_chunks LIMIT 1) LIMIT 5) t").fetchone()[0]
                checks.append(Check("vector search", hits == min(5, expected["filing_chunks"]),
                                    f"nearest-passage query returned {hits} rows"))
            if expected.get("prices_daily"):
                chunks = conn.execute("SELECT count(*) FROM timescaledb_information.chunks "
                                      "WHERE hypertable_name = 'prices_daily'").fetchone()[0]
                newest = conn.execute("SELECT max(ts) FROM prices_daily").fetchone()[0]
                checks.append(Check("price history", chunks > 0 and newest is not None,
                                    f"{chunks} time chunks, newest price {newest}"))
    finally:
        drop_database(name)
    return checks


def restore_backup(dump: Path, into: str, replace: bool = False, live: Optional[str] = None,
                   directory: Optional[Path] = None) -> Optional[Path]:
    """Restore into database `into`. Returns the safety backup's path if one was taken.

    Refuses if `into` exists unless `replace`. Replacing the live database first takes a safety backup of it."""
    if not DB_NAME_RE.match(into):
        raise BackupError(f"'{into}' isn't a usable database name (lowercase letters, digits, underscores)")
    manifest = load_manifest(dump)
    if sha256_of(dump) != manifest["sha256"]:
        raise BackupError(f"{dump.name} doesn't match its checksum note; it may be damaged, so it won't be restored")
    live = live or live_db()
    safety = None
    if database_exists(into):
        if not replace:
            raise BackupError(f"database '{into}' already exists. Restore into a new name, or add --replace to overwrite it")
        if into == live and _has_data(into):
            log.info("taking a safety backup of '%s' before replacing it...", into)
            safety = take_backup(into, directory, label="prerestore-")
            log.info("safety backup: %s", safety)
        drop_database(into)
    restore_into(dump, into)
    return safety


def _has_data(db: str) -> bool:
    with connect_to(db) as c:
        return c.execute("SELECT to_regclass('public.instruments')").fetchone()[0] is not None


# ---- command line ----

def format_age(seconds: float) -> str:
    return f"{seconds / 3600:.0f}h" if seconds < 48 * 3600 else f"{seconds / 86400:.0f}d"


def cmd_list(directory: Path) -> int:
    files = list_backups(directory)
    print(f"Backups in {directory}:")
    if not files:
        print("  none yet. Run: python -m jobs.backup")
        return 0
    for f in files:
        note = "" if manifest_path(f).exists() else "   (no .json note: can't be verified)"
        age = format_age(time.time() - f.stat().st_mtime)
        print(f"  {f.name}   {f.stat().st_size / 1e6:6.1f} MB   {age} old{note}")
    return 0


def cmd_verify(path: Optional[str], directory: Path) -> int:
    if path:
        dump = Path(path)
    else:
        files = list_backups(directory)
        if not files:
            raise BackupError(f"no backups in {directory}")
        dump = files[0]
    if not dump.exists():
        raise BackupError(f"{dump} doesn't exist")
    print(f"Verifying {dump.name} by restoring it into a temporary database (the live one isn't touched)...")
    checks = verify_backup(dump)
    for c in checks:
        print(f"  {'PASS' if c.ok else 'FAIL'}  {c.name:<15} {c.detail}")
    ok = all(c.ok for c in checks)
    print("=> RESTORE VERIFIED" if ok else "=> VERIFICATION FAILED: do not rely on this backup")
    return 0 if ok else 1


def setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(ROOT / "logs" / "backup.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv: list[str] | None = None, notify: Callable[[str, str], object] = send_notification) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-alert", action="store_true", help="don't show a desktop alert if a backup fails")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="how many automatic backups to keep (default 30)")
    parser.add_argument("--wait", type=int, default=900, help="seconds to wait for a running refresh (default 900)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("backup", help="take a backup now (the default)")
    sub.add_parser("list", help="show the backups")
    p_verify = sub.add_parser("verify", help="restore a backup into a temporary database and check it")
    p_verify.add_argument("file", nargs="?", help="default: the newest backup")
    p_restore = sub.add_parser("restore", help="restore a backup into a database")
    p_restore.add_argument("file")
    p_restore.add_argument("--into", required=True, metavar="NAME", help="database to create (or replace, with --replace)")
    p_restore.add_argument("--replace", action="store_true", help="overwrite NAME if it exists (the live database gets a safety backup first)")
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    command = args.command or "backup"
    setup_logging()
    directory = backup_dir()

    try:
        if command == "list":
            return cmd_list(directory)
        if command == "verify":
            return cmd_verify(args.file, directory)
        if command == "restore":
            dump = Path(args.file)
            if not dump.exists():
                raise BackupError(f"{dump} doesn't exist")
            safety = restore_backup(dump, args.into, args.replace, directory=directory)
            print(f"Restored {dump.name} into database '{args.into}'.")
            if safety:
                print(f"The database it replaced was saved first as {safety.name}.")
            print(f"Check it with: python -m jobs.backup verify {dump}")
            return 0
        take_backup(directory=directory, wait=args.wait)
        trim(directory, args.keep)
        return 0
    except Busy as exc:
        log.warning("%s", exc)
        return 3
    except Unreachable as exc:
        log.error("%s", exc)
        if command == "backup" and not args.no_alert:
            notify("Database backup didn't run", "Can't reach the database. Is Docker Desktop running?")
        return 2
    except BackupError as exc:
        log.error("%s", exc)
        if command == "backup" and not args.no_alert:
            notify("Database backup FAILED", str(exc)[:200])
        return 4
    except Exception as exc:
        log.exception("the backup command crashed")
        if command == "backup" and not args.no_alert:
            notify("Database backup crashed", f"{type(exc).__name__}: {exc}"[:200])
        return 4


if __name__ == "__main__":
    sys.exit(main())
