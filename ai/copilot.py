"""Answer questions about companies from their SEC filings, stored prices, and news headlines, with citations.

Usage: python -m ai.copilot "What are Nvidia's biggest risks?" [--symbol NVDA] [--show-prompt]
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date

import psycopg

from data.db import connect

from .answer_checks import (
    causal_claims,
    clean_citations,
    false_news_claim,
    false_price_claim,
    invented_titles,
    invented_titles_caution,
    passage_block,
    unverified_numbers,
)
from .companies import removed_company_named
from .embeddings import Embedder, FastEmbedder
from .followups import Turn, resolve_question, route_by_speaker
from .llm import LLM, get_llm, strip_thinking
from .market import (
    MarketEvidence,
    detect_intent,
    gather_market_evidence,
    join_names,
    outside_scope,
    parse_window,
    period_cautions,
    premise_cautions,
    relevant_cautions,
    unknown_name,
    writing_request,
)
from .router import apply_route, ask_router, changed_kinds, needs_router, router_enabled
from .search import SearchResult, detect_forms, search_filings
from .table_units import add_units
# Moved to their own modules; the tests, the API and the evaluations still import these names from here.
from .answer_checks import quoted_titles  # noqa: F401
from .companies import company_mentions, detect_symbols, lowercase_ticker_ok  # noqa: F401
from .followups import (  # noqa: F401
    CONDENSE_PROMPT,
    HISTORY_ANSWER_CHARS,
    MAX_HISTORY,
    company_is_speaking,
    condense_question,
    names_a_topic,
    routes_somewhere,
)

DISCLAIMER = (
    "This summarizes stored public filings, prices, financial figures, and news headlines. It is not financial advice. "
    "It can contain mistakes, so check the cited sources."
)
NO_EVIDENCE = (
    "I couldn't find anything in the stored filings, prices, or headlines that addresses that question, "
    "so I won't guess. Try naming a company (or ticker) and a topic such as risks, "
    "competition, revenue, legal proceedings, recent price moves, or news."
)
NO_COMPANY = (
    "Tell me which company you mean (a name or ticker) and I can look at its stored prices, headlines, and financial figures. "
    "I only have data for the companies tracked here, and nothing for the market as a whole."
)


def outside_scope_message(kind: str, name: str, tracked: list[str]) -> str:
    """The whole answer for a question about something this app does not hold. Said in code, before the model is asked: with
    only unrelated filings in front of it the model answered "Bitcoin" questions from Tesla's other income."""
    held = (
        "It has stored filings, prices, financial figures, and headlines only for the companies it tracks"
        + (f" ({', '.join(tracked)})" if tracked else "")
        + "."
    )
    if kind == "company":
        return (
            f"{name} isn't one of the companies tracked here, so I have no filings, prices, figures, or headlines for it. "
            f"{held} To look at {name}, use the \"Add a company\" box on the dashboard, then ask again."
        )
    if kind == "unknown":
        return (
            f"I can't find \"{name}\" in anything stored here (filings, prices, or headlines), so I can't answer a question about "
            f"it. {held} If it is a company, use the \"Add a company\" box on the dashboard, then ask again."
        )
    if kind == "writing":
        return (
            "That's outside what this app covers: it answers questions about companies from stored data, and it doesn't write "
            f"emails, posts, poems, code, or other documents. {held} Ask for the facts you need about a tracked company, then write "
            "the message yourself."
        )
    if kind == "chat":
        return f"That's outside what this app covers: it answers questions about companies from stored data. {held}"
    return (
        f"That's outside what this app covers. {held} It has nothing on crypto, commodities, interest rates, or the wider "
        "economy. Name a tracked company and a topic, or ask which companies mention it in their filings."
    )


def not_calculated(names) -> str:
    """The whole answer when the only thing asked for is a ratio this app doesn't compute. Said in code: with only filing
    text in front of it the model found no price and claimed prices were unavailable, which is false."""
    return (
        f"I don't calculate {join_names(names)} here, and I won't piece one together from separate numbers. "
        "For a tracked company I can give its P/E ratio, market value, earnings per share, shares outstanding, revenue, "
        "profit, and margins (all for the last twelve months), its stored prices and news headlines, and what its filings say."
    )


ADVICE_CAUTION = (
    "This app can't tell you whether to buy, sell, or hold. Nothing in this answer is a recommendation: it only shows "
    "stored prices, figures, headlines, and filing text."
)


