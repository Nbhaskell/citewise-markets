import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { StockPage } from "./StockPage";
import { copilotAnswer, detailRoutes, json, mockApi, stockDetail } from "../test/mockApi";

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>Dashboard</p>} />
        <Route path="/stocks/:symbol" element={<StockPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("StockPage", () => {
  it("assembles the page for one company", async () => {
    mockApi({ ...detailRoutes(), "POST /api/copilot": copilotAnswer() });
    renderPage("/stocks/AAPL");

    expect(await screen.findByRole("heading", { level: 1, name: "AAPL" })).toBeInTheDocument();
    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("$340.97", { selector: ".big-price" })).toBeInTheDocument();
    expect(screen.getByText("▲ +1.29% today")).toBeInTheDocument();

    expect(await screen.findByRole("img", { name: /AAPL closing price over 1Y/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Key stats" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Fundamentals" })).toBeInTheDocument();
    expect(await screen.findByText("$466.8 billion")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "AAPL news" })).toBeInTheDocument();
    expect(await screen.findByText("Apple faces a probe")).toBeInTheDocument();
    expect(await screen.findByRole("rowheader", { name: "10-Q" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask about AAPL" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Dashboard" })).toHaveAttribute("href", "/");
    expect(document.title).toBe("AAPL · Citewise for Markets");
  });

  it("accepts a lowercase ticker in the address", async () => {
    mockApi(detailRoutes());
    renderPage("/stocks/aapl");
    expect(await screen.findByRole("heading", { level: 1, name: "AAPL" })).toBeInTheDocument();
  });

  it("limits the news and the copilot to this company", async () => {
    const fetchMock = mockApi({ ...detailRoutes(), "POST /api/copilot": copilotAnswer({ companies: ["AAPL"] }) });
    renderPage("/stocks/AAPL");
    await screen.findByText("Apple faces a probe");
    const newsCall = fetchMock.mock.calls.map(([u]) => new URL(String(u), "http://localhost")).find((u) => u.pathname === "/api/news")!;
    expect(newsCall.searchParams.get("symbol")).toBe("AAPL");
    expect(newsCall.searchParams.get("days")).toBe("7");

    await userEvent.click(screen.getByRole("button", { name: "What are the biggest risks?" }));
    await screen.findByText(/As of fiscal 2026 NVIDIA had/);
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]?.body))).toEqual({ question: "What are the biggest risks?", symbols: ["AAPL"] });
  });

  it("changes the chart range", async () => {
    const fetchMock = mockApi(detailRoutes());
    renderPage("/stocks/AAPL");
    await screen.findByRole("img", { name: /over 1Y/ });
    await userEvent.click(screen.getByRole("button", { name: "6M" }));
    await screen.findByRole("img", { name: /AAPL closing price/ });
    const ranges = fetchMock.mock.calls.map(([u]) => new URL(String(u), "http://localhost")).filter((u) => u.pathname.endsWith("/prices"));
    expect(ranges.map((u) => u.searchParams.get("range"))).toEqual(["1Y", "6M"]);
  });

  it("says when a company isn't tracked, and how to add it", async () => {
    mockApi({
      ...detailRoutes(),
      "GET /api/stocks/ZZZ": json({ detail: "ZZZ is not a tracked company" }, 404),
    });
    renderPage("/stocks/ZZZ");
    expect(await screen.findByRole("heading", { name: "ZZZ isn't a tracked company" })).toBeInTheDocument();
    expect(screen.getByText(/python -m jobs\.add_company ZZZ/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the dashboard" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("heading", { name: "Key stats" })).not.toBeInTheDocument();
  });

  it("removes the company after a confirmation, then shows what was kept instead of the page", async () => {
    const removed = {
      symbol: "AAPL", name: "Apple Inc.", kept: { prices: 1250, filings: 14, headlines: 310, figures: 900 },
      message: "AAPL (Apple Inc.) is no longer tracked. Its stored data was kept.",
    };
    const fetchMock = mockApi({ ...detailRoutes(), "POST /api/remove-company": removed });
    renderPage("/stocks/AAPL");
    await screen.findByText("Apple Inc.");

    await userEvent.click(screen.getByRole("switch", { name: "AAPL: tracked" })); // the switch in the page header
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false); // asked first
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking AAPL" }));

    expect(await screen.findByRole("heading", { name: "AAPL is no longer tracked" })).toBeInTheDocument();
    expect(screen.getByText(/1,250 daily prices, 14 filings, 310 headlines, 900 financial figures/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Key stats" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the dashboard" })).toHaveAttribute("href", "/");
  });

  it("offers no tracking switch for a company that isn't tracked", async () => {
    mockApi({ ...detailRoutes(), "GET /api/stocks/ZZZ": json({ detail: "ZZZ is not a tracked company" }, 404) });
    renderPage("/stocks/ZZZ");
    await screen.findByRole("heading", { name: "ZZZ isn't a tracked company" });
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  it("rejects an address that isn't a ticker without calling the API", async () => {
    const fetchMock = mockApi(detailRoutes());
    renderPage("/stocks/bad$sym");
    expect(await screen.findByRole("heading", { name: "That doesn't look like a ticker" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the other panels working when one fails", async () => {
    mockApi({ ...detailRoutes(), "GET /api/stocks/AAPL/filings": new Response("boom", { status: 500 }) });
    renderPage("/stocks/AAPL");
    expect(await screen.findByText(/The API returned an error \(500\)/)).toBeInTheDocument(); // filings panel
    expect(await screen.findByRole("img", { name: /AAPL closing price/ })).toBeInTheDocument(); // chart still fine
    expect(screen.getByText("Apple faces a probe")).toBeInTheDocument(); // news still fine
    expect(screen.getByRole("heading", { name: "Key stats" })).toBeInTheDocument();
  });

  it("shows the connection problem and a retry when the company details fail", async () => {
    let calls = 0;
    mockApi({
      ...detailRoutes(),
      "GET /api/stocks/AAPL": () => (++calls === 1 ? new Response("", { status: 502 }) : stockDetail),
    });
    renderPage("/stocks/AAPL");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("python -m api"))).toBe(true);
    await userEvent.click(within(alerts.find((a) => a.textContent?.includes("python -m api"))!).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
  });
});

describe("StockPage tracking switch", () => {
  it("has the switch in the header, next to the name, not at the bottom of the page", async () => {
    mockApi(detailRoutes());
    renderPage("/stocks/AAPL");
    const toggle = await screen.findByRole("switch", { name: "AAPL: tracked" });
    expect(toggle.closest("header")).toHaveClass("stock-head");
    expect(screen.queryByRole("heading", { name: /Stop tracking/ })).not.toBeInTheDocument();
  });

  it("cancelling the question leaves the page as it was and the switch usable", async () => {
    const fetchMock = mockApi(detailRoutes());
    renderPage("/stocks/AAPL");
    await userEvent.click(await screen.findByRole("switch", { name: "AAPL: tracked" }));
    expect(screen.getByRole("switch", { name: "AAPL: tracked" })).toBeDisabled(); // the question is open
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("switch", { name: "AAPL: tracked" })).toBeEnabled();
    expect(screen.queryByText(/Stop tracking Apple/)).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
