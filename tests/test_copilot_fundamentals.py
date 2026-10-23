"""The copilot answering revenue, profit, market value, and P/E questions from the stored SEC figures.

Python computes every figure (data/fundamentals.py); the copilot only quotes them as a numbered source. These tests pin
down: which questions go to the figures, what the source says, that cautions reach the answer whether or not the model
repeats them, and that the existing checks (numbers, direction, no advice) still apply to the new source.
"""
from datetime import date

import pytest

from ai.copilot import FIGURES_RULES, NO_COMPANY, SYSTEM_PROMPT, answer_question
from ai.market import (
    MarketEvidence,
    detect_intent,
    evidence_from_fundamentals,
    fundamentals_evidence,
    gather_market_evidence,
    parse_window,
    relevant_cautions,
)
from ai.copilot import unverified_numbers
from data.db import connect
from data.fundamentals import compute
from test_fundamentals import B, company, fact

A = "ZZFC"  # the test company; its name starts "Funco"
TODAY = date(2026, 10, 12)
MODEL = "fake-llm"


# ---- which questions go to the figures ----

@pytest.mark.parametrize("question,topics", [
    ("What is Nvidia's P/E ratio?", {"pe"}),
    ("Tell me Amazon's price-to-earnings ratio.", {"pe"}),
    ("What's Apple's PE ratio?", {"pe"}),
    ("What is Microsoft's market cap?", {"market_value"}),
    ("What is Tesla's market capitalization?", {"market_value"}),
    ("What is Apple's market value?", {"market_value"}),
    ("What's Alphabet's earnings per share?", {"eps"}),
    ("What was Microsoft's revenue over the last twelve months?", {"revenue"}),
    ("How fast is Nvidia's revenue growing?", {"revenue"}),
    ("How much net income did Amazon earn?", {"profit"}),
    ("What are Tesla's profit margins?", {"profit", "margin"}),
    ("What is Tesla's operating margin?", {"margin"}),
    ("How many shares outstanding does Apple have?", {"shares"}),
    ("Give me Apple's key financials", {"general"}),
])
def test_figures_questions_are_recognized(question, topics):
    assert detect_intent(question).fundamentals == frozenset(topics), question


@pytest.mark.parametrize("question", [
    "What does Apple's 10-K say about revenue?",
    "How much revenue did Amazon report in its annual report?",
    "What was Microsoft's revenue last quarter?",          # the figures are twelve-month totals, so a quarter goes to the 10-Q
    "In its latest filing, what total revenue did Microsoft report?",
    "Why is Apple's revenue growing?",                      # a "why" about revenue is a filings question (MD&A explains it)
    "What drove Nvidia's profit?",                          # same
    "What are Nvidia's biggest risks?",
    "How many employees does Tesla have?",
    "What does the 10-K say about stock-based compensation?",
    "How has Nvidia stock done this month?",
    "Should I buy Tesla stock?",
])
def test_other_questions_do_not_get_the_figures(question):
    assert detect_intent(question).fundamentals == frozenset(), question


def test_a_specific_term_still_counts_when_the_question_names_a_filing_word():
    # "P/E" has no filing equivalent, so quarter/annual wording doesn't take it away (the source states its own period)
    assert detect_intent("What was Apple's P/E last quarter?").fundamentals == frozenset({"pe"})
    assert detect_intent("Why is Alphabet's P/E so low?").fundamentals == frozenset({"pe"})


def test_filings_are_searched_only_when_the_question_also_asks_for_them():
    pe = detect_intent("What is Nvidia's P/E ratio?")
    assert pe.fundamentals and not pe.filings and not pe.prices and pe.market
    revenue = detect_intent("What was Microsoft's revenue over the last twelve months?")
    assert revenue.fundamentals and not revenue.filings  # "revenue" is what the figures answer, not a reason to search filings
    mixed = detect_intent("What is Apple's P/E, and what are its biggest risks?")
    assert mixed.fundamentals and mixed.filings
    both = detect_intent("What is Microsoft's P/E ratio and how has the stock done this month?")
    assert both.fundamentals and both.prices and not both.filings


def test_other_routing_is_unchanged():
    got = detect_intent("How's Amazon doing?")
    assert (got.prices, got.headlines, got.fundamentals, got.filings) == (True, True, frozenset(), False)
    plain = detect_intent("What are Nvidia's biggest risks?")
    assert plain.filings and not plain.market


# ---- what the source says ----

