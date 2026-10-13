"""What counts as "the same headline", and which headlines are quote pages. Used by the copilot, the sentiment
totals, and the API so they all agree."""
import re
from typing import Optional


def title_key(title: str, publisher: Optional[str]) -> str:
    """The title with case, spacing, and a trailing " - Publisher" ignored.

    The free news feed returns one story several times, once per outlet that carried it, each with its own link."""
    t = " ".join(title.lower().split())
    if publisher and t.endswith(f" - {publisher.lower()}"):
        t = t[: -len(publisher) - 3]
    return t


# Quote pages and "X vs Y" comparison pages are the bulk of the neutral labels. They say nothing new, and a quoted
# price in a title (an intraday figure) could be mistaken for the stored close. The pattern is deliberately loose; it
# also catches the odd real story (an analyst "stock price target" cut), a cost accepted for one shared rule.
QUOTE_PAGE_RE = re.compile(
    r"\bstock\s+price\b|\bshare\s+price\b|\bprice\s+today\b|\bquote\b|\bprice\s*,|\bvs\.?\s", re.IGNORECASE
)


def is_quote_page(title: str) -> bool:
    return QUOTE_PAGE_RE.search(title) is not None
