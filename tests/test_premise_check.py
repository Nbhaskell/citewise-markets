"""A move the question assumes, checked against the stored closes (DECISIONS: "Fresh held-out round", fix 3).

"Google doubled this month. What drove it?" was answered as if it had (it rose about 1%). The prompt already says to correct a premise the
sources contradict, but the model does not always, and the project's rules want guarantees in code. `premise_cautions` reads the claim from the
question ("doubled", "plunge 20%", "skyrocketed"), compares it with the move over the window the price source shows, and attaches a plain
statement of what the closes show. It never says the question is wrong in its own voice: it quotes the claim and the data. It stays silent when
there is nothing to compare (no price source, several companies, a period it could not read) and for predictions and hypotheticals.
"""
from datetime import date

import pytest

from ai.copilot import answer_question
from ai.market import MarketEvidence, parse_window, premise_cautions
from data.db import connect
from test_copilot_fundamentals import FakeEmbedder, ScriptedLLM

TODAY = date(2026, 10, 16)


def price(symbol, pct):
    return MarketEvidence("price", symbol, f"{symbol} price data", f"Change {pct:+.2f}%", None, TODAY, change=pct, change_pct=pct)


def check(question, pct, symbol="ZZPC"):
    return premise_cautions(question, [price(symbol, pct)], parse_window(question, TODAY))


@pytest.mark.parametrize("question,pct,phrase", [
    ("Google doubled this month. What drove it?", 1.2, "doubled"),
    ("Why did Nvidia triple this year?", 40.0, "triple"),
    ("Why did Tesla halve in a week?", -3.0, "halve"),
    ("Why did Apple stock plunge 20% yesterday?", 0.5, "plunge 20%"),
    ("Why did Amazon stock fall 10% this week?", 9.0, "fall 10%"),      # the right size, the wrong direction
    ("Why did Amazon stock fall 10% this week?", -2.0, "fall 10%"),
    ("Has AMD jumped 15% this month?", 40.0, "jumped 15%"),
    ("Why did Microsoft skyrocket this week?", 0.8, "skyrocket"),
    ("Why is Apple stock crashing?", 6.0, "crashing"),
    ("Why did Tesla tank this week?", 5.0, "tank"),
    ("Is it true that Apple dropped by half this year?", -3.0, "dropped by half"),
    ("Why is Nvidia doubling this year?", 12.0, "doubling"),
    ("Why did Tesla crash this week?", -2.0, "crash"),                  # fell, but not what "crash" says
])
def test_a_claim_the_closes_do_not_support_gets_a_statement_of_what_they_show(question, pct, phrase):
    [caution] = check(question, pct)
    assert "ZZPC" in caution and phrase.lower() in caution.lower() and f"{pct:+.1f}%" in caution, caution
    assert parse_window(question, TODAY).label in caution


@pytest.mark.parametrize("question,pct", [
    ("Google doubled this month. What drove it?", 101.0),
    ("Google doubled this month. What drove it?", 85.0),
    ("Why did Nvidia triple this year?", 215.0),
    ("Why did Tesla halve in a week?", -52.0),
    ("Why did Tesla halve in a week?", -41.0),
    ("Why did Apple stock plunge 20% yesterday?", -19.4),
    ("Why did Amazon stock fall 10% this week?", -9.1),
    ("Why did Microsoft skyrocket this week?", 7.5),
    ("Why is Apple stock crashing?", -8.0),
    ("Why did Tesla crash this week?", -3.5),
    ("Is it true that Apple dropped by half this year?", -52.0),
    ("Did Apple stock rise 1% today?", 1.4),                              # a claim of a point or so is allowed a point of slack
    ("Did Apple stock rise 1% today?", 0.4),
])
def test_a_claim_the_closes_support_gets_nothing(question, pct):
    assert check(question, pct) == [], (question, pct)


@pytest.mark.parametrize("question,pct,fires", [
    ("Google doubled this month.", 79.0, True), ("Google doubled this month.", 80.5, False),
    ("Nvidia tripled this year.", 150.0, True), ("Nvidia tripled this year.", 165.0, False),
    ("Tesla halved this month.", -39.0, True), ("Tesla halved this month.", -41.0, False),
])
def test_the_thresholds_for_doubled_tripled_and_halved(question, pct, fires):
    assert bool(check(question, pct)) is fires


@pytest.mark.parametrize("question,pct", [
    ("Will Tesla stock soar next year?", -1.0),
    ("Could Nvidia crash this month?", 3.0),
    ("Is Tesla about to collapse this year?", 10.0),
    ("What if Apple stock doubles this year?", 1.0),
    ("Do you think Amazon will plunge 20% this month?", 4.0),
    ("Might Microsoft skyrocket over the next week?", -2.0),
    ("How has Tesla stock done this month?", 3.0),                       # no claim
    ("Why did Apple stock rise this week?", -2.0),                       # a plain direction is not checked
    ("Why did Apple stock fall this week?", 2.0),
])
def test_predictions_hypotheticals_and_plain_questions_are_silent(question, pct):
    assert check(question, pct) == [], question


def test_a_period_that_could_not_be_read_is_silent():
    # "last Friday" is a named day (window.day): the window shown is the default month, not that day, so the move is not comparable.
    assert check("Why did Apple stock crash last Friday?", 5.0) == []
    # and a period that is still unmet keeps it silent too
    assert check("Why did Apple stock crash at the end of last week?", 5.0) == []


def test_several_companies_or_no_price_source_is_silent():
    q = "Why did Google and Apple double this month?"
    w = parse_window(q, TODAY)
    assert premise_cautions(q, [price("AAA", 1.0), price("BBB", 2.0)], w) == []
    assert premise_cautions(q, [], w) == []
    assert premise_cautions(q, [MarketEvidence("headline", "AAA", "h", "t", "https://x", TODAY)], w) == []


def test_a_claim_with_no_stated_period_is_checked_against_the_default_window_and_says_which():
    [caution] = check("Why is Apple stock crashing?", 6.0)
    assert "past month" in caution


# ---- it reaches the answer ----

@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZPC', 'Premiseco')")
        first = date.fromordinal(TODAY.toordinal() - 399)
        for i in range(400):  # close = 100 + i: a month's change is about +6%
            c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES ('ZZPC', %s, %s, 'fake')",
                      (date.fromordinal(first.toordinal() + i), 100 + i))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM prices_daily WHERE symbol = 'ZZPC'")
        c.execute("DELETE FROM instruments WHERE symbol = 'ZZPC'")
        c.commit()


def test_the_caution_reaches_the_answer_to_a_question_that_assumes_a_doubling(conn):
    llm = ScriptedLLM("ZZPC closed at 499.00 on 2026-10-16 [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "ZZPC doubled this month. What drove it?", expand=False, today=TODAY)
    assert not ans.refused and any(e.kind == "price" for e in ans.retrieved)
    assert any("doubled" in c and "ZZPC" in c for c in ans.cautions), ans.cautions


def test_no_premise_caution_when_the_move_matches(conn):
    llm = ScriptedLLM("ZZPC closed at 499.00 on 2026-10-16 [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "Why did ZZPC stock soar this month?", expand=False, today=TODAY)
    assert not any("You mention" in c for c in ans.cautions), ans.cautions
