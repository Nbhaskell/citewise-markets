from datetime import date, timedelta

import pytest

from ai.copilot import (
    CAUSE_CAUTION,
    NO_COMPANY,
    NO_EVIDENCE,
    SYSTEM_PROMPT,
    Turn,
    answer_question,
    build_prompt,
    causal_claims,
    unverified_numbers,
)
from ai.index_filings import vector_literal
from ai.market import (
    DEFAULT_WINDOW,
    MarketEvidence,
    detect_intent,
    gather_market_evidence,
    headline_evidence,
    news_days,
    parse_window,
    price_evidence,
    sentiment_evidence,
)
from data.db import connect

A, B = "ZZMA", "ZZMB"  # A has prices, news and a filing; B is a tracked company with no data at all
TODAY = date(2026, 10, 12)
MODEL = "fake-llm"


# ---- reading the question ----

@pytest.mark.parametrize("question,prices,headlines,sentiment,filings", [
    ("How has Nvidia stock done this month?", True, False, False, False),
    ("What is Apple's stock price?", True, False, False, False),
    ("Is Tesla up this year?", True, False, False, False),
    ("Did Microsoft fall last week?", True, False, False, False),
    ("Why is Apple stock crashing?", True, True, False, False),
    ("What's the news on Apple and how's the stock?", True, True, False, False),
    ("How negative is the press coverage of Tesla at the moment?", False, True, True, False),
    ("How much has Tesla stock changed since the start of the year?", True, False, False, False),
    ("Are investors feeling positive about Nvidia lately?", False, True, True, False),
    ("What do investors think of Tesla?", False, True, True, False),
    ("What is the S&P 500 at?", True, False, False, False),  # no index data: with no company named it is refused
    ("How does Apple compare to the Nasdaq this year?", True, False, False, False),
    ("Which did better this month, Apple stock or Microsoft stock?", True, False, False, False),
    ("Tesla stock year to date", True, False, False, False),
    ("What does the 10-K say about stock-based compensation this year?", False, False, False, True),  # not a price question
    ("What's Amazon's 52-week high?", True, False, False, False),
    ("How's Nvidia doing?", True, True, False, False),
    ("What's the latest news on Tesla?", False, True, False, False),
    ("Any headlines about Apple lately?", False, True, False, False),
    ("What is the sentiment on Google?", False, True, True, False),
    ("Is the news about Tesla bullish or bearish?", False, True, True, False),
    ("Why did Nvidia stock drop this week?", True, True, False, False),
    ("Will Tesla stock go up next month?", True, False, False, False),  # routed here so the prompt's no-prediction rule applies
    ("How did Nvidia's stock do, and what are its biggest risks?", True, False, False, True),
    # nothing market-related: unchanged filings-only behavior
    ("What are Nvidia's biggest risks?", False, False, False, True),
    ("How many employees does Tesla have?", False, False, False, True),
    ("What does the 10-K say about stock-based compensation?", False, False, False, True),
    ("Why is Apple's revenue growing?", False, False, False, True),
    ("Should I buy Tesla stock?", False, False, False, True),
    ("Summarize Amazon's legal proceedings", False, False, False, True),
])
def test_intent_rules(question, prices, headlines, sentiment, filings):
    got = detect_intent(question)
    assert (got.prices, got.headlines, got.sentiment, got.filings) == (prices, headlines, sentiment, filings), question


@pytest.mark.parametrize("question,label,days", [
    ("How has Apple stock done this year?", "year to date", None),
    ("Apple stock year-to-date", "year to date", None),
    ("How much has Tesla stock changed since the start of the year?", "year to date", None),  # was read as "past year"
    ("Nvidia stock since January", "year to date", None),
    ("Amazon stock so far this calendar year", "year to date", None),
    ("Nvidia stock over the last 12 months", "past year", 366),
    ("Tesla over the last 6 months", "past 6 months", 183),
    ("Tesla in the past three months", "past 3 months", 92),
    ("Nvidia over the past year", "past year", 366),
    ("Nvidia 52-week high", "past year", 366),
    ("Nvidia stock last month", "past month", 31),
    ("Nvidia stock this week", "past week", 7),
    ("How did Google do today?", "past day", 1),
    ("Nvidia over the last 5 years", "past 5 years", 1830),
])
def test_window_is_read_from_the_question(question, label, days):
    w = parse_window(question)
    assert (w.label, w.days, w.explicit) == (label, days, True)


