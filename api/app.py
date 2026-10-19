"""Read-only HTTP API over the stored market data and the AI tools.

Run:  python -m api          (serves http://127.0.0.1:8000, docs at /docs)

No login yet and it only listens on this computer. Don't expose it to a network as it is.
"""
import logging
from datetime import date
import re
from typing import Annotated, Literal, Optional

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from ai.copilot import Turn, answer_question
from ai.question_log import log_answer
from ai.embeddings import DEFAULT_MODEL, Embedder
from ai.llm import LLM
from ai.market import MarketEvidence
from ai.search import SearchResult, search_filings
from jobs.add_company import normalize_ticker
from jobs.refresh import AlreadyRunning
from jobs.remove_company import NotTracked, remove_company
from jobs.status import freshness, recent_runs

from . import adding, queries, schemas
from .adding import Launcher
from .deps import (
    cors_origins,
    get_chat_model,
    get_conn,
    get_embedder,
    get_instrument_source,
    get_job_launcher,
    get_sentiment_model,
)
from data.sources.base import PriceSource

log = logging.getLogger("api")
SYMBOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
Symbol = Annotated[str, Path(description="Ticker, e.g. AAPL", pattern=SYMBOL_RE.pattern)]
Conn = Annotated[psycopg.Connection, Depends(get_conn)]
SentimentModel = Annotated[str, Depends(get_sentiment_model)]
Source = Annotated[PriceSource, Depends(get_instrument_source)]
Launcher_ = Annotated[Launcher, Depends(get_job_launcher)]

