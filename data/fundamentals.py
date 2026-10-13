"""Trailing-twelve-month figures, margins, market value, and P/E, computed from the SEC figures stored by
`data.ingest_fundamentals`. Python computes every number here; nothing is a model's guess.

Usage: python -m data.fundamentals AAPL MSFT      print the figures, where each one came from, and any cautions

How a trailing-twelve-month (TTM) figure is built: companies file a full-year total (10-K) and year-to-date totals in
each 10-Q (3, 6, or 9 months). TTM = last full year + this year so far - the same stretch last year. If the latest
filing already covers 12 months, that is the figure. Every figure carries the period it covers and the filings it
came from, and unusual situations produce a plain-language caution instead of a quiet number.
"""
import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import psycopg

from .db import connect
from .sources.edgar import Fact

# Several names are in use for the same thing (see WANTED_FACTS); the first current one in each list is used.
REVENUE = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet")
NET_INCOME = ("NetIncomeLoss", "ProfitLoss")  # NetIncomeLoss is the part belonging to the shareholders
EPS = ("EarningsPerShareDiluted",)
OPERATING_INCOME = ("OperatingIncomeLoss",)
GROSS_PROFIT = ("GrossProfit",)
WEIGHTED_SHARES = ("WeightedAverageNumberOfDilutedSharesOutstanding",)
BALANCE_SHEET_SHARES = ("CommonStockSharesOutstanding",)
COVER_SHARES = ("EntityCommonStockSharesOutstanding",)

STALE_CONCEPT_DAYS = 100    # a concept whose latest figure is older than this, next to a newer one, is a leftover
OLD_FIGURES_DAYS = 200      # the latest period is older than this: a filing is overdue or the data is stale
OLD_PRICE_DAYS = 7
PROFIT_VS_OPERATING = 1.2   # net income this many times operating income points at non-operating gains
SHARE_COUNT_GAP = 0.05      # cover-page shares vs the latest weighted average
EPS_SHARE_GAP = 0.10        # net income / EPS vs the weighted average share count


@dataclass(frozen=True)
class Flow:
    """A figure covering a stretch of time (revenue, profit): its TTM value and how it was built."""

    value: float
    how: str                      # plain-language recipe, with the dates
    period_end: date              # where the latest filed period ends
    growth: Optional[float]       # latest period vs the same period a year earlier (0.12 = up 12%)
    growth_label: str
    accessions: tuple[str, ...]   # the filings the pieces came from


@dataclass(frozen=True)
class Shares:
    value: float
    source: str                   # where the count was read
    as_of: date


@dataclass
class Fundamentals:
    symbol: str
    available: bool = False
    unavailable_reason: str = ""
    period_end: Optional[date] = None
    revenue: Optional[Flow] = None
    net_income: Optional[Flow] = None
    diluted_eps: Optional[Flow] = None
    operating_income: Optional[Flow] = None
    gross_profit: Optional[Flow] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    shares: Optional[Shares] = None
    close: Optional[float] = None
    close_date: Optional[date] = None
    market_value: Optional[float] = None
    pe: Optional[float] = None
    pe_note: str = ""
    cautions: list[str] = field(default_factory=list)


def load_facts(conn: psycopg.Connection, symbol: str) -> list[Fact]:
    rows = conn.execute(
        "SELECT taxonomy, concept, unit, period_start, period_end, value, accession_number, form, filed_at "
        "FROM financial_facts WHERE symbol = %s", (symbol.upper(),)).fetchall()
    return [Fact(r[0], r[1], r[2], r[3], r[4], float(r[5]), r[6], r[7], r[8]) for r in rows]


def latest_close(conn: psycopg.Connection, symbol: str) -> tuple[Optional[float], Optional[date]]:
    row = conn.execute("SELECT close, ts FROM prices_daily WHERE symbol = %s ORDER BY ts DESC LIMIT 1", (symbol.upper(),)).fetchone()
    return (float(row[0]), row[1]) if row else (None, None)


