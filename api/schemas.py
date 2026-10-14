"""Response and request shapes. These are the API's contract with the screens."""
import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Health(BaseModel):
    status: str
    database: bool
    ai_model: str
    ai_model_available: bool


class SentimentSummary(BaseModel):
    days: int
    positive: int
    neutral: int
    negative: int
    irrelevant: int
    score: Optional[float] = Field(None, description="-1 (all bad news) to +1 (all good); null if no scored headlines. Each story is counted once, and stock-quote and comparison pages are left out of every count")


class StockSummary(BaseModel):
    symbol: str
    name: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    last_price: Optional[float]
    as_of: Optional[date] = Field(None, description="Date of the latest price bar. During market hours it can be a partial day")
    change: Optional[float]
    change_pct: Optional[float]
    sentiment: SentimentSummary


class StockDetail(StockSummary):
    exchange: Optional[str]
    currency: str
    high_52w: Optional[float]
    low_52w: Optional[float]
    volume: Optional[int]


class PricePoint(BaseModel):
    date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[int]


class PriceSeries(BaseModel):
    symbol: str
    range: str
    points: list[PricePoint]


class NewsItemOut(BaseModel):
    id: str
    title: str
    publisher: Optional[str]
    url: str
    published_at: datetime
    sentiment: Optional[str] = Field(None, description="positive, negative, neutral, irrelevant, or null if not scored yet")


class NewsFeedItem(NewsItemOut):
    symbol: str = Field(description="The company this headline was labeled for. A headline about two companies appears once for each")


class FilingOut(BaseModel):
    accession_number: str
    form: str
    filed_at: date
    period_of_report: Optional[date]
    url: str
    searchable: bool = Field(description="True once the filing has been embedded for search")


class SearchHit(BaseModel):
    symbol: str
    form: str
    filed_at: date
    period_of_report: Optional[date]
    section: Optional[str]
    url: str
    score: float = Field(description="Cosine similarity, higher is closer")
    text: str


TICKER_PATTERN = r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$"


class HistoryTurn(BaseModel):
    """An earlier question and its answer. Only used to understand a follow-up; never treated as evidence."""

    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(max_length=2000)
    companies: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("companies")
    @classmethod
    def _tickers_only(cls, value: list[str]) -> list[str]:
        if not all(re.match(TICKER_PATTERN, c) for c in value):
            raise ValueError("companies must be tickers like AAPL")
        return [c.upper() for c in value]


class CopilotRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    symbols: Optional[list[str]] = Field(None, max_length=5, description="Tickers to restrict to. Default: detected from the question")
    limit: int = Field(6, ge=1, le=10, description="Passages to give the model")
    history: list[HistoryTurn] = Field(
        default_factory=list,
        max_length=4,
        description="Earlier turns of the conversation, oldest first, so a follow-up like 'and its risks?' can be understood. The newest three are used",
    )


SourceKind = Literal["filing", "price", "headline", "sentiment", "fundamentals"]


class Source(BaseModel):
    number: int = Field(description="Matches the [n] citation in the answer")
    kind: SourceKind = Field(description="filing = a passage from an SEC filing; price = figures worked out from stored daily closes; headline = a news title; sentiment = a summary of headline labels; fundamentals = revenue, profit, margins, market value and P/E worked out from SEC filings and the latest price")
    symbol: str
    title: str = Field(description="One line saying what this source is, e.g. 'NVDA 10-K filed 2026-02-25' or 'NVDA price data (stored daily closes), as of 2026-10-12'")
    as_of: date = Field(description="The filing date for a filing, otherwise the date of the data")
    form: Optional[str] = Field(None, description="Filings only: 10-K or 10-Q")
    filed_at: Optional[date] = Field(None, description="Filings only")
    period_of_report: Optional[date] = Field(None, description="Filings only")
    section: Optional[str] = Field(None, description="Filings only")
    url: Optional[str] = Field(None, description="Where to read it: the filing or the headline's article. Null for price and sentiment sources")
    score: Optional[float] = Field(None, description="Filings only: how closely the passage matched the question")
    excerpt: str


class CopilotResponse(BaseModel):
    question: str
    answer: str
    refused: bool = Field(description="True when nothing relevant was found or no company was named, so the model wasn't asked")
    grounded: bool = Field(description="True when the answer cites at least one real source")
    companies: list[str]
    evidence_kinds: list[SourceKind] = Field(description="The kinds of source the model was shown (not only the ones it cited), so the screen can say what was looked at")
    unverified_numbers: list[str] = Field(description="Figures in the answer that are not in the cited sources, a minus sign the sources don't have, or a price move described in the wrong direction. Show a warning if non-empty")
    cautions: list[str] = Field(description="Plain-language warnings to show with the answer, for example when it may suggest a reason for a price move that the data cannot show, or when a financial figure it quotes can mislead (a P/E flattered by investment gains)")
    sources: list[Source]
    searches: list[str]
    interpreted_question: Optional[str] = Field(
        None, description="How a follow-up was understood (the standalone question that was searched). Null if the question was used as written"
    )
    disclaimer: str


class RunOut(BaseModel):
    id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    problems: int


class FreshnessOut(BaseModel):
    symbol: str
    last_price_date: Optional[date]
    newest_headline_at: Optional[datetime]
    newest_filing_date: Optional[date]
    filings_indexed: int
    filings_total: int
    unscored_headlines: int


class StatusOut(BaseModel):
    runs: list[RunOut]
    companies: list[FreshnessOut]


class FundamentalFigure(BaseModel):
    value: float
    how: str = Field(description="How the figure was built, in plain words, with the dates")
    period_end: date = Field(description="Where the latest filed period ends")
    sources: list[str] = Field(description="The SEC filings it came from, e.g. '10-Q filed 2026-07-31 (9 months to 2026-06-27)'")
    growth: Optional[float] = Field(None, description="The latest period vs the same period a year earlier (0.12 = up 12%); null if it can't be told")
    growth_label: Optional[str] = Field(None, description="Which two periods growth compares")


class SharesOut(BaseModel):
    value: float
    source: str = Field(description="Where the count was read, in words")
    as_of: date


class FundamentalsOut(BaseModel):
    """Figures computed from the SEC filings. Every ratio is worked out in Python; cautions explain where a correct number could mislead."""

    symbol: str
    available: bool
    unavailable_reason: Optional[str] = Field(None, description="Why there are no figures (not downloaded yet, or a foreign filer), when available is false")
    period_end: Optional[date] = Field(None, description="End of the latest reported period behind the figures")
    revenue: Optional[FundamentalFigure] = Field(None, description="Dollars over the last twelve months")
    net_income: Optional[FundamentalFigure] = Field(None, description="Dollars over the last twelve months, the part belonging to shareholders")
    diluted_eps: Optional[FundamentalFigure] = Field(None, description="Dollars per share over the last twelve months")
    operating_income: Optional[FundamentalFigure] = Field(None, description="Dollars over the last twelve months")
    gross_margin: Optional[float] = Field(None, description="A fraction: 0.5 = 50%. Null if the company reports no gross profit")
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    shares: Optional[SharesOut] = None
    price: Optional[float] = Field(None, description="The latest stored close, used for market value and P/E")
    price_date: Optional[date] = None
    market_value: Optional[float] = Field(None, description="Shares times the latest close, in dollars")
    pe: Optional[float] = Field(None, description="Latest close divided by diluted EPS for the last twelve months; null when earnings are zero or negative")
    pe_note: Optional[str] = Field(None, description="Why P/E is missing, when it is")
    cautions: list[str]
