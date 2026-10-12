# Web app

The browser screens for stockMarket. React 19, TypeScript, built with Vite. Right now it has the dashboard:
a watchlist, a combined news panel, and a box for asking the filing-grounded copilot questions.

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
src/hooks/        useApi: load data, cancel on leave, retry
src/lib/          format.ts: prices, percentages, relative times, news mood, safe links
src/components/   Watchlist, NewsPanel, CopilotBox, AnswerText, FreshnessBar, Sparkline, pills
src/pages/        Dashboard
src/test/         setup and a fake API for tests
```

## Things to keep true

- Show warnings instead of hiding problems: stale data, a refresh that had errors, the AI model being offline, and
  `unverified_numbers` in copilot answers.
- Never render API text as HTML. Answers go through `AnswerText`, which outputs plain text only.
- Links that come from outside data (news, filings) go through `safeHttpUrl`, which allows only `http(s)`.
- A change is never shown with color alone: arrows, signs, and words come with it.
