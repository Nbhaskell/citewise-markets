from datetime import date

import pytest

from data.db import connect
from data.ingest import ingest_symbol
from data.sources.base import Instrument, PriceBar

SYMBOL = "ZZTEST"


class FakeSource:
    name = "fake"

    def __init__(self, bars):
        self._bars = bars

    def get_instrument(self, symbol):
        return Instrument(symbol=symbol, name="Test Co")

    def get_daily_bars(self, symbol, period="5y"):
        return self._bars


def bar(day, close):
    return PriceBar(SYMBOL, date(2024, 1, day), close, close, close, close, close, 100)


@pytest.fixture
def conn():
    with connect() as c:
        yield c
        c.rollback()
        c.execute("DELETE FROM prices_daily WHERE symbol = %s", (SYMBOL,))
        c.execute("DELETE FROM ingestion_runs WHERE symbol = %s", (SYMBOL,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYMBOL,))
        c.commit()


def count(conn):
    return conn.execute("SELECT count(*) FROM prices_daily WHERE symbol = %s", (SYMBOL,)).fetchone()[0]


def test_ingest_is_idempotent_and_updates(conn):
    assert ingest_symbol(conn, FakeSource([bar(2, 10.0), bar(3, 11.0)]), SYMBOL, "5y") == 2
    assert count(conn) == 2

    ingest_symbol(conn, FakeSource([bar(3, 12.5), bar(4, 13.0)]), SYMBOL, "5y")
    assert count(conn) == 3
    close = conn.execute(
        "SELECT close FROM prices_daily WHERE symbol = %s AND ts = %s", (SYMBOL, date(2024, 1, 3))
    ).fetchone()[0]
    assert float(close) == 12.5


def test_empty_result_is_logged_as_error(conn):
    with pytest.raises(ValueError):
        ingest_symbol(conn, FakeSource([]), SYMBOL, "5y")
    error = conn.execute(
        "SELECT error FROM ingestion_runs WHERE symbol = %s ORDER BY id DESC LIMIT 1", (SYMBOL,)
    ).fetchone()[0]
    assert "no price data" in error
    assert count(conn) == 0
