"""Which tracked companies a piece of text names (by ticker, the first word of the name, or an alias), and which
removed ones."""
import re

import psycopg

from .market import NOT_NAMES

ALIASES = {"google": "GOOGL"}

# A ticker is matched in capitals only, unless it is safe to match as typed ("hows nvda doing"): at least three letters and not a word people
# type for other reasons ("now", "all", "can", "best"). A ticker that is added later and is also a word needs adding here.
LOWERCASE_TICKER_BLOCKLIST = frozenset(NOT_NAMES) | frozenset(
    "now new one two out key low big best fast good well work open real true safe post play snap line tech fund bank gold gas car sun run fit "
    "hot cool".split())


def lowercase_ticker_ok(symbol: str) -> bool:
    return len(symbol) >= 3 and symbol.lower() not in LOWERCASE_TICKER_BLOCKLIST


def company_mentions(conn: psycopg.Connection, text: str, include_removed: bool = False) -> dict[str, list[re.Match]]:
    """Every tracked company the text names (by ticker, first word of its name, or alias), with where it does so. A removed
    company (switched off, data still stored) is found only with `include_removed`: it is not tracked, so it is not answered."""
    found: dict[str, list[re.Match]] = {}
    for symbol, name in conn.execute(f"SELECT symbol, name FROM instruments {'' if include_removed else 'WHERE active '}ORDER BY symbol"):
        patterns = [(rf"\b{re.escape(symbol)}\b", re.IGNORECASE if lowercase_ticker_ok(symbol) else 0)]
        first = re.match(r"[A-Za-z]+", name or "")
        if first and len(first.group()) >= 4:
            patterns.append((rf"\b{re.escape(first.group())}\b", re.IGNORECASE))
        patterns += [(rf"\b{alias}\b", re.IGNORECASE) for alias, s in ALIASES.items() if s == symbol]
        matches = [m for p, flags in patterns for m in re.finditer(p, text, flags)]
        if matches:
            found[symbol] = sorted(matches, key=lambda m: m.start())
    return found


def detect_symbols(conn: psycopg.Connection, question: str) -> list[str]:
    return list(company_mentions(conn, question))


def removed_company_named(conn: psycopg.Connection, text: str) -> str | None:
    """The words of the text that name a company that was removed (as written in the question), or None. Its filings and
    prices are still stored, so without this a question about it would be answered from other companies' filings."""
    named = company_mentions(conn, text, include_removed=True)
    active = company_mentions(conn, text)
    gone = sorted((m for sym, ms in named.items() if sym not in active for m in ms), key=lambda m: m.start())
    return gone[0].group() if gone else None