def test_no_period_means_the_default_month_and_a_week_of_headlines():
    assert parse_window("What is Apple's stock price?") == DEFAULT_WINDOW and not DEFAULT_WINDOW.explicit
    assert news_days(DEFAULT_WINDOW) == 7
    assert news_days(parse_window("news over the past year")) == 90  # capped
    assert news_days(parse_window("news this week")) == 7


# ---- the evidence, against a database with known values ----

@pytest.fixture
def conn():
    with connect() as c:
        for sym, name in ((A, "Marketco"), (B, "Emptyco")):
            c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, %s)", (sym, name))
        first = TODAY - timedelta(days=399)
        for i in range(400):  # one bar a day; close = 100 + i, so every expected figure can be worked out by hand
            c.execute("INSERT INTO prices_daily (symbol, ts, close, source) VALUES (%s, %s, %s, 'fake')",
                      (A, first + timedelta(days=i), 100 + i))
        c.execute("INSERT INTO filings (accession_number, symbol, cik, form, filed_at, url, text) "
                  "VALUES ('0-ZM-A', %s, '1', '10-K', %s, 'https://x/k', 't')", (A, date(2026, 1, 2)))
        v = [1.0] + [0.0] * 383
        c.execute("INSERT INTO filing_chunks (accession_number, chunk_index, section, text, embedding, embedding_model) "
                  "VALUES ('0-ZM-A', 0, 'Item 1A', 'Marketco faces supply risk.', %s::vector, 'fake')", (vector_literal(v),))
        # (id, title, publisher, hours ago, label)
        news = [
            ("n1", "Marketco wins big contract", "Reuters", 5, "positive"),
            ("n2", "Marketco wins big contract - Wire", "Wire", 6, "positive"),  # same story, another source
            ("n3", "Marketco faces probe", "Reuters", 30, "negative"),
            ("n4", "Unrelated company news", "Reuters", 40, "irrelevant"),
            ("n5", "Marketco (ZZMA) Stock Price Today: $123.45", "Quotes", 8, "neutral"),
            ("n6", "Marketco vs. Rivalco: which is better", "Blog", 9, "neutral"),
            ("n7", "Marketco old story", "Reuters", 24 * 40, "neutral"),
            ("n8", "Marketco opens a plant", "Reuters", 50, None),  # never labeled
        ]
        for id_, title, pub, hours, label in news:
            c.execute("INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                      "VALUES (%s, 'fake', %s, %s, %s, now() - make_interval(hours => %s))",
                      (f"fake:zzm-{id_}", title, pub, f"https://x/{id_}", hours))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"fake:zzm-{id_}", A))
            if label:
                c.execute("INSERT INTO news_sentiment (article_id, symbol, label, model) VALUES (%s, %s, %s, %s)",
                          (f"fake:zzm-{id_}", A, label, MODEL))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzm-%'")
        c.execute("DELETE FROM filings WHERE symbol = ANY(%s)", ([A, B],))
        c.execute("DELETE FROM prices_daily WHERE symbol = ANY(%s)", ([A, B],))
        c.execute("DELETE FROM instruments WHERE symbol = ANY(%s)", ([A, B],))
        c.commit()


def test_price_facts_are_worked_out_in_python(conn):
    ev = price_evidence(conn, A, parse_window("last month"), TODAY)
    assert ev.kind == "price" and ev.as_of == TODAY
    # latest close 499 on 2026-10-12; 31 days earlier the close was 468; 31 / 468 = 6.62%
    assert "Latest close: 499.00 on 2026-10-12." in ev.text
    assert "Close on 2026-09-11: 468.00." in ev.text
    assert "Change over the window: +31.00 (+6.62%), a rise." in ev.text
    assert "Highest close in the window: 499.00 on 2026-10-12. Lowest close in the window: 468.00 on 2026-09-11." in ev.text
    assert "(31 trading days)" in ev.text
    assert "52-week closing range: 135.00 to 499.00." in ev.text  # 364 days back from the latest bar is the oldest included


def test_year_to_date_starts_from_the_last_close_of_the_previous_year(conn):
    ev = price_evidence(conn, A, parse_window("this year"), TODAY)
    # 2025-12-31 closed at 214 (285 days before the latest 499); 285 / 214 = 133.18%
    assert "Close on 2025-12-31: 214.00." in ev.text and "+285.00 (+133.18%), a rise." in ev.text


def test_a_window_longer_than_the_history_says_so(conn):
    ev = price_evidence(conn, A, parse_window("over 5 years"), TODAY)
    assert "stored prices only start on 2025-09-08" in ev.text and "Close on 2025-09-08: 100.00." in ev.text


