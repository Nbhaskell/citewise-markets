import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddCompanyBox } from "./AddCompanyBox";
import { json, mockApi } from "../test/mockApi";

const lookup = { symbol: "TSLA", name: "Tesla, Inc.", exchange: "NMS", tracked: false };
const job = (over: Record<string, unknown> = {}) => ({
  job_id: 7,
  symbol: "TSLA",
  status: "success",
  step: null,
  started_at: "2026-10-15T18:00:00Z",
  finished_at: "2026-10-15T18:03:00Z",
  companies: [],
  message: null,
  ...over,
});

async function lookUp(text: string) {
  await userEvent.type(screen.getByLabelText("Ticker"), text);
  await userEvent.click(screen.getByRole("button", { name: "Look up" }));
}

describe("AddCompanyBox", () => {
  it("asks to confirm the looked-up name before writing anything", async () => {
    const fetchMock = mockApi({ "GET /api/add-company/lookup": lookup });
    render(<AddCompanyBox />);
    await lookUp("tsla");

    expect(await screen.findByText("Add Tesla, Inc. (TSLA)?")).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([, init]) => (init?.method ?? "GET") === "GET")).toBe(true);
  });

  it("starts the add only after Yes, and shows the report with its gaps in words", async () => {
    const fetchMock = mockApi({
      "GET /api/add-company/lookup": lookup,
      "POST /api/add-company/jobs": json(
        job({
          status: "partial",
          companies: [{
            symbol: "TSLA", name: "Tesla, Inc.", verdict: "ADDED, WITH GAPS",
            lines: [{ step: "filings", status: "NONE", text: "the SEC has no 10-K or 10-Q on file" }],
          }],
        }),
        202,
      ),
    });
    render(<AddCompanyBox />);
    await lookUp("TSLA");
    await userEvent.click(await screen.findByRole("button", { name: "Yes, add TSLA" }));

    expect(await screen.findByText("TSLA was added, with gaps")).toBeInTheDocument();
    expect(screen.getByText("TSLA - Tesla, Inc.: ADDED, WITH GAPS")).toBeInTheDocument();
    expect(screen.getByText(/the SEC has no 10-K or 10-Q on file/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry TSLA" })).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ ticker: "TSLA" });
    expect(post?.[1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("does not start anything when Cancel is pressed", async () => {
    const fetchMock = mockApi({ "GET /api/add-company/lookup": lookup });
    render(<AddCompanyBox />);
    await lookUp("TSLA");
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    expect(screen.getByLabelText("Ticker")).toBeInTheDocument();
  });

  it("explains a busy lock in plain words", async () => {
    mockApi({
      "GET /api/add-company/lookup": lookup,
      "POST /api/add-company/jobs": json({ detail: "Another update is running (the nightly refresh, a backup, or another add). Try again in a few minutes." }, 409),
    });
    render(<AddCompanyBox />);
    await lookUp("TSLA");
    await userEvent.click(await screen.findByRole("button", { name: "Yes, add TSLA" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another update is running");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows an unknown ticker as not found, with no add offered", async () => {
    mockApi({ "GET /api/add-company/lookup": json({ detail: "No US-listed company found for ZZNOPE. Check the spelling." }, 404) });
    render(<AddCompanyBox />);
    await lookUp("ZZNOPE");
    expect(await screen.findByRole("alert")).toHaveTextContent("No US-listed company found for ZZNOPE");
    expect(screen.queryByRole("button", { name: /Yes, add/ })).not.toBeInTheDocument();
  });

  it("offers a retry for an interrupted add instead of calling it done", async () => {
    mockApi({
      "GET /api/add-company/lookup": lookup,
      "POST /api/add-company/jobs": json(job({ status: "interrupted", message: "The add stopped before it finished." }), 202),
    });
    render(<AddCompanyBox />);
    await lookUp("TSLA");
    await userEvent.click(await screen.findByRole("button", { name: "Yes, add TSLA" }));
    expect(await screen.findByRole("heading", { name: "TSLA: the add stopped early" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry TSLA" })).toBeInTheDocument();
  });
});
