"""What counts as "the same headline". Used by the copilot and the API so both agree."""
from typing import Optional


def title_key(title: str, publisher: Optional[str]) -> str:
    """The title with case, spacing, and a trailing " - Publisher" ignored.

    The free news feed returns one story several times, once per outlet that carried it, each with its own link."""
    t = " ".join(title.lower().split())
    if publisher and t.endswith(f" - {publisher.lower()}"):
        t = t[: -len(publisher) - 3]
    return t