app = FastAPI(
    title="stockMarket API",
    version="0.1.0",
    description=(
        "Read-only access to prices, news, sentiment, SEC filings, and the filing-grounded copilot. "
        "Summaries of public filings, prices, and headlines. Not financial advice."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _local_write_check(request: Request) -> None:
    """The write endpoints (add a company, remove a company). A web page open in the browser can send a request to
    127.0.0.1, so require the local web app's origin and a JSON body. CORS alone only stops the page reading the reply,
    not the request arriving."""
    if request.headers.get("origin") not in cors_origins():
        raise HTTPException(403, "Adding or removing a company is only allowed from the local web app.")
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(415, "Send the request as JSON.")


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


@app.get("/api/add-company/lookup", response_model=schemas.AddLookupOut, tags=["add company"])
def add_company_lookup(conn: Conn, source: Source, ticker: Annotated[str, Query(min_length=1, max_length=12)]):
    """Read-only: looks up the company name so the page can ask "Add X?" before anything is written."""
    try:
        symbol = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    tracked = symbol in queries.tracked_symbols(conn)
    try:
        instrument = source.get_instrument(symbol)
    except Exception as exc:  # the message is fixed text: the source's own error can be long or noisy
        log.warning("lookup of %s failed: %s", symbol, type(exc).__name__)
        raise HTTPException(502, f"Couldn't look up {symbol} right now. Yahoo Finance may be slow or rate-limiting; try again in a few minutes.") from exc
    if not instrument.name:
        raise HTTPException(404, f"No US-listed company found for {symbol}. Check the spelling.")
    return {"symbol": symbol, "name": instrument.name, "exchange": instrument.exchange, "tracked": tracked}


@app.post("/api/add-company/jobs", response_model=schemas.AddJobOut, status_code=202, tags=["add company"],
          dependencies=[Depends(_local_write_check)])
def start_add_company(body: schemas.AddJobIn, conn: Conn, launch: Launcher_):
    try:
        symbol = normalize_ticker(body.ticker)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not adding.lock_is_free(conn):
        raise HTTPException(409, adding.BUSY_MESSAGE)
    try:
        job_id = adding.start_add(conn, symbol, launch)
    except OSError as exc:
        raise HTTPException(500, "The add process could not be started. Check logs/add_company.log, then try again.") from exc
    return adding.job_out(conn, job_id)


@app.get("/api/removed-companies", response_model=list[schemas.RemovedCompany], tags=["remove company"])
def removed_companies(conn: Conn):
    """Read-only: companies that were removed (not tracked, data kept), so the dashboard can offer to switch one back on."""
    return queries.removed_companies(conn)


@app.post("/api/remove-company", response_model=schemas.RemoveOut, tags=["remove company"],
          dependencies=[Depends(_local_write_check)])
def remove_company_endpoint(body: schemas.RemoveIn, conn: Conn):
    """Stop tracking a company. Nothing is deleted: it is switched off, and adding it again brings it back with its history."""
    try:
        symbol = normalize_ticker(body.ticker)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        removal = remove_company(conn, symbol)
    except NotTracked as exc:
        raise HTTPException(404, str(exc)) from exc
    except AlreadyRunning as exc:
        raise HTTPException(409, adding.BUSY_MESSAGE) from exc
    label = f"{removal.symbol} ({removal.name})" if removal.name else removal.symbol
    return {
        "symbol": removal.symbol, "name": removal.name, "kept": removal.kept,
        "message": f"{label} is no longer tracked. Its stored data was kept; switch it back on from the \"Not tracked\" list on the dashboard to track it again.",
    }


@app.get("/api/add-company/jobs/{job_id}", response_model=schemas.AddJobOut, tags=["add company"])
def add_company_job(job_id: Annotated[int, Path(ge=1)], conn: Conn):
    out = adding.job_out(conn, job_id)
    if out is None:
        raise HTTPException(404, "No such add job")
    return out


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


@app.get("/api/stocks/{symbol}/fundamentals", response_model=schemas.FundamentalsOut, tags=["stocks"])
def stock_fundamentals(symbol: Symbol, conn: Conn):
    """Revenue, profit, margins, market value, and P/E from the SEC filings, each with how it was built and any cautions.
    `available` is false for a company with no figures (not downloaded yet, or a foreign filer)."""
    symbol = _require_company(conn, symbol)
    return queries.fundamentals(conn, symbol)


@app.get("/api/stocks/{symbol}/news", response_model=list[schemas.NewsItemOut], tags=["stocks"])
def stock_news(
    symbol: Symbol, conn: Conn, model: SentimentModel,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    include_irrelevant: bool = False,
):
    symbol = _require_company(conn, symbol)
    return queries.news_items(conn, symbol, model, days, limit, include_irrelevant)


@app.get("/api/news", response_model=list[schemas.NewsFeedItem], tags=["news"])
def news_feed(
    conn: Conn, model: SentimentModel,
    days: Annotated[int, Query(ge=1, le=90)] = 3,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    symbol: Annotated[Optional[list[str]], Query(description="Repeat to limit to several tickers")] = None,
    sentiment: Annotated[
        Optional[list[Literal["positive", "negative", "neutral"]]],
        Query(description="Only these labels, e.g. positive and negative to skip routine items"),
    ] = None,
    include_irrelevant: bool = False,
):
    """Latest headlines across every tracked company (for the dashboard's news panel)."""
    if symbol and not all(SYMBOL_RE.match(s) for s in symbol):
        raise HTTPException(422, "symbol must be a ticker like AAPL")
    symbols = [s.upper() for s in symbol] if symbol else None
    return queries.news_feed(conn, model, days, limit, include_irrelevant, symbols, sentiment)


@app.get("/api/changes", response_model=schemas.ChangesOut, tags=["changes"])
def changes(
    conn: Conn, model: SentimentModel,
    days: Annotated[int, Query(ge=1, le=queries.CHANGES_MAX_DAYS, description="Trading days to look back")] = 1,
    since: Annotated[Optional[date], Query(description="Instead of `days`: the stored trading days after this date (the newest 30 at most). For \"since I last looked\"")] = None,
):
    """New filings, unusually big daily moves, and notable headlines over the last few trading days, worked out
    from stored data. A big move is measured against the company's own usual daily move; headlines beside a move are
    timing only and never a cause."""
    return queries.changes(conn, model, days, None, since)


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
    """Answer a question from stored filings, prices, and headlines, with numbered citations. Can take several seconds."""
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
        history = [Turn(t.question, t.answer, tuple(t.companies)) for t in req.history]
        ans = answer_question(conn, embedder, llm, req.question, req.symbols, req.limit, history=history)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    response = {
        "question": ans.question,
        "answer": ans.text,
        "refused": ans.refused,
        "grounded": ans.grounded,
        "companies": ans.symbols,
        "evidence_kinds": sorted({kind_of(r) for r in ans.retrieved}, key=KIND_ORDER.index),
        "model_route": ans.model_route,
        "unverified_numbers": ans.unverified_numbers,
        "cautions": ans.cautions,
        "searches": ans.queries,
        "interpreted_question": ans.interpreted_question,
        "disclaimer": ans.disclaimer,
        "sources": [source_out(n, r) for n, r in ans.sources],
    }
    log_answer(response, len(history))  # the local question log (never raises; off with COPILOT_LOG=off)
    return response


KIND_ORDER = ["price", "fundamentals", "sentiment", "headline", "filing"]


def kind_of(item: SearchResult | MarketEvidence) -> str:
    return item.kind if isinstance(item, MarketEvidence) else "filing"


def source_out(number: int, item: SearchResult | MarketEvidence) -> dict:
    """One cited source in the API's shape. Filing passages keep their original fields; the rest fill only what applies."""
    if isinstance(item, MarketEvidence):
        return {"number": number, "kind": item.kind, "symbol": item.symbol, "title": item.header, "as_of": item.as_of,
                "url": item.url, "excerpt": item.text}
    return {"number": number, "kind": "filing", "symbol": item.symbol, "title": f"{item.symbol} {item.form} filed {item.filed_at}",
            "as_of": item.filed_at, "form": item.form, "filed_at": item.filed_at, "period_of_report": item.period_of_report,
            "section": item.section, "url": item.url, "score": round(item.score, 4), "excerpt": item.text}
