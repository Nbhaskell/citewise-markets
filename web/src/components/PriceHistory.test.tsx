import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PriceHistory } from "./PriceHistory";
import { json, longPrices, mockApi } from "../test/mockApi";

const requestedRanges = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://localhost").searchParams.get("range"));

describe("PriceHistory", () => {
  it("loads one year by default and draws the chart", async () => {
    const fetchMock = mockApi({ "GET /api/stocks/AAPL/prices": () => longPrices("AAPL", "1Y") });
    render(<PriceHistory symbol="AAPL" />);
    expect(await screen.findByRole("img", { name: /AAPL closing price over 1Y/ })).toBeInTheDocument();
    expect(requestedRanges(fetchMock)).toEqual(["1Y"]);
    expect(screen.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "false");
  });

  it("fetches a new range when a range button is pressed", async () => {
    const fetchMock = mockApi({
      "GET /api/stocks/AAPL/prices": (url: URL) => longPrices("AAPL", url.searchParams.get("range") ?? "1Y", 60),
    });
    render(<PriceHistory symbol="AAPL" />);
    await screen.findByRole("img", { name: /over 1Y/ });

    await userEvent.click(screen.getByRole("button", { name: "3M" }));
    expect(await screen.findByRole("img", { name: /over 3M/ })).toBeInTheDocument();
    expect(requestedRanges(fetchMock)).toEqual(["1Y", "3M"]);
    expect(screen.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps showing the old chart, dimmed, while a new range loads", async () => {
    let release!: (value: unknown) => void;
    mockApi({
      "GET /api/stocks/AAPL/prices": (url: URL) =>
        url.searchParams.get("range") === "5Y" ? new Promise((resolve) => (release = resolve)) : longPrices("AAPL", "1Y"),
    });
    render(<PriceHistory symbol="AAPL" />);
    await screen.findByRole("img", { name: /over 1Y/ });

    await userEvent.click(screen.getByRole("button", { name: "5Y" }));
    const chart = screen.getByRole("img", { name: /over 1Y/ });
    expect(chart.closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");

    release(longPrices("AAPL", "5Y"));
    expect(await screen.findByRole("img", { name: /over 5Y/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("img").closest("[aria-busy]")).toHaveAttribute("aria-busy", "false"));
  });

  it("says so when there isn't enough history", async () => {
    mockApi({ "GET /api/stocks/AAPL/prices": () => longPrices("AAPL", "1M", 1) });
    render(<PriceHistory symbol="AAPL" />);
    expect(await screen.findByText("Not enough price history for this range yet.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows an error and retries", async () => {
    let calls = 0;
    mockApi({
      "GET /api/stocks/AAPL/prices": () => (++calls === 1 ? json({ detail: "The database isn't reachable. Is Docker running?" }, 503) : longPrices("AAPL")),
    });
    render(<PriceHistory symbol="AAPL" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("database isn't reachable");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("img", { name: /AAPL closing price/ })).toBeInTheDocument();
  });
});
