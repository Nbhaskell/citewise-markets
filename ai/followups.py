"""Understanding a follow-up question: the rewriting step, the rules that carry the earlier question's topic or comparison
over, and (in the same place, since both decide what a question is about) the rule that sends "What does Apple say about
falling demand?" to the filings."""
import re
from dataclasses import dataclass, replace

import psycopg

from .answer_checks import CITE_RE
from .companies import company_mentions, detect_symbols
from .llm import LLM, strip_thinking
from .market import BARE_STOCK_RE, CAUSE_RE, FILING_RE, STOCK_WORD_RE, Intent, detect_intent
from .search import detect_forms

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


SWITCH_FILLER_RE = re.compile(
    r"\b(?:what|how|about|and|or|then|also|so|ok|okay|now|next|instead|regarding|with|for|on|the|as|well|too|s|"
    r"do|try|check|run|go|ahead|see|please|again|let|lets|me|show|give|same|pull|up|"  # "Now do Alphabet.", "Try Microsoft.", "Same for X"
    r"number|numbers|figure|figures|one|question|idea|thing|approach|treatment)\b",  # "Give me the number for Apple too.", "Same question for X": generic nouns that name no topic
    re.IGNORECASE,
)
# "Switch over to Microsoft.", "Skip to Nvidia.", "Move on to X", "Over to X": a verb of moving on plus "to" says only that the
# company changes. Taken out before the filler words are, so "to" and "over" are not filler in general.
SWITCH_PHRASE_RE = re.compile(
    r"\b(?:switch(?:ing)?|skip(?:ping)?|mov(?:e|ing)|jump(?:ing)?|go(?:ing)?|hop(?:ping)?|cut(?:ting)?|turn(?:ing)?|shift(?:ing)?|pivot(?:ing)?|"
    r"flip(?:ping)?)\s+(?:(?:on|over|across|back|ahead|along)\s+)?(?:on)?to\b|\bover\s+to\b|\bonto\b",
    re.IGNORECASE,
)
PRONOUN_RE = re.compile(r"\b(its|their)\b|\b(it|they)\b", re.IGNORECASE)


# A follow-up that points back at the earlier question without saying what about ("Do the matching calculation for Google.", "Lay
# Amazon alongside it.", "What explains that?"). The rewriting step keeps these vague phrases and loses the topic; when the rewrite
# also names no topic, the earlier question's topic is reused (DECISIONS: "Follow-up topic carry"). Each word needs a question of its own.
POINTS_BACK_RE = re.compile(
    r"\b(?:that|those|same|matching|equivalent|counterpart|likewise|alongside|comparable|by\s+comparison|as\s+much|just\s+did)\b",
    re.IGNORECASE,
)
# Of those, the ones that say "compared with the earlier company" rather than "the same thing for this one".
POINTING_COMPARE_RE = re.compile(r"\b(?:alongside|comparable|by\s+comparison|as\s+much)\b", re.IGNORECASE)


def routes_somewhere(text: str) -> bool:
    """Would the app search for something specific? A market route (prices, headlines, mood, the stored figures), a ratio it does not
    compute, a buy/sell request, a filing noun (risks, legal, employees...), or a 10-K or quarter."""
    intent = detect_intent(text)
    return bool(intent.market or intent.unstored or intent.advice or FILING_RE.search(text) or detect_forms(text))


def names_a_topic(text: str) -> bool:
    """Does the text say what is being asked about? Whatever `routes_somewhere` finds, or a stock word (stock, shares, price): the
    user's own "stock" is a topic even when no price rule reads the sentence."""
    return routes_somewhere(text) or bool(STOCK_WORD_RE.search(text))


def points_back_without_a_topic(question: str, rewrite: str) -> bool:
    """The user's words point back and name no topic, and the rewrite did not supply a routable one either (a rewrite with only a
    stock word in it, "that move in Nvidia's stock", still goes to the filings)."""
    return bool(POINTS_BACK_RE.search(question)) and not names_a_topic(question) and not routes_somewhere(rewrite)