def not_calculated_note(names) -> str:
    return f"This app doesn't calculate {join_names(names)}, so that part of your question is not answered here."


MIN_SCORE = 0.62  # below this, the best passage for the question is judged unrelated and the model isn't asked
CAUSE_CAUTION = (
    "This answer may suggest a reason for the price move. The stored headlines are only titles, so they cannot show "
    "why a price moved. Treat any such explanation as a guess."
)

RRF_K = 60  # reciprocal-rank-fusion constant used when merging several searches

SYSTEM_PROMPT = """You answer questions about public companies using ONLY the numbered sources that the user provides. Sources are passages from SEC filings, price data worked out from stored daily closes, news headlines (titles only, with an automatic sentiment label), and headline sentiment summaries.

Rules:
1. Use only facts stated in the sources. Never use outside knowledge, and never guess.
2. After every sentence that states a fact, cite the source number(s) in square brackets, like [1] or [2][3].
3. If the sources do not contain the answer, say so plainly. Do not fill gaps. If asked for something no source provides (market value, P/E ratio, analyst targets), say it isn't available.
4. Copy figures exactly as written, with their units and the period they refer to. Never calculate, convert, round, or combine numbers. If a figure is not stated directly, say that instead of working it out.
5. Do not give investment advice, price predictions, or buy/sell/hold recommendations. If asked for one, say you can't give it, then summarize the relevant facts from the sources.
6. A headline is only a title. Never say or hint that a headline caused, explains, or drove a price move, and do not use "may have", "might have", "likely", or "suggests" about why a price moved. If asked why a stock moved, say the stored data can't show the cause, give the price move, and list the headlines published in that period as context only.
7. Prices and sentiment are history. Never say what they mean for the future.
8. If the question assumes something the sources contradict (for example it asks why a stock fell when the data shows it rose), say so first, then state what the sources show.
9. Sentiment labels come from an automatic model and are imperfect. Say "labeled", not "is", and mention that most headlines are labeled neutral when you quote a summary.
10. Be concise: a short paragraph or a few bullet points. Mention the filing form and date when comparing across filings, and the date range when quoting prices or sentiment."""

# Added to the prompt only when a financial-figures source is among the evidence. Sent with every question it made the
# local model paraphrase headlines in a way the cause check flags ("news and stock" went from 10 of 10 to 5 of 10).
FIGURES_RULES = """
11. One of the sources is a financial figures source: revenue, profit, margins, market value, and P/E ratio worked out from SEC filings and the latest stored price. Those figures are available, so rule 3 does not apply to them, and like prices they are history (rule 7). It covers the last 12 months unless it says otherwise. Quote each figure exactly, with the period it covers. If the question asks for another period (one quarter, a calendar year), say the source covers the last 12 months and give that figure. When your answer uses a figure and a CAUTION line in the source concerns it, say that caution in plain words next to the figure. Never call a P/E, market value, margin, or growth rate cheap, expensive, high, low, good, or bad, and never say whether a stock is overvalued or undervalued. These figures do not explain why a company's revenue or profit changed; if asked why, say so."""

EXPAND_PROMPT = """Rewrite a question about a company into short search queries for finding the answer inside its SEC filings (10-K and 10-Q).
Write 2 queries, one per line, no numbering and no commentary. Use wording and section names a filing would use (for example "human capital management employees headcount" or "legal proceedings litigation contingencies"). Do not include the company name."""


@dataclass
class Answer:
    question: str
    text: str
    symbols: list[str]
    retrieved: list[SearchResult | MarketEvidence]
    cited: list[int] = field(default_factory=list)  # 1-based numbers of passages the answer cites
    grounded: bool = False  # True only if the answer cites at least one real passage
    unverified_numbers: list[str] = field(default_factory=list)  # figures not found in the cited passages
    queries: list[str] = field(default_factory=list)  # searches run (the question plus any rewrites)
    interpreted_question: str | None = None  # how a follow-up was understood; None if it was used as written
    disclaimer: str = DISCLAIMER
    refused: bool = False  # True when nothing relevant was found (or no company was named), so the model wasn't asked
    cautions: list[str] = field(default_factory=list)  # plain-language warnings the app must show with the answer
    model_route: list[str] = field(default_factory=list)  # kinds of evidence the local model chose, when it and not the keywords did

    @property
    def sources(self) -> list[tuple[int, SearchResult | MarketEvidence]]:
        return [(n, self.retrieved[n - 1]) for n in self.cited]


