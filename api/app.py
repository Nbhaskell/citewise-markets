"""Read-only HTTP API over the stored market data and the AI tools.

Run:  python -m api          (serves http://127.0.0.1:8000, docs at /docs)

No login yet and it only listens on this computer. Don't expose it to a network as it is.
"""
import re
from typing import Annotated, Literal, Optional

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from ai.copilot import NO_EVIDENCE, answer_question
from ai.embeddings import DEFAULT_MODEL, Embedder
from ai.llm import LLM
from ai.search import search_filings
from jobs.status import freshness, recent_runs

from . import queries, schemas
from .deps import cors_origins, get_chat_model, get_conn, get_embedder, get_sentiment_model

SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
Symbol = Annotated[str, Path(description="Ticker, e.g. AAPL", pattern=SYMBOL_RE.pattern)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]
SentimentModel = Annotated[str, Depends(get_sentiment_model)]

app = FastAPI(
    title="stockMarket API",
    version="0.1.0",
    description=(
        "Read-only access to prices, news, sentiment, SEC filings, and the filing-grounded copilot. "
        "Summaries of public filings, not financial advice."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _require_company(conn: psycopg.Connection, symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in queries.tracked_symbols(conn):
        raise HTTPException(404, f"{symbol} is not a tracked company")
    return symbol


@app.get("/health", response_model=schemas.Health, tags=["system"])
def health(conn: Conn, llm: Annotated[LLM, Depends(get_chat_model)]):
    conn.execute("SELECT 1")
    check = getattr(llm, "available", None)
    available = bool(check()) if callable(check) else True
    return {"status": "ok", "database": True, "ai_model": llm.name, "ai_model_available": available}


@app.get("/api/status", response_model=schemas.StatusOut, tags=["system"])
def status(conn: Conn, model: SentimentModel):
    """Nightly refresh history and how fresh each company's data is."""
    return {"runs": recent_runs(conn), "companies": freshness(conn, DEFAULT_MODEL, model)}


@app.get("/api/stocks", response_model=list[schemas.StockSummary], tags=["stocks"])
def list_stocks(conn: Conn, model: SentimentModel, days: Annotated[int, Query(ge=1, le=90)] = 7):
    """Every tracked company with its latest price, daily change, and news sentiment (for the dashboard)."""
    sentiment = queries.sentiment_by_symbol(conn, model, days)
    return [
        {**row, "sentiment": sentiment.get(row["symbol"]) or queries.sentiment_dict(row["symbol"], {}, days)}
        for row in queries.stock_rows(conn)
    ]


@app.get("/api/stocks/{symbol}", response_model=schemas.StockDetail, tags=["stocks"])
def stock_detail(symbol: Symbol, conn: Conn, model: SentimentModel, days: Annotated[int, Query(ge=1, le=90)] = 7):
    symbol = _require_company(conn, symbol)
    row = queries.stock_rows(conn, symbol)[0]
    high, low = queries.year_range(conn, symbol)
    sentiment = queries.sentiment_by_symbol(conn, model, days, symbol).get(symbol) or queries.sentiment_dict(symbol, {}, days)
    return {**row, "high_52w": high, "low_52w": low, "sentiment": sentiment}


@app.get("/api/stocks/{symbol}/prices", response_model=schemas.PriceSeries, tags=["stocks"])
def stock_prices(
    symbol: Symbol, conn: Conn,
    range: Annotated[Literal["1M", "3M", "6M", "1Y", "5Y", "MAX"], Query(description="Window ending at the latest stored price")] = "1Y",
):
    symbol = _require_company(conn, symbol)
    return {"symbol": symbol, "range": range, "points": queries.price_points(conn, symbol, range)}


@app.get("/api/stocks/{symbol}/news", response_model=list[schemas.NewsItemOut], tags=["stocks"])
def stock_news(
    symbol: Symbol, conn: Conn, model: SentimentModel,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    include_irrelevant: bool = False,
):
    symbol = _require_company(conn, symbol)
    return queries.news_items(conn, symbol, model, days, limit, include_irrelevant)


@app.get("/api/stocks/{symbol}/filings", response_model=list[schemas.FilingOut], tags=["filings"])
def stock_filings(symbol: Symbol, conn: Conn):
    symbol = _require_company(conn, symbol)
    return queries.filing_rows(conn, symbol)


@app.get("/api/filings/search", response_model=list[schemas.SearchHit], tags=["filings"])
def search(
    conn: Conn, embedder: Annotated[Embedder, Depends(get_embedder)],
    q: Annotated[str, Query(min_length=2, max_length=300, description="What to look for, in plain English")],
    symbol: Annotated[Optional[list[str]], Query(description="Repeat to search several tickers")] = None,
    form: Annotated[Optional[list[Literal["10-K", "10-Q", "8-K"]]], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    latest: Annotated[bool, Query(description="Only the newest filing of each form")] = False,
):
    """Semantic search over filing passages."""
    if symbol and not all(SYMBOL_RE.match(s) for s in symbol):
        raise HTTPException(422, "symbol must be a ticker like AAPL")
    hits = search_filings(conn, embedder, q, symbol, form, limit, latest)
    return [
        {"symbol": h.symbol, "form": h.form, "filed_at": h.filed_at, "period_of_report": h.period_of_report,
         "section": h.section, "url": h.url, "score": round(h.score, 4), "text": h.text}
        for h in hits
    ]


@app.post("/api/copilot", response_model=schemas.CopilotResponse, tags=["copilot"])
def copilot(
    req: schemas.CopilotRequest, conn: Conn,
    embedder: Annotated[Embedder, Depends(get_embedder)], llm: Annotated[LLM, Depends(get_chat_model)],
):
    """Answer a question from the stored filings, with numbered citations. Can take several seconds."""
    if req.symbols:
        if not all(SYMBOL_RE.match(s) for s in req.symbols):
            raise HTTPException(422, "symbols must be tickers like AAPL")
        missing = sorted({s.upper() for s in req.symbols} - queries.tracked_symbols(conn))
        if missing:
            raise HTTPException(404, f"Not a tracked company: {', '.join(missing)}")
    check = getattr(llm, "available", None)
    if callable(check) and not check():
        raise HTTPException(503, "The AI model isn't running. Start Ollama and try again.")
    try:
        ans = answer_question(conn, embedder, llm, req.question, req.symbols, req.limit)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {
        "question": ans.question,
        "answer": ans.text,
        "refused": ans.text == NO_EVIDENCE,
        "grounded": ans.grounded,
        "companies": ans.symbols,
        "unverified_numbers": ans.unverified_numbers,
        "searches": ans.queries,
        "disclaimer": ans.disclaimer,
        "sources": [
            {"number": n, "symbol": r.symbol, "form": r.form, "filed_at": r.filed_at,
             "period_of_report": r.period_of_report, "section": r.section, "url": r.url,
             "score": round(r.score, 4), "excerpt": r.text}
            for n, r in ans.sources
        ],
    }