# "What does Apple say about falling demand in China?", "Does Tesla sound optimistic about its factory expansion?": a price or mood word
# inside a question about what the COMPANY says. When a tracked company, its management (executives, leadership, CEO, CFO) or its
# 10-K, 10-Q, annual report or filings is the one speaking, the question is about the filings, not the stock (DECISIONS: "Filings
# questions with price or mood words"). The test is who speaks, not which price word appears, so a new price word needs no new entry.
# Each verb and each speaker needs a question of its own.
SPEAKER_VERB = (
    r"(?:say|says|said|describe[sd]?|discuss(?:es|ed)?|disclose[sd]?|mention(?:s|ed)?|state[sd]?|explain(?:s|ed)?|convey(?:s|ed)?|sound(?:s)?|"
    # added after the third sealed round ("Did Alphabet warn that ad prices were dropping?" went to the stock prices)
    r"warn(?:s|ed)?|caution(?:s|ed)?|admit(?:s|ted)?|acknowledge[sd]?|concede[sd]?|signal(?:s|ed|led)?|indicate[sd]?|flag(?:s|ged)?|"
    r"note[sd]?|talk(?:s|ed)?|tell|tells|told)"
)
SPEAKER_STAFF = r"(?:management|executives?|leadership|ceo|cfo)"
SPEAKER_DOC = r"(?:10-?k|10-?q|annual\s+report|filings?)"
# what may follow the company's name: its staff or documents, a small word, then a speaking verb ("Apple's 10-K says", "Tesla also said")
AFTER_COMPANY_RE = re.compile(
    rf"\A(?:['’]s\s+(?:{SPEAKER_STAFF}|{SPEAKER_DOC}))?\s+(?:(?:also|ever|really|actually)\s+)?{SPEAKER_VERB}\b", re.IGNORECASE
)
COMPANY_STAFF_RE = re.compile(rf"\A['’]s\s+{SPEAKER_STAFF}\b", re.IGNORECASE)  # "How bullish is Nvidia's management about ...": no verb needed
DOCUMENT_SPEAKS_RE = re.compile(rf"\b{SPEAKER_DOC}\s+{SPEAKER_VERB}\b", re.IGNORECASE)  # "What does the 10-K say ...": no company needed
# The press named: "Has Apple said anything in the headlines today?" is still about the headlines.
PRESS_NAMED_RE = re.compile(r"\b(?:news|headlines?|press|coverage|stor(?:y|ies)|articles?|reporters?|media|journalists?)\b", re.IGNORECASE)


def company_is_speaking(conn: psycopg.Connection, text: str) -> bool:
    """Is a tracked company, its staff or its documents the one saying, describing or sounding something? (Not analysts, investors,
    "you", "the market" or a news story.)"""
    if DOCUMENT_SPEAKS_RE.search(text):
        return True
    for matches in company_mentions(conn, text).values():
        for m in matches:
            if re.search(r"\bthe\s+\Z", text[:m.start()], re.IGNORECASE):  # "the Tesla signal": the name describes a noun, it is not speaking
                continue
            tail = text[m.end():]
            if COMPANY_STAFF_RE.match(tail) or AFTER_COMPANY_RE.match(tail):
                return True
    return False


def route_by_speaker(conn: psycopg.Connection, text: str, intent: Intent) -> Intent:
    """The intent after the speaker rule: prices, headlines and mood off and the filings on, when the company is the speaker and the press
    is not named. The stored figures are not touched. Returns `intent` itself when nothing changes."""
    if not (intent.prices or intent.headlines) or PRESS_NAMED_RE.search(text) or not company_is_speaking(conn, text):  # (mood comes with headlines)
        return intent
    return replace(intent, prices=False, headlines=False, sentiment=False, filings=True)


