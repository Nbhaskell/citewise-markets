"""Answer questions about companies using their SEC filings, with citations.

Usage: python -m ai.copilot "What are Nvidia's biggest risks?" [--symbol NVDA] [--show-prompt]
"""
import argparse
import re
import sys
from dataclasses import dataclass, field

import psycopg

from data.db import connect

from .embeddings import Embedder, FastEmbedder
from .llm import LLM, get_llm
from .search import SearchResult, search_filings

DISCLAIMER = (
    "This is a summary of public filings, not financial advice. "
    "It can contain mistakes, so check the cited sources."
)
NO_EVIDENCE = (
    "I couldn't find passages in the stored filings that address that question, "
    "so I won't guess. Try naming a company (or ticker) and a topic such as risks, "
    "competition, revenue, or legal proceedings."
)
MIN_SCORE = 0.62  # below this, the best passage for the question is judged unrelated and the model isn't asked
ALIASES = {"google": "GOOGL"}
RRF_K = 60  # reciprocal-rank-fusion constant used when merging several searches

SYSTEM_PROMPT = """You answer questions about public companies using ONLY the numbered passages from SEC filings that the user provides.

Rules:
1. Use only facts stated in the passages. Never use outside knowledge, and never guess.
2. After every sentence that states a fact, cite the passage number(s) in square brackets, like [1] or [2][3].
3. If the passages do not contain the answer, say so plainly. Do not fill gaps.
4. Copy figures exactly as written, with their units and the period they refer to. Never calculate, convert, round, or combine numbers. If a figure is not stated directly, say that instead of working it out.
5. Do not give investment advice, price predictions, or buy/sell/hold recommendations. If asked for one, say you can't give it, then summarize what the filings say that is relevant.
6. Be concise: a short paragraph or a few bullet points. Mention the filing form and date when comparing across filings."""

EXPAND_PROMPT = """Rewrite a question about a company into short search queries for finding the answer inside its SEC filings (10-K and 10-Q).
Write 2 queries, one per line, no numbering and no commentary. Use wording and section names a filing would use (for example "human capital management employees headcount" or "legal proceedings litigation contingencies"). Do not include the company name."""


@dataclass
class Answer:
    question: str
    text: str
    symbols: list[str]
    retrieved: list[SearchResult]
    cited: list[int] = field(default_factory=list)  # 1-based numbers of passages the answer cites
    grounded: bool = False  # True only if the answer cites at least one real passage
    unverified_numbers: list[str] = field(default_factory=list)  # figures not found in the cited passages
    queries: list[str] = field(default_factory=list)  # searches run (the question plus any rewrites)
    disclaimer: str = DISCLAIMER

    @property
    def sources(self) -> list[tuple[int, SearchResult]]:
        return [(n, self.retrieved[n - 1]) for n in self.cited]


def detect_symbols(conn: psycopg.Connection, question: str) -> list[str]:
    found = []
    for symbol, name in conn.execute("SELECT symbol, name FROM instruments ORDER BY symbol"):
        patterns = [(rf"\b{re.escape(symbol)}\b", 0)]
        first = re.match(r"[A-Za-z]+", name or "")
        if first and len(first.group()) >= 4:
            patterns.append((rf"\b{re.escape(first.group())}\b", re.IGNORECASE))
        patterns += [(rf"\b{alias}\b", re.IGNORECASE) for alias, s in ALIASES.items() if s == symbol]
        if any(re.search(p, question, flags) for p, flags in patterns):
            found.append(symbol)
    return found


def passage_block(number: int, r: SearchResult) -> str:
    header = f"[{number}] {r.symbol} {r.form} filed {r.filed_at}"
    if r.period_of_report:
        header += f" (period ending {r.period_of_report})"
    if r.section:
        header += f", {r.section}"
    return f"{header}\n{r.text}"


def build_prompt(question: str, passages: list[SearchResult]) -> str:
    blocks = [passage_block(i, r) for i, r in enumerate(passages, 1)]
    return "Passages:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def clean_citations(text: str, n_passages: int) -> tuple[str, list[int]]:
    """Drop citations that point at passages that don't exist; return the text and cited numbers."""
    cited: list[int] = []

    def fix(match: re.Match) -> str:
        nums = [int(x) for x in re.findall(r"\d+", match.group(1))]
        valid = [x for x in nums if 1 <= x <= n_passages]
        cited.extend(x for x in valid if x not in cited)
        return "".join(f"[{x}]" for x in valid)

    return CITE_RE.sub(fix, text), sorted(cited)


def _numbers(text: str) -> set[str]:
    out = set()
    for token in NUMBER_RE.findall(text):
        token = token.rstrip(",.").replace(",", "")
        if len(token) >= 2:  # skip lone digits like "3 risks"
            out.add(token)
    return out


def unverified_numbers(answer: str, cited: list[int], passages: list[SearchResult]) -> list[str]:
    """Figures in the answer that appear nowhere in the passages it cites (or the headers above them)."""
    blocks = [passage_block(n, passages[n - 1]) for n in (cited or range(1, len(passages) + 1))]
    known = _numbers("\n".join(blocks))
    return sorted(_numbers(CITE_RE.sub("", answer)) - known)


ANNUAL_RE = re.compile(r"\b(annual|10-?K|fiscal year|full[- ]year)\b", re.IGNORECASE)
QUARTER_RE = re.compile(r"\b(quarter|quarterly|10-?Q)\b", re.IGNORECASE)


