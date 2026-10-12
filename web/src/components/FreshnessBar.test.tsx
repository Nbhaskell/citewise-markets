import { render, screen } from "@testing-library/react";
import { FreshnessBar } from "./FreshnessBar";
import { defaultRoutes, json, mockApi, okHealth, okStatus } from "../test/mockApi";

describe("FreshnessBar", () => {
  it("shows how current the data is when everything is healthy", async () => {
    mockApi(defaultRoutes());
    render(<FreshnessBar />);
    expect(await screen.findByText(/Prices through \d{4}-\d{2}-\d{2} · last refresh/)).toBeInTheDocument();
    expect(screen.queryByText(/out of date/)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI model offline/)).not.toBeInTheDocument();
  });

  it("flags a refresh that had problems", async () => {
    const run = { ...okStatus.runs[0], status: "partial", problems: 2 };
    mockApi({ ...defaultRoutes(), "GET /api/status": { ...okStatus, runs: [run] } });
    render(<FreshnessBar />);
    expect(await screen.findByText(/finished as "partial" with 2 problem\(s\)/)).toBeInTheDocument();
  });

  it("flags a refresh that has never run", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/status": { ...okStatus, runs: [] } });
    render(<FreshnessBar />);
    expect(await screen.findByText(/hasn't run yet/)).toBeInTheDocument();
  });

  it("flags old prices", async () => {
    const old = { ...okStatus.companies[0], last_price_date: "2020-01-02" };
    mockApi({ ...defaultRoutes(), "GET /api/status": { ...okStatus, companies: [old] } });
    render(<FreshnessBar />);
    expect(await screen.findByText("Prices look out of date.")).toBeInTheDocument();
  });

  it("says when the AI model is offline", async () => {
    mockApi({ ...defaultRoutes(), "GET /health": { ...okHealth, ai_model_available: false } });
    render(<FreshnessBar />);
    expect(await screen.findByText(/AI model offline/)).toBeInTheDocument();
  });

  it("shows the connection error instead of pretending all is well", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/status": json({ detail: "The database isn't reachable. Is Docker running?" }, 503) });
    render(<FreshnessBar />);
    expect(await screen.findByText(/database isn't reachable/)).toBeInTheDocument();
  });
});
