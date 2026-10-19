import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { RemoveCompany } from "./RemoveCompany";
import { json, mockApi } from "../test/mockApi";

const removed = {
  symbol: "TSLA",
  name: "Tesla, Inc.",
  kept: { prices: 1250, filings: 14, headlines: 310, figures: 900 },
  message: "TSLA (Tesla, Inc.) is no longer tracked. Its stored data was kept; add it again from \"Add a company\" to track it again.",
};

describe("RemoveCompany", () => {
  it("asks first, says nothing is deleted, and sends nothing until confirmed", async () => {
    const fetchMock = mockApi({ "POST /api/remove-company": removed });
    render(<RemoveCompany symbol="TSLA" name="Tesla, Inc." onRemoved={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Stop tracking TSLA" }));
    expect(screen.getByText(/Stop tracking Tesla, Inc\. \(TSLA\)\?/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is deleted/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cancelling goes back without calling the API", async () => {
    const fetchMock = mockApi({});
    render(<RemoveCompany symbol="TSLA" name={null} onRemoved={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Stop tracking TSLA" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Stop tracking TSLA" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("confirming sends the ticker once and reports the result", async () => {
    const onRemoved = vi.fn();
    const fetchMock = mockApi({ "POST /api/remove-company": removed });
    render(<RemoveCompany symbol="TSLA" name="Tesla, Inc." onRemoved={onRemoved} />);

    await userEvent.click(screen.getByRole("button", { name: "Stop tracking TSLA" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));

    await vi.waitFor(() => expect(onRemoved).toHaveBeenCalledWith(removed));
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ ticker: "TSLA" });
  });

  it("shows the API's own message when it is busy, and lets you try again", async () => {
    let calls = 0;
    mockApi({
      "POST /api/remove-company": () =>
        ++calls === 1 ? json({ detail: "Another update is running (the nightly refresh, a backup, or another add). Try again in a few minutes." }, 409) : removed,
    });
    const onRemoved = vi.fn();
    render(<RemoveCompany symbol="TSLA" name="Tesla, Inc." onRemoved={onRemoved} />);

    await userEvent.click(screen.getByRole("button", { name: "Stop tracking TSLA" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another update is running");
    expect(onRemoved).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(onRemoved).toHaveBeenCalledWith(removed));
  });

  it("cannot be confirmed twice while the request is running", async () => {
    let release: (value: unknown) => void = () => {};
    const fetchMock = mockApi({ "POST /api/remove-company": () => new Promise((resolve) => (release = resolve)) });
    render(<RemoveCompany symbol="TSLA" name="Tesla, Inc." onRemoved={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Stop tracking TSLA" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));
    expect(screen.getByRole("button", { name: "Removing..." })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    release(removed);
  });
});
