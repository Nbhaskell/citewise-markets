import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Watchlist } from "./Watchlist";
import { vi } from "vitest";
import { defaultRoutes, json, mockApi, stocks } from "../test/mockApi";
import { renderWithRouter as render } from "../test/renderWithRouter";

describe("Watchlist", () => {
  it("shows each company with price, change, trend and news mood", async () => {
    mockApi(defaultRoutes());
    render(<Watchlist />);

    const aapl = (await screen.findByRole("rowheader", { name: /AAPL/ })).closest("tr")!;
    expect(within(aapl).getByText("$340.97")).toBeInTheDocument();
    expect(within(aapl).getByText("▲ +1.29%")).toHaveClass("up");
    expect(within(aapl).getByText("Neutral")).toBeInTheDocument();
    expect(within(aapl).getByText(/8 positive · 9 negative · 90 routine/)).toBeInTheDocument();
    expect(await within(aapl).findByRole("img", { name: /AAPL price, last month/ })).toHaveClass("up");

    const nvda = screen.getByRole("rowheader", { name: /NVDA/ }).closest("tr")!;
    expect(within(nvda).getByText("▼ -1.29%")).toHaveClass("down");
    expect(within(nvda).getByText("Positive")).toBeInTheDocument();
    expect(await within(nvda).findByRole("img", { name: /NVDA price/ })).toHaveClass("down");
  });

  it("links each company to its detail page", async () => {
    mockApi(defaultRoutes());
    render(<Watchlist />);
    expect(await screen.findByRole("link", { name: "AAPL" })).toHaveAttribute("href", "/stocks/AAPL");
    expect(screen.getByRole("link", { name: "NVDA" })).toHaveAttribute("href", "/stocks/NVDA");
  });

  it("copes with a company that has no price change or news yet", async () => {
    mockApi(defaultRoutes());
    render(<Watchlist />);
    const tsla = (await screen.findByRole("rowheader", { name: /TSLA/ })).closest("tr")!;
    expect(within(tsla).getByText("n/a")).toBeInTheDocument();
    expect(within(tsla).getByText("No news")).toBeInTheDocument();
    expect(await within(tsla).findByLabelText(/not enough data/)).toBeInTheDocument();
  });

  it("explains how to add companies when the list is empty", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/stocks": [] });
    render(<Watchlist />);
    expect(await screen.findByText(/No companies yet/)).toBeInTheDocument();
  });

  it("shows the error and lets the user retry", async () => {
    let calls = 0;
    mockApi({
      ...defaultRoutes(),
      "GET /api/stocks": () => (++calls === 1 ? json({ detail: "The database isn't reachable. Is Docker running?" }, 503) : defaultRoutes()["GET /api/stocks"]),
    });
    render(<Watchlist />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The database isn't reachable");

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("rowheader", { name: /AAPL/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reminds the reader that mood is a rough indicator", async () => {
    mockApi(defaultRoutes());
    render(<Watchlist />);
    expect(await screen.findByText(/rough\s+indicator, not a signal/)).toBeInTheDocument();
  });
});

// --- the tracking switch on each row, and the "Not tracked" list ----------------------------------------------------------


const removedTsla = {
  symbol: "TSLA",
  name: "Tesla, Inc.",
  kept: { prices: 1250, filings: 14, headlines: 310, figures: 900 },
  message: "TSLA (Tesla, Inc.) is no longer tracked.",
};

/** A fake API whose tracked and removed lists change when TSLA is removed or added back, like the real one. */
function statefulRoutes(startRemoved: string[] = []) {
  const removed = new Set(startRemoved);
  const job = (over: Record<string, unknown> = {}) => ({
    job_id: 7, symbol: "TSLA", status: "running", step: "prices", started_at: "2026-10-19T18:00:00Z", finished_at: null,
    companies: [], message: null, ...over,
  });
  const routes = {
    ...defaultRoutes(),
    "GET /api/stocks": () => stocks.filter((s) => !removed.has(s.symbol)),
    "GET /api/removed-companies": () => stocks.filter((s) => removed.has(s.symbol)).map((s) => ({ symbol: s.symbol, name: s.name })),
    "POST /api/remove-company": (_url: URL, init?: RequestInit) => {
      const ticker = JSON.parse(String(init?.body)).ticker as string;
      removed.add(ticker);
      return { ...removedTsla, symbol: ticker, name: stocks.find((s) => s.symbol === ticker)?.name ?? null };
    },
    "POST /api/add-company/jobs": () => job({ status: "queued", step: null }),
    "GET /api/add-company/jobs/7": () => {
      removed.delete("TSLA"); // the add switches the company back on when it finishes
      return job({ status: "success", step: null });
    },
  };
  return { routes, removed };
}

describe("Watchlist tracking switches", () => {
  it("puts a tracked switch beside every company and no Not tracked list when nothing is removed", async () => {
    mockApi(defaultRoutes());
    render(<Watchlist />);
    await screen.findByRole("rowheader", { name: /AAPL/ });
    for (const symbol of ["AAPL", "NVDA", "TSLA"]) {
      expect(screen.getByRole("switch", { name: `${symbol}: tracked` })).toHaveAttribute("aria-checked", "true");
    }
    expect(screen.queryByRole("heading", { name: "Not tracked" })).not.toBeInTheDocument();
  });

  it("asks before removing, and the company link still opens its page", async () => {
    const fetchMock = mockApi(statefulRoutes().routes);
    render(<Watchlist />);
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: tracked" }));

    expect(screen.getByText("Stop tracking Tesla, Inc. (TSLA)?")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    expect(screen.getByRole("link", { name: "TSLA" })).toHaveAttribute("href", "/stocks/TSLA");
  });

  it("cancelling closes the question and changes nothing", async () => {
    const fetchMock = mockApi(statefulRoutes().routes);
    render(<Watchlist />);
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: tracked" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/Stop tracking Tesla/)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "TSLA: tracked" })).toBeEnabled();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("while a question is open the other switches are off, so two can't be open at once", async () => {
    mockApi(statefulRoutes().routes);
    render(<Watchlist />);
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: tracked" }));
    expect(screen.getByRole("switch", { name: "AAPL: tracked" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "NVDA: tracked" })).toBeDisabled();
  });

  it("confirming removes the company from the table and lists it, dimmed, under Not tracked", async () => {
    mockApi(statefulRoutes().routes);
    render(<Watchlist />);
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: tracked" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));

    expect(await screen.findByRole("heading", { name: "Not tracked" })).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Companies not tracked" });
    expect(within(list).getByText("TSLA")).toBeInTheDocument();
    expect(within(list).getByText("Tesla, Inc.")).toBeInTheDocument();
    expect(within(list).getByRole("switch", { name: "TSLA: not tracked" })).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByRole("rowheader", { name: /TSLA/ })).not.toBeInTheDocument(); // gone from the table
    expect(screen.getByRole("rowheader", { name: /AAPL/ })).toBeInTheDocument(); // the others are untouched
    expect(screen.getByRole("switch", { name: "AAPL: tracked" })).toBeEnabled(); // and the switches work again
  });

  it("shows removed companies from the start, and they are not links", async () => {
    mockApi(statefulRoutes(["TSLA"]).routes);
    render(<Watchlist />);
    const list = await screen.findByRole("list", { name: "Companies not tracked" });
    expect(within(list).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("rowheader", { name: /TSLA/ })).not.toBeInTheDocument();
  });

  it("switching a removed company back on asks, runs the update, and moves it back to the table", async () => {
    const { routes } = statefulRoutes(["TSLA"]);
    const fetchMock = mockApi(routes);
    render(<Watchlist pollMs={10} />);
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: not tracked" }));

    expect(screen.getByText("Track Tesla, Inc. (TSLA) again?")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false); // asked first
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));

    expect(await screen.findByText(/Updating TSLA…/)).toBeInTheDocument();
    expect(await screen.findByRole("rowheader", { name: /TSLA/ }, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Not tracked" })).not.toBeInTheDocument();
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts.map(([u]) => new URL(String(u), "http://localhost").pathname)).toEqual(["/api/add-company/jobs"]);
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ ticker: "TSLA" });
  }, 15000);

  it("keeps every switch off while an update runs, so the page can't lose track of it", async () => {
    mockApi({ ...statefulRoutes(["TSLA"]).routes, "GET /api/add-company/jobs/7": { job_id: 7, symbol: "TSLA", status: "running", step: "news",
      started_at: "2026-10-19T18:00:00Z", finished_at: null, companies: [], message: null } });
    render(<Watchlist pollMs={10} />);
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: not tracked" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    await screen.findByText(/Updating TSLA…/);
    expect(screen.getByRole("switch", { name: "TSLA: updating" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "AAPL: tracked" })).toBeDisabled();
  });

  it("says when the Not tracked list can't be loaded, and retries", async () => {
    let calls = 0;
    mockApi({ ...defaultRoutes(), "GET /api/removed-companies": () => (++calls === 1 ? new Response("", { status: 500 }) : []) });
    render(<Watchlist />);
    expect(await screen.findByText(/Couldn't load the list of companies that aren't tracked/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(screen.queryByText(/Couldn't load the list/)).not.toBeInTheDocument());
  });
});

// --- the safeguard: a company just removed stays on screen even when the Not tracked list can't be loaded ----------------------

describe("Watchlist when the Not tracked list can't be loaded (an API that is out of date)", () => {
  const outOfDate = () => json({ detail: "Not Found" }, 404); // what an API from before the list existed answers

  async function removeTsla() {
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: tracked" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));
  }

  it("keeps the removed company in the Not tracked list, with a working switch", async () => {
    mockApi({ ...statefulRoutes().routes, "GET /api/removed-companies": outOfDate });
    render(<Watchlist />);
    await removeTsla();

    const list = await screen.findByRole("list", { name: "Companies not tracked" });
    expect(within(list).getByText("TSLA")).toBeInTheDocument();
    expect(within(list).getByText("Tesla, Inc.")).toBeInTheDocument();
    expect(within(list).getByRole("switch", { name: "TSLA: not tracked" })).toBeEnabled();
    expect(screen.queryByRole("rowheader", { name: /TSLA/ })).not.toBeInTheDocument();
  });

  it("says the API is out of date and how to restart it when the list answers 404", async () => {
    mockApi({ ...statefulRoutes().routes, "GET /api/removed-companies": outOfDate });
    render(<Watchlist />);
    const warning = await screen.findByRole("alert");
    expect(warning).toHaveTextContent(/out of date/);
    expect(warning).toHaveTextContent("scripts\\stop.ps1"); // plain text, so the backslash is read as a backslash
    expect(warning).toHaveTextContent("scripts\\start.ps1");
    expect(warning).toHaveClass("warning"); // a visible box, not a line of small text
  });

  it("also keeps it when the list fails for another reason, with the plain message", async () => {
    mockApi({ ...statefulRoutes().routes, "GET /api/removed-companies": () => new Response("", { status: 500 }) });
    render(<Watchlist />);
    await removeTsla();
    expect(await screen.findByRole("list", { name: "Companies not tracked" })).toHaveTextContent("TSLA");
    expect(screen.getByRole("alert")).toHaveTextContent(/Couldn't load the list of companies that aren't tracked/);
    expect(screen.getByRole("alert")).not.toHaveTextContent(/out of date/);
  });

  it("shows a company once, not twice, when the list does load", async () => {
    mockApi(statefulRoutes().routes);
    render(<Watchlist />);
    await removeTsla();
    await screen.findByRole("list", { name: "Companies not tracked" });
    expect(screen.getAllByRole("switch", { name: "TSLA: not tracked" })).toHaveLength(1);
  });

  it("switching it back on still works, and it then leaves the Not tracked list", async () => {
    const { routes } = statefulRoutes();
    mockApi({ ...routes, "GET /api/removed-companies": outOfDate });
    render(<Watchlist pollMs={10} />);
    await removeTsla();
    await userEvent.click(await screen.findByRole("switch", { name: "TSLA: not tracked" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));

    expect(await screen.findByRole("rowheader", { name: /TSLA/ }, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Companies not tracked" })).not.toBeInTheDocument();
  }, 15000);

  it("lists companies in ticker order when some come from the list and some were just removed", async () => {
    const { routes } = statefulRoutes(["TSLA"]);
    // the list only knows TSLA (stale), so AAPL is on screen because it was just removed here
    mockApi({ ...routes, "GET /api/removed-companies": [{ symbol: "TSLA", name: "Tesla, Inc." }] });
    render(<Watchlist />);
    await userEvent.click(await screen.findByRole("switch", { name: "AAPL: tracked" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking AAPL" }));
    const list = await screen.findByRole("list", { name: "Companies not tracked" });
    await screen.findByText("Apple Inc.");
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent?.slice(0, 4))).toEqual(["AAPL", "TSLA"]);
  });
});
