"""Backup tests use real pg_dump / pg_restore inside the dev container, on small throwaway databases (zz_backup_*),
never the dev data itself."""
import json
import subprocess
from datetime import date, datetime

import psycopg
import pytest

import jobs.backup as backup
from jobs.refresh import LOCK_KEY

SRC, COPY, CHECK = "zz_backup_src", "zz_backup_copy", "zz_backup_check"
VECTOR = "[" + ",".join(["1"] + ["0"] * 383) + "]"


def drop_all():
    for name in (SRC, COPY, CHECK):
        backup.drop_database(name)


@pytest.fixture(scope="module")
def src():
    """A small database with the real schema and a few rows in every kind of table that matters."""
    drop_all()
    with psycopg.connect(backup.make_conninfo(backup.database_url(), dbname="postgres"), autocommit=True) as c:
        c.execute(f"CREATE DATABASE {SRC}")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", _url_for(SRC))  # db/migrate.py reads the target from the environment
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("migrate", backup.ROOT / "db" / "migrate.py")
        migrate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrate)
        migrate.main()
    finally:
        mp.undo()
    with backup.connect_to(SRC) as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZBK', 'Backup Co')")
        c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES ('ZZBK', %s, 12.5, 't'), ('ZZBK', %s, 13.5, 't')",
                  (date(2026, 10, 9), date(2026, 10, 12)))
        c.execute("INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                  "VALUES ('0-ZZBK-1', 'ZZBK', '0000000001', '10-K', '2026-01-02', 'https://x', 'body')")
        c.execute("INSERT INTO filing_chunks (accession_number, chunk_index, text, embedding, embedding_model) "
                  "VALUES ('0-ZZBK-1', %s, 'passage', %s::vector, 'fake')", (0, VECTOR))
        c.execute("INSERT INTO news_articles (id, source, title, url, published_at) VALUES ('zz-1', 't', 'ZZBK soars', 'https://x', now())")
        c.execute("INSERT INTO news_article_symbols VALUES ('zz-1', 'ZZBK')")
        c.commit()
    yield SRC
    drop_all()


def _url_for(db):
    from urllib.parse import urlparse, urlunparse
    return urlunparse(urlparse(backup.database_url())._replace(path=f"/{db}"))


@pytest.fixture
def bdir(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "backup_dir", lambda: tmp_path)
    monkeypatch.setattr(backup, "setup_logging", lambda: None)  # don't write to the real logs/backup.log
    backup.drop_database(COPY)
    backup.drop_database(CHECK)
    yield tmp_path
    backup.drop_database(COPY)
    backup.drop_database(CHECK)


def scalar(db, sql, *params):
    with backup.connect_to(db) as c:
        return c.execute(sql, params).fetchone()[0]


# ---- taking a backup ----

def test_a_backup_writes_a_dump_and_a_matching_note(src, bdir):
    path = backup.take_backup(SRC, bdir, now=datetime(2026, 10, 13, 9, 0, 0))
    assert path.name == "stockmarket-20261013-090000.dump" and path.stat().st_size > 1000
    note = json.loads(backup.manifest_path(path).read_text())
    assert note["sha256"] == backup.sha256_of(path) and note["bytes"] == path.stat().st_size
    assert note["tables"]["instruments"] == 1 and note["tables"]["prices_daily"] == 2 and note["tables"]["filing_chunks"] == 1
    assert "006_job_runs.sql" in note["migrations"]
    assert sorted(p.name for p in bdir.iterdir()) == [path.name, path.with_suffix(".json").name]  # no partial leftovers


def test_a_backup_releases_the_refresh_lock(src, bdir):
    backup.take_backup(SRC, bdir)
    with backup.connect_to(SRC) as other:
        assert other.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0] is True
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def test_a_backup_waits_for_a_running_refresh_and_gives_up_with_busy(src, bdir):
    with backup.connect_to(SRC) as other:
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        with pytest.raises(backup.Busy):
            backup.take_backup(SRC, bdir, wait=0)
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    assert list(bdir.iterdir()) == []


