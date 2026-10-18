import { vi } from "vitest";
import type {
  ChangesOut,
  CopilotResponse,
  Fundamentals,
  Health,
  NewsFeedItem,
  PriceSeries,
  StatusOut,
  StockSummary,
} from "../api/types";

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Handler = unknown | ((url: URL, init?: RequestInit) => unknown | Promise<unknown>);

/**
 * Replaces fetch with fakes keyed by "METHOD /path". A handler may return plain data (sent as 200 JSON),
 * a Response (for errors), or throw. Unmocked routes answer 404 so a forgotten mock is obvious.
 * Returns the fetch mock so tests can inspect the calls made.
 */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    if (!(key in routes)) return json({ detail: `no mock for ${key}` }, 404);
    const handler = routes[key];
    const value = typeof handler === "function" ? await handler(url, init) : handler;
    return value instanceof Response ? value : json(value);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const sentiment = (over: Partial<StockSummary["sentiment"]> = {}) => ({
  days: 7, positive: 8, neutral: 90, negative: 9, irrelevant: 3, score: -0.0093, ...over,
});

export const stocks: StockSummary[] = [
  { symbol: "AAPL", name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics",
    last_price: 340.97, as_of: "2026-10-12", change: 4.34, change_pct: 1.29, sentiment: sentiment() },
  { symbol: "NVDA", name: "NVIDIA Corporation", sector: "Technology", industry: "Semiconductors",
    last_price: 226.32, as_of: "2026-10-12", change: -2.96, change_pct: -1.29, sentiment: sentiment({ positive: 30, negative: 5, score: 0.3 }) },
  { symbol: "TSLA", name: "Tesla, Inc.", sector: "Consumer Cyclical", industry: "Auto",
    last_price: 378.03, as_of: "2026-10-12", change: null, change_pct: null, sentiment: sentiment({ positive: 0, neutral: 0, negative: 0, irrelevant: 0, score: null }) },
];

export const prices = (symbol: string, closes: number[] = [100, 102, 101, 105]): PriceSeries => ({
  symbol,
  range: "1M",
  points: closes.map((close, i) => ({ date: `2026-10-0${i + 1}`, open: close, high: close, low: close, close, volume: 1 })),
});

export const newsItems: NewsFeedItem[] = [
  { id: "n1", symbol: "NVDA", title: "Nvidia wins a big contract", publisher: "Yahoo Finance", url: "https://example.com/a",
    published_at: new Date(Date.now() - 2 * 3600_000).toISOString(), sentiment: "positive" },
  { id: "n2", symbol: "AAPL", title: "Apple faces a probe", publisher: null, url: "javascript:alert(1)",
    published_at: new Date(Date.now() - 26 * 3600_000).toISOString(), sentiment: "negative" },
];

export const okStatus: StatusOut = {
  runs: [{ id: 1, started_at: new Date().toISOString(), finished_at: new Date().toISOString(), status: "success", problems: 0 }],
  companies: [{ symbol: "AAPL", last_price_date: new Date().toISOString().slice(0, 10), newest_headline_at: null,
    newest_filing_date: null, filings_indexed: 4, filings_total: 4, unscored_headlines: 0 }],
};

export const okHealth: Health = { status: "ok", database: true, ai_model: "ollama:qwen3:latest", ai_model_available: true };

export const copilotAnswer = (over: Partial<CopilotResponse> = {}): CopilotResponse => ({
  question: "How many employees does NVIDIA have?",
  answer: "As of fiscal 2026 NVIDIA had approximately 42,000 employees [1].",
  refused: false,
  grounded: true,
  companies: ["NVDA"],
  evidence_kinds: ["filing"],
  model_route: [],
  unverified_numbers: [],
  cautions: [],
  searches: ["How many employees does NVIDIA have?"],
  disclaimer: "This summarizes stored public filings, prices, and news headlines. It is not financial advice.",
  sources: [{ number: 1, kind: "filing", symbol: "NVDA", title: "NVDA 10-K filed 2026-02-25", as_of: "2026-02-25", form: "10-K",
    filed_at: "2026-02-25", period_of_report: "2026-01-25", section: "Part I, Item 1", url: "https://www.sec.gov/x", score: 0.76,
    excerpt: "approximately 42,000 employees in 38 countries" }],
  ...over,
});

export const defaultRoutes = (): Record<string, Handler> => ({
  "GET /api/stocks": stocks,
  "GET /api/stocks/AAPL/prices": prices("AAPL"),
  "GET /api/stocks/NVDA/prices": prices("NVDA", [110, 100, 90]),
  "GET /api/stocks/TSLA/prices": prices("TSLA", []),
  "GET /api/news": newsItems,
  "GET /api/changes": changesData,
  "GET /api/status": okStatus,
  "GET /health": okHealth,
  "POST /api/copilot": copilotAnswer(),
});

export const stockDetail = {
  ...stocks[0],
  exchange: "NMS",
  currency: "USD",
  high_52w: 360,
  low_52w: 200,
  volume: 53_200_000,
};

export const filingRows = [
  { accession_number: "0-1", form: "10-Q", filed_at: "2026-07-31", period_of_report: "2026-06-27", url: "https://www.sec.gov/q", searchable: true },
  { accession_number: "0-2", form: "10-K", filed_at: "2025-10-31", period_of_report: "2025-09-27", url: "javascript:alert(1)", searchable: false },
];

