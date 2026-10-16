"""Check how well the model understands follow-up questions. Needs the database and Ollama running.

Usage: python -m ai.eval_followups [--repeat 2]

Each case is a short conversation plus a follow-up. It passes if the follow-up resolves to the right companies (and,
where given, the standalone question mentions the right topic). Only the "understand the question" step runs, not the
full answer, so it takes about a minute. Use it to compare models or prompts. Results are a sample, not a guarantee.
"""
import argparse
import sys
import time
from dataclasses import dataclass, field

from data.db import connect

from .copilot import Turn, resolve_question
from .llm import get_llm


@dataclass(frozen=True)
class Case:
    name: str
    kind: str  # "follow-up" must be understood from earlier turns; "standalone" must not be changed by them
    history: tuple[Turn, ...]
    question: str
    expect: frozenset[str]  # the companies that should be searched ({} = none, a cross-company question)
    topic: str = ""  # a word the standalone question should contain
    keywords: tuple[str, ...] = field(default=())


def turn(q: str, a: str, *companies: str) -> Turn:
    return Turn(q, a, companies)


TSLA_EMP = turn("How many employees does Tesla have?", "As of December 31, 2025, Tesla had 134,785 employees worldwide.", "TSLA")
NVDA_RISK = turn("What are NVIDIA's biggest risks?", "NVIDIA's biggest risks include export controls and supply constraints.", "NVDA")
AAPL_EMP = turn("How many employees does Apple have?", "Apple had approximately 166,000 full-time employees.", "AAPL")

CASES: tuple[Case, ...] = (
    # Follow-ups that depend on earlier turns
    Case("pronoun, new topic", "follow-up", (TSLA_EMP,), "And what about its biggest risks?", frozenset({"TSLA"}), "risk"),
    Case("pronoun, other topic", "follow-up", (NVDA_RISK,), "How many employees does it have?", frozenset({"NVDA"}), "employees"),
    Case("which of them", "follow-up",
         (turn("Compare Apple's and Microsoft's biggest risks.", "Apple cites supply chain; Microsoft cites competition.", "AAPL", "MSFT"),),
         "Which of them has more employees?", frozenset({"AAPL", "MSFT"}), "employees"),
    Case("elliptical new company", "follow-up",
         (turn("What does Amazon say about legal proceedings?", "Amazon is subject to many legal claims.", "AMZN"),),
         "What about Google?", frozenset({"GOOGL"}), "legal"),
    Case("and <company>?", "follow-up", (AAPL_EMP,), "and Microsoft?", frozenset({"MSFT"}), "employees"),
    Case("same company, other report", "follow-up",
         (turn("How much did Microsoft's revenue grow in its latest annual report?", "Revenue grew 18%.", "MSFT"),),
         "What about the latest quarterly report?", frozenset({"MSFT"}), "quarter"),
    Case("tell me more", "follow-up",
         (turn("What does Tesla say about competition?", "Tesla faces competition from many automakers.", "TSLA"),),
         "Tell me more about that", frozenset({"TSLA"}), "competition"),
    Case("compare with another", "follow-up",
         (turn("Discuss Alphabet's cybersecurity governance.", "Alphabet's board oversees cybersecurity risk.", "GOOGL"),),
         "How does that compare to Amazon's?", frozenset({"GOOGL", "AMZN"}), "cybersecurity"),
    Case("most recent of two", "follow-up",
         (AAPL_EMP, NVDA_RISK), "What about its legal proceedings?", frozenset({"NVDA"}), "legal"),
    Case("deliberately back to the first", "follow-up",
         (AAPL_EMP, NVDA_RISK), "What about the first one's legal proceedings?", frozenset({"AAPL"}), "legal"),
    Case("their (two companies)", "follow-up",
         (turn("Compare Apple's and Tesla's debt.", "Apple has more debt than Tesla.", "AAPL", "TSLA"),),
         "What are their biggest risks?", frozenset({"AAPL", "TSLA"}), "risk"),
    # Questions that must NOT be bent by the earlier conversation
    Case("different company, full question", "standalone", (TSLA_EMP,), "How many employees does NVIDIA have?", frozenset({"NVDA"}), "employees"),
    Case("different topic and company", "standalone", (TSLA_EMP,), "What does Amazon say about legal proceedings?", frozenset({"AMZN"}), "legal"),
    Case("cross-company question", "standalone", (TSLA_EMP,), "Which company has the most employees?", frozenset(), "employees"),
    Case("new company after risks", "standalone", (NVDA_RISK,), "What are Microsoft's biggest risks?", frozenset({"MSFT"}), "risk"),
    Case("new company and report", "standalone", (AAPL_EMP,), "How did Microsoft's revenue change in its latest annual report?", frozenset({"MSFT"}), "revenue"),
    Case("unrelated question", "standalone", (TSLA_EMP,), "What is the best pizza recipe?", frozenset(), "pizza"),
)


