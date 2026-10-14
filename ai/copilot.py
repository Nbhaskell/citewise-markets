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

from .embeddings import Embedder, FastEmbedder
from .llm import LLM, get_llm
from .market import (
    BARE_STOCK_RE,
    MarketEvidence,
    detect_intent,
    gather_market_evidence,
    join_names,
    parse_window,
    relevant_cautions,
)
from .search import SearchResult, search_filings

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


def not_calculated(names) -> str:
    """The whole answer when the only thing asked for is a ratio this app doesn't compute. Said in code: with only filing
    text in front of it the model found no price and claimed prices were unavailable, which is false."""
    return (
        f"I don't calculate {join_names(names)} here, and I won't piece one together from separate numbers. "
        "For a tracked company I can give its P/E ratio, market value, earnings per share, shares outstanding, revenue, "
        "profit, and margins (all for the last twelve months), its stored prices and news headlines, and what its filings say."
    )


def not_calculated_note(names) -> str:
    return f"This app doesn't calculate {join_names(names)}, so that part of your question is not answered here."


MIN_SCORE = 0.62  # below this, the best passage for the question is judged unrelated and the model isn't asked
CAUSE_CAUTION = (
    "This answer may suggest a reason for the price move. The stored headlines are only titles, so they cannot show "
    "why a price moved. Treat any such explanation as a guess."
)
ALIASES = {"google": "GOOGL"}
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

CONDENSE_PROMPT = """You rewrite the latest question in a conversation about public companies so it can be understood on its own.

Rules:
1. Replace pronouns and references ("it", "its", "they", "that company", "the other one", "and Google?") with the specific company names or topics they refer to, taken from the conversation. Pronouns refer to the company in the MOST RECENT question and answer, unless the latest question says otherwise.
2. If the latest question compares something to what was just discussed (for example "how does that compare to Amazon's?"), name BOTH the company just discussed and the new one.
3. If the latest question already stands on its own, or switches to a different company or topic, return it exactly as written. Never carry a company over unless the question refers back to it.
4. Do not answer the question and do not add facts. Keep it short.
5. Output only the rewritten question, on one line."""

MAX_HISTORY = 3  # earlier turns shown to the rewriting step
HISTORY_ANSWER_CHARS = 400  # how much of each earlier answer the rewriting step sees
REFERENCE_RE = re.compile(
    r"\b(it|its|it's|their|theirs|they|them|that|those|this|these|same|former|latter|the company|the other)\b", re.IGNORECASE
)


