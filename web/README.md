# Web app

The browser screens for stockMarket. React 19, TypeScript, built with Vite. Three screens so far:

- **Dashboard** (`/`): a watchlist, a combined news panel, and a box for asking the copilot questions (it answers from stored filings, prices, and headlines).
- **Stock detail** (`/stocks/AAPL`): an interactive price chart, key stats with a 52-week range bar, that company's news,
  its SEC filings, and the copilot limited to that company. Click a ticker on the dashboard to get there.
- **Copilot** (`/copilot`): a full-page chat with a saved history, a company filter, and Stop and retry.

## Run it

You need Node.js (LTS) and the Python API running. From the repo root:

```bash
.venv\Scripts\python -m api          # terminal 1: the API on http://127.0.0.1:8000
cd web
npm install                          # first time only
npm run dev                          # terminal 2: the app on http://localhost:5173
```

Open `http://localhost:5173`. In development, Vite forwards `/api` and `/health` to the Python API, so the browser
only talks to one address. The port must stay 5173 (or 3000): the API only accepts those origins.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with live reload |
| `npm test` | Runs all tests once (Vitest, Testing Library, jsdom) |
| `npm run typecheck` | TypeScript check with no output |
| `npm run build` | Type check, then a production build into `dist/` |
| `npm run gen:api` | Regenerates `src/api/schema.d.ts` from `openapi.json` |

## Types come from the API

The data types are generated from the API itself, not written by hand, so the screens can't quietly drift from the
backend. After changing any API endpoint or response shape:

```bash
.venv\Scripts\python -m api.export_openapi    # from the repo root: rewrites web/openapi.json
cd web && npm run gen:api                      # rewrites src/api/schema.d.ts
```

A Python test (`tests/test_openapi_contract.py`) fails if `openapi.json` is out of date.

## Layout

```
src/api/          client.ts (fetch + friendly errors), types.ts (names for generated types), schema.d.ts (generated)
src/hooks/        useApi: load data, cancel on leave, retry; useConversation: the copilot's saved history
                  useElementWidth: size an SVG to its container
src/lib/          format.ts: prices, percentages, dates, volumes, news mood, safe links
                  chart.ts: axis ticks, scales, and paths for the price chart (pure functions)
                  conversation.ts: the copilot history's shape, validation, and browser storage
src/components/   Watchlist, NewsPanel, CopilotBox, AnswerText, FreshnessBar, Sparkline, pills,
                  PriceHistory + PriceChart, KeyStats, FilingsList,
                  AnswerView (one copilot answer), Composer, ConversationView, CompanyFilter
src/pages/        Dashboard, StockPage, CopilotPage
src/test/         setup and a fake API for tests
```

## The price chart

`PriceChart` is hand-drawn SVG (no charting library). It draws at its container's real pixel width, so axis text stays
readable on a phone. A readout above the chart shows the selected day: hover or touch to pick one, or focus the
chart and use the arrow keys (Shift for 10 days, Home and End for the ends). The line is green if the range ended
at or above where it started, red if below. The math lives in `src/lib/chart.ts` so it can be tested directly.

## The copilot page

- **Follow-ups work, with limits.** Each new question is sent with the last three finished questions of the current
  topic (citation markers removed, answers trimmed). The server uses them only to rewrite a follow-up into a
  standalone question; the answer is written from the stored sources alone. The page shows "Understood as: ..." under a
  question that was rewritten, so a wrong reading is visible.
- **Topics:** "Start a new topic" keeps earlier questions on screen (with a divider) but stops them being sent. The
  topic is saved, so a reload doesn't quietly resume the old one. Only finished, real answers count as history, not
  refusals, errors, or stopped questions. A retry uses only what came before that question.
- **History is saved in this browser only** (`localStorage`, the newest 20). Unfinished questions aren't saved. Saved
  data is validated field by field on load, because anything with access to the browser can edit it; damaged
  entries are dropped. If the browser refuses to save (private window, full storage), the page says so.
- **One question at a time**, because the AI model answers one at a time. While one is running the button becomes
  Stop, and a stopped or failed question can be asked again in place.
- **Company filter:** pick up to five companies (the API's limit), or none for all. When no company is named or
  chosen, the answer carries a notice listing the companies it actually drew on.

## Things to keep true

- Show warnings instead of hiding problems: stale data, a refresh that had errors, the AI model being offline, and
  `unverified_numbers` and `cautions` in copilot answers.
- Never render API text as HTML. Answers go through `AnswerText`, which outputs plain text only.
- Links that come from outside data (headlines, filings) go through `safeHttpUrl`, which allows only `http(s)`.
- A change is never shown with color alone: arrows, signs, and words come with it.