# Written AFTER the prompt and safeguards above were tuned, in different wording. They were once the held-out set; they have
# since been run and used to adjust the rules, so (as of 2026-10-16) they are folded into CASES below and `HELD_OUT` is
# for fresh cases only.
MSFT_REV = turn("How much did Microsoft's revenue grow in its latest annual report?", "Revenue grew 18%.", "MSFT")
GOOGL_LEGAL = turn("What legal proceedings is Alphabet involved in?", "Alphabet faces many regulatory and legal matters.", "GOOGL")

PREVIOUS_HELD_OUT: tuple[Case, ...] = (
    Case("how about <company>", "follow-up", (MSFT_REV,), "How about Amazon?", frozenset({"AMZN"}), "revenue"),
    Case("they + new subtopic", "follow-up", (GOOGL_LEGAL,), "Are they involved in any antitrust matters?", frozenset({"GOOGL"}), "antitrust"),
    Case("the company", "follow-up", (NVDA_RISK, TSLA_EMP), "Does the company mention any recalls?", frozenset({"TSLA"}), "recall"),
    Case("same thing, new company", "follow-up",
         (turn("What does Tesla say about competition?", "Tesla faces competition from many automakers.", "TSLA"),),
         "What does Apple say about the same thing?", frozenset({"AAPL"}), "competition"),
    Case("that company's", "follow-up", (NVDA_RISK,), "What is that company's latest 10-Q about?", frozenset({"NVDA"}), "10-Q"),
    Case("drop to one of two", "follow-up",
         (turn("Compare Apple's and Microsoft's biggest risks.", "Apple cites supply chain; Microsoft cites competition.", "AAPL", "MSFT"),),
         "Tell me just about Microsoft's risks.", frozenset({"MSFT"}), "risk"),
    Case("names a company, uses 'its'", "standalone", (TSLA_EMP,), "What does Microsoft say about its cloud revenue?", frozenset({"MSFT"}), "cloud"),
    Case("explicitly all companies", "standalone", (AAPL_EMP,), "Compare all the companies' legal proceedings.", frozenset(), "legal"),
    Case("fresh topic, no company", "standalone", (NVDA_RISK,), "Which of the companies mentions climate change the most?", frozenset(), "climate"),
    Case("follow-up on the answer's detail", "follow-up", (NVDA_RISK,), "Which of those risks is the biggest one?", frozenset({"NVDA"}), "risk"),
)

# Written 2026-10-16 for step (c) (follow-ups that keep both companies, "Now do X" switches), in wording unlike the fixes'
# unit tests and probes, before any was run. Several are deliberate stretches (a comparison word or filler the rules do not
# know: "beat", "measure up", "ahead", "see"), so the score will show where the rules end. Once run, they are tuning material.
TSLA_RISK = turn("What are Tesla's biggest risks?", "Tesla cites supply chain and regulation.", "TSLA")
APPLE_TESLA_DEBT = turn("Compare Apple's and Tesla's debt.", "Apple has more debt than Tesla.", "AAPL", "TSLA")

STEP_C: tuple[Case, ...] = (
    Case("c: any riskier than", "follow-up", (TSLA_RISK,), "Does that look any riskier than Apple's?", frozenset({"TSLA", "AAPL"}), "risk"),
    Case("c: did that beat", "follow-up", (AAPL_EMP,), "Did that beat Microsoft?", frozenset({"AAPL", "MSFT"}), "employees"),
    Case("c: measure up", "follow-up", (TSLA_EMP,), "How does it measure up to Microsoft?", frozenset({"TSLA", "MSFT"}), "employees"),
    Case("c: okay, do next", "follow-up", (NVDA_RISK,), "Okay, do Tesla next.", frozenset({"TSLA"}), "risk"),
    Case("c: go ahead and do", "follow-up", (NVDA_RISK,), "Go ahead and do Amazon.", frozenset({"AMZN"}), "risk"),
    Case("c: run the same for", "follow-up", (AAPL_EMP,), "Run the same for Tesla.", frozenset({"TSLA"}), "employees"),
    Case("c: let's see instead", "follow-up", (AAPL_EMP,), "Let's see Amazon instead.", frozenset({"AMZN"}), "employees"),
    Case("c: more than a third", "follow-up", (APPLE_TESLA_DEBT,), "Is that more than Microsoft?", frozenset({"AAPL", "TSLA", "MSFT"}), "debt"),
    Case("c: comparison with its own topic", "follow-up", (AAPL_EMP,), "How do its margins compare to Amazon's?", frozenset({"AAPL", "AMZN"}), "margin"),
    Case("c: standalone comparison", "standalone", (NVDA_RISK,), "Is Apple bigger than Microsoft?", frozenset({"AAPL", "MSFT"}), "bigger"),
    Case("c: standalone, starts with do", "standalone", (TSLA_EMP,), "Do Microsoft and Amazon both mention litigation?",
         frozenset({"MSFT", "AMZN"}), "litigation"),
)
CASES = CASES + PREVIOUS_HELD_OUT + STEP_C