def _is_bare_switch(text: str, mentions: dict[str, list[re.Match]]) -> bool:
    """Only company names and filler words: "What about Tesla?", "And Tesla's?". Nothing says what to ask about it."""
    rest = text
    for match in sorted((m for ms in mentions.values() for m in ms), key=lambda m: m.start(), reverse=True):
        rest = rest[: match.start()] + " " + rest[match.end():]
    return not re.sub(r"[\W_]+", "", SWITCH_FILLER_RE.sub(" ", SWITCH_PHRASE_RE.sub(" ", rest)))


def _swap_company(text: str, old: list[re.Match], new: str) -> str:
    for match in sorted(old, key=lambda m: m.start(), reverse=True):
        text = text[: match.start()] + new + text[match.end():]
    return text


COMPARE_RE = re.compile(
    r"\b(?:than|versus|vs|against|compare[sd]?\s+(?:to|with)|compare|stack(?:s|ed)?\s+up|relative\s+to|beats?|"
    r"outperform(?:s|ed)?|measures?\s+up)\b",
    re.IGNORECASE,
)
# "Does Amazon say anything similar?": similar to what the company just discussed said. A comparison and a reference back in
# one cue. "Similar" before a noun ("similar companies", "a similar number of") is not it.
SIMILAR_RE = re.compile(
    r"\b(?:(?:anything|something|nothing|everything|much)\s+(?:similar|alike|comparable|like\s+(?:that|this|it))"
    r"|(?:similar|alike|comparable|likewise)\W*$)",
    re.IGNORECASE,
)
# "all the companies", "which company": every tracked company, not the ones just discussed. "the company" (singular) is a
# reference back and is in REFERENCE_RE, so it is not here.
ALL_COMPANIES_RE = re.compile(
    r"\b(?:all\s+(?:of\s+)?(?:the\s+)?companies|the\s+companies|every\s+company|each\s+company|any\s+company|"
    r"which\s+compan(?:y|ies)|across\s+companies)\b|\bcompanies['’]",
    re.IGNORECASE,
)
# Words a comparison can have around its two companies and still say nothing about WHAT is compared ("Is that better or
# worse than Amazon?"). Anything else ("its revenue", "the risks") is a topic of its own. Comparative adjectives are a
# closed list on purpose: an unknown one just means the topic is not carried, and the companies still are.
COMPARE_FILLER_RE = re.compile(
    r"\b(?:is|are|was|were|how|does|do|did|than|that|this|it|its|those|these|they|them|their|the|same|or|and|to|with|"
    r"versus|vs|against|compare|compared|compares|stack|stacks|up|down|then|now|too|also|any|s|like|look|looks|as|so|about|what|"
    r"better|worse|stronger|weaker|higher|lower|bigger|larger|smaller|cheaper|faster|slower|safer|riskier|more|less|fewer|"
    r"greater|similar|different|good|bad|well|much|many|big|large|small|high|low|strong|weak|cheap|expensive|fast|slow|"
    r"risky|safe|ahead|behind|beat|beats|outperform|outperforms|measure|measures|"
    r"longer|shorter|list|lists|number|count|total|amount|figure|figures|"  # generic nouns: "Is Tesla's list longer than that?"
    r"say|says|said|mention|mentions|anything|something|alike|comparable|likewise|has|have|had|there|at|"  # "Does Amazon say anything similar?"
    r"fare|fared|fares|faring|perform|performs|performed|performing)\b",  # "Did Microsoft fare better than that?"
    re.IGNORECASE,
)


def _is_bare_comparison(text: str, mentions: dict[str, list[re.Match]]) -> bool:
    """Only company names, comparison words and filler: nothing says what is being compared."""
    rest = text
    for match in sorted((m for ms in mentions.values() for m in ms), key=lambda m: m.start(), reverse=True):
        rest = rest[: match.start()] + " " + rest[match.end():]
    return not re.sub(r"[\W_]+", "", COMPARE_FILLER_RE.sub(" ", rest))