def system_prompt(passages: list[SearchResult | MarketEvidence]) -> str:
    """The rules for the model. The financial-figures rules are added only when such a source is present, so every other
    kind of question gets exactly the prompt it was evaluated with."""
    if any(isinstance(p, MarketEvidence) and p.kind == "fundamentals" for p in passages):
        return SYSTEM_PROMPT + FIGURES_RULES
    return SYSTEM_PROMPT


def build_prompt(question: str, passages: list[SearchResult | MarketEvidence]) -> str:
    blocks = [passage_block(i, r) for i, r in enumerate(passages, 1)]
    return "Sources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


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


def _generate_checked_full(
    llm: LLM, question: str, passages: list[SearchResult | MarketEvidence]
) -> tuple[str, list[int], list[str], list[str], list[str]]:
    """The answer, its citations, figures/directions that don't match the sources, causes it implies, and titles it
    invents. One retry when anything is wrong: the model must stop doing its own arithmetic, stop explaining price moves,
    and quote only what the sources say."""
    prompt = build_prompt(question, passages)
    system = system_prompt(passages)
    text, cited = clean_citations(strip_thinking(llm.generate(system, prompt)), len(passages))
    bad, causes = unverified_numbers(text, cited, passages, question), causal_claims(text, passages)
    titles = invented_titles(text, passages, question)
    if bad or causes or titles:
        complaints = []
        if titles:
            complaints.append(
                f"It quotes headlines or text that are not in the sources: {'; '.join(titles[:5])}. List only headlines "
                "copied exactly from the sources, or say the sources contain none."
            )
        if bad:
            complaints.append(
                f"It contains figures or directions that do not match the sources: {', '.join(bad)}. "
                "Rewrite the answer using only figures copied exactly from the sources, with the direction (rise or fall) "
                "the sources state, even if the question assumed otherwise. Do no arithmetic."
            )
        if causes:
            complaints.append(
                f"It suggests a cause for the price move ({'; '.join(causes)}). Headlines are only titles and cannot "
                "show why a price moved. Remove that and say only that the stored data can't show the cause."
            )
        correction = f"{prompt}\n\nYour previous answer:\n{text}\n\n{' '.join(complaints)} Leave out anything you can't support."
        text, cited = clean_citations(strip_thinking(llm.generate(system, correction)), len(passages))
        bad, causes = unverified_numbers(text, cited, passages, question), causal_claims(text, passages)
        titles = invented_titles(text, passages, question)
    return text, cited, bad, causes, titles


def _generate_checked(
    llm: LLM, question: str, passages: list[SearchResult | MarketEvidence]
) -> tuple[str, list[int], list[str]]:
    return _generate_checked_full(llm, question, passages)[:3]


