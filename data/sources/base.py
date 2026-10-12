"""The contract every market data source implements.

Swapping yfinance for a licensed feed means writing one new class here;
nothing downstream changes.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    currency: str = "USD"


@dataclass(frozen=True)
class PriceBar:
    symbol: str
    ts: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    adj_close: Optional[float]
    volume: Optional[int]


class PriceSource(Protocol):
    name: str

    def get_instrument(self, symbol: str) -> Instrument: ...

    def get_daily_bars(self, symbol: str, period: str = "5y") -> list[PriceBar]: ...
