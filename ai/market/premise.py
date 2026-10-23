"""A move the question assumes ("why did it crash?"), checked against the stored closes."""
import re

from .windows import Window

_UP_VERBS = r"rise|rose|rises|jump(?:ed|s)?|surg(?:e|ed|es)|soar(?:ed|s)?|gain(?:ed|s)?|climb(?:ed|s)?|rall(?:y|ied|ies)|spik(?:e|ed|es)|increas(?:e|ed|es)|up"
_DOWN_VERBS = (
    r"fall|fell|falls|drop(?:ped|s)?|plung(?:e|ed|es)|sink|sank|tumbl(?:e|ed|es)|slid(?:e|es)?|slump(?:ed|s)?|crash(?:ed|es)?|"
    r"declin(?:e|ed|es)|los(?:t|e|es)|tank(?:ed|s)?|down"
)
_PCT_CLAIM_RE = re.compile(
    rf"\b(?P<verb>{_UP_VERBS}|{_DOWN_VERBS})\s+(?:by\s+|about\s+|nearly\s+|over\s+|around\s+|more\s+than\s+)?"
    r"(?P<n>\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_UP_RE = re.compile(rf"(?:{_UP_VERBS})$", re.IGNORECASE)
# the least a move must be for the question's word to be fair: "doubled" is +100%, so +80% or more passes; "halved" is -50%
_MULTIPLE_CLAIMS = (
    (re.compile(r"\bdoubl(?:e|ed|es|ing)\b", re.IGNORECASE), 80.0, "min"),
    (re.compile(r"\btripl(?:e|ed|es|ing)\b", re.IGNORECASE), 160.0, "min"),
    (re.compile(r"\bquadrupl(?:e|ed|es|ing)\b", re.IGNORECASE), 240.0, "min"),
    (re.compile(r"\bhalv(?:e|ed|es|ing)\b|\b(?:dropp(?:ed|ing)|fell|falling|cut|down|lost|losing)\s+(?:by\s+|in\s+)half\b", re.IGNORECASE), -40.0, "max"),
)
_STRONG_UP_RE = re.compile(r"\b(?:soar\w*|skyrocket\w*|surg(?:e|ed|es|ing)|spik(?:e|ed|es|ing)|rocket\w*|explod\w*)\b", re.IGNORECASE)
_STRONG_DOWN_RE = re.compile(r"\b(?:crash\w*|plung\w*|plummet\w*|tank(?:ed|s|ing)?|collaps\w*|crater\w*|nosedive\w*|tumbl\w*)\b", re.IGNORECASE)
STRONG_MOVE_PCT = 3.0  # "soared" and "crashed" need at least this much, in the right direction
_PREDICTION_WORDS_RE = re.compile(
    r"\b(?:will|would|could|might|may|can|if|whether|going\s+to|about\s+to|likely\s+to|what\s+if)\b", re.IGNORECASE
)


def _claims(question: str):
    """(the words as written, a test of the actual percentage change) for each move the question asserts or asks about. Predictions and
    hypotheticals ("will soar", "could crash", "what if it doubles") are skipped: there is nothing to compare."""
    found, taken = [], []

    def usable(m) -> bool:
        sentence_start = max(question.rfind(c, 0, m.start()) for c in ".?!") + 1
        return not _PREDICTION_WORDS_RE.search(question[sentence_start:m.start()])

    for m in _PCT_CLAIM_RE.finditer(question):
        if not usable(m):
            continue
        n = float(m.group("n"))
        signed = n if _UP_RE.match(m.group("verb")) else -n
        def ok(actual, signed=signed):  # `signed` is bound as a default, so each claim keeps its own value
            return abs(actual - signed) <= 1.0 or (actual * signed > 0 and 0.5 <= abs(actual) / abs(signed) <= 2.0)

        found.append((m.start(), m.group(0), ok))
        taken.append(m.span())
    for pattern, bound, kind in _MULTIPLE_CLAIMS:
        for m in pattern.finditer(question):
            if usable(m):
                test = (lambda actual, b=bound: actual >= b) if kind == "min" else (lambda actual, b=bound: actual <= b)
                found.append((m.start(), m.group(0), test))
                taken.append(m.span())
    for pattern, test in ((_STRONG_UP_RE, lambda actual: actual >= STRONG_MOVE_PCT), (_STRONG_DOWN_RE, lambda actual: actual <= -STRONG_MOVE_PCT)):
        for m in pattern.finditer(question):
            if usable(m) and not any(a <= m.start() < b for a, b in taken):
                found.append((m.start(), m.group(0), test))
    return [(phrase, ok) for _, phrase, ok in sorted(found, key=lambda t: t[0])]


def premise_cautions(question: str, evidence: list, window: Window) -> list[str]:
    """A plain statement of what the stored closes show when the question assumes a move they do not support ("Google doubled this
    month" when it rose 1%). It quotes the claim and the data and never calls the question wrong. Silent when there is nothing to compare:
    no price source, several companies, a period that could not be read, a prediction. At most one statement."""
    prices = [e for e in evidence if e.kind == "price"]
    if len(prices) != 1 or window.unmet or window.day or prices[0].change_pct is None:  # a named day: the shown move is not that day's
        return []
    e = prices[0]
    for phrase, supported in _claims(question):
        if not supported(e.change_pct):
            return [
                f"You mention that {e.symbol} “{phrase}”; the stored closes show {e.change_pct:+.1f}% over the {window.label}, "
                "so the question may assume a move that did not happen."
            ]
    return []
