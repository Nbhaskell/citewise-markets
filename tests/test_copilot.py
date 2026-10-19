from datetime import date

import pytest

from ai.copilot import (
    NO_EVIDENCE,
    SYSTEM_PROMPT,
    answer_question,
    build_prompt,
    clean_citations,
    _generate_checked,
    dedupe,
    detect_forms,
    detect_symbols,
    expand_queries,
    strip_thinking,
    unverified_numbers,
)
from ai.index_filings import vector_literal
from ai.search import SearchResult
from data.db import connect

SYMS = ("ZZCA", "ZZCB")


def vec(i, tilt=0.0):
    v = [0.0] * 384
    v[i] = 1.0
    v[(i + 1) % 384] = tilt
    return v


class FakeEmbedder:
    name = "fake"
    dim = 384

    def __init__(self, v):
        self._v = v

    def embed_query(self, text):
        return self._v


class FakeLLM:
    name = "fake-llm"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        return self.reply


def result(symbol="A", text="t", form="10-K", score=0.9):
    return SearchResult(1, "acc", symbol, form, date(2025, 1, 1), None, "u", "Item 1A", text, score)


def test_clean_citations_drops_invalid_numbers_and_merges_groups():
    text, cited = clean_citations("Fact [1]. Other [2, 9]. Bad [7]. Multi [3][1].", 3)
    assert text == "Fact [1]. Other [2]. Bad . Multi [3][1]."
    assert cited == [1, 2, 3]


def test_strip_thinking_removes_reasoning_block():
    assert strip_thinking("<think>hmm\nmore</think>\nAnswer [1]") == "Answer [1]"


def test_dedupe_keeps_first_copy_per_company_and_limit():
    rs = [result("A", "Same  text"), result("A", "same text", "10-Q"), result("B", "same text"), result("A", "other")]
    out = dedupe(rs, 10)
    assert [(r.symbol, r.form) for r in out] == [("A", "10-K"), ("B", "10-K"), ("A", "10-K")]
    assert len(dedupe(rs, 2)) == 2


def test_build_prompt_numbers_passages_and_includes_question():
    prompt = build_prompt("Why?", [result(text="alpha"), result("B", "beta", "10-Q")])
    assert "[1] A 10-K filed 2025-01-01, Item 1A\nalpha" in prompt
    assert "[2] B 10-Q" in prompt and prompt.endswith("Question: Why?")
    assert "ONLY" in SYSTEM_PROMPT and "investment advice" in SYSTEM_PROMPT