def test_a_failed_dump_leaves_nothing_behind_and_releases_the_lock(src, bdir, monkeypatch):
    real = backup.docker

    def failing(args, stdin=None, stdout=None):
        if args[0] == "pg_dump":
            stdout.write_bytes(b"half a dump")
            return subprocess.CompletedProcess(args, 1, b"", b"pg_dump: out of disk")
        return real(args, stdin, stdout)

    monkeypatch.setattr(backup, "docker", failing)
    with pytest.raises(backup.BackupError, match="out of disk"):
        backup.take_backup(SRC, bdir)
    assert list(bdir.iterdir()) == []
    monkeypatch.undo()
    with backup.connect_to(SRC) as other:
        assert other.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0] is True
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def test_a_dump_that_cannot_be_read_back_is_discarded(src, bdir, monkeypatch):
    real = backup.docker

    def garbage(args, stdin=None, stdout=None):
        if args[0] == "pg_dump":
            stdout.write_bytes(b"not a dump")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return real(args, stdin, stdout)

    monkeypatch.setattr(backup, "docker", garbage)
    with pytest.raises(backup.BackupError, match="can't be read back"):
        backup.take_backup(SRC, bdir)
    assert list(bdir.iterdir()) == []


def test_docker_missing_is_reported_as_unreachable(src, bdir, monkeypatch):
    def nope(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(backup.subprocess, "run", nope)
    with pytest.raises(backup.Unreachable, match="docker"):
        backup.take_backup(SRC, bdir)
    assert list(bdir.iterdir()) == []


# ---- verify and restore ----

def test_verify_restores_to_a_temporary_database_and_cleans_up(src, bdir):
    path = backup.take_backup(SRC, bdir)
    checks = backup.verify_backup(path, temp_name=CHECK)
    assert [c.name for c in checks] == ["file checksum", "row counts", "schema version", "extensions", "vector search", "price history"]
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
    assert backup.database_exists(CHECK) is False


def test_verify_catches_a_damaged_file_without_restoring_it(src, bdir):
    path = backup.take_backup(SRC, bdir)
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    checks = backup.verify_backup(path, temp_name=CHECK)
    assert [c.ok for c in checks] == [False] and "damaged" in checks[0].detail
    assert backup.database_exists(CHECK) is False


def test_verify_catches_rows_that_do_not_match_what_was_backed_up(src, bdir):
    path = backup.take_backup(SRC, bdir)
    note = json.loads(backup.manifest_path(path).read_text())
    note["tables"]["news_articles"] += 5  # as if the backup were missing rows
    backup.manifest_path(path).write_text(json.dumps(note))
    checks = {c.name: c for c in backup.verify_backup(path, temp_name=CHECK)}
    assert not checks["row counts"].ok and "news_articles: 1 restored vs 6 backed up" in checks["row counts"].detail
    assert backup.database_exists(CHECK) is False  # cleaned up even when a check fails


def test_verify_without_a_note_says_so(src, bdir):
    path = backup.take_backup(SRC, bdir)
    backup.manifest_path(path).unlink()
    with pytest.raises(backup.BackupError, match="nothing to check"):
        backup.verify_backup(path, temp_name=CHECK)


def test_restore_into_a_new_database_brings_back_everything(src, bdir):
    path = backup.take_backup(SRC, bdir)
    assert backup.restore_backup(path, COPY, live="stockmarket", directory=bdir) is None
    assert scalar(COPY, "SELECT close FROM prices_daily WHERE symbol = 'ZZBK' AND ts = '2026-10-12'") == 13.5
    assert scalar(COPY, "SELECT count(*) FROM filing_chunks WHERE embedding <=> %s::vector < 0.01", VECTOR) == 1
    assert scalar(COPY, "SELECT title FROM news_articles") == "ZZBK soars"
    with backup.connect_to(COPY) as c:  # it's writable: new rows, new ids, new hypertable chunks
        c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES ('ZZBK', '2021-01-04', 1, 't')")
        c.execute("INSERT INTO job_runs (job, status) VALUES ('t', 'running')")
        c.commit()


def test_restore_refuses_to_overwrite_an_existing_database_without_replace(src, bdir):
    path = backup.take_backup(SRC, bdir)
    backup.restore_backup(path, COPY, live="stockmarket", directory=bdir)
    with backup.connect_to(COPY) as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZNEW', 'Added After')")
        c.commit()
    with pytest.raises(backup.BackupError, match="already exists"):
        backup.restore_backup(path, COPY, live="stockmarket", directory=bdir)
    assert scalar(COPY, "SELECT count(*) FROM instruments") == 2  # untouched


def test_replacing_the_live_database_saves_a_safety_backup_first(src, bdir):
    path = backup.take_backup(SRC, bdir)
    backup.restore_backup(path, COPY, live="stockmarket", directory=bdir)
    with backup.connect_to(COPY) as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZNEW', 'Added After')")
        c.commit()
    safety = backup.restore_backup(path, COPY, replace=True, live=COPY, directory=bdir)  # pretend COPY is the live one
    assert safety is not None and "prerestore-" in safety.name and safety.exists()
    assert scalar(COPY, "SELECT count(*) FROM instruments") == 1  # back to the backup's contents
    assert backup.load_manifest(safety)["tables"]["instruments"] == 2  # the safety copy holds what was replaced
    assert backup.trim(bdir, keep=1) == [] and safety.exists()  # safety backups are never trimmed


def test_replacing_a_non_live_database_takes_no_safety_backup(src, bdir):
    path = backup.take_backup(SRC, bdir)
    backup.restore_backup(path, COPY, live="stockmarket", directory=bdir)
    assert backup.restore_backup(path, COPY, replace=True, live="stockmarket", directory=bdir) is None


def test_a_failed_restore_leaves_no_half_built_database(src, bdir):
    bad = bdir / "stockmarket-20200101-000000.dump"
    bad.write_bytes(b"this is not a postgres dump")
    backup.manifest_path(bad).write_text(json.dumps({"sha256": backup.sha256_of(bad), "tables": {}, "migrations": []}))
    with pytest.raises(backup.BackupError, match="pg_restore failed"):
        backup.restore_backup(bad, COPY, live="stockmarket", directory=bdir)
    assert backup.database_exists(COPY) is False


def test_a_damaged_file_is_not_restored(src, bdir):
    path = backup.take_backup(SRC, bdir)
    path.write_bytes(path.read_bytes()[:-100])
    with pytest.raises(backup.BackupError, match="checksum"):
        backup.restore_backup(path, COPY, live="stockmarket", directory=bdir)
    assert backup.database_exists(COPY) is False


@pytest.mark.parametrize("name", ["", "Bad Name", "x; DROP DATABASE stockmarket", "UPPER", "1abc"])
def test_restore_rejects_odd_database_names(src, bdir, name):
    path = backup.take_backup(SRC, bdir)
    with pytest.raises(backup.BackupError, match="usable database name"):
        backup.restore_backup(path, name, live="stockmarket", directory=bdir)


# ---- keeping the folder tidy ----

def test_trim_removes_only_old_automatic_backups(tmp_path):
    names = ["stockmarket-20261010-010000.dump", "stockmarket-20261011-010000.dump", "stockmarket-20261012-010000.dump",
             "stockmarket-prerestore-20200101-000000.dump", "notes.dump", "stockmarket-2026.dump"]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
        if n.startswith("stockmarket-2026101"):
            backup.manifest_path(tmp_path / n).write_text("{}")
    removed = backup.trim(tmp_path, keep=2)
    assert [p.name for p in removed] == ["stockmarket-20261010-010000.dump"]
    assert not backup.manifest_path(tmp_path / "stockmarket-20261010-010000.dump").exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".dump") == sorted(names[1:])


