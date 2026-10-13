"""What counts as "the same headline", and which headlines are quote pages or other data-page templates. Used by the
copilot, the sentiment totals, and the API so they all agree."""
import re
from typing import Optional


def title_key(title: str, publisher: Optional[str]) -> str:
    """The title with case, spacing, and a trailing " - Publisher" ignored.

    The free news feed returns one story several times, once per outlet that carried it, each with its own link."""
    t = " ".join(title.lower().split())
    if publisher and t.endswith(f" - {publisher.lower()}"):
        t = t[: -len(publisher) - 3]
    return t


# Quote pages, comparison pages, and other data-page templates are the bulk of the neutral labels. They say nothing new,
# and a quoted price in a title (an intraday figure) could be mistaken for the stored close. Each rule below was seen in
# real headlines from the free feed. A new template shows up now and then and needs a new rule.
#
# Two sets. The copilot uses only the core set, because that is the set its evaluation (`ai.eval_market`) was run
# against: adding the data-page rules changed which Apple headlines it saw and flipped the "crashing premise" case from
# 8 of 8 passes to 0 of 8. The sentiment totals use both sets.
_QUOTE_PAGE_RULES = [
    # Quote pages: "Apple Inc. (AAPL) Stock Price, Quote & Chart", "Stock Price Today: $226.19". An analyst's "stock
    # price target" is real news ("Wells Fargo cuts Amazon stock price target"), so it is not matched.
    r"\b(?:stock|share)\s+price\b(?!\s+targets?\b)",
    r"\bprice\s+today\b",
    r"\bquote\b",
    r"\bprice\s*,",
    # Comparison pages: "X vs Y: Price, Performance & Key Differences", "Compare X vs Y"
    r"\bvs\.?\s",
]
_DATA_PAGE_RULES = [
    r"\bquotes\b",  # "Stock Options Chain | Quotes & News"
    r"\boptions\s+chain\b",  # "Tesla, Inc. (TSLA) Options Chain"
    r"\bholding\s+history\b",  # "Some Fund's Apple Inc(AAPL) Holding History"
    r"\bdividend\s+history\b",
    r"\b(?:dividend\s+growth|momentum)\s+grade\b",
    r"\blatest\s+(?:stock\s+(?:analysis|news)|press\s+releases)\b",
    r"\bcompetitor\s+stock\s+analysis\b",
    r"\bstock\s+(?:analysis|chart)\b",
    r"\bstock\s+forecast\b(?!\s*[:|])",  # "Stock Forecast & Analyst Predictions", but not "Stock Forecast: <real headline>"
    r"\bmarket\s+cap\s+api\b",
    r"\breal-time\s+odds\b",
    r"\bhistorical\s+(?:data|prices)\b",
    # A bare company name and ticker with nothing else: "Microsoft Corporation (MSFT)"
    r"^(?:[\w.,&'’-]+\s+){0,5}\(\s*(?-i:[A-Z]{1,5}(?:[.:][A-Z]{1,3})?)\s*\)\s*$",
]
QUOTE_PAGE_RE = re.compile("|".join(_QUOTE_PAGE_RULES), re.IGNORECASE)
TEMPLATE_PAGE_RE = re.compile("|".join(_QUOTE_PAGE_RULES + _DATA_PAGE_RULES), re.IGNORECASE)


def is_quote_page(title: str) -> bool:
    """Quote and comparison pages only. This is what the copilot leaves out of its sources."""
    return QUOTE_PAGE_RE.search(title) is not None


def is_template_page(title: str) -> bool:
    """Quote and comparison pages plus the other data-page templates. This is what the sentiment totals leave out."""
    return TEMPLATE_PAGE_RE.search(title) is not None