def comparison_companies(
    conn: psycopg.Connection, question: str, history: list[Turn], pointing: bool = False
) -> list[str] | None:
    """"Is that better or worse than Amazon?" after a question about Nvidia compares Nvidia (what "that" is) with Amazon.
    The rewriting step is meant to name both and sometimes names only the new one, so only Amazon was searched. Returns the
    companies of the last turn followed by the newly named ones, or None when this is not that kind of question: no
    comparison word, no reference back ("that", "it"), a reference to something older ("the other one"), no earlier
    company, or a question that already names the earlier company (then it says what it means)."""
    similar = bool(SIMILAR_RE.search(question))
    if not history or BACKREF_RE.search(question):
        return None
    if not pointing and (not (COMPARE_RE.search(question) or similar) or not (REFERENCE_RE.search(question) or similar)):
        return None  # a question that points back without a topic ("Lay Amazon alongside it.") is already known to compare
    named = company_mentions(conn, question)
    recent = [c.upper() for c in history[-1].companies]
    if not named or not recent or set(named) & set(recent):
        return None
    return recent + sorted(named, key=lambda symbol: named[symbol][0].start())


def carry_comparison(
    conn: psycopg.Connection, question: str, history: list[Turn], companies: list[str], pointing: bool = False
) -> str | None:
    """A bare comparison asked again about the earlier topic: "Is that better or worse than Amazon?" after "How has Nvidia
    stock done this month?" becomes "How has Nvidia stock done this month, compared with Amazon?". Only the earlier
    *question* is reused, never its answer. None when the question has a topic of its own or the earlier topic does not
    clearly belong to the company "that" stands for."""
    named = company_mentions(conn, question)
    recent = [c.upper() for c in history[-1].companies]
    if not (pointing or _is_bare_comparison(question, named)):
        return None
    typed = " and ".join(m.group(0) for m in sorted((ms[0] for ms in named.values()), key=lambda m: m.start()))
    for earlier in reversed(history):
        before = company_mentions(conn, earlier.question)
        if before and _is_bare_switch(earlier.question, before):
            continue  # a bare "What about Tesla?" has no topic; the question before it does
        if pointing and not names_a_topic(earlier.question):
            return None  # nothing to carry
        base = earlier.question
        if len(before) == 1 and len(recent) == 1 and set(before) != set(recent):
            base = _swap_company(base, next(iter(before.values())), recent[0])  # the topic, about the company "that" is
        composed = f"{base.rstrip(' ?.!')}, compared with {typed}?"
        return composed if set(detect_symbols(conn, composed)) == set(companies) else None
    return None


def carry_topic(conn: psycopg.Connection, question: str, history: list[Turn], pointing: bool = False) -> str | None:
    """"What about Tesla?" after a question about Nvidia means the same question about Tesla. The rewriting step is told
    to leave a question that switches company alone, so it hands this back unchanged and the search ran on nothing but
    a company name. Only the earlier *question* is reused (its answer never is), and only when it is clear what to swap:
    the earlier question names exactly one tracked company, or has a pronoun standing for it. Returns None otherwise."""
    named = company_mentions(conn, question)
    if not named or not (pointing or _is_bare_switch(question, named)) or set(named) & {c.upper() for c in history[-1].companies}:
        return None
    typed = " and ".join(  # the company as the user wrote it, in the order they wrote it
        m.group(0) for m in sorted((ms[0] for ms in named.values()), key=lambda m: m.start())
    )
    for earlier in reversed(history):
        before = company_mentions(conn, earlier.question)
        if before and _is_bare_switch(earlier.question, before):
            continue  # an earlier "What about Tesla?" has no topic either; the one before it does
        if pointing and not names_a_topic(earlier.question):
            return None  # nothing to carry
        if len(before) == 1:
            return _swap_company(earlier.question, next(iter(before.values())), typed)
        if not before and PRONOUN_RE.search(earlier.question):
            return PRONOUN_RE.sub(lambda m: f"{typed}'s" if m.group(1) else typed, earlier.question)
        return None
    return None


