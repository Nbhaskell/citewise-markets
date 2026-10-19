"""A local log of the questions asked through the web app (DECISIONS: "Question log").

One JSON line per answered question is appended to `logs/copilot_questions.jsonl` (this PC only; `logs/` is git-ignored and nothing leaves the
machine). It keeps what was asked, how it was understood, which data was looked at, and the answer, so the real questions and the answers
that looked wrong can replace synthetic evaluation rounds (`python -m ai.review_questions` lists them and marks likely misses). It does not keep
the sources' text.

This is a server-side write that is not a new endpoint; the owner approved it on 2026-10-19 (CLAUDE.md: API rules). It must never break an
answer: any failure is reported on stderr and swallowed. Switch it off with `COPILOT_LOG=off` (also `0`, `false`, `no`, `none`); a blank or
unrecognised value keeps it on. `COPILOT_LOG_FILE` points it somewhere else (the tests do). The test suite switches it off (tests/conftest.py).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .router import router_enabled

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "logs" / "copilot_questions.jsonl"
OFF_VALUES = ("off", "0", "false", "no", "none")


def log_enabled() -> bool:
    return os.environ.get("COPILOT_LOG", "").strip().lower() not in OFF_VALUES


def log_path() -> Path:
    custom = os.environ.get("COPILOT_LOG_FILE", "").strip()
    return Path(custom) if custom else DEFAULT_PATH


def log_answer(response: dict, history_len: int = 0) -> None:
    """Append one answered question (the API's response dict) to the log. Never raises."""
    if not log_enabled():
        return
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": response.get("question"),
            "interpreted_question": response.get("interpreted_question"),
            "follow_up": history_len > 0,
            "companies": response.get("companies", []),
            "evidence_kinds": response.get("evidence_kinds", []),
            "model_route": response.get("model_route", []),
            "router": router_enabled(None),
            "refused": response.get("refused"),
            "grounded": response.get("grounded"),
            "unverified_numbers": response.get("unverified_numbers", []),
            "cautions": response.get("cautions", []),
            "sources": len(response.get("sources", [])),
            "answer": response.get("answer"),
        }
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # a log that cannot be written must not take the answer with it
        print(f"question log not written: {exc}", file=sys.stderr)
