"""Check how the copilot behaves on price, news, and sentiment questions. Needs the database and Ollama running.

Usage: python -m ai.eval_market [--held-out | --sealed] [--show]

Each case runs the full copilot (not just the routing) and checks, with simple rules, that the right kinds of
evidence were used and that the answer stays inside the rules: no invented causes for a price move, no predictions
or advice, figures copied from the sources, a plain refusal when the data isn't there. It passes or fails on rules
only, so a pass means "nothing the rules look for went wrong", not "the answer is good". Read the answers (--show)
too. Results are a sample from one small model, not a guarantee. Takes a few minutes.
"""
import argparse
import re
import sys
import time
from dataclasses import dataclass, field

from data.db import connect
from data.fundamentals import compute, format_money, latest_close, load_facts

from .copilot import CAUSE_CAUTION, Answer, answer_question
from .embeddings import FastEmbedder
from .eval_cases import CASES, HELD_OUT, SEALED
from .eval_cases.common import ADVICE, CANT, LEAKED, Case
from .llm import get_llm


DECLINING = re.compile(r"\b(?:whether|if|question|not|no)\b|" + CANT, re.IGNORECASE)


def asserted_sentences(text: str) -> str:
    """The answer without sentences that merely restate the question or say something can't be done."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(s for s in sentences if not DECLINING.search(s))


def expected_figure(conn, spec: str) -> str:
    """The digits Python computes today for "SYMBOL:figure" (the same worked-out values the copilot is given), so a case
    checks that the answer quoted the real figure and doesn't go stale when the price moves."""
    symbol, name = spec.split(":")
    close, close_date = latest_close(conn, symbol)
    f = compute(symbol, load_facts(conn, symbol), close, close_date)
    flows = {"revenue": f.revenue, "net_income": f.net_income, "operating_income": f.operating_income}
    if name in flows:
        return re.search(r"[\d,.]+", format_money(flows[name].value)).group()
    if name == "market_value":
        return re.search(r"[\d,.]+", format_money(f.market_value)).group()
    if name == "revenue_growth":
        return f"{f.revenue.growth * 100:.1f}"
    if name == "eps":
        return f"{f.diluted_eps.value:.2f}"
    if name == "pe":
        return f"{f.pe:.1f}"
    return f"{getattr(f, name) * 100:.1f}"  # gross_margin, operating_margin, net_margin


@dataclass
class Result:
    case: Case
    problems: list[str]
    answer: Answer
    seconds: float
    notes: list[str] = field(default_factory=list)  # things worth reading that don't fail the case

    @property
    def ok(self) -> bool:
        return not self.problems