# ---- picking figures ----

def _periods(facts: list[Fact], concept: str) -> dict[tuple[Optional[date], date], Fact]:
    """One figure per period. A restated figure comes from a later filing, so the newest filing wins."""
    out: dict[tuple[Optional[date], date], Fact] = {}
    for f in sorted((f for f in facts if f.concept == concept), key=lambda f: (f.filed_at, f.accession_number)):
        out[(f.period_start, f.period_end)] = f
    return out


def _choose(facts: list[Fact], names: tuple[str, ...]) -> dict[tuple[Optional[date], date], Fact]:
    """The periods of the first concept in `names` that is current. A concept whose latest figure is far older than
    another's is a leftover from an earlier naming (Apple's pre-2018 revenue name, Amazon's 2009 gross profit)."""
    candidates = {n: _periods(facts, n) for n in names}
    latest = {n: max(k[1] for k in p) for n, p in candidates.items() if p}
    if not latest:
        return {}
    newest = max(latest.values())
    for n in names:
        if n in latest and (newest - latest[n]).days <= STALE_CONCEPT_DAYS:
            return candidates[n]
    return {}


def _dur(period: tuple[Optional[date], date]) -> int:
    return (period[1] - period[0]).days


def _near(a: date, b: date, tol: int) -> bool:
    return abs((a - b).days) <= tol


def trailing(periods: dict[tuple[Optional[date], date], Fact]) -> tuple[Optional[Flow], str]:
    """The trailing-twelve-month figure and the plain reason if it can't be built."""
    flows = {k: f for k, f in periods.items() if k[0] is not None and _dur(k) > 60}
    if not flows:
        return None, "no period figures stored"
    latest = max(flows, key=lambda k: (k[1], _dur(k)))
    last = flows[latest]
    year_ago = latest[1] - timedelta(days=365)

    if _dur(latest) >= 340:  # the filing already covers a full year
        prior = next((flows[k] for k in sorted(flows, key=lambda k: abs((k[1] - year_ago).days))
                      if _dur(k) >= 340 and _near(k[1], year_ago, 12)), None)
        growth = last.value / prior.value - 1 if prior and prior.value > 0 else None
        return Flow(last.value, f"the 12 months ending {latest[1]}", latest[1], growth,
                    f"the 12 months ending {latest[1]} vs the 12 months a year earlier",
                    (last.accession_number,)), ""

    months = round(_dur(latest) / 30.4)
    year = next((flows[k] for k in flows if _dur(k) >= 340 and _near(k[1], latest[0] - timedelta(days=1), 10)), None)
    if year is None:
        return None, f"the last full year before {latest[0]} isn't in the stored data"
    prior = next((flows[k] for k in sorted(flows, key=lambda k: abs((k[1] - year_ago).days))
                  if _near(k[1], year_ago, 12) and abs(_dur(k) - _dur(latest)) <= 10), None)
    if prior is None:
        return None, f"the same {months} months a year before {latest[1]} aren't in the stored data"
    value = year.value + last.value - prior.value
    how = (f"the last full year (ended {year.period_end}) + the {months} months to {latest[1]} "
           f"- the same {months} months a year earlier")
    growth = last.value / prior.value - 1 if prior.value > 0 else None
    return Flow(value, how, latest[1], growth, f"the {months} months to {latest[1]} vs the same {months} months a year earlier",
                (year.accession_number, last.accession_number, prior.accession_number)), ""


