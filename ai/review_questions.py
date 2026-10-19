"""List the questions logged by the web app and mark the answers that look like misses.

Usage: python -m ai.review_questions [--last 20] [--since 2026-10-19] [--flagged] [--full] [--path FILE]

A question is "flagged" when it was refused, the answer says the sources do not have what was asked ("gave up"), the answer cites nothing, or
it quotes numbers that are not in its sources. Two more notes are shown but are not flags: the local model's router chose the data, and a caution
was shown. The signals are a first filter for the owner to read, not a verdict: a refusal can be right.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .question_log import log_path

GAVE_UP_RE = re.compile(
    r"\b(?:sources?|data|information|filings?)\b[^.]{0,60}?\b(?:do(?:es)?\s+not|don['’]t|doesn['’]t)\s+(?:provide|include|contain|mention|cover|address|specify|show|have)\b"
    r"|\bnot\s+(?:possible|available)\b|\bcannot\s+(?:be\s+)?determine",
    re.IGNORECASE,
)
FLAGS = ("refused", "gave up", "uncited", "unverified numbers")


def signals(record: dict) -> list[str]:
    out = []
    if record.get("refused"):
        out.append("refused")
    if GAVE_UP_RE.search(record.get("answer") or ""):
        out.append("gave up")
    if not record.get("refused") and not record.get("grounded"):
        out.append("uncited")
    if record.get("unverified_numbers"):
        out.append("unverified numbers")
    if record.get("model_route"):
        out.append("router chose")
    if record.get("cautions"):
        out.append("caution shown")
    return out


def flagged(record: dict) -> bool:
    return any(s in FLAGS for s in signals(record))


def load(path: Path) -> tuple[list[dict], int]:
    """The logged records, and how many lines could not be read (blank lines are not counted)."""
    if not path.exists():
        return [], 0
    records, bad = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(rec, dict):
            records.append(rec)
        else:
            bad += 1
    return records, bad


def _when(record: dict):
    try:
        when = datetime.fromisoformat(record.get("ts", ""))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=None, help="the log file (default: logs/copilot_questions.jsonl)")
    parser.add_argument("--last", type=int, default=20, help="how many of the newest questions to show (default 20)")
    parser.add_argument("--since", help="only questions from this day on, YYYY-MM-DD")
    parser.add_argument("--flagged", action="store_true", help="only the questions that look like misses")
    parser.add_argument("--full", action="store_true", help="show whole answers, not the first 300 characters")
    args = parser.parse_args(argv)

    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            print("--since must be a date like YYYY-MM-DD")
            return 2

    path = args.path or log_path()
    records, bad = load(path)
    if not records:
        print(f"No questions logged yet ({path}).")
        return 0
    if since:
        records = [r for r in records if (w := _when(r)) is not None and w >= since]
    if args.flagged:
        records = [r for r in records if flagged(r)]
    shown = records[-args.last:] if args.last > 0 else records
    if not shown:
        print("No questions matched.")
        return 0

    for r in shown:
        sig = signals(r)
        when = _when(r)
        stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if when else "unknown time"
        print(f"\n[{stamp}] ({', '.join(sig) if sig else 'no signals'})  companies: {', '.join(r.get('companies') or []) or '-'}  "
              f"data: {', '.join(r.get('evidence_kinds') or []) or '-'}")
        print(f"Q: {r.get('question')}")
        if r.get("interpreted_question"):
            print(f"   understood as: {r['interpreted_question']}")
        answer = (r.get("answer") or "").strip()
        if not args.full and len(answer) > 300:
            answer = answer[:300].rstrip() + "..."
        print("A: " + answer.replace("\n", "\n   "))
    n_flag = sum(flagged(r) for r in shown)
    n_ref = sum(bool(r.get("refused")) for r in shown)
    n_route = sum(bool(r.get("model_route")) for r in shown)
    print(f"\n{len(shown)} questions, {n_flag} flagged, {n_ref} refused, {n_route} router-routed, {bad} unreadable line(s).")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
