"""Ways of typing a question that the routing missed (DECISIONS: "Typing variants"), found in the owner's own question log.

"Hows nvda doing?" was refused ("tell me which company"): a lowercase ticker was not a company, and "hows" without an apostrophe was not
"how's". A curly apostrophe ("How’s NVDA doing?", what a phone types) got no route either. Every alternative has a question of its own.
Fixture company: Marketco (ZZMA), with prices, headlines and a filing (tests/test_market.py). Nothing here calls a model.
"""
import pytest

from ai.copilot import answer_question, company_mentions, lowercase_ticker_ok
from ai.market import detect_intent, normalize_typing
from test_market import FakeEmbedder, conn  # noqa: F401  (conn is a fixture)
from test_router import RouterLLM


# ---- apostrophes and contractions typed without one ----


@pytest.mark.parametrize("typed, fixed", [
    ("How’s NVDA doing?", "How's NVDA doing?"),                  # a right single quote
    ("How‘s NVDA doing?", "How's NVDA doing?"),                  # a left single quote
    ("Hows NVDA doing?", "How's NVDA doing?"),
    ("hows nvda doing", "how's nvda doing"),
    ("Whats Apple's P/E?", "What's Apple's P/E?"),
    ("whats the news", "what's the news"),
    ("Wheres the Tesla stock?", "Where's the Tesla stock?"),
    ("Whos buying Amazon?", "Who's buying Amazon?"),
    ("Thats odd for Nvidia.", "That's odd for Nvidia."),
    ("Theres news on AMD.", "There's news on AMD."),
    ("HOWS TSLA?", "HOW's TSLA?"),                                    # capitals kept
])
def test_curly_apostrophes_and_missing_ones_are_fixed(typed, fixed):
    assert normalize_typing(typed) == fixed


@pytest.mark.parametrize("text", [
    "How's NVDA doing?", "What's Apple's P/E?", "Show me Nvidia's news", "Is that so?", "Nothing to change here.", "Where is it?",
])
def test_text_that_needs_no_fixing_is_left_alone(text):
    assert normalize_typing(text) == text


def test_shows_and_whatsapp_are_not_touched():
    assert normalize_typing("Shows Microsoft's segments.") == "Shows Microsoft's segments."
    assert normalize_typing("Whatsapp is not tracked.") == "Whatsapp is not tracked."


def test_fixing_twice_changes_nothing_more():
    once = normalize_typing("Hows nvda doing? Whats Apple’s P/E?")
    assert normalize_typing(once) == once


@pytest.mark.parametrize("question", [
    "Hows NVDA doing?", "How’s NVDA doing?", "hows NVDA doing", "How‘s NVDA doing?",
])
def test_how_is_it_doing_is_a_price_and_news_question_however_it_is_typed(question):
    got = detect_intent(question)
    assert got.prices and got.headlines, question


@pytest.mark.parametrize("question", ["Whats Apple’s P/E?", "Whats Apple's P/E?", "What’s Apple’s P/E?"])
def test_a_p_e_question_is_read_however_the_apostrophes_are_typed(question):
    assert "pe" in detect_intent(question).fundamentals, question


# ---- a ticker typed in lowercase ----


@pytest.mark.parametrize("symbol", ["NVDA", "AMD", "TSLA", "AAPL", "SIG", "XOM", "CRWV", "ZZMA"])
def test_an_ordinary_ticker_may_be_matched_in_lowercase(symbol):
    assert lowercase_ticker_ok(symbol), symbol


@pytest.mark.parametrize("symbol", [
    "NOW", "ALL", "CAN", "ARE", "FOR", "NEW", "ONE", "TWO", "OUT", "KEY", "LOW", "BIG", "BEST", "GOOD", "FAST", "WELL", "WORK", "OPEN", "REAL", "TRUE",
    "SAFE", "POST", "PLAY", "SNAP", "LINE", "TECH", "FUND", "BANK", "GOLD", "GAS", "CAR", "SUN", "RUN", "FIT", "HOT", "COOL",   # words people type
    "F", "T", "C", "GM", "IT", "ON", "A",                                                                                   # too short
])
def test_a_ticker_that_is_also_a_common_word_or_too_short_is_not_matched_in_lowercase(symbol):
    assert not lowercase_ticker_ok(symbol), symbol


def test_a_lowercase_ticker_names_the_company(conn):
    assert set(company_mentions(conn, "how is zzma doing")) == {"ZZMA"}
    assert set(company_mentions(conn, "How is ZZMA doing")) == {"ZZMA"}              # still works in capitals
    assert set(company_mentions(conn, "How is Zzma doing")) == {"ZZMA"}              # and in any mix


def test_a_ticker_inside_a_longer_word_is_not_a_mention(conn):
    assert company_mentions(conn, "the zzmatic process and zzmab") == {}


def test_a_blocked_word_ticker_is_still_matched_only_in_capitals(conn, monkeypatch):
    monkeypatch.setattr("ai.copilot.LOWERCASE_TICKER_BLOCKLIST", frozenset({"zzma"}))
    assert company_mentions(conn, "how is zzma doing") == {}
    assert set(company_mentions(conn, "How is ZZMA doing")) == {"ZZMA"}


def test_a_short_ticker_is_matched_only_in_capitals(conn, monkeypatch):
    monkeypatch.setattr("ai.copilot.lowercase_ticker_ok", lambda symbol: False)
    assert company_mentions(conn, "how is zzma doing") == {}


# ---- through the whole copilot ----


def kinds(question, conn):
    ans = answer_question(conn, FakeEmbedder(), RouterLLM(answer="Marketco is up [1]."), question, expand=False, router=False)
    return ans, {getattr(r, "kind", "filing") for r in ans.retrieved}


@pytest.mark.parametrize("question", ["Hows zzma doing?", "How’s ZZMA doing?", "hows zzma doing", "Whats the latest news on zzma?"])
def test_the_question_the_owner_typed_is_answered_not_refused(conn, question):
    ans, seen = kinds(question, conn)
    assert not ans.refused and ans.symbols == ["ZZMA"] and seen, question


def test_the_question_is_kept_as_typed(conn):
    ans, _ = kinds("Hows zzma doing?", conn)
    assert ans.question == "Hows zzma doing?" and ans.interpreted_question is None      # fixing the typing is not a rewrite


def test_how_is_it_doing_reaches_prices_and_headlines(conn):
    _, seen = kinds("Hows zzma doing?", conn)
    assert {"price", "headline"} <= seen