def test_list_shows_newest_first_and_flags_a_missing_note(tmp_path, capsys):
    for n in ("stockmarket-20261010-010000.dump", "stockmarket-20261012-010000.dump"):
        (tmp_path / n).write_bytes(b"x")
    backup.manifest_path(tmp_path / "stockmarket-20261012-010000.dump").write_text("{}")
    backup.cmd_list(tmp_path)
    out = capsys.readouterr().out
    assert out.index("20261012") < out.index("20261010") and out.count("can't be verified") == 1


# ---- the command ----

class Alerts:
    def __init__(self):
        self.shown = []

    def __call__(self, title, body):
        self.shown.append((title, body))


def test_main_backs_up_trims_and_shows_no_alert(src, bdir, monkeypatch):
    monkeypatch.setattr(backup, "live_db", lambda: SRC)
    for n in ("stockmarket-20200101-000000.dump", "stockmarket-20200102-000000.dump"):
        (bdir / n).write_bytes(b"x")
    alerts = Alerts()
    assert backup.main(["--keep", "2"], notify=alerts) == 0
    assert alerts.shown == [] and len(backup.list_backups(bdir)) == 2
    assert not (bdir / "stockmarket-20200101-000000.dump").exists()


def test_main_verify_and_restore_round_trip(src, bdir, monkeypatch, capsys):
    monkeypatch.setattr(backup, "live_db", lambda: SRC)
    assert backup.main([]) == 0
    assert backup.main(["verify"]) == 0
    assert "RESTORE VERIFIED" in capsys.readouterr().out
    newest = backup.list_backups(bdir)[0]
    assert backup.main(["restore", str(newest), "--into", COPY]) == 0
    assert backup.main(["restore", str(newest), "--into", COPY]) == 4  # exists, no --replace
    assert scalar(COPY, "SELECT count(*) FROM instruments") == 1


