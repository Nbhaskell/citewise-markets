import { vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ChangesOut } from "../api/types";
import { ChangesPage } from "./ChangesPage";
import { changesData, defaultRoutes, json, mockApi } from "../test/mockApi";

const page = () => (
  <MemoryRouter initialEntries={["/changes"]}>
    <ChangesPage />
  </MemoryRouter>
);
const routes = (data: Partial<ChangesOut> = {}) => ({
  ...defaultRoutes(),
  "GET /api/changes": () => ({ ...changesData, ...data }),
});

describe("ChangesPage", () => {
  it("shows the three sections and says what the window is", async () => {
    mockApi(routes());
    render(page());
    expect(await screen.findByRole("heading", { level: 1, name: "What changed" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "New filings" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Big moves" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Notable headlines" })).toBeInTheDocument();
    expect(await screen.findByText(/Latest trading day: Oct 14, 2026/)).toBeInTheDocument();
    expect(document.title).toBe("What changed · Citewise for Markets");
  });

  it("asks for the latest day first, then for the window you pick", async () => {
    const fetchMock = mockApi(routes());
    render(page());
    await screen.findByText(/Latest trading day/);
    const days = () => fetchMock.mock.calls.map(([u]) => new URL(String(u), "http://x").searchParams.get("days")).filter(Boolean);
    expect(days()).toEqual(["1"]);
    const group = screen.getByRole("group", { name: "Look back" });
    expect(within(group).getByRole("button", { name: "Latest day" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(group).getByRole("button", { name: "7 days" }));
    await waitFor(() => expect(days().at(-1)).toBe("7"));
    expect(within(group).getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("explains an empty filings list by naming the newest stored filing", async () => {
    mockApi(routes());
    render(page());
    expect(await screen.findByText(/Nothing was filed in this window\. The newest stored filing is NVDA's 10-Q, filed Aug 26, 2026\./)).toBeInTheDocument();
  });

  it("lists new filings with a link to the company and a safe SEC link", async () => {
    mockApi(routes({
      filings: [
        { symbol: "AAPL", form: "10-Q", filed_at: "2026-10-14", period_of_report: "2026-09-27", url: "https://www.sec.gov/q", accession_number: "0-1" },
        { symbol: "MSFT", form: "10-K", filed_at: "2026-10-14", period_of_report: null, url: "javascript:alert(1)", accession_number: "0-2" },
      ],
    }));
    render(page());
    const section = (await screen.findByRole("heading", { name: "New filings" })).closest("section")!;
    expect(within(section).getByRole("link", { name: "AAPL" })).toHaveAttribute("href", "/stocks/AAPL");
    expect(within(section).getByRole("link", { name: "View on SEC" })).toHaveAttribute("href", "https://www.sec.gov/q");
    expect(within(section).getAllByRole("link", { name: "View on SEC" })).toHaveLength(1); // the javascript: link is dropped
    expect(within(section).getByText(/period ended Sep 27, 2026/)).toBeInTheDocument();
    expect(within(section).queryByText(/Nothing was filed/)).not.toBeInTheDocument();
  });

  it("shows each big move with its size, its usual size, and a market-wide label", async () => {
    mockApi(routes());
    render(page());
    const section = (await screen.findByRole("heading", { name: "Big moves" })).closest("section")!;
    const amd = within(section).getByRole("link", { name: "AMD" }).closest("li")!;
    expect(amd).toHaveTextContent("▼ -5.73%");
    expect(amd).toHaveTextContent("Usual day: ±2.37%");
    expect(amd).toHaveTextContent("Listed at 4.74% or more");
    expect(amd).toHaveTextContent("Market-wide day");
    expect(amd).toHaveTextContent("closed $480.50, against $509.70 on Oct 13, 2026");
    const tsla = within(section).getByRole("link", { name: "TSLA" }).closest("li")!;
    expect(tsla).toHaveTextContent("▲ +5.26%");
    expect(tsla).toHaveTextContent("Not enough earlier history");
    expect(tsla).not.toHaveTextContent("Market-wide day");
  });

  it("warns on a market-wide day and says the move may not be about the company", async () => {
    mockApi(routes());
    render(page());
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("6 of 7 companies fell by more than 1%");
    expect(note).toHaveTextContent("may reflect the whole market, not the company");
  });

  it("puts headlines beside a move as timing only, never as a cause, and drops unsafe links", async () => {
    mockApi(routes());
    render(page());
    expect(await screen.findByText(/timing only; they don't show why it moved/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AMD slides with chip stocks" })).toHaveAttribute("href", "https://example.com/amd");
    expect(screen.getByText("Unsafe link headline").closest("a")).toBeNull();
    expect(screen.getByText("No stored headlines were published about it that day.")).toBeInTheDocument();
  });

  it("says plainly when nothing moved", async () => {
    mockApi(routes({ moves: [], market_days: [] }));
    render(page());
    expect(await screen.findByText("No unusually big moves in this window.")).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("shows notable headlines with counts, and says when it is only the newest few", async () => {
    mockApi(routes());
    render(page());
    const section = (await screen.findByRole("heading", { name: "Notable headlines" })).closest("section")!;
    expect(within(section).getByText(/5 positive, 2 negative · showing the newest 1/)).toBeInTheDocument();
    const link = within(section).getByRole("link", { name: "Nvidia wins a contract" });
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(section).toHaveTextContent('"notable" means "labeled", not "important"');
  });

  it("reports a mood shift in words and scores, and its absence", async () => {
    mockApi(routes());
    const { unmount } = render(page());
    const shifts = await screen.findByRole("list", { name: "Mood shifts" });
    expect(shifts).toHaveTextContent("Positive (+0.60, 20 stories) over the last 7 days");
    expect(shifts).toHaveTextContent("against Negative (-0.33, 30 stories) the 7 days before");
    unmount();

    mockApi(routes({ mood_shifts: [] }));
    render(page());
    expect(await screen.findByText(/No company's news mood moved much from the week before/)).toBeInTheDocument();
  });

  it("says when there are no headlines at all", async () => {
    mockApi(routes({ headlines: [] }));
    render(page());
    expect(await screen.findByText("No positive or negative headlines in this window.")).toBeInTheDocument();
  });

  it("warns, with the dates, when a company has no price for the latest day", async () => {
    mockApi(routes({ stale: [{ symbol: "TSLA", as_of: "2026-10-13" }, { symbol: "ZZZ", as_of: null }] }));
    render(page());
    const alert = await screen.findByText(/No price yet for Oct 14, 2026 for/);
    expect(alert).toHaveTextContent("TSLA (latest Oct 13, 2026), ZZZ (latest none)");
    expect(alert).toHaveTextContent("their latest moves may be missing");
  });

  it("uses the multi-day wording for a longer window", async () => {
    mockApi(routes({ days: 7, window_start: "2026-10-06" }));
    render(page());
    expect(await screen.findByText("The last 7 trading days: Oct 6, 2026 to Oct 14, 2026.")).toBeInTheDocument();
  });

  it("says so when no prices are stored", async () => {
    mockApi(routes({ as_of: null, window_start: null, moves: [], market_days: [], filings: [], headlines: [], newest_filing: null }));
    render(page());
    expect(await screen.findByText(/No prices are stored yet/)).toBeInTheDocument();
    expect(screen.getByText(/No filings are stored yet/)).toBeInTheDocument();
  });

  it("shows an error with a retry, and recovers", async () => {
    let fail = true;
    mockApi({ ...defaultRoutes(), "GET /api/changes": () => (fail ? json({ detail: "Database is down" }, 500) : changesData) });
    render(page());
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Big moves" })).toBeInTheDocument();
  });

  it("keeps the old result on screen, dimmed, while a new window loads", async () => {
    let release: () => void = () => {};
    mockApi({
      ...defaultRoutes(),
      "GET /api/changes": (url: URL) =>
        url.searchParams.get("days") === "1"
          ? changesData
          : new Promise((resolve) => { release = () => resolve({ ...changesData, days: 3, window_start: "2026-10-12" }); }),
    });
    render(page());
    await screen.findByRole("heading", { name: "Big moves" });
    await userEvent.click(screen.getByRole("button", { name: "3 days" }));
    const section = screen.getByRole("heading", { name: "Big moves" }).closest("section")!;
    expect(section.parentElement).toHaveAttribute("aria-busy", "true");
    release();
    await waitFor(() => expect(section.parentElement).toHaveAttribute("aria-busy", "false"));
  });
});

describe("ChangesPage: since last visit", () => {
  const KEY = "stockmarket.changes.lastVisit.v1";
  const queries = (fetchMock: ReturnType<typeof mockApi>) =>
    fetchMock.mock.calls.map(([u]) => new URL(String(u), "http://x").searchParams);

  it("offers nothing on a first visit, and remembers the newest trading day it showed", async () => {
    mockApi(routes());
    render(page());
    await screen.findByText(/Latest trading day/);
    expect(screen.queryByRole("button", { name: /Since last visit/ })).not.toBeInTheDocument();
    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBe("2026-10-14"));
  });

  it("offers the earlier visit's date and asks for what came after it", async () => {
    window.localStorage.setItem(KEY, "2026-10-10");
    const fetchMock = mockApi({
      ...defaultRoutes(),
      "GET /api/changes": (url: URL) =>
        url.searchParams.get("since") ? { ...changesData, days: 2, since: "2026-10-10", window_start: "2026-10-13" } : changesData,
    });
    render(page());
    await screen.findByText(/Latest trading day/);
    const button = screen.getByRole("button", { name: "Since last visit (Oct 10, 2026)" });
    expect(button).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(button);
    expect(await screen.findByText("Since your last visit (Oct 10, 2026): 2 trading days, Oct 13, 2026 to Oct 14, 2026.")).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-pressed", "true");
    const last = queries(fetchMock).at(-1)!;
    expect(last.get("since")).toBe("2026-10-10");
    expect(last.get("days")).toBeNull();
  });

  it("keeps offering the date it read when the page opened, even though this visit saves a newer one", async () => {
    window.localStorage.setItem(KEY, "2026-10-10");
    mockApi(routes());
    render(page());
    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBe("2026-10-14"));
    expect(screen.getByRole("button", { name: "Since last visit (Oct 10, 2026)" })).toBeInTheDocument();
  });

  it("says plainly when no trading day has been stored since", async () => {
    window.localStorage.setItem(KEY, "2026-10-14");
    mockApi({
      ...defaultRoutes(),
      "GET /api/changes": (url: URL) =>
        url.searchParams.get("since")
          ? { ...changesData, days: 0, since: "2026-10-14", window_start: null, moves: [], market_days: [], headlines: [] }
          : changesData,
    });
    render(page());
    await userEvent.click(await screen.findByRole("button", { name: /Since last visit/ }));
    expect(await screen.findByText(/No new trading days since Oct 14, 2026/)).toBeInTheDocument();
    expect(screen.getByText("No unusually big moves in this window.")).toBeInTheDocument();
  });

  it("never moves the saved date backwards", async () => {
    window.localStorage.setItem(KEY, "2026-10-20");
    mockApi(routes());
    render(page());
    await screen.findByText(/Latest trading day/);
    expect(window.localStorage.getItem(KEY)).toBe("2026-10-20");
  });

  it("ignores a saved value that is not a date", async () => {
    window.localStorage.setItem(KEY, "yesterday");
    mockApi(routes());
    render(page());
    await screen.findByText(/Latest trading day/);
    expect(screen.queryByRole("button", { name: /Since last visit/ })).not.toBeInTheDocument();
    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBe("2026-10-14"));
  });

  it("still works when the browser blocks storage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    mockApi(routes());
    render(page());
    expect(await screen.findByText(/Latest trading day: Oct 14, 2026/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Since last visit/ })).not.toBeInTheDocument();
  });
});