def test_stale_and_partial_day_notes(conn):
    assert "stored prices end on 2026-10-12; newer prices have not been loaded" in price_evidence(
        conn, A, DEFAULT_WINDOW, TODAY + timedelta(days=10)).text
    assert "partial trading day" in price_evidence(conn, A, DEFAULT_WINDOW, TODAY).text
    assert "Note" not in price_evidence(conn, A, DEFAULT_WINDOW, TODAY + timedelta(days=1)).text


def test_no_prices_means_no_evidence(conn):
    assert price_evidence(conn, B, DEFAULT_WINDOW, TODAY) is None


def test_headlines_are_deduplicated_filtered_and_newest_first(conn):
    evs = headline_evidence(conn, A, MODEL, days=7)
    assert [e.text for e in evs] == [
        "Marketco wins big contract", "Marketco faces probe", "Marketco opens a plant"]
    first = evs[0]
    assert first.kind == "headline" and first.url == "https://x/n1"
    assert first.header.endswith("Reuters, " + first.as_of.isoformat() + ", automatic label: positive")
    assert "automatic label: not labeled" in evs[2].header
    assert len(headline_evidence(conn, A, MODEL, days=7, limit=2)) == 2
    assert "Marketco old story" in [e.text for e in headline_evidence(conn, A, MODEL, days=60)]


def test_sentiment_summary_counts_only_the_window_and_says_it_is_imperfect(conn):
    ev = sentiment_evidence(conn, A, MODEL, 7, TODAY)
    assert "2 positive, 2 neutral, 1 negative, 1 not actually about the company" in ev.text
    assert "imperfect" in ev.text and "Score: +0.20" in ev.text  # (2 - 1) / 5 relevant
    assert sentiment_evidence(conn, B, MODEL, 7, TODAY) is None


def test_only_the_requested_kinds_are_gathered(conn):
    only_prices = gather_market_evidence(conn, [A], detect_intent("stock price"), DEFAULT_WINDOW, MODEL, TODAY)
    assert [e.kind for e in only_prices] == ["price"]
    news = gather_market_evidence(conn, [A], detect_intent("any news?"), DEFAULT_WINDOW, MODEL, TODAY)
    assert {e.kind for e in news} == {"headline"}
    both = gather_market_evidence(conn, [A], detect_intent("why did the stock fall?"), DEFAULT_WINDOW, MODEL, TODAY)
    assert [e.kind for e in both][0] == "price" and "headline" in {e.kind for e in both}


def test_comparing_companies_splits_the_headline_budget(conn):
    conn.execute("INSERT INTO instruments (symbol, name) VALUES ('ZZMC', 'Thirdco')")
    conn.commit()
    try:
        evs = gather_market_evidence(conn, [A, "ZZMC"], detect_intent("news"), DEFAULT_WINDOW, MODEL, TODAY)
        assert len(evs) == 3 and {e.symbol for e in evs} == {A}  # ZZMC has no news; A is capped at 3
    finally:
        conn.rollback()
        conn.execute("DELETE FROM instruments WHERE symbol = 'ZZMC'")
        conn.commit()


# ---- the copilot using it ----

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


def test_a_price_question_is_answered_from_price_data_without_searching_filings(conn):
    llm, emb = ScriptedLLM("MarketCo closed at 499.00 on 2026-10-12 [1]."), FakeEmbedder()
    ans = answer_question(conn, emb, llm, "How has ZZMA stock done this month?", expand=False)
    assert emb.queries == [] and ans.queries == []  # no filing search at all
    assert ans.grounded and not ans.refused and ans.unverified_numbers == []
    assert isinstance(ans.sources[0][1], MarketEvidence) and ans.sources[0][1].kind == "price"
    assert "[1] ZZMA price data" in llm.calls[0][1] and "Latest close: 499.00" in llm.calls[0][1]