def test_main_verify_failure_exits_1(src, bdir, monkeypatch, capsys):
    monkeypatch.setattr(backup, "live_db", lambda: SRC)
    assert backup.main([]) == 0
    newest = backup.list_backups(bdir)[0]
    newest.write_bytes(newest.read_bytes()[:-50])
    assert backup.main(["verify"]) == 1
    assert "VERIFICATION FAILED" in capsys.readouterr().out


def test_main_exit_3_while_a_refresh_runs_with_no_alert(src, bdir, monkeypatch):
    monkeypatch.setattr(backup, "live_db", lambda: SRC)
    alerts = Alerts()
    with backup.connect_to(SRC) as other:
        other.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        assert backup.main(["--wait", "0"], notify=alerts) == 3
        other.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    assert alerts.shown == []


def test_main_exit_2_with_an_alert_when_the_database_is_unreachable(bdir, monkeypatch):
    monkeypatch.setattr(backup, "live_db", lambda: "zz_does_not_exist")
    alerts = Alerts()
    assert backup.main([], notify=alerts) == 2
    assert len(alerts.shown) == 1 and "Docker" in alerts.shown[0][1]
    assert backup.main(["--no-alert"], notify=alerts) == 2 and len(alerts.shown) == 1


def test_main_exit_4_with_an_alert_when_the_dump_fails(src, bdir, monkeypatch):
    monkeypatch.setattr(backup, "live_db", lambda: SRC)
    monkeypatch.setattr(backup, "take_backup", lambda **kw: (_ for _ in ()).throw(backup.BackupError("disk full")))
    alerts = Alerts()
    assert backup.main([], notify=alerts) == 4
    assert alerts.shown == [("Database backup FAILED", "disk full")]


def test_main_crash_is_exit_4_with_an_alert(bdir, monkeypatch):
    monkeypatch.setattr(backup, "take_backup", lambda **kw: 1 / 0)
    alerts = Alerts()
    assert backup.main([], notify=alerts) == 4
    assert alerts.shown and alerts.shown[0][0] == "Database backup crashed"


def test_main_verify_with_no_backups_is_an_error_without_an_alert(bdir):
    alerts = Alerts()
    assert backup.main(["verify"], notify=alerts) == 4 and alerts.shown == []
