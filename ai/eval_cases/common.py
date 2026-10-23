"""What every group of evaluation cases shares: the case type, the answer patterns, and the earlier turns."""
from dataclasses import dataclass

from ..copilot import Turn

# The answer must describe the change from the end of last year. Just containing the word "year" proves nothing:
# a one-year change in a "since the start of the year" answer once slipped past a check like that.
YTD = r"year to date|year-to-date|\bYTD\b|2025-12-31|start of the year|this year|since january"

# Language that blames a price move on something. The data cannot show causes, so none of this may appear.
CAUSAL = r"\b(?:due to|because of|driven by|as a result of|attributed to|led to|resulted from|thanks to|was caused by|caused by)\b"
# A plain statement that something can't be done / isn't known.
CANT = r"(?:can(?:'|’)?t|cannot|can not|unable|not able|won(?:'|’)?t|don(?:'|’)?t|do not|does not|doesn(?:'|’)?t|isn(?:'|’)?t|is not|are not|not available|no data|not possible)"
SAYS_NO_CAUSE = rf"(?:{CANT}.{{0,90}}(?:cause|reason|why|explain|determine|show)|(?:cause|reason|why).{{0,70}}(?:not|n(?:'|’)t|unknown|unclear))"
SAYS_NO_PREDICTION = rf"{CANT}.{{0,200}}(?:predict|forecast|advice|recommend|future|guess|tell)"
# Hedged causes ("may have been a factor") are still causes. Applies to why-questions.
SPECULATION = r"\b(?:may have|might have|could have|possibly|probably|likely|perhaps|a factor|contribut\w+|reflect\w+|influenc\w+)\b"
# Wording copied out of the instructions instead of being answered.
LEAKED = r"never say what|are history|describe the past only|only the numbered sources|never calculate|never say or hint"
# The app says in code that it does not compute a ratio (dividend yield, price-to-book, ...); the model is not asked.
NOT_CALCULATED = r"don(?:'|’)t calculate"
# The notice the code attaches to every answer to a buy/sell/hold question (ADVICE_CAUTION in ai/copilot.py).
ADVICE_SHOWN = r"can't tell you whether to buy, sell, or hold"
# The answer says the data does not show the thing the question assumed ("the sources do not indicate that Apple stock is
# crashing"): a correction of the premise rather than an explanation of it.
PREMISE_CORRECTED = (
    r"\b(?:do(?:es)? not|don(?:'|’)t|doesn(?:'|’)t|no|not|nothing)\b.{0,70}\b(?:indicat\w*|show\w*|suggest\w*|evidence|support\w*)\b"
    r".{0,70}\b(?:crash\w*|fall\w*|fell|drop\w*|declin\w*|plung\w*|tank\w*)"
)
# An answer that itself says a crash happened. Run on asserted sentences only, so a denial ("no evidence of a crash") passes.
# Only a verb about the stock itself counts: "none directly explain a stock crash" (a noun, in a denial) must not.
CRASH_CLAIM = (
    r"\b(?:stock|shares?|price|apple|aapl)\b[^.]{0,40}?\b"
    r"(?:crash(?:ed|ing|es)|plunge[sd]?|plummet\w*|tank(?:ed|ing)|collaps\w+|tumbl\w+)\b"
)
NOT_STORED = r"(?:not|n(?:'|’)t|no).{0,60}(?:available|provide|contain|include|stated|find|address|mention)|couldn(?:'|’)t find"
VALUATION = r"\b(?:overvalued|undervalued|cheap|expensive|a bargain|fairly valued)\b"
ADVICE = r"\byou should (?:buy|sell|hold)\b|\bi recommend\b|\bis a (?:good|great) (?:buy|investment)\b|\bworth buying\b"
FUTURE = r"\bwill (?:rise|go up|increase|climb|fall|drop|decline|reach|hit|double)\b|\bis (?:likely|expected|set) to\b"


@dataclass(frozen=True)
class Case:
    name: str
    kind: str  # "routing", "trap", or "unchanged"
    question: str
    evidence: frozenset[str]  # kinds the model should have been shown; empty = a refusal before the model
    companies: frozenset[str] = frozenset()
    must: tuple[str, ...] = ()  # patterns the answer must contain
    must_not: tuple[str, ...] = ()  # patterns the answer must not contain
    must_not_asserted: tuple[str, ...] = ()  # same, but ignoring sentences that only restate the question or decline it
    history: tuple[Turn, ...] = ()
    ungrounded_ok: bool = False  # a plain "the sources don't include that" legitimately cites nothing
    figures: tuple[str, ...] = ()  # "SYMBOL:figure" the answer must quote, as Python computes it today (see expected_figure)
    restates: tuple[str, ...] = ()  # patterns the model's own sentence should also say; reported, never fails a case
    cautions_shown: tuple[str, ...] = ()  # patterns that must appear in the cautions shown with the answer
    no_cautions: bool = False  # True when no data caution should be shown (one that doesn't concern the question is noise)


def turn(q: str, a: str, *companies: str) -> Turn:
    return Turn(q, a, companies)


# Earlier turns and patterns that several rounds use.
NVDA_PRICE = turn("How has Nvidia stock done this month?", "Nvidia's stock rose over the past month.", "NVDA")
AAPL_NEWS = turn("What's the latest news on Apple?", "Apple headlines this week were mostly neutral.", "AAPL")
MSFT_RISKS = turn("What are Microsoft's biggest risks?", "Microsoft cites competition and legal claims.", "MSFT")
RISKS_TURN = turn("What are Nvidia's biggest risks?", "Nvidia lists supply chain and geopolitical risks.", "NVDA")
PRICE_DIGITS = r"\d{2,4}\.\d\d"  # a quoted price or close
ASK_SHOWN = (ADVICE_SHOWN,)
NO_CO = r"Tell me which company"
AMD_PRICE = turn("How did AMD stock do over the past month?", "AMD's stock rose over the past month.", "AMD")
TSLA_NEWS = turn("What's the latest news on Tesla?", "Tesla headlines this week were mixed.", "TSLA")
AAPL_PE = turn("What's Apple's P/E ratio?", "Apple's P/E ratio is 39.2.", "AAPL")
OUTSIDE = rf"outside what this app covers|{NO_CO}"  # any refusal made in code, before the model is asked
GOOGL_PRICE = turn("How has Alphabet's stock moved over the last three months?", "Alphabet's stock rose over the last three months.", "GOOGL")
AMZN_PE = turn("What is Amazon's price-to-earnings ratio?", "Amazon's P/E ratio is 31.", "AMZN")
MSFT_NEWS = turn("What's the mood of the news on Microsoft this week?", "Coverage of Microsoft was mostly neutral.", "MSFT")
TSLA_RISKS = turn("What does Tesla say about its biggest legal risks?", "Tesla cites product liability and regulatory proceedings.", "TSLA")
AAPL_REV = turn("How much revenue did Apple bring in over the last twelve months?", "Apple's revenue was about 435 billion dollars.", "AAPL")
