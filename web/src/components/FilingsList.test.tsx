import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilingsList } from "./FilingsList";
import { filingRows, json, mockApi } from "../test/mockApi";

describe("FilingsList", () => {
  it("lists filings with dates, search status, and a safe link to the SEC", async () => {
    mockApi({ "GET /api/stocks/AAPL/filings": filingRows });
    render(<FilingsList symbol="AAPL" />);

    const quarterly = (await screen.findByRole("rowheader", { name: "10-Q" })).closest("tr")!;
    expect(within(quarterly).getByText("Jul 31, 2026")).toBeInTheDocument();
    expect(within(quarterly).getByText("Jun 27, 2026")).toBeInTheDocument();
    expect(within(quarterly).getByText("Searchable")).toBeInTheDocument();
    const link = within(quarterly).getByRole("link", { name: "View on SEC" });
    expect(link).toHaveAttribute("href", "https://www.sec.gov/q");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("flags filings the copilot can't use yet, and drops an unsafe link", async () => {
    mockApi({ "GET /api/stocks/AAPL/filings": filingRows });
    render(<FilingsList symbol="AAPL" />);
    const annual = (await screen.findByRole("rowheader", { name: "10-K" })).closest("tr")!;
    expect(within(annual).getByText("Not indexed")).toBeInTheDocument();
    expect(within(annual).queryByRole("link")).not.toBeInTheDocument();
  });

  it("explains how to add filings when there are none", async () => {
    mockApi({ "GET /api/stocks/AAPL/filings": [] });
    render(<FilingsList symbol="AAPL" />);
    expect(await screen.findByText(/No filings stored for AAPL yet.*data\.ingest_filings AAPL/)).toBeInTheDocument();
  });

  it("shows an error and retries", async () => {
    let calls = 0;
    mockApi({ "GET /api/stocks/AAPL/filings": () => (++calls === 1 ? json({ detail: "boom" }, 500) : filingRows) });
    render(<FilingsList symbol="AAPL" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("rowheader", { name: "10-Q" })).toBeInTheDocument();
  });
});