def detect_forms(question: str) -> list[str] | None:
    """Restrict to 10-Ks or 10-Qs when the question clearly asks for one; otherwise search both."""
    annual, quarterly = bool(ANNUAL_RE.search(question)), bool(QUARTER_RE.search(question))
    if annual != quarterly:
        return ["10-K"] if annual else ["10-Q"]
    return None


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def expand_queries(llm: LLM, question: str) -> list[str]:
    """Ask the model for keyword-style rewrites of the question. Never fails the answer."""
    try:
        reply = strip_thinking(llm.generate(EXPAND_PROMPT, question))
    except Exception:
        return []
    lines = [re.sub(r"^[\s\-*\d.)]+", "", line).strip() for line in reply.splitlines()]
    return [q for q in lines if 3 <= len(q) <= 200][:2]


def dedupe(results: list[SearchResult], limit: int) -> list[SearchResult]:
    """Companies repeat paragraphs across filings; keep the best-ranked copy of each."""
    seen, out = set(), []
    for r in results:
        key = (r.symbol, " ".join(r.text.lower().split())[:300])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:limit]


def _search_company(
    conn: psycopg.Connection, embedder: Embedder, queries: list[str], symbol: str | None, limit: int,
    forms: list[str] | None = None,
) -> tuple[list[SearchResult], float]:
    """Search with every query and merge by reciprocal rank. Also returns the best score
    for the original question (queries[0]), which is what the relevance cutoff judges."""
    fused: dict[int, float] = {}
    by_id: dict[int, SearchResult] = {}
    best_original = 0.0
    for qi, query in enumerate(queries):
        found = search_filings(
            conn, embedder, query, [symbol] if symbol else None, forms, limit=limit * 3, latest_only=True
        )
        if qi == 0 and found:
            best_original = found[0].score
        for rank, r in enumerate(found):
            by_id.setdefault(r.chunk_id, r)
            fused[r.chunk_id] = fused.get(r.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    ordered = [by_id[i] for i in sorted(fused, key=fused.get, reverse=True)]
    return dedupe(ordered, limit), best_original


def retrieve(
    conn: psycopg.Connection, embedder: Embedder, queries: list[str], symbols: list[str], limit: int,
    forms: list[str] | None = None,
) -> tuple[list[SearchResult], float]:
    if len(symbols) <= 1:
        return _search_company(conn, embedder, queries, symbols[0] if symbols else None, limit, forms)
    per_company = max(2, limit // len(symbols))  # comparisons need evidence from every company
    results, best = [], 0.0
    for symbol in symbols:
        found, score = _search_company(conn, embedder, queries, symbol, per_company, forms)
        results += found
        best = max(best, score)
    return results, best


def _generate_checked(llm: LLM, question: str, passages: list[SearchResult]) -> tuple[str, list[int], list[str]]:
    prompt = build_prompt(question, passages)
    text, cited = clean_citations(strip_thinking(llm.generate(SYSTEM_PROMPT, prompt)), len(passages))
    bad = unverified_numbers(text, cited, passages)
    if bad:  # one retry: the model must stop doing its own arithmetic
        correction = (
            f"{prompt}\n\nYour previous answer:\n{text}\n\n"
            f"It contains figures that do not appear in the passages: {', '.join(bad)}. "
            "Rewrite the answer using only figures copied exactly from the passages. "
            "Do no arithmetic. Leave out anything you can't support."
        )
        text, cited = clean_citations(strip_thinking(llm.generate(SYSTEM_PROMPT, correction)), len(passages))
        bad = unverified_numbers(text, cited, passages)
    return text, cited, bad


def answer_question(
    conn: psycopg.Connection,
    embedder: Embedder,
    llm: LLM,
    question: str,
    symbols: list[str] | None = None,
    limit: int = 6,
    expand: bool = True,
) -> Answer:
    symbols = [s.upper() for s in symbols] if symbols else detect_symbols(conn, question)
    forms = detect_forms(question)
    passages, best = retrieve(conn, embedder, [question], symbols, limit, forms)
    if not passages or best < MIN_SCORE:
        return Answer(question, NO_EVIDENCE, symbols, passages, queries=[question])

    queries = [question]
    if expand and (extra := expand_queries(llm, question)):
        queries += extra
        passages, _ = retrieve(conn, embedder, queries, symbols, limit, forms)

    text, cited, bad = _generate_checked(llm, question, passages)
    return Answer(question, text, symbols, passages, cited, grounded=bool(cited), unverified_numbers=bad, queries=queries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--symbol", action="append", help="company ticker; repeat for several (default: detect)")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--no-expand", action="store_true", help="skip the query-rewriting step")
    parser.add_argument("--show-prompt", action="store_true", help="print the passages sent to the model")
    args = parser.parse_args(argv)

    embedder, llm = FastEmbedder(), get_llm()
    with connect() as conn:
        ans = answer_question(conn, embedder, llm, args.question, args.symbol, args.limit, not args.no_expand)
        if args.show_prompt:
            print(build_prompt(args.question, ans.retrieved), "\n")

    print(f"[{llm.name}] companies: {', '.join(ans.symbols) or 'none detected'}")
    print(f"searches: {' | '.join(ans.queries)}\n")
    print(ans.text)
    if ans.retrieved and not ans.grounded and ans.text != NO_EVIDENCE:
        print("\nWARNING: this answer cites no passages, so treat it as unverified.")
    if ans.unverified_numbers:
        print(f"\nWARNING: these figures are not in the cited passages: {', '.join(ans.unverified_numbers)}")
    if ans.sources:
        print("\nSources:")
        for n, r in ans.sources:
            print(f"  [{n}] {r.symbol} {r.form} filed {r.filed_at}, {r.section or '-'}\n      {r.url}")
    print(f"\n{ans.disclaimer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