/** 400 days of closes rising by 1 a day, ending 2026-10-09. */
export const longPrices = (symbol: string, range = "1Y", n = 120) => ({
  symbol,
  range,
  points: Array.from({ length: n }, (_, k) => {
    const d = new Date(Date.UTC(2026, 9, 9) - (n - 1 - k) * 86_400_000).toISOString().slice(0, 10);
    const close = 200 + k;
    return { date: d, open: close, high: close + 1, low: close - 1, close, volume: 1_000_000 + k };
  }),
});

export const detailRoutes = (): Record<string, Handler> => ({
  ...defaultRoutes(),
  "GET /api/stocks/AAPL": stockDetail,
  "GET /api/stocks/AAPL/prices": () => longPrices("AAPL"),
  "GET /api/stocks/AAPL/filings": filingRows,
  ...fundamentalsRoutes(),
  "GET /api/news": newsItems.filter((n) => n.symbol === "AAPL"),
});

export const fundamentalsData: Fundamentals = {
  symbol: "AAPL",
  available: true,
  unavailable_reason: null,
  period_end: "2026-06-27",
  revenue: {
    value: 466_800_000_000, period_end: "2026-06-27", growth: 0.162,
    growth_label: "the 9 months to 2026-06-27 vs the same 9 months a year earlier",
    how: "the last full year (ended 2025-09-27) + the 9 months to 2026-06-27 - the same 9 months a year earlier",
    sources: ["10-K filed 2025-10-31 (the year ended 2025-09-27)", "10-Q filed 2026-07-31 (9 months to 2026-06-27)",
      "10-Q filed 2025-08-01 (the same 9 months a year earlier)"],
  },
  net_income: { value: 128_900_000_000, period_end: "2026-06-27", growth: 0.2, growth_label: "9 months vs the same 9 months a year earlier",
    how: "the last full year + the 9 months - the same 9 months a year earlier", sources: ["10-Q filed 2026-07-31 (9 months to 2026-06-27)"] },
  diluted_eps: { value: 8.72, period_end: "2026-06-27", growth: null, growth_label: null,
    how: "the last full year + the 9 months - the same 9 months a year earlier", sources: [] },
  operating_income: { value: 154_900_000_000, period_end: "2026-06-27", growth: null, growth_label: null, how: "operating income recipe", sources: [] },
  gross_margin: 0.487, operating_margin: 0.332, net_margin: 0.276,
  shares: { value: 14_590_000_000, source: "the cover page of the 10-Q filed 2026-07-31", as_of: "2026-07-17" },
  price: 340.97, price_date: "2026-10-12", market_value: 4_976_000_000_000, pe: 39.1, pe_note: null,
  cautions: [],
};

export const fundamentalsRoutes = (over: Partial<Fundamentals> = {}): Record<string, Handler> => ({
  "GET /api/stocks/AAPL/fundamentals": { ...fundamentalsData, ...over },
});

export const changesData: ChangesOut = {
  days: 1,
  since: null,
  as_of: "2026-10-14",
  window_start: "2026-10-14",
  stale: [],
  filings: [],
  newest_filing: { symbol: "NVDA", form: "10-Q", filed_at: "2026-08-26", period_of_report: "2026-07-26", url: "https://www.sec.gov/n", accession_number: "0-9" },
  moves: [
    {
      symbol: "AMD", name: "Advanced Micro Devices", date: "2026-10-14", previous_date: "2026-10-13", close: 480.5, previous_close: 509.7,
      change_pct: -5.73, typical_pct: 2.37, threshold_pct: 4.74, market_wide: true,
      headlines: [
        { id: "h1", title: "AMD slides with chip stocks", publisher: "Wire", url: "https://example.com/amd", sentiment: "negative",
          published_at: new Date(Date.now() - 3 * 3600_000).toISOString() },
        { id: "h2", title: "Unsafe link headline", publisher: null, url: "javascript:alert(1)", sentiment: null,
          published_at: new Date(Date.now() - 4 * 3600_000).toISOString() },
      ],
    },
    {
      symbol: "TSLA", name: "Tesla, Inc.", date: "2026-10-14", previous_date: "2026-10-13", close: 400, previous_close: 380,
      change_pct: 5.26, typical_pct: null, threshold_pct: 3, market_wide: false, headlines: [],
    },
  ],
  market_days: [{ date: "2026-10-14", direction: "down", moved_that_way: 6, companies: 7 }],
  headlines: [
    {
      symbol: "NVDA", positive: 5, negative: 2,
      items: [{ id: "n1", title: "Nvidia wins a contract", publisher: "Wire", url: "https://example.com/n", sentiment: "positive",
        published_at: new Date(Date.now() - 2 * 3600_000).toISOString() }],
    },
  ],
  mood_shifts: [{ symbol: "NVDA", score_now: 0.6, stories_now: 20, score_before: -0.3333, stories_before: 30 }],
  rules: { min_move_pct: 3, typical_multiple: 2, baseline_days: 60, headlines_per_company: 3, mood_days: 7 },
};