def _shares(facts: list[Fact]) -> Optional[Shares]:
    """Shares outstanding. The cover-page count is the freshest; a company with several share classes may have none
    (Alphabet), and then the balance-sheet total is used."""
    def newest(names):
        found = [f for n in names for f in facts if f.concept == n and f.period_start is None]
        return max(found, key=lambda f: (f.period_end, f.filed_at), default=None)

    cover, sheet = newest(COVER_SHARES), newest(BALANCE_SHEET_SHARES)
    if cover and not (sheet and (sheet.period_end - cover.period_end).days > STALE_CONCEPT_DAYS):
        return Shares(cover.value, f"the cover page of the {cover.form} filed {cover.filed_at}", cover.period_end)
    if sheet:
        return Shares(sheet.value, f"the balance sheet at {sheet.period_end} ({sheet.form} filed {sheet.filed_at})", sheet.period_end)
    return None


# ---- the calculation ----

def compute(symbol: str, facts: list[Fact], close: Optional[float], close_date: Optional[date],
            today: Optional[date] = None) -> Fundamentals:
    today = today or date.today()
    out = Fundamentals(symbol.upper(), close=close, close_date=close_date)
    reasons: dict[str, str] = {}

    def flow(name: str, names: tuple[str, ...]) -> Optional[Flow]:
        periods = _choose(facts, names)
        result, why = trailing(periods) if periods else (None, "no figures stored")
        if result is None:
            reasons[name] = why
        return result

    if not facts:
        out.unavailable_reason = ("no financial figures are stored for this company: they haven't been downloaded yet, or "
                                  "it reports under another accounting standard (a foreign filer) that isn't supported")
        return out

    out.revenue, out.net_income = flow("revenue", REVENUE), flow("net income", NET_INCOME)
    out.diluted_eps, out.operating_income = flow("diluted EPS", EPS), flow("operating income", OPERATING_INCOME)
    out.gross_profit = flow("gross profit", GROSS_PROFIT)
    anchor = (out.revenue or out.diluted_eps or out.net_income)
    if anchor is None:
        out.unavailable_reason = "the stored figures can't be turned into twelve-month totals: " + "; ".join(
            f"{k}: {v}" for k, v in reasons.items())
        return out
    out.available, out.period_end = True, anchor.period_end

    # Gross profit is simply absent for some companies, and a leftover from an older period is as good as absent.
    if out.gross_profit is not None and abs((out.gross_profit.period_end - anchor.period_end).days) > 30:
        out.gross_profit = None

    named = {"revenue": out.revenue, "net income": out.net_income, "diluted EPS": out.diluted_eps,
             "operating income": out.operating_income, "gross profit": out.gross_profit}
    for name, f in named.items():
        if f is not None and abs((f.period_end - anchor.period_end).days) > 30:
            out.cautions.append(f"{name} is for the period ending {f.period_end}, not {anchor.period_end} like the rest")
    for name in ("revenue", "net income", "diluted EPS", "operating income"):
        if named[name] is None:
            out.cautions.append(f"{name} isn't available: {reasons.get(name)}")
    # gross profit is simply absent for some companies (Alphabet reports none), so that is not a caution

    if out.revenue and out.revenue.value > 0:
        for attr, f in (("gross_margin", out.gross_profit), ("operating_margin", out.operating_income), ("net_margin", out.net_income)):
            if f is not None and abs((f.period_end - out.revenue.period_end).days) <= 30:
                setattr(out, attr, f.value / out.revenue.value)

    out.shares = _shares(facts)
    if out.shares and close:
        out.market_value = out.shares.value * close
    if out.diluted_eps is not None and close:
        if out.diluted_eps.value > 0:
            out.pe = close / out.diluted_eps.value
        else:
            out.pe_note = "not meaningful: earnings per share over the last twelve months is zero or negative"
    elif close and out.diluted_eps is None:
        out.pe_note = "not available: no earnings per share figure"

    # ---- cautions: places where a correct number could still mislead ----
    if (today - anchor.period_end).days > OLD_FIGURES_DAYS:
        out.cautions.append(f"the latest reported period ended {anchor.period_end}, which is old; a filing may be missing")
    if close_date is not None and (today - close_date).days > OLD_PRICE_DAYS:
        out.cautions.append(f"the stored price is from {close_date}, so market value and P/E use an old price")
    if close is None:
        out.cautions.append("no stored price, so market value and P/E can't be computed")
    ni, op = out.net_income, out.operating_income
    if ni and op and ni.value > 0 and ni.value > PROFIT_VS_OPERATING * max(op.value, 0):
        ratio = f"{ni.value / op.value:.1f} times" if op.value > 0 else "positive despite an operating loss, and"
        out.cautions.append(
            f"net income is {ratio} operating income, which usually means gains outside the core business "
            "(such as investments), so earnings per share and P/E may flatter the company")
    weighted = _choose(facts, WEIGHTED_SHARES)
    wavg = weighted[max(weighted, key=lambda k: (k[1], _dur(k) if k[0] else 0))].value if weighted else None
    if out.shares and wavg and abs(out.shares.value / wavg - 1) > SHARE_COUNT_GAP:
        out.cautions.append(
            f"the share count ({out.shares.value / 1e9:.2f} billion, from {out.shares.source}) differs from the latest "
            f"average used for earnings per share ({wavg / 1e9:.2f} billion) by {abs(out.shares.value / wavg - 1):.0%}, "
            "so market value depends on which one is used (new shares may have been issued)")
    if out.shares and out.shares.source.startswith("the balance sheet"):
        out.cautions.append(f"the share count is from the balance sheet date ({out.shares.as_of}), not the filing's cover page")
    if ni and out.diluted_eps and wavg and ni.value > 0 and out.diluted_eps.value > 0:
        implied = ni.value / out.diluted_eps.value
        if abs(implied / wavg - 1) > EPS_SHARE_GAP:
            out.cautions.append("net income and earnings per share imply a share count that differs from the reported "
                                f"average by {abs(implied / wavg - 1):.0%}; one of the figures may cover a different period")
    return out


