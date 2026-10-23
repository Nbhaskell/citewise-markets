"""Apply db/migrations/*.sql in filename order, once each.

Usage: python db/migrate.py   (reads DATABASE_URL from the environment or .env)
"""
import os
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    env_file = ROOT / ".env"
    if not url and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    if not url:
        sys.exit("DATABASE_URL is not set (copy .env.example to .env)")
    return url


def connect() -> psycopg.Connection:
    """Connect, or exit with the usual cause. Without a timeout a database that is not running hung for over two minutes and then
    printed a traceback."""
    url = database_url()
    try:
        return psycopg.connect(url, autocommit=True, connect_timeout=10)
    except psycopg.OperationalError:
        where = conninfo_to_dict(url)
        sys.exit(
            f"Can't reach the database at {where.get('host', 'localhost')}:{where.get('port', 5432)}. "
            "Is it running? Start it with: docker compose up -d (then wait until it is healthy), "
            "and check that DATABASE_URL in .env matches POSTGRES_PASSWORD."
        )


def main() -> None:
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            print(f"applying {path.name}")
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
    print("up to date")


if __name__ == "__main__":
    main()
