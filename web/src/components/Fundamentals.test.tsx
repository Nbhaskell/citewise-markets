import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Fundamentals } from "./Fundamentals";
import { fundamentalsData, fundamentalsRoutes, json, mockApi } from "../test/mockApi";

function stat(label: string): HTMLElement {
  return screen.getByText(label, { selector: "dt" }).parentElement as HTMLElement;
}

describe("Fundamentals", () => {
  it("shows the figures in words with the dates they cover", async () => {
    mockApi(fundamentalsRoutes());
    render(<Fundamentals symbol="AAPL" />);

    expect(await screen.findByRole("heading", { name: "Fundamentals" })).toBeInTheDocument();
    expect(await screen.findByText(/Last 12 months, through Jun 27, 2026\. Price \$340\.97 on Oct 12, 2026\./)).toBeInTheDocument();
    expect(within(stat("Market value")).getByText("$4.98 trillion")).toBeInTheDocument();
    expect(within(stat("P/E")).getByText("39.1")).toBeInTheDocument();
    expect(within(stat("Revenue")).getByText("$466.8 billion")).toBeInTheDocument();
    expect(within(stat("Net income")).getByText("$128.9 billion")).toBeInTheDocument();
    expect(within(stat("Diluted EPS")).getByText("$8.72")).toBeInTheDocument();
    expect(within(stat("Operating income")).getByText("$154.9 billion")).toBeInTheDocument();
    expect(within(stat("Gross margin")).getByText("48.7%")).toBeInTheDocument();
    expect(within(stat("Operating margin")).getByText("33.2%")).toBeInTheDocument();
    expect(within(stat("Net margin")).getByText("27.6%")).toBeInTheDocument();
    expect(within(stat("Shares outstanding")).getByText("14.59 billion")).toBeInTheDocument();
    expect(screen.getByText(/not financial advice/)).toBeInTheDocument();
  });

  it("shows growth with an arrow and the two periods it compares", async () => {
    mockApi(fundamentalsRoutes());
    render(<Fundamentals symbol="AAPL" />);
    const revenue = (await screen.findByText("Revenue", { selector: "dt" })).parentElement!;
    expect(within(revenue).getByText("▲ +16.20%")).toBeInTheDocument();
    expect(within(revenue).getByText(/9 months to 2026-06-27 vs the same 9 months a year earlier/)).toBeInTheDocument();
  });

  it("keeps each calculation one click away, with its source filings", async () => {
    mockApi(fundamentalsRoutes());
    render(<Fundamentals symbol="AAPL" />);
    const revenue = (await screen.findByText("Revenue", { selector: "dt" })).parentElement!;
    const summary = within(revenue).getByText("How this was calculated");
    expect(within(revenue).getByText(/the last full year \(ended 2025-09-27\)/)).not.toBeVisible();
    await userEvent.click(summary);
    expect(within(revenue).getByText(/the last full year \(ended 2025-09-27\)/)).toBeVisible();
    expect(within(revenue).getByText("10-Q filed 2026-07-31 (9 months to 2026-06-27)")).toBeVisible();

    const pe = stat("P/E");
    await userEvent.click(within(pe).getByText("How this was calculated"));
    expect(within(pe).getByText(/\$340\.97, the latest close, ÷ \$8\.72, diluted earnings per share/)).toBeVisible();
    const cap = stat("Market value");
    await userEvent.click(within(cap).getByText("How this was calculated"));
    expect(within(cap).getByText(/14\.59 billion shares \(from the cover page of the 10-Q filed 2026-07-31\) × \$340\.97/)).toBeVisible();
  });

  it("puts cautions above the figures, labeled in words", async () => {
    mockApi(fundamentalsRoutes({ cautions: ["net income is 1.7 times operating income, which usually means gains outside the core business"] }));
    render(<Fundamentals symbol="AAPL" />);
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("Caution: net income is 1.7 times operating income");
    expect(note.compareDocumentPosition(stat("Market value")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows no caution box when there are none", async () => {
    mockApi(fundamentalsRoutes());
    render(<Fundamentals symbol="AAPL" />);
    await screen.findByText("Market value", { selector: "dt" });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("explains a missing P/E instead of leaving a blank", async () => {
    mockApi(fundamentalsRoutes({ pe: null, pe_note: "not meaningful: earnings per share over the last twelve months is zero or negative" }));
    render(<Fundamentals symbol="AAPL" />);
    const pe = (await screen.findByText("P/E", { selector: "dt" })).parentElement!;
    expect(within(pe).getByText("n/a")).toBeInTheDocument();
    expect(within(pe).getByText(/zero or negative/)).toBeInTheDocument();
  });

  it("leaves out a margin or figure the company doesn't report", async () => {
    mockApi(fundamentalsRoutes({ gross_margin: null, operating_income: null }));
    render(<Fundamentals symbol="AAPL" />);
    await screen.findByText("Market value", { selector: "dt" });
    expect(screen.queryByText("Gross margin")).not.toBeInTheDocument();
    expect(screen.queryByText("Operating income", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getByText("Operating margin")).toBeInTheDocument();
  });

  it("says why a company has no fundamentals and how to fetch them", async () => {
    mockApi({
      "GET /api/stocks/TSM/fundamentals": {
        ...fundamentalsData, symbol: "TSM", available: false, revenue: null, net_income: null, diluted_eps: null,
        operating_income: null, shares: null, market_value: null, pe: null,
        unavailable_reason: "it reports under another accounting standard (a foreign filer) that isn't supported",
      },
    });
    render(<Fundamentals symbol="TSM" />);
    expect(await screen.findByText(/No fundamentals for TSM: it reports under another accounting standard/)).toBeInTheDocument();
    expect(screen.getByText(/python -m data\.ingest_fundamentals TSM/)).toBeInTheDocument();
    expect(screen.queryByText("Market value")).not.toBeInTheDocument();
  });

  it("shows an error with a retry that works", async () => {
    let calls = 0;
    mockApi({
      "GET /api/stocks/AAPL/fundamentals": () => {
        calls += 1;
        return calls === 1 ? json({ detail: "The database is down" }, 500) : fundamentalsData;
      },
    });
    render(<Fundamentals symbol="AAPL" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The database is down");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("$4.98 trillion")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows text from the API as text, never as HTML", async () => {
    const evil = "<img src=x onerror=alert(1)>";
    mockApi(fundamentalsRoutes({ cautions: [evil] }));
    const { container } = render(<Fundamentals symbol="AAPL" />);
    expect(await screen.findByRole("note")).toHaveTextContent(evil);
    expect(container.querySelector("img")).toBeNull();
  });

  it("asks for the company it was given", async () => {
    const fetchMock = mockApi(fundamentalsRoutes());
    render(<Fundamentals symbol="AAPL" />);
    await screen.findByText("Market value", { selector: "dt" });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/stocks/AAPL/fundamentals");
  });
});
