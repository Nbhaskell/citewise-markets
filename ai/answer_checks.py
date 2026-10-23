"""Checks on what the model wrote, done in code: citations, figures and their direction, causes it implies, headlines it
made up, and false claims that prices or news are missing. `passage_block`, the way a source is shown to the model, is here
because the checks read the sources exactly as the model saw them."""
import re

import psycopg

from .market import MarketEvidence
from .search import SearchResult


def passage_block(number: int, r: SearchResult | MarketEvidence) -> str:
    if isinstance(r, MarketEvidence):
        return f"[{number}] {r.header}\n{r.text}"
    header = f"[{number}] {r.symbol} {r.form} filed {r.filed_at}"
    if r.period_of_report:
        header += f" (period ending {r.period_of_report})"
    if r.section:
        header += f", {r.section}"
    return f"{header}\n{r.text}"


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


DECLINE_RE = re.compile(r"\b(?:not|no|nothing|none|never|cannot|unable|nor|neither)\b|n['’]t", re.IGNORECASE)
ECHO_RE = re.compile(r"\b(?:whether|if)\b", re.IGNORECASE)  # restating the question, not asserting
FORECAST_MODAL_RE = re.compile(
    r"\b(?:will|would|going\s+to|shall|expected\s+to|likely\s+to|bound\s+to)\b|\b(?:won|wouldn|shan)['’]t\b", re.IGNORECASE
)  # "won't" and "wouldn't" are predictions that happen to contain a decline marker


def _users_own_numbers(question: str, plain: str, missing: set[str]) -> set[str]:
    """Missing figures that the question itself contains, when every sentence of the answer that uses them declines or
    restates the question without predicting anything. "Will Microsoft hit $600?" answered "the sources do not say whether
    Microsoft will hit $600" is correct, and the number is the user's, not a claim. Narrow on purpose, since this check is
    the only code-level guard on figures: "Microsoft will not hit $600" (a prediction), "Microsoft is at $600" (a claim),
    and a number the user didn't type are all still flagged."""
    mine = _numbers(question)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", plain)
    out = set()
    for number in missing & mine:
        uses = [s for s in sentences if number in _numbers(s)]
        if uses and all(
            DECLINE_RE.search(s) and (ECHO_RE.search(s) or not FORECAST_MODAL_RE.search(s)) for s in uses
        ):
            out.add(number)
    return out


def unverified_numbers(
    answer: str, cited: list[int], passages: list[SearchResult | MarketEvidence], question: str = ""
) -> list[str]:
    """Figures in the answer that appear nowhere in the passages it cites (or the headers above them), a minus sign
    the sources don't have, and price moves described in the wrong direction. A figure the question itself contains is
    let through when the answer only declines or restates (see _users_own_numbers)."""
    used = list(cited or range(1, len(passages) + 1))
    blocks = [passage_block(n, passages[n - 1]) for n in used]
    known, plain = _numbers("\n".join(blocks)), CITE_RE.sub("", answer)
    missing = _numbers(plain) - known
    missing -= _users_own_numbers(question, plain, missing)
    known_negatives = _negatives("\n".join(blocks))
    missing |= {f"-{v}" for v in _negatives(plain) if len(v) >= 2 and v not in known_negatives}
    market = [passages[n - 1] for n in used if isinstance(passages[n - 1], MarketEvidence)]
    return sorted(missing) + direction_errors(plain, market)


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


TITLE_MIN_WORDS = 3  # a shorter quote is a scare-quoted word or a phrase, not a headline
SENTIMENT_TAG_RE = re.compile(r"\[\s*sentiment\s*:[^\]]*\]|\(\s*sentiment\s*:[^)]*\)", re.IGNORECASE)
LIST_MARK_RE = re.compile(r"^\s*(?:(?:[-*•]|\d+[.)])\s*)?(?:(?:headline|title)\s*:\s*)?", re.IGNORECASE)
ELLIPSIS_RE = re.compile(r"\.\.\.|…")


def _squash(text: str) -> str:
    """Lower case, letters and digits only, one space between words: so a quote matches its source whatever the punctuation."""
    return " ".join(re.sub(r"[\W_]+", " ", text.lower()).split())


def quoted_titles(text: str) -> list[str]:
    """What the answer presents as a headline or a quotation: text inside quotation marks, and the words before a
    "[Sentiment: ...]" tag (the model's own list format for headlines). Short ones are left out (see TITLE_MIN_WORDS)."""
    plain = CITE_RE.sub("", text)
    found = [part for span in QUOTED_RE.findall(plain) for part in ELLIPSIS_RE.split(span.strip('"“”'))]
    for line in plain.splitlines():
        if tag := SENTIMENT_TAG_RE.search(line):
            found.append(LIST_MARK_RE.sub("", line[: tag.start()]).strip(" \t\"“”'‘’:-–—"))
    return [t.strip() for t in found if len(_squash(t).split()) >= TITLE_MIN_WORDS]


def invented_titles(text: str, passages: list[SearchResult | MarketEvidence], question: str = "") -> list[str]:
    """Titles or quotations in the answer that appear in none of the sources and not in the question. The numbers check
    cannot see these: "Tesla Faces Legal Challenges [Sentiment: Negative]" has no digits and no citation, and it was
    written by the model, not found in the data. Looks at every source given to the model, cited or not, and matches the
    words regardless of punctuation and case, so a quote that merely drops a trailing " - Reuters" still passes."""
    known = _squash(question + "\n" + "\n".join(passage_block(n, p) for n, p in enumerate(passages, 1)))
    out: list[str] = []
    for title in quoted_titles(text):
        if _squash(title) not in known and title not in out:
            out.append(title)
    return out