def figures(**drop):
    return compute(A, company(**drop), 24.0, TODAY, TODAY)


def test_the_source_states_every_figure_with_its_period_and_recipe():
    ev = evidence_from_fundamentals(figures())
    assert ev.kind == "fundamentals" and ev.symbol == A and ev.url is None and ev.as_of == date(2026, 6, 30)
    assert "calculated in Python" in ev.text
    for line in (
        "Revenue (last 12 months): $120.0 billion",
        "Net income (last 12 months): $24.0 billion",
        "Diluted earnings per share (last 12 months): $2.40",
        "Operating income (last 12 months): $30.0 billion",
        "Gross margin: 50.0%", "Operating margin: 25.0%", "Net margin: 20.0%",
        "Latest stored close: 24.00 on 2026-10-12",
        "Market value: $242.4 billion",
        "P/E ratio: 10.0",
    ):
        assert line in ev.text, line
    assert "the last full year (ended 2025-12-31)" in ev.text  # the recipe travels with the figure
    assert "Revenue growth: +50.0%" in ev.text and "an increase" in ev.text
    assert "CAUTION" not in ev.text and ev.cautions == ()


def test_growth_direction_is_written_in_words_and_checked():
    ev = evidence_from_fundamentals(figures())
    assert unverified_numbers("Revenue rose 50.0% over the period [1].", [1], [ev]) == []
    wrong = unverified_numbers("Revenue fell by 50.0% [1].", [1], [ev])  # right digits, wrong direction
    assert wrong and "stored growth is +50.0%" in wrong[0] and "an increase" in wrong[0]


def test_a_decline_is_called_a_decrease():
    facts = [f for f in company() if f.concept != "Revenues"]
    for start, end, v, accn in (("2025-01-01", "2025-12-31", 100, "fy25"), ("2025-01-01", "2025-06-30", 60, "h1-25"),
                                ("2026-01-01", "2026-06-30", 40, "h1-26")):
        facts.append(fact("Revenues", start, end, v * B, accn, "10-K", "2026-02-05"))
    ev = evidence_from_fundamentals(compute(A, facts, 24.0, TODAY, TODAY))
    assert "Revenue growth: -33.3%" in ev.text and "a decrease" in ev.text
    assert unverified_numbers("Revenue grew 33.3% [1].", [1], [ev])
    assert unverified_numbers("Revenue fell 33.3% [1].", [1], [ev]) == []


def test_a_wrong_pe_or_a_rounded_one_is_flagged_like_any_other_figure():
    ev = evidence_from_fundamentals(figures())
    assert unverified_numbers("The P/E ratio is 10.0 [1].", [1], [ev]) == []
    assert unverified_numbers("The P/E ratio is 12.5 [1].", [1], [ev]) == ["12.5"]
    assert unverified_numbers("The market value is $242 billion [1].", [1], [ev]) == ["242"]  # the model rounded it


def test_no_figures_is_said_plainly_with_the_reason():
    ev = evidence_from_fundamentals(compute("ZZFOR", [], 24.0, TODAY, TODAY))
    assert ev.kind == "fundamentals" and "not available" in ev.text and "foreign filer" in ev.text
    assert "P/E ratio:" not in ev.text and ev.cautions == ()


def test_negative_earnings_have_no_pe_and_the_source_says_why():
    facts = [f for f in company() if f.concept != "EarningsPerShareDiluted"] + [
        fact("EarningsPerShareDiluted", "2025-01-01", "2025-12-31", -1.0, "fy25", "10-K", "2026-02-05", "USD/shares"),
        fact("EarningsPerShareDiluted", "2025-01-01", "2025-06-30", -0.5, "h1-25", "10-Q", "2025-07-30", "USD/shares"),
        fact("EarningsPerShareDiluted", "2026-01-01", "2026-06-30", -0.4, "h1-26", "10-Q", "2026-07-30", "USD/shares")]
    ev = evidence_from_fundamentals(compute(A, facts, 24.0, TODAY, TODAY))
    assert "P/E ratio: not meaningful" in ev.text


