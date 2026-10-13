import json
from datetime import datetime, timedelta, timezone

import pytest

from ai.sentiment import SentimentSummary, label_counts, score_batch, score_symbol, summarize
from data.db import connect

SYMBOL = "ZZSEN"


class KeywordLLM:
    """Labels a headline by a keyword in it; `skip` leaves headlines unlabeled like a flaky model."""

    def __init__(self, name="fake-a", skip=()):
        self.name, self.skip, self.calls = name, set(skip), 0

    def generate(self, system, user, json_schema=None):
        assert json_schema is not None and "ZZSEN" in user
        self.calls += 1
        results = []
        for line in user.split("Headlines:\n")[1].splitlines():
            n, title = line.split(". ", 1)
            if any(s in title for s in self.skip):
                continue
            label = "positive" if "beats" in title else "negative" if "probe" in title else "neutral"
            results.append({"id": int(n), "sentiment": label})
        return json.dumps({"results": results})


class CannedLLM:
    name = "canned"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, system, user, json_schema=None):
        return self.reply


def test_score_batch_keeps_only_valid_entries():
    reply = json.dumps({"results": [
        {"id": 1, "sentiment": "positive"}, {"id": 1, "sentiment": "negative"},  # duplicate id: first wins
        {"id": 2, "sentiment": "great"},  # not a label
        {"id": 9, "sentiment": "neutral"},  # no such headline
        {"id": "3", "sentiment": "irrelevant"}, {"sentiment": "neutral"},
    ]})
    assert score_batch(CannedLLM(reply), "Co", "ZZ", ["a", "b", "c"]) == {1: "positive", 3: "irrelevant"}


@pytest.mark.parametrize("reply", ["not json", "[]", '{"results": "oops"}', "null", '{"other": 1}'])
def test_score_batch_survives_malformed_replies(reply):
    assert score_batch(CannedLLM(reply), "Co", "ZZ", ["a"]) == {}


@pytest.fixture
def conn():
    now = datetime.now(timezone.utc)
    titles = [("zzs1", "Co beats earnings", 1), ("zzs2", "Regulators open probe into Co", 2),
              ("zzs3", "Co holds annual meeting", 3), ("zzs4", "Old story: Co beats estimates", 30)]
    with connect() as c:
        c.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Sentiment Co')", (SYMBOL,))
        for key, title, days_ago in titles:
            c.execute(
                "INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
                "VALUES (%s, 'fake', %s, 'Wire', 'https://x', %s)", (f"fake:{key}", title, now - timedelta(days=days_ago)))
            c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"fake:{key}", SYMBOL))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzs%'")
        c.execute("DELETE FROM instruments WHERE symbol = %s", (SYMBOL,))
        c.commit()


def labels(conn, model):
    rows = conn.execute("SELECT article_id, label FROM news_sentiment WHERE symbol = %s AND model = %s", (SYMBOL, model))
    return {a.removeprefix("fake:"): label for a, label in rows}


def test_scores_everything_once_and_batches(conn):
    llm = KeywordLLM()
    assert score_symbol(conn, llm, SYMBOL, batch_size=3) == (4, 0)
    assert llm.calls == 2  # 4 headlines in batches of 3
    assert labels(conn, "fake-a") == {"zzs1": "positive", "zzs2": "negative", "zzs3": "neutral", "zzs4": "positive"}
    assert score_symbol(conn, llm, SYMBOL) == (0, 0) and llm.calls == 2  # nothing left to do


def test_skipped_headlines_are_retried_next_run(conn):
    assert score_symbol(conn, KeywordLLM(skip=["annual"]), SYMBOL) == (3, 1)
    assert "zzs3" not in labels(conn, "fake-a")
    assert score_symbol(conn, KeywordLLM(), SYMBOL) == (1, 0)
    assert labels(conn, "fake-a")["zzs3"] == "neutral"


def test_a_different_model_scores_separately(conn):
    score_symbol(conn, KeywordLLM("fake-a"), SYMBOL)
    assert score_symbol(conn, KeywordLLM("fake-b"), SYMBOL) == (4, 0)
    assert len(labels(conn, "fake-b")) == 4


def test_unknown_symbol_is_rejected(conn):
    with pytest.raises(ValueError, match="not in instruments"):
        score_symbol(conn, KeywordLLM(), "NOPE")


