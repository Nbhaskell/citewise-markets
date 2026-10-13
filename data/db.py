import os
from pathlib import Path
from typing import Optional

import psycopg

ROOT = Path(__file__).resolve().parent.parent


def get_setting(name: str) -> Optional[str]:
    """Read a setting from the environment, falling back to the project's .env file."""
    value = os.environ.get(name)
    env_file = ROOT / ".env"
    if not value and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"')
    return value or None


def database_url() -> str:
    url = get_setting("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (copy .env.example to .env)")
    return url


CONNECT_TIMEOUT_SECONDS = 10  # without this, a database that isn't running can hang a connection for minutes


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url(), connect_timeout=CONNECT_TIMEOUT_SECONDS)
