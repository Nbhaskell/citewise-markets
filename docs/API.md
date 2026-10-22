# API

The FastAPI backend that the web app uses. Start it with the command below; it also serves interactive documentation. Design notes are in [ARCHITECTURE.md](ARCHITECTURE.md#api-api).

## Run it

```bash
.venv\Scripts\python -m api
```

Serves `http://127.0.0.1:8000`. Open `http://127.0.0.1:8000/docs` for interactive documentation where you can try
every endpoint. The database must be running, and Ollama for the copilot.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /health` | Database and AI model status |
| `GET /api/status` | Nightly job history and how fresh each company's data is |
| `GET /api/stocks` | Every tracked company: latest price, daily change, news sentiment (the dashboard) |
| `GET /api/news?days=3&limit=30&sentiment=positive&sentiment=negative` | Latest headlines across all companies (filters: `symbol`, `sentiment`, `include_irrelevant`) |
| `GET /api/changes?days=1` (or `?since=2026-10-13`) | What changed over the last 1 to 30 trading days, or the stored trading days after a date: filings filed in the window, big moves (each with its usual-day size and that day's headlines), market-wide days, notable headlines, and week-over-week news-mood shifts. All worked out in Python from stored data |
| `GET /api/stocks/{symbol}` | One company, plus 52-week range and volume |
| `GET /api/stocks/{symbol}/prices?range=1M\|3M\|6M\|1Y\|5Y\|MAX` | Daily price bars for a chart |
| `GET /api/stocks/{symbol}/news?days=7&limit=30` | Headlines with sentiment labels (add `include_irrelevant=true` to see all) |
| `GET /api/stocks/{symbol}/fundamentals` | Revenue, profit, EPS, margins, market value, and P/E from the SEC filings, each with how it was built, its source filings, and cautions. `available` is false for a company with no figures |
| `GET /api/stocks/{symbol}/filings` | Stored SEC filings and whether each is searchable |
| `GET /api/filings/search?q=...&symbol=AAPL&form=10-K&latest=true` | Matching filing passages with source links |
| `POST /api/copilot` with `{"question": "...", "symbols": ["NVDA"], "history": [...]}` | A cited answer from filings, prices, financial figures, and headlines. Each source has a `kind` (`filing`, `price`, `fundamentals`, `headline`, or `sentiment`). `history` (optional, up to 4 earlier question and answer pairs) only helps understand a follow-up; the reply's `interpreted_question` says how it was read |

The copilot can take several seconds, so show a loading state. Check `unverified_numbers` and `cautions` in its reply
and show them to the user if they aren't empty.

**It is read-only and has no login.** It only listens on this computer (`127.0.0.1`) and only allows requests from
the local web app's address (`localhost:5173` or `:3000`). Don't expose it to a network until accounts exist.