def gains_company():
    """Net income 72 against operating income 30, with earnings per share to match (7.20): the 'investment gains'
    situation (Alphabet, Amazon), and nothing else unusual."""
    facts = [f for f in company() if f.concept not in ("NetIncomeLoss", "EarningsPerShareDiluted")]
    for start, end, v, accn in (("2025-01-01", "2025-12-31", 40, "fy25"), ("2025-01-01", "2025-06-30", 8, "h1-25"),
                                ("2026-01-01", "2026-06-30", 40, "h1-26")):
        facts.append(fact("NetIncomeLoss", start, end, v * B, accn, "10-K", "2026-02-05"))
    for start, end, v, accn in (("2025-01-01", "2025-12-31", 4.0, "fy25"), ("2025-01-01", "2025-06-30", 0.8, "h1-25"),
                                ("2026-01-01", "2026-06-30", 4.0, "h1-26")):
        facts.append(fact("EarningsPerShareDiluted", start, end, v, accn, "10-K", "2026-02-05", "USD/shares"))
    return facts


def test_cautions_are_written_into_the_source_and_carried_with_their_scope():
    ev = evidence_from_fundamentals(compute(A, gains_company(), 24.0, TODAY, TODAY))
    assert "CAUTION: net income is 2.4 times operating income" in ev.text
    (text, scopes), = ev.cautions
    assert "may flatter" in text and {"pe", "eps", "net_income"} <= set(scopes) and "revenue" not in scopes


# ---- cautions reach the answer ----

def test_a_caution_applies_only_to_the_figures_the_question_or_answer_is_about():
    ev = evidence_from_fundamentals(compute(A, gains_company(), 24.0, TODAY, TODAY))
    pe = relevant_cautions([ev], frozenset({"pe"}), "The P/E ratio is 10.0 [1].")
    assert len(pe) == 1 and pe[0].startswith(f"Caution for {A}:") and "gains outside the core business" in pe[0]
    assert relevant_cautions([ev], frozenset({"revenue"}), "Revenue is $120.0 billion [1].") == []
    # a question about revenue whose answer wanders into P/E still carries the warning
    assert len(relevant_cautions([ev], frozenset({"revenue"}), "Revenue is $120.0 billion [1]. Its P/E is 3.3 [1].")) == 1
    assert len(relevant_cautions([ev], frozenset({"general"}), "x")) == 1


def test_old_figures_apply_to_everything():
    ev = evidence_from_fundamentals(compute(A, company(), 24.0, TODAY, date(2027, 6, 1)))
    assert "which is old" in ev.text
    assert len(relevant_cautions([ev], frozenset({"revenue"}), "x")) >= 1


# ---- through the whole copilot, with a fake model ----

class FakeEmbedder:
    name = "fake"
    dim = 384

    def __init__(self):
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return [1.0] + [0.0] * 383


class ScriptedLLM:
    name = MODEL

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def generate(self, system, user, json_schema=None):
        self.calls.append((system, user))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def store(c, facts):
    for f in facts:
        c.execute(
            "INSERT INTO financial_facts (symbol, taxonomy, concept, unit, period_start, period_end, value, accession_number, "
            "form, filed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (A, f.taxonomy, f.concept, f.unit, f.period_start, f.period_end, f.value, f.accession_number, f.form, f.filed_at))
    c.commit()


@pytest.fixture
def conn():
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Funco Holdings')", (A,))
        c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, 24, 'fake')", (A, TODAY))
        c.commit()
        yield c
        c.rollback()
        for table in ("financial_facts", "prices_daily"):
            c.execute(f"DELETE FROM {table} WHERE symbol = %s", (A,))
        c.execute("DELETE FROM instruments WHERE symbol = %s", (A,))
        c.commit()


def ask(conn, question, llm, **kw):
    return answer_question(conn, FakeEmbedder(), llm, question, expand=False, today=TODAY, **kw)


def test_a_pe_question_is_answered_from_the_figures_without_searching_filings(conn):
    store(conn, company())
    llm, emb = ScriptedLLM("The P/E ratio is 10.0, the latest close over diluted EPS for the last 12 months [1]."), FakeEmbedder()
    ans = answer_question(conn, emb, llm, "What is ZZFC's P/E ratio?", expand=False, today=TODAY)
    assert emb.queries == [] and ans.queries == []
    assert ans.grounded and not ans.refused and ans.unverified_numbers == [] and ans.cautions == []
    assert isinstance(ans.sources[0][1], MarketEvidence) and ans.sources[0][1].kind == "fundamentals"
    assert "[1] ZZFC financial figures" in llm.calls[0][1] and "P/E ratio: 10.0" in llm.calls[0][1]