# ---- display ----

def _money(v: float) -> str:
    return f"${v / 1e12:,.2f} trillion" if abs(v) >= 1e12 else f"${v / 1e9:,.1f} billion"


def format_report(f: Fundamentals) -> str:
    if not f.available:
        return f"{f.symbol}: not available - {f.unavailable_reason}"
    lines = [f"{f.symbol}  (latest reported period ends {f.period_end}; price {f.close if f.close else 'n/a'} on {f.close_date})"]

    def line(label: str, flow: Optional[Flow], fmt) -> None:
        if flow is not None:
            lines.append(f"  {label:<20} {fmt(flow.value):<18} = {flow.how}")

    line("revenue", f.revenue, _money)
    if f.revenue and f.revenue.growth is not None:
        lines.append(f"  {'revenue growth':<20} {f.revenue.growth:+.1%}{'':<12} = {f.revenue.growth_label}")
    line("net income", f.net_income, _money)
    line("diluted EPS", f.diluted_eps, lambda v: f"${v:.2f}")
    line("operating income", f.operating_income, _money)
    for label, value in (("gross margin", f.gross_margin), ("operating margin", f.operating_margin), ("net margin", f.net_margin)):
        if value is not None:
            lines.append(f"  {label:<20} {value:.1%}")
    if f.shares:
        lines.append(f"  {'shares outstanding':<20} {f.shares.value / 1e9:.2f} billion   = {f.shares.source}")
    if f.market_value:
        lines.append(f"  {'market value':<20} {_money(f.market_value)}  = shares x latest close")
    lines.append(f"  {'P/E':<20} " + (f"{f.pe:.1f}  = latest close / diluted EPS (last 12 months)" if f.pe else f.pe_note or "not available"))
    lines += [f"  CAUTION: {c}" for c in f.cautions]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+")
    args = parser.parse_args(argv)
    with connect() as conn:
        for symbol in args.symbols:
            close, close_date = latest_close(conn, symbol)
            print(format_report(compute(symbol, load_facts(conn, symbol), close, close_date)), end="\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
