"""Shadow measurement for the router "second look" (docs/DECISIONS.md, "Router second look").

Today the model is asked only when the keyword rules find no route. This script records what the router WOULD say about every research
question, without changing any answer, and then scores several policies for "what to do when the keywords chose something specific"
OFFLINE, from the recording, so nothing needs the model twice and a changed rule can be re-scored without it.

    python -m ai.eval_router_shadow --plan                       what it would do, no model, no recording
    python -m ai.eval_router_shadow --run --out FILE [--repeat 3] [--only "sl "]    ask the model (needs Ollama), save, report
    python -m ai.eval_router_shadow --score FILE [--only "sl "]  re-score a recording offline

A case counts as passed when the kinds of evidence the policy ends up with equal the kinds the case expects (the same primary check the
evaluation makes; this does not write or read an answer). Cases with a follow-up (their standalone question needs the rewrite step) and
cases that expect a refusal made in code are left out. The sealed set is never measured: there is no option for it, and any case that
belongs to it is dropped.
"""
import argparse
import json
import sys
import time
from typing import Callable, Optional

from .eval_market import CASES, SEALED, Case
from .llm import LLM, get_llm
from .market import Intent, detect_intent
from .router import Route, apply_route, ask_router, deliberately_filings, evidence_kinds

SECONDS_PER_CALL = 1.5  # measured: the router call adds about a second and a half on this PC

# What to do when the keywords chose a specific route (any of prices, headlines, sentiment or figures). When they chose nothing the
# model decides, as it does today, in every policy. Each takes the keyword kinds and the kinds the router chose on its own.
POLICIES: dict[str, Callable[[list[str], list[str]], list[str]]] = {
    "today": lambda kw, rt: kw,                                                          # never second-guess
    "replace": lambda kw, rt: rt,                                                        # the model overrules
    "replace-to-filings": lambda kw, rt: rt if rt == ["filing"] else kw,                 # overrule only to send it to the filings
    "intersect-else-router": lambda kw, rt: [k for k in kw if k in rt] or rt,            # keep what both chose; nothing shared: the model
    "intersect-else-keywords": lambda kw, rt: [k for k in kw if k in rt] or kw,          # keep what both chose; nothing shared: the keywords
}


def final_kinds(policy: str, question: str, has_company: bool, route: Optional[Route]) -> list[str]:
    """The kinds of evidence a policy would end up with. A question decided in code (an unstored ratio, advice), a question the keywords
    hold to the filings on purpose (a filing named, a quarter, "why", dividends, "sales") and a router that failed or gave a verdict that
    is not a route (outside, writing) all keep the keyword route, as they do today."""
    keywords = detect_intent(question)
    kw = evidence_kinds(keywords)
    if route is None or keywords.unstored or keywords.advice or deliberately_filings(question):
        return kw
    routed, verdict = apply_route(Intent(), route, has_company, question)
    if verdict is not None:
        return kw
    rt = evidence_kinds(routed)
    return POLICIES[policy](kw, rt) if keywords.market else rt


# ---- which cases ----


def shadow_cases(cases=CASES, only: tuple[str, ...] = ()) -> list[Case]:
    """Research cases with no follow-up. Anything in the sealed set is dropped, always."""
    sealed = {c.name for c in SEALED}
    return [c for c in cases if c.evidence and not c.history and c.name not in sealed and (not only or c.name.startswith(only))]


# ---- the recording ----


def route_to_json(route: Optional[Route]) -> Optional[dict]:
    if route is None:
        return None
    return {"category": route.category, "prices": route.prices, "news": route.news, "sentiment": route.sentiment,
            "figures": sorted(route.figures), "filings": route.filings, "advice": route.advice}


def route_from_json(data: Optional[dict]) -> Optional[Route]:
    if data is None:
        return None
    return Route(data["category"], data["prices"], data["news"], data["sentiment"], frozenset(data["figures"]), data["filings"],
                 data["advice"])


def _records(cases: list[Case], repeat: int, ask: Callable[[str], Optional[dict]]) -> list[dict]:
    """One record per case. Scores are keyed by name and the evaluation uses one name twice, so a repeated name gets " (2)", " (3)"."""
    seen: dict[str, int] = {}
    out = []
    for c in cases:
        seen[c.name] = seen.get(c.name, 0) + 1
        name = c.name if seen[c.name] == 1 else f"{c.name} ({seen[c.name]})"
        out.append({"name": name, "question": c.question, "expected": sorted(c.evidence), "companies": sorted(c.companies),
                    "routes": [ask(c.question) for _ in range(repeat)]})
    return out


def record(llm: LLM, cases: list[Case], repeat: int) -> list[dict]:
    """Ask the router about each case `repeat` times. A failed call is recorded as None, as the app treats it."""
    return _records(cases, repeat, lambda question: route_to_json(ask_router(llm, question)))