def test_summary_counts_window_and_score(conn):
    score_symbol(conn, KeywordLLM(), SYMBOL)
    s = summarize(conn, SYMBOL, "fake-a", days=7)  # the 30-day-old story falls outside
    assert (s.positive, s.neutral, s.negative, s.irrelevant) == (1, 1, 1, 0)
    assert s.score == 0.0
    assert summarize(conn, SYMBOL, "fake-a", days=60).score == pytest.approx(1 / 4)
    assert summarize(conn, SYMBOL, "other-model").score is None


def add_story(c, key, title, publisher, hours_ago, labels, symbols=(SYMBOL,)):
    """Insert one article for each symbol and give it the label `labels[symbol]` (None leaves it unlabeled)."""
    c.execute("INSERT INTO news_articles (id, source, title, publisher, url, published_at) "
              "VALUES (%s, 'fake', %s, %s, 'https://x', now() - make_interval(hours => %s))",
              (f"fake:{key}", title, publisher, hours_ago))
    for sym in symbols:
        c.execute("INSERT INTO news_article_symbols (article_id, symbol) VALUES (%s, %s)", (f"fake:{key}", sym))
        if labels.get(sym):
            c.execute("INSERT INTO news_sentiment (article_id, symbol, label, model) VALUES (%s, %s, %s, 'fake-a')",
                      (f"fake:{key}", sym, labels[sym]))


def test_totals_count_each_story_once_and_skip_quote_pages(conn):
    score_symbol(conn, KeywordLLM(), SYMBOL)  # beats = positive, probe = negative, the rest neutral
    # a repeat of "Co beats earnings" from another outlet, carrying the outlet in the title like Google News does
    add_story(conn, "zzs5", "Co beats earnings - Other Wire", "Other Wire", 1, {SYMBOL: "positive"})
    # one story carried twice and labeled differently each time: the newest copy's label is the one that counts
    add_story(conn, "zzs6", "Co settles lawsuit", "Wire", 3, {SYMBOL: "negative"})
    add_story(conn, "zzs7", "CO SETTLES  LAWSUIT", "Wire 2", 20, {SYMBOL: "neutral"})
    for i, title in enumerate(["Co (ZZSEN) Stock Price Today: $12.30", "Co Stock Price, News, Quote & History",
                               "Co vs. Rival: Which Is a Better Buy?"]):
        add_story(conn, f"zzs8{i}", title, "Quotes", 2, {SYMBOL: "positive"})  # even a "positive" quote page is left out
    conn.commit()
    s = summarize(conn, SYMBOL, "fake-a", days=7)
    # positive: beats (once). negative: probe + the newest copy of the lawsuit story. neutral: annual meeting only.
    assert (s.positive, s.neutral, s.negative, s.irrelevant) == (1, 1, 2, 0)
    assert s.score == pytest.approx(-1 / 4)


def test_a_story_about_two_companies_counts_for_each(conn):
    other = "ZZSE2"
    conn.execute("INSERT INTO instruments (symbol, name) VALUES (%s, 'Second Co')", (other,))
    try:
        add_story(conn, "zzs9", "Co and Second Co announce a merger", "Wire", 1, {SYMBOL: "positive", other: "irrelevant"},
                  symbols=(SYMBOL, other))
        add_story(conn, "zzs90", "Co and Second Co announce a merger", "Other", 2, {SYMBOL: "positive", other: "irrelevant"},
                  symbols=(SYMBOL, other))
        conn.commit()
        everyone = label_counts(conn, "fake-a", days=7)
        assert everyone == {SYMBOL: {"positive": 1}, other: {"irrelevant": 1}}
        assert label_counts(conn, "fake-a", days=7, symbol=other) == {other: {"irrelevant": 1}}
        assert label_counts(conn, "other-model", days=7) == {}
    finally:
        conn.rollback()
        conn.execute("DELETE FROM news_articles WHERE id LIKE 'fake:zzs%'")
        conn.execute("DELETE FROM instruments WHERE symbol = %s", (other,))
        conn.commit()


def test_score_formula_ignores_irrelevant():
    assert SentimentSummary("X", 3, 1, 0, 50).score == pytest.approx(3 / 4)
    assert SentimentSummary("X", 0, 0, 0, 5).score is None
