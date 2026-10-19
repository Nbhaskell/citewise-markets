import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { StopTrackingConfirm } from "./StopTrackingConfirm";
import { json, mockApi } from "../test/mockApi";

const removed = {
  symbol: "TSLA",
  name: "Tesla, Inc.",
  kept: { prices: 1250, filings: 14, headlines: 310, figures: 900 },
  message: "TSLA (Tesla, Inc.) is no longer tracked. Its stored data was kept.",
};

function show(over: { onRemoved?: () => void; onCancel?: () => void; name?: string | null } = {}) {
  const props = { onRemoved: vi.fn(), onCancel: vi.fn(), ...over };
  render(<StopTrackingConfirm symbol="TSLA" name={over.name === undefined ? "Tesla, Inc." : over.name} {...props} />);
  return props;
}

describe("StopTrackingConfirm", () => {
  it("asks first, says nothing is deleted, and sends nothing until confirmed", () => {
    const fetchMock = mockApi({ "POST /api/remove-company": removed });
    show();
    expect(screen.getByText("Stop tracking Tesla, Inc. (TSLA)?")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is deleted/)).toBeInTheDocument();
    expect(screen.getByText(/switch TSLA back on from the "Not tracked" list/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("falls back to the ticker when the company has no name", () => {
    show({ name: null });
    expect(screen.getByText("Stop tracking TSLA?")).toBeInTheDocument();
  });

  it("cancelling calls onCancel without calling the API", async () => {
    const fetchMock = mockApi({});
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("confirming sends the ticker once and reports the result", async () => {
    const fetchMock = mockApi({ "POST /api/remove-company": removed });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));

    await vi.waitFor(() => expect(props.onRemoved).toHaveBeenCalledWith(removed));
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
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another update is running");
    expect(props.onRemoved).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(props.onRemoved).toHaveBeenCalledWith(removed));
  });

  it("cannot be confirmed twice or cancelled while the request is running", async () => {
    let release: (value: unknown) => void = () => {};
    const fetchMock = mockApi({ "POST /api/remove-company": () => new Promise((resolve) => (release = resolve)) });
    show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, stop tracking TSLA" }));
    expect(screen.getByRole("button", { name: "Removing..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    release(removed);
  });
});