@pytest.fixture
def conn():
    with connect() as c:
        for sym, name in (("ZZCA", "Zetacorp Inc."), ("ZZCB", "Omegaware Ltd.")):
            c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, %s)", (sym, name))
        for acc, sym in (("0-ZC-A", "ZZCA"), ("0-ZC-B", "ZZCB")):
            c.execute(
                "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                "VALUES (%s, %s, '1', '10-K', %s, 'https://x', 't')", (acc, sym, date(2025, 1, 1)))
        rows = [("0-ZC-A", 0, "Zeta risk one", vec(0)), ("0-ZC-A", 1, "Zeta risk one", vec(0, 0.01)),
                ("0-ZC-A", 2, "Zeta revenue", vec(5)), ("0-ZC-B", 0, "Omega risk", vec(0, 0.2))]
        for acc, i, text, v in rows:
            c.execute(
                "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
                "VALUES (%s, %s, 'Item 1A', %s, %s::vector, 'fake')", (acc, i, text, vector_literal(v)))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM filings WHERE symbol = ANY(%s)", (list(SYMS),))
        c.execute("DELETE FROM instruments WHERE symbol = ANY(%s)", (list(SYMS),))
        c.commit()


def test_detect_symbols_by_ticker_and_company_name(conn):
    assert detect_symbols(conn, "What is ZZCA doing?") == ["ZZCA"]
    assert detect_symbols(conn, "compare zetacorp with OMEGAWARE") == ["ZZCA", "ZZCB"]
    # a ticker of three or more letters that is not a common word is matched in lowercase too ("hows nvda doing"); the words and short
    # tickers that must stay capitals-only are tested in tests/test_typing_variants.py (DECISIONS: "Typing variants")
    assert detect_symbols(conn, "zzca?") == ["ZZCA"]


def test_grounded_answer_cites_real_passages_only(conn):
    llm = FakeLLM("Risk exists [1][9].")
    ans = answer_question(conn, FakeEmbedder(vec(0)), llm, "zetacorp risks?", limit=3, expand=False)
    assert ans.symbols == ["ZZCA"] and ans.grounded and ans.cited == [1]
    assert "[9]" not in ans.text and ans.sources[0][1].text == "Zeta risk one"
    assert len(llm.calls) == 1 and "Zeta risk one" in llm.calls[0][1]
    texts = [r.text for r in ans.retrieved]
    assert texts.count("Zeta risk one") == 1  # near-duplicate chunk removed


def test_uncited_answer_is_flagged_ungrounded(conn):
    ans = answer_question(conn, FakeEmbedder(vec(0)), FakeLLM("No citations here."), "ZZCA risks?", expand=False)
    assert not ans.grounded and ans.cited == []


def test_irrelevant_question_skips_the_model(conn):
    llm = FakeLLM("should not be used")
    ans = answer_question(conn, FakeEmbedder(vec(200)), llm, "pizza?", symbols=["ZZCA"])
    assert ans.text == NO_EVIDENCE and llm.calls == [] and not ans.grounded


def test_comparison_retrieves_from_each_company(conn):
    llm = FakeLLM("Both [1][2].")
    ans = answer_question(conn, FakeEmbedder(vec(0)), llm, "zetacorp vs omegaware risks?", limit=4, expand=False)
    assert {r.symbol for r in ans.retrieved} == {"ZZCA", "ZZCB"}


REV = result(text="Fiscal Year 2026 Revenue increased $50.1 billion or 18% driven by cloud.")


def test_unverified_numbers_flags_only_figures_missing_from_cited_passages():
    assert unverified_numbers("Revenue grew $50.1 billion or 18% [1].", [1], [REV]) == []
    assert unverified_numbers("Revenue grew $49.9 billion or 18% [1].", [1], [REV]) == ["49.9"]
    assert unverified_numbers("There are 3 risks and 1,250 items [1].", [1], [REV]) == ["1250"]  # lone digits ignored


class ScriptedLLM:
    name = "scripted"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def generate(self, system, user):
        self.prompts.append(user)
        return self.replies.pop(0)


def test_wrong_number_triggers_one_retry_and_the_fix_is_used():
    llm = ScriptedLLM("Revenue grew $49.9 billion [1].", "Revenue grew 18% [1].")
    text, cited, bad = _generate_checked(llm, "growth?", [REV])
    assert text == "Revenue grew 18% [1]." and cited == [1] and bad == []
    assert len(llm.prompts) == 2 and "49.9" in llm.prompts[1] and "Do no arithmetic" in llm.prompts[1]


def test_number_error_that_survives_the_retry_is_reported():
    llm = ScriptedLLM("Grew $49.9 billion [1].", "Still $49.8 billion [1].")
    text, cited, bad = _generate_checked(llm, "growth?", [REV])
    assert bad == ["49.8"] and len(llm.prompts) == 2


def test_no_retry_when_numbers_check_out():
    llm = ScriptedLLM("Revenue rose 18% [1].")
    assert _generate_checked(llm, "growth?", [REV])[2] == [] and len(llm.prompts) == 1


def test_expand_queries_cleans_lines_and_survives_model_failure():
    llm = ScriptedLLM("1. human capital employees headcount\n- number of employees by region\n\nextra line")
    assert expand_queries(llm, "How many employees?") == ["human capital employees headcount", "number of employees by region"]

    class Broken:
        name = "broken"

        def generate(self, system, user):
            raise RuntimeError("Ollama down")

    assert expand_queries(Broken(), "q") == []


class RecordingEmbedder(FakeEmbedder):
    def __init__(self):
        super().__init__(vec(0))
        self.seen = []

    def embed_query(self, text):
        self.seen.append(text)
        return self._v


def test_expansion_searches_every_rewrite_before_answering(conn):
    llm = ScriptedLLM("alt one\nalt two", "Zeta has risk [1].")
    emb = RecordingEmbedder()
    ans = answer_question(conn, emb, llm, "zetacorp risks?", limit=3)
    assert ans.queries == ["zetacorp risks?", "alt one", "alt two"]
    assert {"alt one", "alt two"} <= set(emb.seen) and ans.grounded
    assert len(llm.prompts) == 2  # one rewrite call, one answer call


def test_expansion_failure_falls_back_to_the_plain_question(conn):
    class Flaky(ScriptedLLM):
        def generate(self, system, user):
            if system.startswith("Rewrite"):
                raise RuntimeError("boom")
            return super().generate(system, user)

    ans = answer_question(conn, FakeEmbedder(vec(0)), Flaky("Zeta [1]."), "zetacorp risks?", limit=3)
    assert ans.queries == ["zetacorp risks?"] and ans.grounded


def test_detect_forms_only_when_the_question_is_clear():
    assert detect_forms("revenue growth in the latest annual report") == ["10-K"]
    assert detect_forms("What did the 10-K say about fiscal year 2026?") == ["10-K"]
    assert detect_forms("How did the last quarter go?") == ["10-Q"]
    assert detect_forms("annual vs quarterly results") is None
    assert detect_forms("What are the risks?") is None


def test_annual_question_only_retrieves_annual_filings(conn):
    conn.execute(
        "INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
        "VALUES ('0-ZC-Q', 'ZZCA', '1', '10-Q', %s, 'https://x', 't')", (date(2025, 6, 1),))
    conn.execute(
        "INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
        "VALUES ('0-ZC-Q', 0, 'Item 2', 'quarterly note', %s::vector, 'fake')", (vector_literal(vec(0)),))
    conn.commit()
    ans = answer_question(conn, FakeEmbedder(vec(0)), FakeLLM("ok [1]."), "zetacorp annual risks?", limit=5, expand=False)
    assert ans.retrieved and {r.form for r in ans.retrieved} == {"10-K"}
