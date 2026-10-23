"""db/migrate.py with no database to talk to (a first-time user who has not started Docker, or has a wrong password).

It used to wait over two minutes and print a traceback. It now gives up after a timeout and says what to check, without printing the
password from DATABASE_URL.
"""
import importlib.util
from pathlib import Path

import psycopg
import pytest

MIGRATE = Path(__file__).resolve().parent.parent / "db" / "migrate.py"


def load_migrate():
    spec = importlib.util.spec_from_file_location("migrate_under_test", MIGRATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migrate(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone:hunter2@127.0.0.1:15999/stockmarket")
    return load_migrate()


def test_an_unreachable_database_exits_with_the_usual_cause_and_no_password(migrate, monkeypatch):
    def refuse(*args, **kwargs):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(migrate.psycopg, "connect", refuse)
    with pytest.raises(SystemExit) as stopped:
        migrate.main()
    message = str(stopped.value)
    assert "127.0.0.1:15999" in message and "docker compose up -d" in message and "POSTGRES_PASSWORD" in message
    assert "hunter2" not in message


def test_the_connection_is_given_a_timeout(migrate, monkeypatch):
    seen = {}

    def refuse(url, **kwargs):
        seen.update(kwargs)
        raise psycopg.OperationalError("timeout")

    monkeypatch.setattr(migrate.psycopg, "connect", refuse)
    with pytest.raises(SystemExit):
        migrate.main()
    assert 0 < seen["connect_timeout"] <= 30