BACKREF_RE = re.compile(r"\b(first|earlier|previous|previously|before|other|former|original)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Turn:
    """One earlier question and answer. Used only to understand a follow-up, never as evidence for an answer."""

    question: str
    answer: str
    companies: tuple[str, ...] = ()


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

    @property
    def sources(self) -> list[tuple[int, SearchResult | MarketEvidence]]:
        return [(n, self.retrieved[n - 1]) for n in self.cited]


def company_mentions(conn: psycopg.Connection, text: str) -> dict[str, list[re.Match]]:
    """Every tracked company the text names (by ticker, first word of its name, or alias), with where it does so."""
    found: dict[str, list[re.Match]] = {}
    for symbol, name in conn.execute("SELECT symbol, name FROM instruments ORDER BY symbol"):
        patterns = [(rf"\b{re.escape(symbol)}\b", 0)]
        first = re.match(r"[A-Za-z]+", name or "")
        if first and len(first.group()) >= 4:
            patterns.append((rf"\b{re.escape(first.group())}\b", re.IGNORECASE))
        patterns += [(rf"\b{alias}\b", re.IGNORECASE) for alias, s in ALIASES.items() if s == symbol]
        matches = [m for p, flags in patterns for m in re.finditer(p, text, flags)]
        if matches:
            found[symbol] = sorted(matches, key=lambda m: m.start())
    return found


def detect_symbols(conn: psycopg.Connection, question: str) -> list[str]:
    return list(company_mentions(conn, question))


def passage_block(number: int, r: SearchResult | MarketEvidence) -> str:
    if isinstance(r, MarketEvidence):
        return f"[{number}] {r.header}\n{r.text}"
    header = f"[{number}] {r.symbol} {r.form} filed {r.filed_at}"
    if r.period_of_report:
        header += f" (period ending {r.period_of_report})"
    if r.section:
        header += f", {r.section}"
    return f"{header}\n{r.text}"


def system_prompt(passages: list[SearchResult | MarketEvidence]) -> str:
    """The rules for the model. The financial-figures rules are added only when such a source is present, so every other
    kind of question gets exactly the prompt it was evaluated with."""
    if any(isinstance(p, MarketEvidence) and p.kind == "fundamentals" for p in passages):
        return SYSTEM_PROMPT + FIGURES_RULES
    return SYSTEM_PROMPT


def build_prompt(question: str, passages: list[SearchResult | MarketEvidence]) -> str:
    blocks = [passage_block(i, r) for i, r in enumerate(passages, 1)]
    return "Sources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


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


SIGNED_RE = re.compile(r"(?:(?<=\s)|(?<=\()|^)([-−–])\s?\$?(\d[\d,]*(?:\.\d+)?)")  # "-3.68", but not the dashes in dates or "10-K"
DOWN_RE = re.compile(
    r"\b(?:fell|fall(?:s|en|ing)?|drop(?:s|ped|ping)?|declin\w+|decreas\w+|down|lower|lost|loss|slump\w*|dip(?:s|ped)?|sank|plung\w+|"
    r"shr(?:ank|unk|ink\w*))\b",
    re.IGNORECASE,
)
UP_RE = re.compile(
    r"\b(?:rose|ris(?:e|es|en|ing)|gain(?:s|ed)?|increas\w+|up|higher|climb\w*|rall(?:y|ied|ies)|jump\w*|surg\w+|advanc\w+|"
    r"grew|grow(?:s|ing)?|expand\w*)\b",
    re.IGNORECASE,
)


def _negatives(text: str) -> set[str]:
    return {m.group(2).replace(",", "") for m in SIGNED_RE.finditer(text)}


def _stored_moves(ev: MarketEvidence):
    """Each change a source states with its direction: (the figures that state it, did it rise, how to describe it).
    A price move is checked on its dollar and percent figures; a growth figure (revenue, profit) on its percent."""
    if ev.kind == "price" and ev.change is not None and ev.change_pct is not None and round(ev.change_pct, 2) != 0:
        rose = ev.change_pct > 0
        yield ({f"{abs(ev.change):.2f}", f"{abs(ev.change_pct):.2f}"}, rose,
               f"{abs(ev.change_pct):.2f} ({ev.symbol}'s stored change is {ev.change_pct:+.2f}%, {'a rise' if rose else 'a fall'})")
    for pct in ev.growth_pcts:
        if round(pct, 1) != 0:
            yield ({f"{abs(pct):.1f}"}, pct > 0,
                   f"{abs(pct):.1f} ({ev.symbol}'s stored growth is {pct:+.1f}%, {'an increase' if pct > 0 else 'a decrease'})")


def direction_errors(plain: str, evidence: list[MarketEvidence]) -> list[str]:
    """Moves the answer describes in the wrong direction: a sentence that gives the stored change (or growth) figure
    but says it fell when the data shows a rise (or the reverse). The digits alone would pass the figures check."""
    out = []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", plain)
    for ev in evidence:
        for figures, rose, label in _stored_moves(ev):
            for s in sentences:
                if not any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", s) for f in figures):
                    continue
                wrong, right = (DOWN_RE, UP_RE) if rose else (UP_RE, DOWN_RE)
                if wrong.search(s) and not right.search(s) and label not in out:
                    out.append(label)
    return out


def unverified_numbers(answer: str, cited: list[int], passages: list[SearchResult | MarketEvidence]) -> list[str]:
    """Figures in the answer that appear nowhere in the passages it cites (or the headers above them), a minus sign
    the sources don't have, and price moves described in the wrong direction."""
    used = list(cited or range(1, len(passages) + 1))
    blocks = [passage_block(n, passages[n - 1]) for n in used]
    known, plain = _numbers("\n".join(blocks)), CITE_RE.sub("", answer)
    missing = _numbers(plain) - known
    known_negatives = _negatives("\n".join(blocks))
    missing |= {f"-{v}" for v in _negatives(plain) if len(v) >= 2 and v not in known_negatives}
    market = [passages[n - 1] for n in used if isinstance(passages[n - 1], MarketEvidence)]
    return sorted(missing) + direction_errors(plain, market)


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


def condense_question(llm: LLM, question: str, history: list[Turn]) -> str:
    """Turn a follow-up into a standalone question using the last few turns. Falls back to the original on any doubt."""
    turns = history[-MAX_HISTORY:]
    if not turns:
        return question
    lines = []
    for i, t in enumerate(turns, 1):
        answer = CITE_RE.sub("", t.answer).strip()[:HISTORY_ANSWER_CHARS]
        about = ", ".join(t.companies) or "no company"
        recent = " (MOST RECENT)" if i == len(turns) else ""
        lines.append(f"Question {i}{recent}: {t.question}\nAnswer {i} (about {about}): {answer}")
    prompt = "Conversation so far:\n\n" + "\n\n".join(lines) + f"\n\nLatest question: {question}"
    try:
        reply = strip_thinking(llm.generate(CONDENSE_PROMPT, prompt))
    except Exception:
        return question
    first = next((ln.strip() for ln in reply.splitlines() if ln.strip()), "")
    first = re.sub(r"^(rewritten question|question|latest question)\s*:\s*", "", first, flags=re.IGNORECASE).strip(" \"'")
    return first if 3 <= len(first) <= 300 else question


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


CAUSE_HINT_RE = re.compile(
    r"\b(?:due to|because of|driven by|as a result of|attributed to|thanks to|caused by|led to|resulted from)\b"
    r"|\b(?:may|might|could|possibly|probably|likely|perhaps)\b[^.]{0,40}\b(?:influenc|contribut|caus|driv|impact|affect|explain|factor|behind)\w*",
    re.IGNORECASE,
)
NEGATION_RE = re.compile(r"\b(?:not|no|never|cannot|unable)\b|n't", re.IGNORECASE)
QUOTED_RE = re.compile(r'"[^"]*"|“[^”]*”')


def causal_claims(text: str, evidence: list[SearchResult | MarketEvidence]) -> list[str]:
    """Statements that put a price move down to something. Headlines are only titles, so the data can't support any
    cause. Only checked when the answer was given both price data and headlines. Quoted headline text is ignored, and
    so are clauses that deny a cause ("the data does not show why")."""
    kinds = {e.kind for e in evidence if isinstance(e, MarketEvidence)}
    if not {"price", "headline"} <= kinds:
        return []
    plain = QUOTED_RE.sub("", CITE_RE.sub("", text))
    clauses = re.split(r"(?<=[.!?])\s+|\n+|;\s*|,\s*(?:but|however|though|although|while)\s+", plain)
    return [c.strip()[:120] for c in clauses if CAUSE_HINT_RE.search(c) and not NEGATION_RE.search(c)]


def _generate_checked_full(
    llm: LLM, question: str, passages: list[SearchResult | MarketEvidence]
) -> tuple[str, list[int], list[str], list[str]]:
    """The answer, its citations, figures/directions that don't match the sources, and causes it implies. One retry
    when anything is wrong: the model must stop doing its own arithmetic and stop explaining price moves."""
    prompt = build_prompt(question, passages)
    system = system_prompt(passages)
    text, cited = clean_citations(strip_thinking(llm.generate(system, prompt)), len(passages))
    bad, causes = unverified_numbers(text, cited, passages), causal_claims(text, passages)
    if bad or causes:
        complaints = []
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
        bad, causes = unverified_numbers(text, cited, passages), causal_claims(text, passages)
    return text, cited, bad, causes


def _generate_checked(
    llm: LLM, question: str, passages: list[SearchResult | MarketEvidence]
) -> tuple[str, list[int], list[str]]:
    return _generate_checked_full(llm, question, passages)[:3]


SWITCH_FILLER_RE = re.compile(
    r"\b(?:what|how|about|and|or|then|also|so|ok|okay|now|next|instead|regarding|with|for|on|the|as|well|too|s)\b", re.IGNORECASE
)
PRONOUN_RE = re.compile(r"\b(its|their)\b|\b(it|they)\b", re.IGNORECASE)


def _is_bare_switch(text: str, mentions: dict[str, list[re.Match]]) -> bool:
    """Only company names and filler words: "What about Tesla?", "And Tesla's?". Nothing says what to ask about it."""
    rest = text
    for match in sorted((m for ms in mentions.values() for m in ms), key=lambda m: m.start(), reverse=True):
        rest = rest[: match.start()] + " " + rest[match.end():]
    return not re.sub(r"[\W_]+", "", SWITCH_FILLER_RE.sub(" ", rest))


def _swap_company(text: str, old: list[re.Match], new: str) -> str:
    for match in sorted(old, key=lambda m: m.start(), reverse=True):
        text = text[: match.start()] + new + text[match.end():]
    return text


def carry_topic(conn: psycopg.Connection, question: str, history: list[Turn]) -> str | None:
    """"What about Tesla?" after a question about Nvidia means the same question about Tesla. The rewriting step is told
    to leave a question that switches company alone, so it hands this back unchanged and the search ran on nothing but
    a company name. Only the earlier *question* is reused (its answer never is), and only when it is clear what to swap:
    the earlier question names exactly one tracked company, or has a pronoun standing for it. Returns None otherwise."""
    named = company_mentions(conn, question)
    if not named or not _is_bare_switch(question, named) or set(named) & {c.upper() for c in history[-1].companies}:
        return None
    typed = " and ".join(  # the company as the user wrote it, in the order they wrote it
        m.group(0) for m in sorted((ms[0] for ms in named.values()), key=lambda m: m.start())
    )
    for earlier in reversed(history):
        before = company_mentions(conn, earlier.question)
        if before and _is_bare_switch(earlier.question, before):
            continue  # an earlier "What about Tesla?" has no topic either; the one before it does
        if len(before) == 1:
            return _swap_company(earlier.question, next(iter(before.values())), typed)
        if not before and PRONOUN_RE.search(earlier.question):
            return PRONOUN_RE.sub(lambda m: f"{typed}'s" if m.group(1) else typed, earlier.question)
        return None
    return None


def resolve_question(
    conn: psycopg.Connection,
    llm: LLM,
    question: str,
    symbols: list[str] | None,
    history: list[Turn] | None,
) -> tuple[str, list[str], str | None]:
    """Work out what is really being asked: (standalone question, companies to search, how a follow-up was
    understood or None). Chosen companies always win; otherwise they come from the standalone question."""
    history = history or []
    search_question = condense_question(llm, question, history) if history else question
    if history and not symbols and " ".join(search_question.lower().split()) == " ".join(question.lower().split()):
        search_question = carry_topic(conn, question, history) or search_question
    elif history and not symbols and BARE_STOCK_RE.search(question) and not detect_intent(search_question).prices:
        search_question = question  # "ok, and Alphabet stock?" was rewritten into the earlier risks question; the user's words win
    if (
        not symbols
        and history
        and REFERENCE_RE.search(question)
        and not BACKREF_RE.search(question)
        and not detect_symbols(conn, question)
    ):
        # A bare pronoun ("its legal proceedings") means the company in the most recent turn. If the rewrite picked
        # a company that wasn't in that turn at all, the model misread it: trust the rule, and say what was assumed.
        recent = [c.upper() for c in history[-1].companies]
        named = detect_symbols(conn, search_question)
        if recent and named and not set(named) & set(recent):
            return question, recent, f"{question} (assuming {', '.join(recent)})"
    if symbols:
        found = [s.upper() for s in symbols]
    else:
        found = detect_symbols(conn, search_question) or detect_symbols(conn, question)
        if not found and history and REFERENCE_RE.search(question):
            found = list(history[-1].companies)  # "its risks": the rewrite didn't name it, so carry the last company
    same = " ".join(search_question.lower().split()) == " ".join(question.lower().split())
    return search_question, found, None if same else search_question


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
) -> Answer:
    """Answer from filings, stored prices, financial figures, and headlines. `history` only helps understand a follow-up;
    the answer itself is written from the retrieved sources alone, so earlier answers can never be used as evidence.
    `today` is only for tests (it dates the freshness notes and cautions)."""
    search_question, symbols, interpreted = resolve_question(conn, llm, question, symbols, history)
    intent = detect_intent(search_question)

    def refuse(text: str, found=(), queries=()) -> Answer:
        return Answer(
            question, text, symbols, list(found), queries=list(queries), interpreted_question=interpreted, refused=True
        )

    if intent.unstored_only:
        return refuse(not_calculated(intent.unstored))
    if intent.market and not symbols:
        return refuse(NO_COMPANY)
    market: list[MarketEvidence] = []
    if intent.market:
        market = gather_market_evidence(conn, symbols, intent, parse_window(search_question), getattr(llm, "name", ""), today)

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
            return refuse(NO_EVIDENCE, found, queries)
    if not market and not passages:
        return refuse(NO_EVIDENCE)

    evidence = market + passages  # prices and headlines first: they are short, and the passages are numbered after them
    text, cited, bad, causes = _generate_checked_full(llm, search_question, evidence)
    cautions = (
        ([CAUSE_CAUTION] if causes else []) + relevant_cautions(evidence, intent.fundamentals, text)
        + ([not_calculated_note(intent.unstored)] if intent.unstored else [])
    )
    return Answer(
        question, text, symbols, evidence, cited, grounded=bool(cited), unverified_numbers=bad,
        queries=queries, interpreted_question=interpreted, cautions=cautions,
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
    print(f"searches: {' | '.join(ans.queries) or 'none (no filing search was needed)'}\n")
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