def test_the_caution_is_attached_even_when_the_model_leaves_it_out(conn):
    store(conn, gains_company())
    ans = ask(conn, "What is ZZFC's P/E ratio?", ScriptedLLM("The P/E ratio is 3.3 [1]."))
    assert len(ans.cautions) == 1
    assert ans.cautions[0].startswith("Caution for ZZFC:") and "gains outside the core business" in ans.cautions[0]


def test_a_revenue_question_does_not_carry_the_earnings_caution(conn):
    store(conn, gains_company())
    ans = ask(conn, "What was ZZFC's revenue over the last twelve months?", ScriptedLLM("Revenue was $120.0 billion [1]."))
    assert ans.cautions == [] and ans.unverified_numbers == []


def test_the_market_value_caution_is_about_market_value(conn):
    facts = [f for f in company() if f.concept != "EntityCommonStockSharesOutstanding"]
    facts.append(fact("EntityCommonStockSharesOutstanding", None, "2026-07-20", 11.5 * B, "h1-26", "10-Q", "2026-07-30", "shares", "dei"))
    store(conn, facts)
    mv = ask(conn, "What is ZZFC's market capitalization?", ScriptedLLM("Its market value is $276.0 billion [1]."))
    assert len(mv.cautions) == 1 and "share count" in mv.cautions[0]
    pe = ask(conn, "What is ZZFC's P/E ratio?", ScriptedLLM("The P/E ratio is 10.0 [1]."))
    assert pe.cautions == []


def test_a_wrong_growth_direction_triggers_the_retry(conn):
    store(conn, company())
    llm = ScriptedLLM("Revenue fell 50.0% [1].", "Revenue rose 50.0% [1].")
    ans = ask(conn, "How has ZZFC's revenue changed?", llm)
    assert ans.text == "Revenue rose 50.0% [1]." and ans.unverified_numbers == [] and len(llm.calls) == 2


def test_a_company_with_no_figures_gets_an_honest_answer_not_a_refusal(conn):
    ans = ask(conn, "What is ZZFC's P/E ratio?", ScriptedLLM("The P/E ratio isn't available: no financial figures are stored [1]."))
    assert not ans.refused and ans.grounded and "not available" in ans.sources[0][1].text


def test_a_figures_question_with_no_company_is_not_guessed_at(conn):
    llm = ScriptedLLM("should not be asked")
    ans = ask(conn, "What is the P/E ratio?", llm)
    assert ans.text == NO_COMPANY and ans.refused and llm.calls == []


def test_prices_and_figures_can_be_asked_together(conn):
    store(conn, company())
    ev = gather_market_evidence(conn, [A], detect_intent("What is ZZFC's P/E ratio and its stock price?"),
                                parse_window("x"), MODEL, TODAY)
    assert [e.kind for e in ev] == ["price", "fundamentals"]


def test_figures_are_only_gathered_when_asked_for(conn):
    store(conn, company())
    assert [e.kind for e in gather_market_evidence(conn, [A], detect_intent("stock price"), parse_window("x"), MODEL, TODAY)] == ["price"]
    assert fundamentals_evidence(conn, A, TODAY).text.count("P/E ratio: 10.0") == 1


def test_the_everyday_prompt_is_untouched_and_the_figures_rules_say_the_figures_exist():
    # The shared prompt is what every other kind of question was evaluated with; changing its wording (even slightly) made
    # "should I sell" go from 16 of 20 to 4 of 20. Everything about the figures lives in FIGURES_RULES.
    assert "financial figures" not in SYSTEM_PROMPT.lower()
    assert "investment advice" in SYSTEM_PROMPT.lower() and "never calculate" in SYSTEM_PROMPT.lower()
    assert "rule 3 does not apply" in FIGURES_RULES


def test_the_figures_rules_are_sent_only_with_a_figures_source(conn):
    rules = FIGURES_RULES.lower()
    for needle in ("caution", "cheap", "expensive", "do not explain why", "last 12 months"):
        assert needle in rules, needle
    assert "caution" not in SYSTEM_PROMPT.lower() and "overvalued" not in SYSTEM_PROMPT.lower()  # not in the everyday prompt
    store(conn, company())
    pe = ScriptedLLM("The P/E ratio is 10.0 [1].")
    ask(conn, "What is ZZFC's P/E ratio?", pe)
    assert pe.calls[0][0] == SYSTEM_PROMPT + FIGURES_RULES
    price = ScriptedLLM("It closed at 24.00 [1].")
    ask(conn, "What is the ZZFC stock price?", price)
    assert price.calls[0][0] == SYSTEM_PROMPT  # a price question gets exactly the prompt it was evaluated with
