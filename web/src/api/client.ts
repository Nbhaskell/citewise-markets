import type {
  AddJobOut,
  AddLookupOut,
  ChangesOut,
  CopilotRequest,
  CopilotResponse,
  FilingOut,
  Fundamentals,
  Health,
  NewsFeedItem,
  NewsLabel,
  PriceRange,
  PriceSeries,
  RemoveOut,
  RemovedCompany,
  StatusOut,
  StockDetail,
  StockSummary,
} from "./types";

// Empty means "same origin": in development Vite proxies /api to the Python server.
const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

const UNREACHABLE = "Can't reach the API. Is it running? Start it with: python -m api";

/** The API's own message, if it sent one. FastAPI uses a string for errors we raise and a list for validation. */
async function detailOf(res: Response): Promise<string | undefined> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // not JSON; fall through
  }
  return undefined;
}

function fallbackMessage(status: number): string {
  // A 502/504 with no message comes from the dev-server proxy when the API isn't running at all.
  if (status === 502 || status === 504) return UNREACHABLE;
  return status === 422 ? "That request wasn't valid." : `The API returned an error (${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!res.ok) throw new ApiError((await detailOf(res)) ?? fallbackMessage(res.status), res.status);
  return (await res.json()) as T;
}

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }),
  status: (signal?: AbortSignal) => request<StatusOut>("/api/status", { signal }),
  stocks: (signal?: AbortSignal) => request<StockSummary[]>("/api/stocks", { signal }),
  stock: (symbol: string, signal?: AbortSignal) =>
    request<StockDetail>(`/api/stocks/${encodeURIComponent(symbol)}`, { signal }),
  fundamentals: (symbol: string, signal?: AbortSignal) =>
    request<Fundamentals>(`/api/stocks/${encodeURIComponent(symbol)}/fundamentals`, { signal }),
  filings: (symbol: string, signal?: AbortSignal) =>
    request<FilingOut[]>(`/api/stocks/${encodeURIComponent(symbol)}/filings`, { signal }),
  prices: (symbol: string, range: PriceRange, signal?: AbortSignal) =>
    request<PriceSeries>(`/api/stocks/${encodeURIComponent(symbol)}/prices?range=${range}`, { signal }),
  news: (opts: { days?: number; limit?: number; sentiment?: NewsLabel[]; symbol?: string }, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (opts.days) params.set("days", String(opts.days));
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.symbol) params.set("symbol", opts.symbol);
    opts.sentiment?.forEach((label) => params.append("sentiment", label));
    return request<NewsFeedItem[]>(`/api/news?${params}`, { signal });
  },
  changes: (window: { days: number } | { since: string }, signal?: AbortSignal) =>
    request<ChangesOut>(
      `/api/changes?${"since" in window ? `since=${encodeURIComponent(window.since)}` : `days=${window.days}`}`,
      { signal },
    ),
  addLookup: (ticker: string, signal?: AbortSignal) =>
    request<AddLookupOut>(`/api/add-company/lookup?ticker=${encodeURIComponent(ticker)}`, { signal }),
  startAdd: (ticker: string, signal?: AbortSignal) =>
    request<AddJobOut>("/api/add-company/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
      signal,
    }),
  addJob: (jobId: number, signal?: AbortSignal) => request<AddJobOut>(`/api/add-company/jobs/${jobId}`, { signal }),
  removedCompanies: (signal?: AbortSignal) => request<RemovedCompany[]>("/api/removed-companies", { signal }),
  removeCompany: (ticker: string, signal?: AbortSignal) =>
    request<RemoveOut>("/api/remove-company", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
      signal,
    }),
  copilot: (body: CopilotRequest, signal?: AbortSignal) =>
    request<CopilotResponse>("/api/copilot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    }),
};
