"""Give a table passage the unit sentence that the cut between passages separated from it.

Filings are cut into passages of roughly 1,000 characters, and the cut often falls between a table's unit sentence ("in
millions, except number of shares, which are reflected in thousands") and the table itself. The model is then shown bare
numbers and cannot tell millions from thousands: Apple's buyback table came back as "26,223 shares" (it is in thousands).
Measured on the stored filings, 283 of 1,479 table passages had their units cut off in the passage just before, and
another 321 had no unit statement nearby at all.

This runs when the prompt is built, so the stored passages and the search index are unchanged. It only ever copies words
that the filing itself states, from the nearest of the two passages before, and says where they came from. If no unit
statement is found it adds nothing: a wrong unit would be worse than none.
"""
import dataclasses
import re

import psycopg

from .search import SearchResult

LOOKBACK = 2  # passages before the table that may hold its unit sentence; further back it may belong to another table
UNIT_NOTE_PREFIX = "[Units stated just before this table:"

UNIT_RE = re.compile(
    r"\(\s*in\s+(?:thousands|millions|billions)|\bin\s+(?:thousands|millions|billions)\b|reflected\s+in\s+(?:thousands|millions)",
    re.IGNORECASE,
)
_PARENTHETICAL_RE = re.compile(r"\([^()]{0,300}\)")
_NUMBERISH_LINE_RE = re.compile(r"[\$\(\)\s\d,.\-—%]+")


def is_table_like(text: str) -> bool:
    """Mostly short lines of numbers (the flattened text of a table), and long enough to be more than a stray figure."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 12:
        return False
    return sum(1 for line in lines if _NUMBERISH_LINE_RE.fullmatch(line)) / len(lines) >= 0.35


def _statement_in(text: str) -> str | None:
    """The last unit statement in `text`: the parenthetical that holds it, or else the words around it."""
    matches = list(UNIT_RE.finditer(text))
    if not matches:
        return None
    for paren in reversed(list(_PARENTHETICAL_RE.finditer(text))):
        if UNIT_RE.search(paren.group()):
            return " ".join(paren.group().split())
    last = matches[-1]
    return " ".join(text[max(0, last.start() - 1): last.end() + 160].split())


def unit_note(conn: psycopg.Connection, passage: SearchResult) -> str | None:
    """The unit statement for a table passage that has none of its own, or None."""
    if not is_table_like(passage.text) or UNIT_RE.search(passage.text):
        return None
    before = conn.execute(
        "SELECT p.text FROM filing_chunks c JOIN filing_chunks p "
        "ON p.accession_number = c.accession_number AND p.chunk_index < c.chunk_index AND p.chunk_index >= c.chunk_index - %s "
        "WHERE c.id = %s ORDER BY p.chunk_index DESC",
        (LOOKBACK, passage.chunk_id),
    ).fetchall()
    for (text,) in before:  # nearest first
        if statement := _statement_in(text):
            return statement
    return None


def add_units(conn: psycopg.Connection, passages: list[SearchResult]) -> list[SearchResult]:
    out = []
    for passage in passages:
        note = unit_note(conn, passage)
        out.append(dataclasses.replace(passage, text=f"{UNIT_NOTE_PREFIX} {note}]\n{passage.text}") if note else passage)
    return out
