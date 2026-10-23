"""Prices, headlines, headline sentiment, and company financial figures as numbered evidence for the copilot.

Every number the model may quote is worked out here (or in data/fundamentals.py), in Python, and written into the
source text. The model only copies figures; it never calculates them. Headlines are titles only (no article text), so
nothing here can show *why* a stock moved, and the financial figures can't show why a company's profit changed.

Usage: python -m ai.market AAPL "How has Apple stock done this year?"   (print the evidence the copilot would see)
"""
# The package keeps the names the rest of the app imports from `ai.market`.
from .advice import asks_for_advice  # noqa: F401
from .evidence import (  # noqa: F401
    MarketEvidence,
    evidence_from_fundamentals,
    fundamentals_evidence,
    gather_market_evidence,
    headline_evidence,
    price_evidence,
    relevant_cautions,
    sentiment_evidence,
)
from .intent import Intent, detect_intent  # noqa: F401
from .premise import premise_cautions  # noqa: F401
from .scope import (  # noqa: F401
    NAME_RUN_RE,
    NOT_NAMES,
    UNTRACKED_COMPANIES,
    _name_run_words,
    join_names,
    outside_scope,
    unknown_name,
    writing_request,
)
from .topics import (  # noqa: F401
    BARE_STOCK_RE,
    CAUSE_RE,
    FILING_FORM_RE,
    FILING_RE,
    PRICE_PREDICTION_RE,
    STOCK_WORD_RE,
    TWELVE_MONTHS_AS_QUARTERS_RE,
    WHY_RE,
    normalize_typing,
    year_start_comparison,
)
from .windows import DEFAULT_WINDOW, Window, news_days, parse_window, period_cautions  # noqa: F401
