import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Watchlist } from "./Watchlist";
import { defaultRoutes, json, mockApi } from "../test/mockApi";
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
