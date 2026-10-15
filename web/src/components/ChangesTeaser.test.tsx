import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ChangesOut } from "../api/types";
import { ChangesTeaser } from "./ChangesTeaser";
import { changesData, json, mockApi } from "../test/mockApi";

const show = (data: Partial<ChangesOut> = {}) => {
  const fetchMock = mockApi({ "GET /api/changes": () => ({ ...changesData, ...data }) });
  render(
    <MemoryRouter>
      <ChangesTeaser />
    </MemoryRouter>,
  );
  return fetchMock;
};
const move = (symbol: string, pct: number): ChangesOut["moves"][number] => ({
  ...changesData.moves[0], symbol, change_pct: pct, market_wide: false, headlines: [],
});

describe("ChangesTeaser", () => {
  it("summarises the latest day in counts and links to the full page", async () => {
    const fetchMock = show();
    expect(await screen.findByText(/2 big moves · 0 new filings · 7 positive or negative headlines/)).toBeInTheDocument();
    expect(screen.getByText("Latest trading day: Oct 14, 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /See everything that changed/ })).toHaveAttribute("href", "/changes");
    expect(new URL(String(fetchMock.mock.calls[0][0]), "http://x").searchParams.get("days")).toBe("1");
  });

  it("shows the biggest moves with an arrow and sign, and the market-wide label", async () => {
    show();
    const list = await screen.findByRole("list", { name: "Biggest moves" });
    const amd = within(list).getByRole("link", { name: "AMD" }).closest("li")!;
    expect(amd).toHaveTextContent("▼ -5.73%");
    expect(amd).toHaveTextContent("Market-wide day");
    expect(within(list).getByRole("link", { name: "TSLA" }).closest("li")).toHaveTextContent("▲ +5.26%");
  });

  it("lists only the first three moves and says how many more there are", async () => {
    show({ moves: ["A", "B", "C", "D", "E"].map((s, i) => move(s, 3.5 + i)) });
    const list = await screen.findByRole("list", { name: "Biggest moves" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("and 2 more")).toBeInTheDocument();
  });

  it("uses singular wording for one of each", async () => {
    show({
      moves: [move("A", 4)],
      headlines: [{ symbol: "A", positive: 1, negative: 0, items: [] }],
      filings: [{ symbol: "A", form: "10-Q", filed_at: "2026-10-14", period_of_report: null, url: "https://x", accession_number: "1" }],
    });
    expect(await screen.findByText(/1 big move · 1 new filing · 1 positive or negative headline$/)).toBeInTheDocument();
    expect(screen.queryByText(/and \d+ more/)).not.toBeInTheDocument();
  });

  it("says nothing moved rather than hiding the card", async () => {
    show({ moves: [], market_days: [], headlines: [] });
    expect(await screen.findByText(/0 big moves · 0 new filings · 0 positive or negative headlines/)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Biggest moves" })).not.toBeInTheDocument();
  });

  it("warns when a company has no price for the latest day", async () => {
    show({ stale: [{ symbol: "TSLA", as_of: "2026-10-13" }] });
    expect(await screen.findByText("No price yet for the latest day for TSLA.")).toBeInTheDocument();
  });

  it("says so when no prices are stored", async () => {
    show({ as_of: null, window_start: null, moves: [], headlines: [] });
    expect(await screen.findByText("No prices are stored yet.")).toBeInTheDocument();
  });

  it("fails on its own with a retry that works, and still links to the page", async () => {
    let fail = true;
    mockApi({ "GET /api/changes": () => (fail ? json({ detail: "Database is down" }, 500) : changesData) });
    render(
      <MemoryRouter>
        <ChangesTeaser />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    expect(screen.getByRole("link", { name: /See everything that changed/ })).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/2 big moves/)).toBeInTheDocument();
  });
});
