"""A table's unit sentence ("in millions, except ... thousands") can end up in the passage before the table.

Filings are cut into roughly 1,000-character passages, and the cut often falls between that sentence and its table. The
copilot is then shown a table of bare numbers: Apple's buyback table reached the model without "reflected in thousands"
and "26,223" came back as 26,223 shares. When a table passage has no unit statement of its own, the nearest one from the
passages just before it is attached, in code, when the prompt is built. Stored data and the search index are untouched.
"""
from datetime import date

import pytest

from ai.copilot import answer_question
from ai.index_filings import vector_literal
from ai.search import SearchResult
from ai.table_units import UNIT_NOTE_PREFIX, add_units, is_table_like, unit_note
from data.db import connect

UNITS = "(in millions, except number of shares, which are reflected in thousands, and per-share amounts)"
TABLE = "\n".join(["Periods", "Total Number", "of Shares Purchased", "Average Price", "Paid Per Share"]
                  + ["May 3, 2026 to May 30, 2026:", "26,920", "$", "297.18", "26,920", "May 31, 2026 to June 27, 2026:",
                     "26,223", "$", "296.18", "26,223", "Total", "79,611", "$", "138,004", "(1)"])
PROSE = ("The Company announced a program to repurchase up to $100 billion of its common stock. The programs do not "
         "obligate the Company to acquire a minimum amount of shares. Under the programs, shares may be repurchased in "
         "privately negotiated or open market transactions, including under plans complying with Rule 10b5-1.")


# ---- recognizing a table ----

def test_a_column_of_numbers_is_a_table_and_prose_is_not():
    assert is_table_like(TABLE)
    assert not is_table_like(PROSE)
    assert not is_table_like("26,223\n$\n296.18")  # too short to call a table


# ---- the database: a fake filing cut into passages ----

def vec(i):
    v = [0.0] * 384
    v[i] = 1.0
    return v


@pytest.fixture
def db():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZTU', 'Tableco Inc.')")
        for acc in ("0-ZT-A", "0-ZT-B"):
            c.execute("INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                      "VALUES (%s, 'ZZTU', '1', '10-Q', %s, 'https://x', 't')", (acc, date(2026, 7, 31)))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM filings WHERE symbol = 'ZZTU'")
        c.execute("DELETE FROM instruments WHERE symbol = 'ZZTU'")
        c.commit()


def passages(db, acc, texts):
    """Store `texts` as chunks 0, 1, 2... of one filing; return them as SearchResults."""
    out = []
    for i, text in enumerate(texts):
        cid = db.execute(
            "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
            "VALUES (%s, %s, 'Part II, Item 2', %s, %s::vector, 'fake') RETURNING id",
            (acc, i, text, vector_literal(vec(0)))).fetchone()[0]
        out.append(SearchResult(cid, acc, "ZZTU", "10-Q", date(2026, 7, 31), None, "https://x", "Part II, Item 2", text, 1.0))
    db.commit()
    return out


def test_a_table_gets_the_units_stated_just_before_it(db):
    before, table = passages(db, "0-ZT-A", [f"Share repurchase activity was as follows {UNITS}:", TABLE])
    assert unit_note(db, table) == UNITS
    [got] = add_units(db, [table])
    assert got.text.startswith(UNIT_NOTE_PREFIX) and UNITS in got.text.splitlines()[0]
    assert got.text.endswith(TABLE)  # the passage itself is unchanged underneath
    assert got.chunk_id == table.chunk_id and got.accession_number == "0-ZT-A"


def test_a_table_with_its_own_units_is_left_alone(db):
    own = f"Share repurchase activity was as follows {UNITS}:\n" + TABLE
    older = "(in thousands) something else entirely"
    _, table = passages(db, "0-ZT-A", [older, own])
    assert unit_note(db, table) is None and add_units(db, [table])[0].text == own


def test_prose_is_never_given_units(db):
    _, prose = passages(db, "0-ZT-A", [f"Amounts are shown {UNITS}:", PROSE])
    assert unit_note(db, prose) is None and add_units(db, [prose])[0].text == PROSE


def test_nothing_is_invented_when_no_units_were_stated_nearby(db):
    _, _, table = passages(db, "0-ZT-A", ["Some prose about risks.", "More prose about competition.", TABLE])
    assert unit_note(db, table) is None and add_units(db, [table])[0].text == TABLE


def test_units_from_too_far_back_are_not_used(db):
    """A unit statement three passages back may belong to another table, and a wrong unit is worse than none."""
    *_, table = passages(db, "0-ZT-A", [f"Amounts are shown {UNITS}:", "Prose one.", "Prose two.", "Prose three.", TABLE])
    assert unit_note(db, table) is None


def test_the_nearest_statement_wins(db):
    older, newer = "(in billions, except per-share amounts)", "(in millions, except per-share amounts)"
    *_, table = passages(db, "0-ZT-A", [f"First table {older}:", f"Second table {newer}:", TABLE])
    assert unit_note(db, table) == newer


def test_the_first_passage_of_a_filing_has_nothing_before_it(db):
    [table] = passages(db, "0-ZT-A", [TABLE])
    assert unit_note(db, table) is None


def test_another_filings_units_are_never_borrowed(db):
    passages(db, "0-ZT-B", [f"Amounts are shown {UNITS}:"])
    [table] = passages(db, "0-ZT-A", [TABLE])
    assert unit_note(db, table) is None


def test_every_passage_is_handled_and_the_order_is_kept(db):
    _, table_a = passages(db, "0-ZT-A", [f"Shown {UNITS}:", TABLE])
    [prose_b] = passages(db, "0-ZT-B", [PROSE])
    got = add_units(db, [prose_b, table_a])
    assert [g.chunk_id for g in got] == [prose_b.chunk_id, table_a.chunk_id]
    assert got[0].text == PROSE and got[1].text.startswith(UNIT_NOTE_PREFIX)


# ---- through the whole copilot, with a fake model ----

class FakeEmbedder:
    name = "fake"
    dim = 384

    def embed_query(self, text):
        return vec(0)


class RecordingLLM:
    name = "recording"

    def __init__(self):
        self.prompts = []

    def generate(self, system, user, json_schema=None):
        if system.startswith("Rewrite a question"):
            return ""
        self.prompts.append(user)
        return "The table is in the source [1]."


def test_the_model_is_shown_the_units_with_the_table(db):
    passages(db, "0-ZT-A", [f"Share repurchase activity was as follows {UNITS}:", TABLE])
    llm = RecordingLLM()
    ans = answer_question(db, FakeEmbedder(), llm, "What are Tableco's biggest risks?", expand=False)
    shown = "\n".join(llm.prompts)
    assert TABLE in shown and f"{UNIT_NOTE_PREFIX}" in shown and "reflected in thousands" in shown
    assert any(UNIT_NOTE_PREFIX in r.text for r in ans.retrieved)  # and the reader sees the same excerpt