def test_a_wrong_price_is_flagged_even_though_it_is_cited(conn):
    llm = ScriptedLLM("The stock closed at 512.34 [1].", "It closed at 512.34 [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "What is the ZZMA stock price?", expand=False)
    assert ans.grounded and ans.unverified_numbers == ["512.34"]
    assert len(llm.calls) == 2 and "Do no arithmetic" in llm.calls[1][1]


def test_a_derived_figure_the_model_calculated_is_flagged(conn):
    llm = ScriptedLLM("It gained 6.6% [1].")  # the data says +6.62%; rounding it is the model doing its own maths
    ans = answer_question(conn, FakeEmbedder(), llm, "How is the ZZMA stock doing this month?", expand=False)
    assert "6.6" in ans.unverified_numbers


def test_a_market_question_without_a_company_is_not_guessed_at(conn):
    llm = ScriptedLLM("should not be asked")
    ans = answer_question(conn, FakeEmbedder(), llm, "How is the stock market doing this week?", expand=False)
    assert ans.text == NO_COMPANY and ans.refused and llm.calls == []


def test_an_index_question_without_a_company_is_refused_not_answered_from_a_filing(conn):
    llm, emb = ScriptedLLM("should not be asked"), FakeEmbedder()
    ans = answer_question(conn, emb, llm, "What is the S&P 500 at?", expand=False)
    assert ans.text == NO_COMPANY and ans.refused and llm.calls == [] and emb.queries == []


def test_a_company_with_no_stored_data_is_refused_not_invented(conn):
    llm = ScriptedLLM("should not be asked")
    ans = answer_question(conn, FakeEmbedder(), llm, "What is the ZZMB stock price?", symbols=[B], expand=False)
    assert ans.text == NO_EVIDENCE and ans.refused and llm.calls == []


def test_a_mixed_question_numbers_market_evidence_before_filing_passages(conn):
    llm = ScriptedLLM("The stock rose [1] and it faces supply risk [2].")
    ans = answer_question(conn, FakeEmbedder(), llm, "How did ZZMA stock do this month, and what are its risks?",
                          expand=False)
    kinds = [getattr(r, "kind", "filing") for r in ans.retrieved]
    assert kinds == ["price", "filing"] and ans.cited == [1, 2]
    assert ans.queries  # the filing search did run


def test_filing_only_questions_are_unchanged(conn):
    llm, emb = ScriptedLLM("Supply risk [1]."), FakeEmbedder()
    ans = answer_question(conn, emb, llm, "What are ZZMA's biggest risks?", expand=False)
    assert emb.queries and [getattr(r, "kind", "filing") for r in ans.retrieved] == ["filing"]
    assert "Latest close" not in llm.calls[0][1]


def test_earlier_answers_never_reach_the_prompt_that_writes_the_answer(conn):
    secret = "ZZ-SECRET-EARLIER-ANSWER-TEXT"

    class Llm(ScriptedLLM):
        def generate(self, system, user, json_schema=None):
            self.calls.append((system, user))
            return "How has ZZMA stock done this month?" if system.startswith("You rewrite") else "Up [1]."

    llm = Llm()
    history = [Turn("Tell me about ZZMA", f"{secret} It faces supply risk [1].", ("ZZMA",))]
    answer_question(conn, FakeEmbedder(), llm, "And how has it done this month?", history=history, expand=False)
    answer_prompts = [u for s, u in llm.calls if not s.startswith("You rewrite")]
    assert answer_prompts and all(secret not in u for u in answer_prompts)


def up(change=8.03, pct=3.68):
    text = f"Change over the window: {change:+.2f} ({pct:+.2f}%). Highest close in the window: 239.24 on 2026-10-12."
    return MarketEvidence("price", "ZZMA", "ZZMA price data", text, None, TODAY, change=change, change_pct=pct)


@pytest.mark.parametrize("answer,flagged", [
    ("ZZMA fell by 3.68% over the month [1].", True),               # the real failure: right digits, wrong direction
    ("The price dropped 8.03 [1].", True),
    ("ZZMA rose 3.68% [1].", False),
    ("ZZMA is up 8.03, a gain of 3.68% [1].", False),
    ("ZZMA is up 3.68% from its low, down from its high of 239.24 [1].", False),  # a fall mentioned next to a different figure
    ("It did not fall; it rose 3.68% [1].", False),                  # mixed wording is left alone rather than guessed at
    ("Shares fell on 2026-10-12 [1].", False),                        # no change figure in the sentence
])
def test_a_price_move_in_the_wrong_direction_is_flagged(answer, flagged):
    bad = unverified_numbers(answer, [1], [up()])
    assert bool(bad) is flagged, bad
    if flagged:
        assert "stored change is +3.68%, a rise" in " ".join(bad)


def test_the_same_check_works_for_a_real_fall():
    down = up(-5.10, -2.34)
    assert unverified_numbers("ZZMA fell 2.34% [1].", [1], [down]) == []
    assert unverified_numbers("ZZMA rose 2.34% [1].", [1], [down])


def test_a_minus_sign_the_sources_do_not_have_is_flagged():
    assert unverified_numbers("The change was -3.68% [1].", [1], [up()]) == ["-3.68"]
    assert unverified_numbers("The change was (-3.68%) [1].", [1], [up()]) == ["-3.68"]
    assert unverified_numbers("The change was +3.68% [1].", [1], [up()]) == []
    assert unverified_numbers("The change was -5.10 [1].", [1], [up(-5.10, -2.34)]) == []
    assert unverified_numbers("The high was on 2026-10-12 [1].", [1], [up()]) == []  # dashes in dates are not minus signs


def test_a_wrong_direction_triggers_the_retry_and_the_correction_is_used(conn):
    llm = ScriptedLLM("ZZMA fell by 31.00 over the past month [1].", "ZZMA rose by 31.00 over the past month [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "Why did ZZMA stock fall this month?", expand=False)
    assert ans.text == "ZZMA rose by 31.00 over the past month [1]." and ans.unverified_numbers == []
    assert len(llm.calls) == 2 and "even if the question assumed otherwise" in llm.calls[1][1]
    assert "31.00" in llm.calls[0][1] and "a rise" in llm.calls[0][1]


def test_a_wrong_direction_that_survives_the_retry_is_reported(conn):
    llm = ScriptedLLM("ZZMA fell by 31.00 [1].", "ZZMA still fell by 31.00 [1].")
    ans = answer_question(conn, FakeEmbedder(), llm, "Why did ZZMA stock fall this month?", expand=False)
    assert any("stored change is" in b for b in ans.unverified_numbers)


def both():
    return [up(), MarketEvidence("headline", "ZZMA", "ZZMA headline", "Marketco wins big contract", "https://x", TODAY)]


@pytest.mark.parametrize("answer,flagged", [
    # sentences the local model actually produced
    ("These headlines are from the same date and may have influenced market sentiment, but the sources do not "
     "specify the exact reason for the stock's movement.", True),
    ("A negative headline [2], which may have contributed to market sentiment, but the data does not confirm causation.", True),
    ("The stock rose because of the contract news [2].", True),
    ("The rise was driven by strong demand [1].", True),
    # statements that are fine
    ("The stored data cannot show the cause of the price move [1]. Headlines are listed as context only [2].", False),
    ("This headline does not explain the stock's movement [2].", False),
    ("The stock rose 3.68% [1]. A headline said \"shares rose because of a new contract\" [2].", False),  # quoted text
    ("The sources do not provide information on the cause of the movement [1].", False),
])
def test_a_cause_suggested_for_a_price_move_is_detected(answer, flagged):
    assert bool(causal_claims(answer, both())) is flagged, answer


def test_causes_are_only_policed_when_prices_and_headlines_were_both_given():
    text = "The charge was due to a one-time legal settlement [1]."
    assert causal_claims(text, [up()]) == []  # filings and price-only answers may legitimately give reasons


def test_a_suggested_cause_triggers_one_retry_and_the_fix_is_used(conn):
    bad = "ZZMA rose by 31.00 [1], which may have been influenced by contract news [2]."
    good = "ZZMA rose by 31.00 [1]. The stored data can't show why [1]."
    llm = ScriptedLLM(bad, good)
    ans = answer_question(conn, FakeEmbedder(), llm, "Why did ZZMA stock move this month?", expand=False)
    assert ans.text == good and ans.cautions == []
    assert len(llm.calls) == 2 and "suggests a cause" in llm.calls[1][1]


def test_a_cause_that_survives_the_retry_is_shown_as_a_caution(conn):
    bad = "ZZMA rose by 31.00 [1], which may have been influenced by contract news [2]."
    ans = answer_question(conn, FakeEmbedder(), ScriptedLLM(bad, bad), "Why did ZZMA stock move this month?", expand=False)
    assert ans.cautions == [CAUSE_CAUTION]


def test_the_prompt_keeps_its_safety_rules():
    for needle in ("investment advice", "price predictions", "never say or hint that a headline caused", "ONLY", "Never calculate"):
        assert needle.lower() in SYSTEM_PROMPT.lower(), needle
    prompt = build_prompt("Q?", [MarketEvidence("headline", "ZZMA", "ZZMA headline, Wire, 2026-10-10, automatic label: neutral",
                                                  "Marketco news", "https://x", TODAY)])
    assert prompt.startswith("Sources:") and "[1] ZZMA headline, Wire" in prompt and prompt.endswith("Question: Q?")