# ---- scoring, offline ----


def score(records: list[dict]) -> dict[str, dict[str, list[bool]]]:
    """policy -> case name -> one pass/fail per repeat."""
    return {
        policy: {
            r["name"]: [
                set(final_kinds(policy, r["question"], bool(r["companies"]), route_from_json(route))) == set(r["expected"])
                for route in r["routes"]
            ]
            for r in records
        }
        for policy in POLICIES
    }


def _group(name: str) -> str:
    return "development (sl)" if name.startswith("sl ") else "older cases"


def report(records: list[dict]) -> str:
    scored = score(records)
    runs = sum(len(r["routes"]) for r in records)
    lines = [f"{len(records)} cases, {runs} case-runs", ""]
    names = [r["name"] for r in records]
    groups = sorted({_group(n) for n in names})
    lines.append(f"{'policy':26} {'all':>9}  " + "  ".join(f"{g:>20}" for g in groups))
    for policy, by_case in scored.items():
        total = sum(sum(v) for v in by_case.values())
        cells = []
        for g in groups:
            ns = [n for n in names if _group(n) == g]
            cells.append(f"{sum(sum(by_case[n]) for n in ns)}/{sum(len(by_case[n]) for n in ns)}")
        lines.append(f"{policy:26} {total:>4}/{runs:<4}  " + "  ".join(f"{c:>20}" for c in cells))
    base = scored["today"]
    for policy, by_case in scored.items():
        lines += ["", policy]
        if policy == "today":
            lines.append("  (the baseline: the model is asked only when the keywords found no route)")
            continue
        gains = [(n, sum(by_case[n]) - sum(base[n])) for n in names if sum(by_case[n]) > sum(base[n])]
        losses = [(n, sum(base[n]) - sum(by_case[n])) for n in names if sum(by_case[n]) < sum(base[n])]
        lines.append(f"  gains over today ({len(gains)}): " + "; ".join(f"{n} (+{d})" for n, d in gains))
        lines.append(f"  losses against today ({len(losses)}): " + "; ".join(f"{n} (-{d})" for n, d in losses))
    return "\n".join(lines)


# ---- the command line ----


def plan(cases: list[Case], repeat: int) -> str:
    sealed = len(SEALED)
    calls = len(cases) * repeat
    keywords_only = _records(cases, 1, lambda question: None)        # no router: every policy falls back to the keywords
    by_group: dict[str, list[bool]] = {}
    for name, passed in score(keywords_only)["today"].items():
        by_group.setdefault(_group(name), []).extend(passed)
    lines = [
        f"cases measured: {len(cases)} (research cases with no follow-up; the follow-ups and the refusals decided in code are left out)",
        f"repeats: {repeat}   model calls: {calls}   about {calls * SECONDS_PER_CALL / 60:.0f} minutes at {SECONDS_PER_CALL} s per call",
        "it asks the router question only: no answer is written, no search is run, nothing in the app changes",
        f"sealed set: not touched ({sealed} cases are excluded, and this script has no option for them)",
        f"policies scored offline from the recording: {', '.join(POLICIES)}",
        "keywords alone, no model needed (what the 'today' column starts from when the model is not asked):",
    ]
    lines += [f"  {g}: {sum(v)}/{len(v)}" for g, v in sorted(by_group.items())]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="say what a run would do; no model is built")
    mode.add_argument("--run", action="store_true", help="ask the model (needs Ollama), save the recording, print the report")
    mode.add_argument("--score", metavar="FILE", help="re-score a saved recording offline")
    parser.add_argument("--out", help="where --run saves the recording (JSON)")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--only", action="append", default=[], help='only cases whose name starts with this (for example "sl ")')
    args = parser.parse_args(argv)
    if args.run and not args.out:
        parser.error("--run needs --out FILE")
    only = tuple(args.only)

    if args.score:
        with open(args.score, encoding="utf-8") as f:
            data = json.load(f)
        records = [r for r in data["records"] if not only or r["name"].startswith(only)]
        print(report(records))
        return 0
    cases = shadow_cases(CASES, only)
    if args.plan:
        print(plan(cases, args.repeat))
        return 0

    llm = get_llm()
    available = getattr(llm, "available", None)
    if callable(available) and not available():
        sys.exit("The AI model isn't reachable. Start Ollama and try again.")
    started = time.time()
    records = record(llm, cases, args.repeat)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"model": getattr(llm, "name", ""), "repeat": args.repeat, "seconds": round(time.time() - started),
                   "records": records}, f, indent=1)
    print(f"saved {len(records)} cases x {args.repeat} to {args.out} in {time.time() - started:.0f} s\n")
    print(report(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
