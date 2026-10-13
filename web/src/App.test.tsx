import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { defaultRoutes, mockApi } from "./test/mockApi";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App", () => {
  it("assembles the dashboard: freshness, watchlist, news, and the copilot", async () => {
    mockApi(defaultRoutes());
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Watchlist" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Latest news" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask the copilot" })).toBeInTheDocument();
    expect(await screen.findByRole("rowheader", { name: /NVDA/ })).toBeInTheDocument();
    expect(await screen.findByText(/Prices through/)).toBeInTheDocument();
    expect(screen.getByText(/Not financial advice/, { selector: "header span" })).toBeInTheDocument();
  });

  it("keeps working when one panel's data fails", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/news": new Response("boom", { status: 500 }) });
    renderAt("/");
    expect(await screen.findByRole("rowheader", { name: /AAPL/ })).toBeInTheDocument(); // watchlist still fine
    expect(await screen.findByText(/The API returned an error \(500\)/)).toBeInTheDocument(); // news shows its own error
    expect(screen.getByRole("textbox", { name: "Your question" })).toBeInTheDocument(); // copilot still usable
  });

  it("shows a friendly page for unknown addresses", async () => {
    mockApi(defaultRoutes());
    renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the dashboard" })).toHaveAttribute("href", "/");
  });

  it("has navigation between the dashboard and the copilot, and marks where you are", async () => {
    mockApi(defaultRoutes());
    renderAt("/copilot");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Copilot" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(await screen.findByRole("heading", { level: 1, name: "Copilot" })).toBeInTheDocument();
  });

  it("links the dashboard's copilot box to the full page", async () => {
    mockApi(defaultRoutes());
    renderAt("/");
    expect(await screen.findByRole("link", { name: /Open the full-page copilot/ })).toHaveAttribute("href", "/copilot");
    expect(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });
});
