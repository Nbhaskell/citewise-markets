"""Fixes for four CodeQL alerts (DECISIONS: "CodeQL alerts fixed"): the placeholder contact check and two slow regexes."""
import time

import pytest

from ai.market import BARE_STOCK_RE, parse_window
from data.sources.edgar import is_placeholder_user_agent


@pytest.mark.parametrize("ua,placeholder", [
    ("Your Name your-email@example.com", True),
    ("Jo Smith jo@EXAMPLE.com", True),
    ("Jo Smith jo@mail.example.com", True),
    ("Jo Smith <jo@example.com>", True),
    ("Jo Smith jo@gmail.com", False),
    ("Jo Smith jo@notexample.com", False),
    ("Jo Smith jo@example.com.evil.org", False),
    ("example.com research bot jo@gmail.com", False),
    ("", True),
    (None, True),
])
def test_placeholder_user_agent(ua, placeholder):
    assert is_placeholder_user_agent(ua) is placeholder


@pytest.mark.parametrize("make", [
    lambda: "&" * 50000, lambda: "&" * 50000 + " x", lambda: "." * 50000, lambda: "-" * 50000 + "x", lambda: "a" + "&" * 50000,
], ids=["amps", "amps-then-word", "dots", "hyphens", "word-then-amps"])
def test_bare_stock_regex_is_fast_on_repeated_punctuation(make):
    text = make()
    start = time.perf_counter()
    assert BARE_STOCK_RE.search(text) is None
    assert time.perf_counter() - start < 0.5


@pytest.mark.parametrize("text", ["Tesla stock", "ok, and Alphabet stock?", "...Tesla stock", "What's Nvidia's shares now"])
def test_bare_stock_regex_still_matches(text):
    assert BARE_STOCK_RE.search(text)


def test_window_parsing_is_fast_on_long_whitespace():
    for text in ["last couple" + " " * 50000, "last couple" + " " * 50000 + "of weeks", "last couple of" + " " * 50000]:
        start = time.perf_counter()
        parse_window(text)
        assert time.perf_counter() - start < 0.5


def test_window_few_and_couple_of_still_read():
    assert parse_window("over the last couple of weeks").days == 14
    assert parse_window("over the last couple   of weeks").days == 14
    assert parse_window("the last few weeks").days == 21
