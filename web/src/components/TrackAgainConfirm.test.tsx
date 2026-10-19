import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { TrackAgainConfirm } from "./TrackAgainConfirm";
import { json, mockApi } from "../test/mockApi";

const job = (over: Record<string, unknown> = {}) => ({
  job_id: 7,
  symbol: "TSLA",
  status: "running",
  step: "prices",
  started_at: "2026-10-19T18:00:00Z",
  finished_at: null,
  companies: [],
  message: null,
  ...over,
});

function show(over: { onDone?: () => void; onCancel?: () => void } = {}) {
  const props = { onDone: vi.fn(), onCancel: vi.fn(), ...over };
  render(<TrackAgainConfirm symbol="TSLA" name="Tesla, Inc." pollMs={5} {...props} />);
  return props;
}

describe("TrackAgainConfirm", () => {
  it("asks first, explains the wait, and starts nothing until confirmed", () => {
    const fetchMock = mockApi({});
    show();
    expect(screen.getByText("Track Tesla, Inc. (TSLA) again?")).toBeInTheDocument();
    expect(screen.getByText(/takes a few minutes and needs Ollama running/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cancelling calls onCancel without calling the API", async () => {
    const fetchMock = mockApi({});
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("confirming starts the add once, shows progress, and reports when it finishes", async () => {
    let polls = 0;
    const fetchMock = mockApi({
      "POST /api/add-company/jobs": job({ status: "queued", step: null }),
      "GET /api/add-company/jobs/7": () => (++polls < 3 ? job({ step: "news" }) : job({ status: "success", step: null })),
    });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));

    expect(await screen.findByText(/Updating TSLA…/)).toBeInTheDocument();
    await vi.waitFor(() => expect(props.onDone).toHaveBeenCalledTimes(1));
    expect(props.onDone).toHaveBeenCalledWith(expect.objectContaining({ status: "success" }));
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ ticker: "TSLA" });
    expect(polls).toBeGreaterThanOrEqual(3);
  });

  it("names the step that is running", async () => {
    mockApi({ "POST /api/add-company/jobs": job({ step: "filings" }), "GET /api/add-company/jobs/7": job({ step: "filings" }) });
    show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    expect(await screen.findByText(/Working on: filings/)).toBeInTheDocument();
  });

  it("counts an add that finished with gaps as tracked again", async () => {
    mockApi({ "POST /api/add-company/jobs": job({ status: "partial", finished_at: "2026-10-19T18:04:00Z" }) });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    await vi.waitFor(() => expect(props.onDone).toHaveBeenCalledTimes(1));
  });

  it("does not report done when the add failed, and offers another try", async () => {
    mockApi({
      "POST /api/add-company/jobs": job({ status: "failed", message: "The add ended without a report. See logs/add_company.log." }),
    });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The add ended without a report");
    expect(props.onDone).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("does not report done when the add was interrupted", async () => {
    mockApi({
      "POST /api/add-company/jobs": job({ status: "running" }),
      "GET /api/add-company/jobs/7": job({ status: "interrupted", message: "The add stopped before it finished." }),
    });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The add stopped before it finished");
    expect(props.onDone).not.toHaveBeenCalled();
  });

  it("shows the API's message when another update is running, and retries", async () => {
    let calls = 0;
    mockApi({
      "POST /api/add-company/jobs": () =>
        ++calls === 1 ? json({ detail: "Another update is running (the nightly refresh, a backup, or another add). Try again in a few minutes." }, 409) : job({ status: "success" }),
    });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another update is running");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await vi.waitFor(() => expect(props.onDone).toHaveBeenCalledTimes(1));
  });

  it("keeps going when one progress check fails", async () => {
    let polls = 0;
    mockApi({
      "POST /api/add-company/jobs": job(),
      "GET /api/add-company/jobs/7": () => (++polls === 1 ? new Response("", { status: 500 }) : job({ status: "success" })),
    });
    const props = show();
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    await vi.waitFor(() => expect(props.onDone).toHaveBeenCalledTimes(1));
  });
});

describe("TrackAgainConfirm reports when it is busy", () => {
  it("says running from the moment it starts until it ends, and not running when it fails", async () => {
    const onRunning = vi.fn();
    mockApi({ "POST /api/add-company/jobs": job({ status: "failed", message: "It failed." }) });
    render(<TrackAgainConfirm symbol="TSLA" name={null} onDone={vi.fn()} onCancel={vi.fn()} onRunning={onRunning} pollMs={5} />);
    expect(onRunning).toHaveBeenLastCalledWith(false); // asking: not running yet
    await userEvent.click(screen.getByRole("button", { name: "Yes, track TSLA again" }));
    await screen.findByRole("alert");
    expect(onRunning.mock.calls.map(([v]) => v)).toContain(true);
    expect(onRunning).toHaveBeenLastCalledWith(false);
  });
});
