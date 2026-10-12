"""Response and request shapes. These are the API's contract with the screens."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    score: Optional[float] = Field(None, description="-1 (all bad news) to +1 (all good); null if no scored headlines")


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


class CopilotRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    symbols: Optional[list[str]] = Field(None, max_length=5, description="Tickers to restrict to. Default: detected from the question")
    limit: int = Field(6, ge=1, le=10, description="Passages to give the model")


class Source(BaseModel):
    number: int = Field(description="Matches the [n] citation in the answer")
    symbol: str
    form: str
    filed_at: date
    period_of_report: Optional[date]
    section: Optional[str]
    url: str
    score: float
    excerpt: str


class CopilotResponse(BaseModel):
    question: str
    answer: str
    refused: bool = Field(description="True when nothing relevant was found, so the model wasn't asked")
    grounded: bool = Field(description="True when the answer cites at least one real passage")
    companies: list[str]
    unverified_numbers: list[str] = Field(description="Figures in the answer that are not in the cited passages. Show a warning if non-empty")
    sources: list[Source]
    searches: list[str]
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
