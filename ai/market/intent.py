"""Which kinds of evidence a question needs: prices, headlines, mood, the stored figures, or filings."""
import re
from dataclasses import dataclass

from .advice import asks_for_advice
from .topics import (
    BARE_STOCK_RE,
    CAUSE_RE,
    CLOSE_EXTREME_RE,
    CLOSE_NOUN_RE,
    COME_OUT_RE,
    FILING_RE,
    GENERAL_RE,
    HOW_MANY_SHARES_RE,
    HOW_MUCH_MONEY_RE,
    INDEX_RE,
    LATELY_RE,
    MARKET_VALUE_PATTERN,
    NEWS_RE,
    NEWS_VOICE_RE,
    PERIOD_COMPARE_RE,
    PERIOD_MOVE_RE,
    PRICE_CLAIM_RE,
    PRICE_MOVE_NOUN_RE,
    PRICE_PREDICTION_RE,
    PRICE_RE,
    PRICE_VERB_DAY_RE,
    RECENCY_RE,
    RECENT_MOVE_RE,
    SENTIMENT_RE,
    SHARES_ACTION_RE,
    STOCK_NOUN_RE,
    STOCK_WORD_RE,
    SWINGS_RE,
    TIME_OF_DAY_RE,
    normalize_typing,
    question_topics,
    unstored_figures,
    year_start_comparison,
)
from .windows import parse_window


@dataclass(frozen=True)
class Intent:
    prices: bool = False
    headlines: bool = False
    sentiment: bool = False
    filings: bool = True
    fundamentals: frozenset[str] = frozenset()  # the financial figures asked for (pe, market_value, revenue, ...)
    unstored: tuple[str, ...] = ()  # ratios asked for that this app doesn't compute (dividend yield, price-to-book, ...)
    unstored_only: bool = False  # True when that is the whole question: nothing else here can be answered
    advice: bool = False  # the question asks for a buy, sell, or hold call

    @property
    def market(self) -> bool:
        return self.prices or self.headlines or self.sentiment or bool(self.fundamentals)


def detect_intent(question: str) -> Intent:
    """Which kinds of evidence the question needs. Plain keyword rules, so the choice is predictable and testable.
    With no market wording the copilot behaves exactly as it did before (filings only)."""
    question = normalize_typing(question)
    advice = asks_for_advice(question)
    unstored, question = unstored_figures(question)
    share_count = bool(HOW_MANY_SHARES_RE.search(question)) and not SHARES_ACTION_RE.search(question)
    question = HOW_MANY_SHARES_RE.sub(" ", question)  # "shares does" is not a price verb, so cut the phrase out first
    # "stock" plus a named period ("Apple stock or Microsoft stock, this month?") is a price question even without a verb
    price_text = re.sub(MARKET_VALUE_PATTERN, " ", question, flags=re.IGNORECASE)  # "How much is Apple worth?" is not "how much is" a price
    if not STOCK_WORD_RE.search(question):  # "How much did Apple earn / pay in dividends?" asks about money, not the stock price
        price_text = HOW_MUCH_MONEY_RE.sub(" ", price_text)
    topics, rest = question_topics(question)
    prices = (
        bool(PRICE_RE.search(price_text)) or bool(INDEX_RE.search(question)) or bool(BARE_STOCK_RE.search(question))
        or (bool(STOCK_NOUN_RE.search(question)) and parse_window(question).explicit)
        or (bool(PERIOD_MOVE_RE.search(question)) and parse_window(question).explicit)
        or year_start_comparison(question)
        or bool(CLOSE_NOUN_RE.search(question))
        or bool(CLOSE_EXTREME_RE.search(question))
        or bool(PRICE_VERB_DAY_RE.search(question))
        or bool(SWINGS_RE.search(question))
        or bool(PRICE_PREDICTION_RE.search(question))
        or (
            bool(PRICE_MOVE_NOUN_RE.search(question)) and bool(CAUSE_RE.search(question))
            and (parse_window(question).explicit or bool(STOCK_NOUN_RE.search(question)) or bool(RECENCY_RE.search(question)))
        )
        or (bool(PRICE_CLAIM_RE.search(question)) and (parse_window(question).explicit or bool(STOCK_NOUN_RE.search(question))))
        or (bool(PERIOD_COMPARE_RE.search(question)) and not topics and parse_window(question).explicit)  # not "revenue than a year ago"
        or (bool(RECENT_MOVE_RE.search(question)) and (bool(RECENCY_RE.search(question)) or parse_window(question).explicit))
    )
    sentiment = bool(SENTIMENT_RE.search(question))
    general = bool(GENERAL_RE.search(question)) and not STOCK_WORD_RE.search(question)  # "How's Nvidia doing?" wants both
    headlines = (
        bool(NEWS_RE.search(question)) or bool(NEWS_VOICE_RE.search(question)) or bool(COME_OUT_RE.search(question)) or sentiment or general
        or (bool(TIME_OF_DAY_RE.search(question)) and not prices and not topics)  # "Where did Nvidia trade this morning?" is a price question
        or (prices and bool(CAUSE_RE.search(question)))
        or (bool(LATELY_RE.search(question)) and not prices)  # "lately" is a news cue only when it is not already a price question
    )
    if share_count:
        topics = topics | {"shares"}
    market = prices or headlines or sentiment or bool(topics)
    # The words that sent the question to the figures ("revenue", "income") aren't also a reason to search the filings
    return Intent(
        prices, headlines, sentiment, filings=not market or bool(FILING_RE.search(rest)), fundamentals=topics,
        unstored=unstored, unstored_only=bool(unstored) and not market and not FILING_RE.search(rest), advice=advice,
    )
