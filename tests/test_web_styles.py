"""Rules in web/src/styles.css that fix real defects found by using the app, checked as text.

The web tests cannot see stylesheets (jsdom does not apply them, and the Vitest config turns CSS off, which makes even a raw import
empty), so these rules are checked here. Each was a real defect found in a browser or an accessibility scan: the watchlist's price cut off
mid-number on a phone, a dimmed line at 4.06:1 contrast, and tap targets under 24px. A rule written differently needs this test updated.
"""
import re
from pathlib import Path

import pytest

WEB_SRC = Path(__file__).resolve().parent.parent / "web" / "src"
CSS = (WEB_SRC / "styles.css").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    """The declarations of the rule whose selector is exactly `selector`."""
    found = re.search(r"(?:^|\n)" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert found, f"no rule for {selector}"
    return found.group(1)


def narrow_container_block() -> tuple[int, str]:
    found = re.search(r"@container\s*\(max-width:\s*(\d+)px\)\s*\{(.*?)\n\}", CSS, re.S)
    assert found, "no @container (max-width) block"
    return int(found.group(1)), found.group(2)


def test_the_watchlist_hides_its_trend_and_mood_columns_in_a_narrow_card():
    width, body = narrow_container_block()
    assert re.search(r"\.watch-optional\s*\{\s*display:\s*none;?\s*\}", body)
    assert re.search(r"tbody th\s*\{\s*white-space:\s*normal;?\s*\}", body)  # company names may wrap
    assert re.search(r"th, td\s*\{\s*padding-left:\s*6px;\s*padding-right:\s*6px;\s*\}", body)  # the filings list was 5px too wide
    # A phone's card is about 305px wide (a 375px screen); the table needs about 585px with every column, so the cut-off sits between.
    assert 305 < width < 585


def test_the_table_wrapper_is_the_container_that_is_measured():
    assert re.search(r"overflow-x:\s*auto", rule(".table-wrap"))
    assert re.search(r"\.table-wrap\s*\{\s*container-type:\s*inline-size;?\s*\}", CSS)


def test_a_removed_company_is_dimmed_with_the_muted_colour_not_opacity():
    # Opacity on top of the muted colour took the text to 4.06:1 in light mode; the minimum is 4.5:1.
    assert re.search(r"color:\s*var\(--muted\)", rule(".removed-line .symbol"))
    assert "opacity" not in rule(".removed-line .symbol")
    assert "opacity" not in rule(".removed-line .muted")


def test_ticker_links_have_room_to_be_at_least_24px_tall():
    assert re.search(r"display:\s*inline-block", rule(".symbol"))
    assert re.search(r"padding:\s*2px 0", rule(".symbol"))


def test_stand_alone_links_are_at_least_24px_tall():
    # Some sit in small text, where padding alone left them 21px tall; a minimum height says what is meant.
    assert re.search(r"min-height:\s*24px", rule(".tap"))
    assert re.search(r"display:\s*inline-flex", rule(".tap"))


def test_checkboxes_are_at_least_24px():
    assert re.search(r"width:\s*1\.5rem.*height:\s*1\.5rem", rule('input[type="checkbox"]'), re.S)


def test_the_how_was_this_calculated_toggles_have_room_to_be_at_least_24px_tall():
    assert re.search(r"padding:\s*3px 0", rule("details summary"))  # they were 20px tall


def test_the_add_company_ticker_field_is_at_least_24px_tall():
    assert re.search(r"min-height:\s*1\.75rem", rule(".add-company .add-form input"))  # 28px; it was 21px


@pytest.mark.parametrize("name", [".watch-optional", ".tap"])
def test_the_classes_the_stylesheet_relies_on_are_used_by_the_components(name):
    used = "".join(p.read_text(encoding="utf-8") for p in WEB_SRC.rglob("*.tsx") if not p.name.endswith(".test.tsx"))
    assert name.lstrip(".") in used