def answer_question(
    conn: psycopg.Connection,
    embedder: Embedder,
    llm: LLM,
    question: str,
    symbols: list[str] | None = None,
    limit: int = 6,
    expand: bool = True,
    history: list[Turn] | None = None,
    today: date | None = None,
    router: bool | None = None,
) -> Answer:
    """Answer from filings, stored prices, financial figures, and headlines. `history` only helps understand a follow-up;
    the answer itself is written from the retrieved sources alone, so earlier answers can never be used as evidence.
    `today` is only for tests (it dates the freshness notes and cautions)."""
    search_question, symbols, interpreted = resolve_question(conn, llm, question, symbols, history)
    first_intent = detect_intent(search_question)
    intent = route_by_speaker(conn, search_question, first_intent)  # "What does Apple say about falling demand?": the filings, not the price
    decided_by_speaker = intent is not first_intent  # a deliberate filings route: the router is not asked to second-guess it
    model_route: list[str] = []  # set below when the router picked the evidence; every answer, refusals too, carries it

    def refuse(text: str, found=(), queries=()) -> Answer:
        return Answer(
            question, text, symbols, list(found), queries=list(queries), interpreted_question=interpreted, refused=True,
            model_route=model_route,
            # a refusal says nothing about buying or selling, so the notice is what tells the reader why no call was given
            cautions=[ADVICE_CAUTION] if intent.advice else [],
        )

    tracked = [r[0] for r in conn.execute("SELECT symbol FROM instruments WHERE active ORDER BY symbol")]
    if writing_request(question) or writing_request(search_question):  # even with a tracked company named: an email is not research
        return refuse(outside_scope_message("writing", "", tracked))
    if intent.unstored_only:
        return refuse(not_calculated(intent.unstored))
    if not symbols and (gone := removed_company_named(conn, search_question)):  # switched off by "remove": its data is kept, but it is not tracked
        return refuse(outside_scope_message("company", gone, tracked))
    if not symbols and (outside := outside_scope(search_question)):  # before the generic refusal: it says what is missing
        return refuse(outside_scope_message(outside[0], outside[1], tracked))
    if not symbols and (name := unknown_name(conn, search_question)):  # a name the stored text has never seen
        return refuse(outside_scope_message("unknown", name, tracked))
    router_says_outside = False
    if router_enabled(router) and not decided_by_speaker and needs_router(intent, search_question):  # no specific route found: ask the model what kind of question this is
        keyword_intent = intent
        intent, verdict = apply_route(intent, ask_router(llm, search_question), has_company=bool(symbols), question=search_question)
        model_route = changed_kinds(keyword_intent, intent)
        if verdict == "writing":
            return refuse(outside_scope_message("writing", "", tracked))
        router_says_outside = verdict == "outside"  # only a hint: it changes the message when nothing relevant is found, never the search
    if intent.market and not symbols:
        return refuse(NO_COMPANY)
    market: list[MarketEvidence] = []
    window = parse_window(search_question, today)
    if intent.market:
        market = gather_market_evidence(conn, symbols, intent, window, getattr(llm, "name", ""), today)

    passages: list[SearchResult] = []
    queries: list[str] = []
    if intent.filings:
        forms = detect_forms(search_question)
        found, best = retrieve(conn, embedder, [search_question], symbols, limit, forms)
        queries = [search_question]
        if found and best >= MIN_SCORE:
            passages = found
            if expand and (extra := expand_queries(llm, search_question)):
                queries += extra
                passages, _ = retrieve(conn, embedder, queries, symbols, limit, forms)
        elif not market:
            return refuse(outside_scope_message("chat", "", tracked) if router_says_outside else NO_EVIDENCE, found, queries)
    if not market and not passages:
        return refuse(NO_EVIDENCE)

    passages = add_units(conn, passages)  # a table whose unit sentence was cut off into the passage before gets it back
    evidence = market + passages  # prices and headlines first: they are short, and the passages are numbered after them
    text, cited, bad, causes, titles = _generate_checked_full(llm, search_question, evidence)
    cautions = (
        ([CAUSE_CAUTION] if causes else []) + ([invented_titles_caution(titles)] if titles else [])
        + ([c] if (c := false_price_claim(conn, text, symbols, evidence)) else [])
        + ([c] if (c := false_news_claim(conn, text, symbols, evidence, intent.headlines or intent.sentiment)) else [])
        + ([ADVICE_CAUTION] if intent.advice else [])
        + period_cautions(window, market, today)
        + premise_cautions(search_question, market, window)
        + relevant_cautions(evidence, intent.fundamentals, text)
        + ([not_calculated_note(intent.unstored)] if intent.unstored else [])
    )
    return Answer(
        question, text, symbols, evidence, cited, grounded=bool(cited), unverified_numbers=bad,
        queries=queries, interpreted_question=interpreted, cautions=cautions, model_route=model_route,
    )


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
    print(f"searches: {' | '.join(ans.queries) or 'none (no filing search was needed)'}")
    if ans.model_route:
        print(f"chosen by the local model, not the keyword rules: {', '.join(ans.model_route)}")
    print()
    print(ans.text)
    if ans.retrieved and not ans.grounded and not ans.refused:
        print("\nWARNING: this answer cites no passages, so treat it as unverified.")
    if ans.unverified_numbers:
        print(f"\nWARNING: these figures are not in the cited passages: {', '.join(ans.unverified_numbers)}")
    for caution in ans.cautions:
        print(f"\nWARNING: {caution}")
    if ans.sources:
        print("\nSources:")
        for n, r in ans.sources:
            if isinstance(r, MarketEvidence):
                print(f"  [{n}] {r.header}" + (f"\n      {r.url}" if r.url else ""))
            else:
                print(f"  [{n}] {r.symbol} {r.form} filed {r.filed_at}, {r.section or '-'}\n      {r.url}")
    print(f"\n{ans.disclaimer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