def invented_titles_caution(titles: list[str]) -> str:
    shown = "; ".join(f"“{t[:90]}”" for t in titles[:3])
    return (
        f"This answer quotes {'a headline or quotation' if len(titles) == 1 else 'headlines or quotations'} that "
        f"{'is' if len(titles) == 1 else 'are'} not in the stored sources: {shown}. The wording was made up by the model, "
        "so don't rely on it."
    )


# "not", "no", "doesn't", "cannot", "lacks", ... ("\w*n't" so a contraction counts; a plain \bn't would never match inside a word)
_NEGATION = r"(?:not|no|none|cannot|unable|without|lack\w*|missing|\w*n['’]t)"
NO_PRICE_CLAIM_RE = re.compile(
    rf"\b(?:stock|share|market|current|latest|closing)\s+prices?\b[^.\n]{{0,80}}\b(?:{_NEGATION}|unavailable|absent)\b"
    rf"|\b{_NEGATION}\b[^.\n]{{0,80}}\b(?:stock|share|market|current|latest|closing)\s+prices?\b"
    rf"|\bprice\s+(?:data|information|movements?|history)\b[^.\n]{{0,60}}\b(?:{_NEGATION}|unavailable)\b"
    rf"|\b{_NEGATION}\b[^.\n]{{0,60}}\bprice\s+(?:data|information|movements?|history)\b",
    re.IGNORECASE,
)
NO_PRICE_CAUTION = (
    "This answer says a stock price isn't available. This app does store daily closing prices for {names}, but the answer "
    "was written from filings only and did not use them. Ask for the stock price directly to see them."
)


def false_price_claim(conn: psycopg.Connection, text: str, symbols: list[str], evidence: list) -> str | None:
    """A caution when an answer written without any price source says the stock price is missing, for companies whose
    prices are stored. The model only saw filing text, so it reads its own gap as the app's ("the sources do not include
    Apple's stock price"). Worded to be true either way: a filing really may not state a price, and that is also covered."""
    if not symbols or not NO_PRICE_CLAIM_RE.search(CITE_RE.sub("", text)):
        return None
    if any(isinstance(e, MarketEvidence) and e.kind == "price" for e in evidence):
        return None
    stored = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM prices_daily WHERE symbol = ANY(%s)", (symbols,))}
    if stored != set(symbols):
        return None
    return NO_PRICE_CAUTION.format(names=", ".join(symbols))


# The news words that count: "news", "headlines" (plural, so "headline revenue" is not one), "stories", "news articles" and
# press or media coverage. Not a bare "articles" ("articles of incorporation").
_NEWS_THING = (
    r"(?:(?:recent|latest|current)\s+)?(?:news(?:\s+(?:stories|articles|headlines|coverage))?|headlines|stories|"
    r"press\s+coverage|media\s+coverage)"
)
NO_NEWS_CLAIM_RE = re.compile(
    rf"\b{_NEGATION}\b[^.\n]{{0,70}}\b{_NEWS_THING}\b|\b{_NEWS_THING}\b[^.\n]{{0,60}}\b(?:{_NEGATION}|unavailable|absent)\b",
    re.IGNORECASE,
)
NEWS_WINDOW_DAYS = 30
NO_NEWS_CAUTION = (
    "This answer says there is no news. This app stores headlines for {names}, but this answer did not use them. "
    "Ask for the news directly (for example, “What's the latest news on {first}?”) to see them."
)


def false_news_claim(
    conn: psycopg.Connection, text: str, symbols: list[str], evidence: list, asked_for_news: bool = False
) -> str | None:
    """The news version of `false_price_claim`: an answer written without any headline source that says there are no
    news stories, for companies whose recent headlines are stored. Not when the question asked for news: then the news
    route ran and found nothing in its window, so "no news this week" is true and not a gap in what was used. Worded to be
    true either way, with the count and the newest date so the reader can see the data is there."""
    if asked_for_news or not symbols or not NO_NEWS_CLAIM_RE.search(CITE_RE.sub("", text)):
        return None
    if any(isinstance(e, MarketEvidence) and e.kind in ("headline", "sentiment") for e in evidence):
        return None
    rows = conn.execute(
        "SELECT s.symbol, count(*), (max(a.published_at) AT TIME ZONE 'UTC')::date "
        "FROM news_articles a JOIN news_article_symbols s ON s.article_id = a.id "
        "WHERE s.symbol = ANY(%s) AND a.published_at >= now() - make_interval(days => %s) GROUP BY s.symbol",
        (symbols, NEWS_WINDOW_DAYS),
    ).fetchall()
    if {r[0] for r in rows} != set(symbols):
        return None
    by_symbol = {sym: (n, newest) for sym, n, newest in rows}
    names = ", ".join(f"{sym} ({by_symbol[sym][0]} in the last {NEWS_WINDOW_DAYS} days, the newest on {by_symbol[sym][1]})" for sym in symbols)
    return NO_NEWS_CAUTION.format(names=names, first=symbols[0])
