import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewsPanel } from "./NewsPanel";
import { defaultRoutes, mockApi } from "../test/mockApi";

describe("NewsPanel", () => {
  it("lists headlines with company, label, source and age", async () => {
    mockApi(defaultRoutes());
    render(<NewsPanel />);
    const link = await screen.findByRole("link", { name: "Nvidia wins a big contract" });
    const item = link.closest("li")!;
    expect(item).toHaveTextContent("NVDA");
    expect(item).toHaveTextContent("Positive");
    expect(item).toHaveTextContent("Yahoo Finance · 2h ago");
    expect(link).toHaveAttribute("href", "https://example.com/a");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("never turns an unsafe link into a clickable link", async () => {
    mockApi(defaultRoutes());
    render(<NewsPanel />);
    const title = await screen.findByText("Apple faces a probe");
    expect(title.closest("a")).toBeNull();
    expect(screen.getByText(/Unknown source · 1d ago/)).toBeInTheDocument();
  });

  it("starts with positive and negative headlines only, and can show everything", async () => {
    const fetchMock = mockApi(defaultRoutes());
    render(<NewsPanel />);
    await screen.findByText("Nvidia wins a big contract");
    const firstQuery = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost").searchParams;
    expect(firstQuery.getAll("sentiment")).toEqual(["positive", "negative"]);

    await userEvent.click(screen.getByRole("checkbox", { name: /Positive and negative only/ }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1));
    const lastQuery = new URL(String(fetchMock.mock.calls.at(-1)![0]), "http://localhost").searchParams;
    expect(lastQuery.getAll("sentiment")).toEqual([]);
  });

  it("says why it's empty, depending on the filter", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/news": [] });
    render(<NewsPanel />);
    expect(await screen.findByText(/No positive or negative headlines in the last 3 days/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(await screen.findByText("No headlines in the last 3 days.")).toBeInTheDocument();
  });
});
