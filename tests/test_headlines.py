import pytest

from data.headlines import is_quote_page, is_template_page, title_key

# Real headlines from the free news feed. These were also used to write the rules, so passing them shows the rules do
# what they were written to do, not that they will handle every future template.
QUOTE_AND_COMPARISON_PAGES = [
    "Apple Inc. (AAPL) Stock Price, News, Quote & History",
    "Nvidia Corp (NVDA) Stock Price Today: $226.19",
    "Apple Inc. Stock Price: Quote, Forecast, Splits & News (AAPL)",
    "Alphabet Inc Class A (GOOGL) vs Hecla Mining Company Common Stock (HL): Price, Performance & Key Differences",
    "Compare Alphabet Inc Class A (GOOGL) vs Halozyme Therapeutics Inc. Common Stock (HALO) Price & Performance",
    "Broadcom vs. Intel: Which Chip Stock Is a Better Buy in 2026?",
    "Apple Stock Price Forecast. Should You Buy AAPL?",
    "Wall Street sets Google (GOOGL) stock price for the next 12 months",
    "META_TITLE_QUOTE",  # a template placeholder that was never filled in
    "OG_TITLE_STOCK_2",
]

# Not matched by the core rules (the copilot still sees them), but left out of the sentiment totals.
DATA_PAGE_TEMPLATES = [
    "AMZN 261007 225.00C (AMZN261007C225000) Stock Options Chain | Quotes & News",
    "Tesla, Inc. (TSLA) Options Chain",
    "Columbia Disciplined Value Fund's Apple Inc(AAPL) Holding History",
    "Dividend History - Apple (AAPL)",
    "Apple Inc. (AAPL) Stock Dividend Growth Grade & History",
    "Microsoft Corporation (MSFT) Latest Stock Analysis",
    "Microsoft Corporation (MSFT) Latest Press Releases & Corporate News",
    "Page 680 | Microsoft Corporation (MSFT) Competitor Stock Analysis",
    "Alphabet (Nasdaq:GOOG) - Stock Analysis",
    "Apple (NasdaqGS:AAPL) Stock Forecast & Analyst Predictions",
    "TSLA Stock Forecast - Tesla Inc",
    "Apple Inc. (AAPL) Market Cap API",
    "Microsoft Predictions & Real-Time Odds",
    "Tesla, Inc. (TSLA) - Historical data, historical prices (daily)",
    "APPLE INC (AAPL) Stock Chart",
    "Microsoft Corporation (MSFT)",
    "NVIDIA CORPORATION (NVDA)",
    "Alphabet Inc Class C (GOOG)",
]

REAL_STORIES = [
    "Wells Fargo cuts Amazon stock price target on cost pressures By Investing.com",
    "Amazon Analysts Slash Price Targets Ahead Of Q3 – Wells Fargo Sees AWS Acceleration To Continue In Q4",
    "Apple Stock Climbs as JPMorgan Lifts Target, BofA Reiterates Buy",
    "Microsoft Market Capitalization Rises Above $4 Trillion",
    "Tesla chart watchers eye $400-mark as key level for breakout",
    "Options market points to 50% chance Nvidia hits $6T market cap this month",
    "Amazon Stock Forecast: AWS AI Boom Drives Growth as $220 Billion Capex Raises the Stakes",  # a headline, not a template
    "Why Microsoft's AI Growth Story Justifies A Strong Buy (NASDAQ:MSFT)",
    "Alphabet: Betting Big On The Frontier AI Labs (NASDAQ:GOOG)",
    "Unlike EV Narrative, Cybercab Does Not Need Tesla To Overcome An Entire Industry (TSLA)",
    "Here are the Compelling Reasons to Add Alphabet (GOOGL)",
    "What's Going On With Amazon Stock Friday? - Amazon.com (NASDAQ:AMZN)",
    "Amazon Reportedly in Talks to Buy AI Startup Decart for $7 Billion - Amazon.com (NASDAQ:AMZN)",
    "Intel aims to boost AI turnaround with new GPU chips to take on Nvidia",
    "Nvidia (NVDA) Sees a More Significant Dip Than Broader Market: Some Facts to Know",
    "SEC Probes Tesla",  # capitals, but not one placeholder token
    "Meta_Title_Quote",  # underscores in mixed case are not the all-caps placeholder
    "AAPL_Q3 results beat estimates",
]


@pytest.mark.parametrize("title", QUOTE_AND_COMPARISON_PAGES)
def test_quote_and_comparison_pages_are_left_out_everywhere(title):
    assert is_quote_page(title) and is_template_page(title), title


@pytest.mark.parametrize("title", DATA_PAGE_TEMPLATES)
def test_other_data_pages_are_left_out_of_totals_only(title):
    assert is_template_page(title), title
    assert not is_quote_page(title), title  # the copilot's set is deliberately narrower; see data/headlines.py


@pytest.mark.parametrize("title", REAL_STORIES)
def test_real_stories_are_never_mistaken_for_templates(title):
    assert not is_quote_page(title) and not is_template_page(title), title


def test_the_ticker_alone_rule_needs_an_uppercase_ticker_and_few_words():
    assert is_template_page("Microsoft Corporation (MSFT)")
    assert not is_template_page("Microsoft Corporation (msft)")  # not a ticker
    assert not is_template_page("Why Everyone Is Suddenly Talking About Microsoft Corporation Again (MSFT)")  # a real title


def test_title_key_ignores_case_spacing_and_a_trailing_publisher():
    assert title_key("Big  Deal Today - Wire", "Wire") == title_key("big deal today", "Other") == "big deal today"
    assert title_key("Big Deal - Not The Publisher", "Wire") == "big deal - not the publisher"
    assert title_key("Plain", None) == "plain"
