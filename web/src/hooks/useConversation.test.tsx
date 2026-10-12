import { act, renderHook, waitFor } from "@testing-library/react";
import { useConversation } from "./useConversation";
import { STORAGE_KEY } from "../lib/conversation";
import { copilotAnswer, json, mockApi } from "../test/mockApi";

const bodies = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => JSON.parse(String(init?.body)));

describe("useConversation", () => {
  it("sends a question, shows it as waiting, then stores the answer", async () => {
    let release!: (v: unknown) => void;
    mockApi({ "POST /api/copilot": () => new Promise((resolve) => (release = resolve)) });
    const { result } = renderHook(() => useConversation());

    let problem: string | null = "unset";
    act(() => {
      problem = result.current.ask("  What are the risks?  ", []);
    });
    expect(problem).toBeNull();
    expect(result.current.busy).toBe(true);
    expect(result.current.exchanges).toMatchObject([{ question: "What are the risks?", status: "pending" }]);

    await act(async () => release(copilotAnswer()));
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.exchanges[0]).toMatchObject({ status: "done", result: { grounded: true } });
  });

  it("sends the chosen companies, or none for 'all companies'", async () => {
    const fetchMock = mockApi({ "POST /api/copilot": copilotAnswer() });
    const { result } = renderHook(() => useConversation());
    act(() => void result.current.ask("First question?", ["NVDA", "TSLA"]));
    await waitFor(() => expect(result.current.busy).toBe(false));
    act(() => void result.current.ask("Second question?", []));
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(bodies(fetchMock)).toEqual([
      { question: "First question?", symbols: ["NVDA", "TSLA"] },
      { question: "Second question?" },
    ]);
  });

  it("rejects bad questions without calling the API", () => {
    const fetchMock = mockApi({ "POST /api/copilot": copilotAnswer() });
    const { result } = renderHook(() => useConversation());
    expect(result.current.ask("hi", [])).toMatch(/at least 3 characters/);
    expect(result.current.ask("x".repeat(501), [])).toMatch(/under 500/);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.exchanges).toEqual([]);
  });

  it("allows only one question at a time, even for two calls in the same instant", async () => {
    const fetchMock = mockApi({ "POST /api/copilot": () => new Promise(() => undefined) });
    const { result } = renderHook(() => useConversation());
    let first: string | null = "unset";
    let second: string | null = "unset";
    act(() => {
      first = result.current.ask("First question?", []);
      second = result.current.ask("Second question?", []);
    });
    expect(first).toBeNull();
    expect(second).toMatch(/Wait for the current answer/);
    expect(bodies(fetchMock)).toHaveLength(1);
    expect(result.current.exchanges).toHaveLength(1);
  });

  it("records an error with the API's message, and retry replaces it with the answer", async () => {
    let calls = 0;
    mockApi({
      "POST /api/copilot": () => (++calls === 1 ? json({ detail: "The AI model isn't running. Start Ollama and try again." }, 503) : copilotAnswer()),
    });
    const { result } = renderHook(() => useConversation());
    act(() => void result.current.ask("What are the risks?", ["NVDA"]));
    await waitFor(() => expect(result.current.exchanges[0].status).toBe("error"));
    expect(result.current.exchanges[0].error).toContain("Start Ollama");

    const id = result.current.exchanges[0].id;
    act(() => result.current.retry(id));
    await waitFor(() => expect(result.current.exchanges[0].status).toBe("done"));
    expect(result.current.exchanges).toHaveLength(1); // replaced in place, not added again
    expect(result.current.exchanges[0].error).toBeUndefined();
  });

  it("can stop a question that is waiting, which cancels the request", async () => {
    let signal: AbortSignal | null | undefined;
    mockApi({
      "POST /api/copilot": (_url: URL, init?: RequestInit) => {
        signal = init?.signal;
        return new Promise(() => undefined);
      },
    });
    const { result } = renderHook(() => useConversation());
    act(() => void result.current.ask("What are the risks?", []));
    expect(signal?.aborted).toBe(false);

    act(() => result.current.stop());
    expect(signal?.aborted).toBe(true);
    expect(result.current.exchanges[0].status).toBe("stopped");
    expect(result.current.busy).toBe(false);
    expect(result.current.ask("Another question?", [])).toBeNull(); // free to ask again
  });

  it("ignores stop and retry when they don't apply", () => {
    mockApi({});
    const { result } = renderHook(() => useConversation());
    act(() => result.current.stop());
    act(() => result.current.retry("nope"));
    expect(result.current.exchanges).toEqual([]);
  });

  it("clears everything and forgets the saved copy", async () => {
    mockApi({ "POST /api/copilot": copilotAnswer() });
    const { result } = renderHook(() => useConversation());
    act(() => void result.current.ask("What are the risks?", []));
    await waitFor(() => expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull());
    act(() => result.current.clear());
    expect(result.current.exchanges).toEqual([]);
    await waitFor(() => expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull());
  });

  it("brings the conversation back when the page is reopened, minus anything unfinished", async () => {
    mockApi({ "POST /api/copilot": (_u: URL, init?: RequestInit) => (JSON.parse(String(init?.body)).question === "Never answered?" ? new Promise(() => undefined) : copilotAnswer()) });
    const first = renderHook(() => useConversation());
    act(() => void first.result.current.ask("Answered question?", []));
    await waitFor(() => expect(first.result.current.exchanges[0]?.status).toBe("done"));
    act(() => void first.result.current.ask("Never answered?", []));
    expect(first.result.current.exchanges).toHaveLength(2);
    first.unmount();

    const second = renderHook(() => useConversation());
    expect(second.result.current.exchanges.map((e) => e.question)).toEqual(["Answered question?"]);
    expect(second.result.current.busy).toBe(false);
  });

  it("tells the page when the browser won't save the history", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    mockApi({ "POST /api/copilot": copilotAnswer() });
    const { result } = renderHook(() => useConversation());
    act(() => void result.current.ask("What are the risks?", []));
    await waitFor(() => expect(result.current.saveFailed).toBe(true));
    expect(result.current.exchanges[0].status).toBe("done"); // the answer still shows
  });

  it("cancels the request if the page is closed while waiting", () => {
    let signal: AbortSignal | null | undefined;
    mockApi({ "POST /api/copilot": (_u: URL, init?: RequestInit) => ((signal = init?.signal), new Promise(() => undefined)) });
    const { result, unmount } = renderHook(() => useConversation());
    act(() => void result.current.ask("What are the risks?", []));
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
