"""Label news headlines positive, negative, neutral, or irrelevant for a company's stock.

Usage:
  python -m ai.sentiment AAPL NVDA            score unscored headlines, then print a summary
  python -m ai.sentiment AAPL --days 3        summarize the last 3 days
  python -m ai.sentiment AAPL --no-score      only print the summary
"""
import argparse
import json
import sys
from dataclasses import dataclass

import psycopg

from data.db import connect

from .llm import LLM, get_llm

LABEL_VALUE = {"positive": 1, "neutral": 0, "negative": -1}  # "irrelevant" is left out of averages
BATCH_SIZE = 15

SYSTEM_PROMPT = """You label news headlines by how they affect the stock of ONE company, from the point of view of an investor who owns it.

Labels:
- positive: likely good for the stock (strong results, upgrades, new wins, favorable rulings)
- negative: likely bad for the stock (weak results, downgrades, lawsuits, probes, recalls, lost customers)
- neutral: no clear effect, or routine/low-information items (a fund buying or selling shares, price quote pages, listicles, explainers, analyst opinion pieces without news)
- irrelevant: not actually about the named company

Judge only the headline text. Do not use outside knowledge. When unsure, choose neutral.
Reply as JSON: {"results": [{"id": <number>, "sentiment": "<label>"}, ...]} with one entry per headline."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral", "irrelevant"]},
                },
                "required": ["id", "sentiment"],
            },
        }
    },
    "required": ["results"],
}


def score_batch(llm: LLM, company: str, symbol: str, headlines: list[str]) -> dict[int, str]:
    """Labels keyed by 1-based headline number. Entries the model got wrong or skipped are left out."""
    lines = "\n".join(f"{i}. {h}" for i, h in enumerate(headlines, 1))
    user = f"Company: {company} ({symbol})\n\nHeadlines:\n{lines}"
    try:
        data = json.loads(llm.generate(SYSTEM_PROMPT, user, json_schema=SCHEMA))
    except (json.JSONDecodeError, TypeError):
        return {}
    labels: dict[int, str] = {}
    for item in data.get("results", []) if isinstance(data, dict) else []:
        try:
            n, label = int(item["id"]), item["sentiment"]
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= n <= len(headlines) and label in {"positive", "negative", "neutral", "irrelevant"}:
            labels.setdefault(n, label)
    return labels


def score_symbol(conn: psycopg.Connection, llm: LLM, symbol: str, batch_size: int = BATCH_SIZE) -> tuple[int, int]:
    """Score every headline for `symbol` that this model hasn't labeled yet. Returns (scored, left_unscored)."""
    symbol = symbol.upper()
    row = conn.execute("SELECT name FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
    if row is None:
        raise ValueError(f"{symbol} is not in instruments; run data.ingest {symbol} first")
    pending = conn.execute(
        "SELECT a.id, a.title FROM news_articles a "
        "JOIN news_article_symbols s ON s.article_id = a.id AND s.symbol = %s "
        "WHERE NOT EXISTS (SELECT 1 FROM news_sentiment n "
        "                  WHERE n.article_id = a.id AND n.symbol = s.symbol AND n.model = %s) "
        "ORDER BY a.published_at DESC",
        (symbol, llm.name),
    ).fetchall()

    scored = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        labels = score_batch(llm, row[0] or symbol, symbol, [title for _, title in batch])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO news_sentiment (article_id, symbol, label, model) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                [(batch[n - 1][0], symbol, label, llm.name) for n, label in labels.items()],
            )
        conn.commit()
        scored += len(labels)
    return scored, len(pending) - scored


@dataclass(frozen=True)
class SentimentSummary:
    symbol: str
    positive: int
    neutral: int
    negative: int
    irrelevant: int

    @property
    def counted(self) -> int:
        return self.positive + self.neutral + self.negative

    @property
    def score(self) -> float | None:
        """Mean of +1/0/-1 over relevant headlines, from -1 (all bad) to +1 (all good); None if no data."""
        return (self.positive - self.negative) / self.counted if self.counted else None


def summarize(conn: psycopg.Connection, symbol: str, model: str, days: int = 7) -> SentimentSummary:
    counts = dict(
        conn.execute(
            "SELECT n.label, count(*) FROM news_sentiment n JOIN news_articles a ON a.id = n.article_id "
            "WHERE n.symbol = %s AND n.model = %s AND a.published_at >= now() - make_interval(days => %s) "
            "GROUP BY n.label",
            (symbol.upper(), model, days),
        ).fetchall()
    )
    return SentimentSummary(symbol.upper(), *(counts.get(k, 0) for k in ("positive", "neutral", "negative", "irrelevant")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--no-score", action="store_true", help="skip scoring; only summarize")
    args = parser.parse_args(argv)

    llm = get_llm()
    failures = 0
    with connect() as conn:
        for symbol in args.symbols:
            try:
                if not args.no_score:
                    scored, left = score_symbol(conn, llm, symbol)
                    print(f"{symbol.upper()}: scored {scored} headlines" + (f", {left} could not be scored" if left else ""))
                s = summarize(conn, symbol, llm.name, args.days)
                score = "n/a" if s.score is None else f"{s.score:+.2f}"
                print(
                    f"  last {args.days}d: {s.positive} positive, {s.neutral} neutral, {s.negative} negative, "
                    f"{s.irrelevant} irrelevant | score {score}"
                )
            except Exception as exc:
                failures += 1
                conn.rollback()
                print(f"{symbol.upper()}: FAILED - {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