def carry_cause(conn: psycopg.Connection, question: str, history: list[Turn]) -> str | None:
    """"What explains that?" after a question about a stock's price means "... and what explains that?": the earlier question with
    the cause question appended (its answer is never used). Only when the question names no company and the earlier question is a
    price question, because a cause question about a price brings the headlines (published beside the move, never offered as its
    cause). None otherwise."""
    if not CAUSE_RE.search(question) or company_mentions(conn, question):
        return None
    for earlier in reversed(history):
        before = company_mentions(conn, earlier.question)
        if before and _is_bare_switch(earlier.question, before):
            continue  # a bare "What about Tesla?" has no topic; the question before it does
        if not detect_intent(earlier.question).prices:
            return None
        return f"{earlier.question.rstrip(' ?.!')}, and {question[0].lower()}{question[1:]}"
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
    # "Do the matching calculation for Google.": the question points back and neither it nor the rewrite says what about.
    pointing = not symbols and points_back_without_a_topic(question, search_question)  # (every use below also needs a history)
    # A rewrite that names the earlier company ("Is Tesla in the same boat?" -> "...as Microsoft") is a comparison, whatever words the user
    # chose; a swap would drop the earlier company. (When the user named it too, the comparison and swap rules both decline.)
    earlier_companies = {c.upper() for c in history[-1].companies} if history else set()
    added_earlier = bool(set(detect_symbols(conn, search_question)) & earlier_companies)
    comparing = pointing and bool(
        COMPARE_RE.search(question) or SIMILAR_RE.search(question) or POINTING_COMPARE_RE.search(question) or added_earlier
    )
    compare = None if symbols else comparison_companies(conn, question, history, pointing=comparing)
    carried = carry_topic(conn, question, history, pointing=pointing and not comparing) if history and not symbols else None
    if carried:
        # A bare switch ("Skip to Nvidia.") names no topic, so any topic in the rewrite is the earlier one reworded or one it
        # invented ("Microsoft's company summary"). The earlier question itself, about the new company, wins.
        search_question = carried
    elif history and not symbols and BARE_STOCK_RE.search(question) and not detect_intent(search_question).prices:
        search_question = question  # "ok, and Alphabet stock?" was rewritten into the earlier risks question; the user's words win
    elif pointing and (caused := carry_cause(conn, question, history)):
        search_question = caused  # "What explains that?": the earlier price question, and the cause question about it
    if (
        history and not symbols and ALL_COMPANIES_RE.search(question) and not REFERENCE_RE.search(question)
        and not BACKREF_RE.search(question) and not detect_symbols(conn, question)
    ):
        return question, [], None  # "the companies" is all of them; a rewrite that names some (NVDA and AMD) made them up
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
    note = None
    lost = bool(compare) and not set(compare) <= set(detect_symbols(conn, search_question))
    if compare and (lost or comparing or _is_bare_comparison(question, company_mentions(conn, question))):
        # The rewrite lost the company "that" stands for, or the comparison names no topic of its own, so a topic in the
        # rewrite is the earlier one reworded or an invented one ("Data Center revenue"). Rebuild the question from the
        # earlier one when the comparison has no topic of its own; otherwise keep the model's wording and, when it lost a
        # company, say which companies were compared.
        rebuilt = carry_comparison(conn, question, history, compare, pointing=comparing)
        if rebuilt:
            search_question = rebuilt
        elif lost:
            note = f"{search_question} (comparing {' and '.join(compare)})"
    if symbols:
        found = [s.upper() for s in symbols]
    else:
        found = compare or detect_symbols(conn, search_question) or detect_symbols(conn, question)
        if not found and history and REFERENCE_RE.search(question):
            found = list(history[-1].companies)  # "its risks": the rewrite didn't name it, so carry the last company
    same = " ".join(search_question.lower().split()) == " ".join(question.lower().split())
    return search_question, found, note or (None if same else search_question)