# Fresh cases for the whole second-round work, written 2026-10-16 BEFORE anything was run, in wording used nowhere else
# (checked against every case, test, and doc with a script). "stretch" marks a wording the rules probably do not know.
# RUN 2026-10-16 (3 repeats, identical each time): 3 of 8 passed (docs/DECISIONS.md, "Fresh held-out round"). Not tuned yet.
# They are tuning material from now on: write new ones before the next fair score.
HELD_OUT: tuple[Case, ...] = (
    Case("fr resolve: same again for", "follow-up", (TSLA_RISK,), "Same again for AMD, please.", frozenset({"AMD"}), "risk"),
    Case("fr resolve: longer list stretch", "follow-up", (NVDA_RISK,), "Is Tesla's list longer than that?",
         frozenset({"NVDA", "TSLA"}), "risk"),
    Case("fr resolve: number for too", "follow-up", (MSFT_REV,), "Give me the number for Apple too.", frozenset({"AAPL"}), "revenue"),
    Case("fr resolve: more people than", "follow-up", (AAPL_EMP,), "Does Amazon employ more people than that?",
         frozenset({"AAPL", "AMZN"}), "employees"),
    Case("fr resolve: skip to stretch", "follow-up", (GOOGL_LEGAL,), "Skip to Nvidia.", frozenset({"NVDA"}), "legal"),
    Case("fr resolve: which of the two", "follow-up", (APPLE_TESLA_DEBT,), "Which of the two spends more on research?",
         frozenset({"AAPL", "TSLA"}), "research"),
    Case("fr resolve: standalone comparison", "standalone", (TSLA_EMP,), "Does Amazon use more contractors than Nvidia?",
         frozenset({"AMZN", "NVDA"}), "contractors"),
    Case("fr resolve: standalone, all companies", "standalone", (NVDA_RISK,), "Summarize what the companies say about tariffs.",
         frozenset(), "tariffs"),
)


@dataclass
class Result:
    case: Case
    ok: bool
    companies: list[str]
    rewritten: str | None
    seconds: float


def run_case(conn, llm, case: Case) -> Result:
    started = time.time()
    search_question, companies, interpreted = resolve_question(conn, llm, case.question, None, list(case.history))
    ok = set(companies) == set(case.expect) and (not case.topic or case.topic.lower() in search_question.lower())
    return Result(case, ok, companies, interpreted, time.time() - started)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=1, help="run everything this many times to see how stable it is")
    parser.add_argument("--held-out", action="store_true", help="run only the cases that were never used to tune the prompt")
    args = parser.parse_args(argv)
    cases = HELD_OUT if args.held_out else CASES
    if not cases:
        sys.exit("There are no held-out cases yet: every case has been looked at. Write new ones first (see HELD_OUT).")

    llm = get_llm()
    available = getattr(llm, "available", None)
    if callable(available) and not available():
        sys.exit("The AI model isn't reachable. Start Ollama and try again.")

    runs: list[list[Result]] = []
    with connect() as conn:
        for _ in range(args.repeat):
            runs.append([run_case(conn, llm, c) for c in cases])

    first = runs[0]
    print(f"model: {llm.name}\n")
    for r in first:
        print(f"{'PASS' if r.ok else 'FAIL'}  [{r.case.kind:<10}] {r.case.name}")
        if not r.ok:
            print(f"      follow-up : {r.case.question}")
            print(f"      understood: {r.rewritten or '(used as written)'}")
            print(f"      companies : {sorted(r.companies) or 'none'}  (expected {sorted(r.case.expect) or 'none'})")
    for kind in ("follow-up", "standalone"):
        rs = [r for r in first if r.case.kind == kind]
        print(f"\n{kind}: {sum(r.ok for r in rs)}/{len(rs)} passed")
    print(f"total: {sum(r.ok for r in first)}/{len(first)}   average {sum(r.seconds for r in first) / len(first):.1f}s per case")
    if args.repeat > 1:
        unstable = [cases[i].name for i in range(len(cases)) if len({run[i].ok for run in runs}) > 1]
        print(f"stability over {args.repeat} runs: {len(cases) - len(unstable)}/{len(cases)} cases gave the same result every time")
        if unstable:
            print("  flip-flopped:", ", ".join(unstable))
    return 0 if all(r.ok for r in first) else 1


if __name__ == "__main__":
    sys.exit(main())