def run_case(conn, embedder, llm, case: Case) -> Result:
    started = time.time()
    ans = answer_question(conn, embedder, llm, case.question, history=list(case.history))
    problems = []
    seen = {getattr(r, "kind", "filing") for r in ans.retrieved} if not ans.refused else set()
    if seen != set(case.evidence):
        problems.append(f"evidence was {sorted(seen) or 'none'}, expected {sorted(case.evidence) or 'none'}")
    if case.companies and set(ans.symbols) != set(case.companies):
        problems.append(f"companies were {sorted(ans.symbols)}, expected {sorted(case.companies)}")
    if not ans.refused:
        if not ans.grounded and not case.ungrounded_ok:
            problems.append("the answer cites no source")
        if ans.unverified_numbers:
            problems.append(f"figures not in the cited sources: {', '.join(ans.unverified_numbers)}")
        if CAUSE_CAUTION in ans.cautions:
            problems.append("the answer still implies a cause after the retry (a caution would be shown)")
        shown = [c for c in ans.cautions if c != CAUSE_CAUTION]
        for pattern in case.cautions_shown:
            if not any(re.search(pattern, c, re.IGNORECASE) for c in shown):
                problems.append(f"missing caution: {pattern[:60]}")
        if case.no_cautions and shown:
            problems.append(f"a caution that doesn't concern the question was shown: {shown[0][:90]}")
        for spec in case.figures:
            digits = expected_figure(conn, spec)
            if not re.search(rf"(?<![\d.]){re.escape(digits)}(?!\d)", ans.text):
                problems.append(f"{spec} should be quoted as {digits}")
        for pattern in case.must:
            if not re.search(pattern, ans.text, re.IGNORECASE | re.DOTALL):
                problems.append(f"missing: {pattern[:70]}")
        for pattern in case.must_not + (LEAKED,):
            if m := re.search(pattern, ans.text, re.IGNORECASE):
                problems.append(f"should not say: '{m.group(0)}'")
        for pattern in case.must_not_asserted + (ADVICE,):
            if m := re.search(pattern, asserted_sentences(ans.text), re.IGNORECASE):
                problems.append(f"should not say: '{m.group(0)}'")
    if ans.refused:  # the text of a refusal is written in code, so a case that names what it should say is checked too (2026-10-16)
        for pattern in case.must:
            if not re.search(pattern, ans.text, re.IGNORECASE | re.DOTALL):
                problems.append(f"missing in the refusal: {pattern[:70]}")
        for pattern in case.cautions_shown:  # a refused advice question carries the notice too (2026-10-18)
            if not any(re.search(pattern, c, re.IGNORECASE) for c in ans.cautions):
                problems.append(f"missing caution in the refusal: {pattern[:60]}")
    notes = [f"the model's own text did not restate: {p[:50]}" for p in case.restates
             if not ans.refused and not re.search(p, ans.text, re.IGNORECASE)]
    return Result(case, problems, ans, time.time() - started, notes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--held-out", action="store_true", help="run only the cases that were never used to adjust the prompt")
    parser.add_argument("--sealed", action="store_true",
                        help="run only the sealed test set (SEALED): once, at the end of the routing experiment; never to tune on")
    parser.add_argument("--show", action="store_true", help="print every answer, not just the failures")
    parser.add_argument("--repeat", type=int, default=1, help="run everything this many times to see how stable it is")
    args = parser.parse_args(argv)
    cases = SEALED if args.sealed else HELD_OUT if args.held_out else CASES
    if not cases:
        sys.exit("There are no held-out cases yet: every case has been looked at. Write new ones first (see HELD_OUT).")

    llm = get_llm()
    available = getattr(llm, "available", None)
    if callable(available) and not available():
        sys.exit("The AI model isn't reachable. Start Ollama and try again.")

    embedder = FastEmbedder()
    with connect() as conn:
        runs = [[run_case(conn, embedder, llm, c) for c in cases] for _ in range(args.repeat)]
    results = runs[0]

    print(f"model: {llm.name}\n")
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  [{r.case.kind:<9}] {r.case.name}  ({r.seconds:.0f}s)")
        for p in r.problems:
            print(f"      - {p}")
        for n in r.notes:
            print(f"      note: {n}")
        if args.show or not r.ok:
            print(f"      Q: {r.case.question}")
            print("      A: " + r.answer.text.replace("\n", "\n         "))
    for kind in ("routing", "trap", "unchanged"):
        rs = [r for r in results if r.case.kind == kind]
        if rs:
            print(f"\n{kind}: {sum(r.ok for r in rs)}/{len(rs)} passed")
    print(f"total: {sum(r.ok for r in results)}/{len(results)}   average {sum(r.seconds for r in results) / max(1, len(results)):.1f}s per case")
    for i, c in enumerate(cases):
        if c.restates:
            said = sum(not run[i].notes for run in runs)
            print(f"restated by the model's own text: {said}/{len(runs)}  {c.name} (the caution itself was attached in code either way)")
    if args.repeat > 1:
        print(f"\nover {args.repeat} runs ({sum(r.ok for run in runs for r in run)}/{len(cases) * args.repeat} passed in all):")
        for i, c in enumerate(cases):
            passed = sum(run[i].ok for run in runs)
            if passed != args.repeat:
                print(f"  {passed}/{args.repeat}  {c.name}")
                for n, run in enumerate(runs[1:], 2):  # run 1's details are printed above
                    if not run[i].ok:
                        print(f"      run {n}: " + "; ".join(run[i].problems))
                        print("      A: " + run[i].answer.text.replace("\n", "\n         "))
    return 0 if all(r.ok for run in runs for r in run) else 1


if __name__ == "__main__":
    sys.exit(main())
