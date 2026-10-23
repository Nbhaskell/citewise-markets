"""Prices, headlines, headline sentiment, and company financial figures as numbered evidence for the copilot.

Usage: python -m ai.market AAPL "How has Apple stock done this year?"   (print the evidence the copilot would see)
"""
import argparse
import sys

from data.db import connect

from .evidence import gather_market_evidence
from .intent import detect_intent
from .windows import parse_window


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbol")
    parser.add_argument("question")
    parser.add_argument("--model", default="ollama:qwen3:latest", help="whose sentiment labels to use")
    args = parser.parse_args(argv)
    intent, window = detect_intent(args.question), parse_window(args.question)
    print(f"intent: {intent}\nwindow: {window}\n")
    with connect() as conn:
        for i, ev in enumerate(gather_market_evidence(conn, [args.symbol.upper()], intent, window, args.model), 1):
            print(f"[{i}] {ev.header}\n{ev.text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
