"""Free, unofficial Yahoo Finance data. Fine for prototyping, not licensed for a public product."""
import math

import yfinance as yf

from .base import Instrument, PriceBar


def _num(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


class YFinanceSource:
    name = "yfinance"

    def get_instrument(self, symbol: str) -> Instrument:
        info = yf.Ticker(symbol).get_info()
        return Instrument(
            symbol=symbol.upper(),
            name=info.get("longName") or info.get("shortName"),
            exchange=info.get("exchange"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            currency=info.get("currency") or "USD",
        )

    def get_daily_bars(self, symbol: str, period: str = "5y") -> list[PriceBar]:
        df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        bars = []
        for ts, row in df.iterrows():
            close = _num(row["Close"])
            if close is None:
                continue
            volume = _num(row["Volume"])
            bars.append(
                PriceBar(
                    symbol=symbol.upper(),
                    ts=ts.date(),
                    open=_num(row["Open"]),
                    high=_num(row["High"]),
                    low=_num(row["Low"]),
                    close=close,
                    adj_close=_num(row["Adj Close"]),
                    volume=int(volume) if volume is not None else None,
                )
            )
        return bars
