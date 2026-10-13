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
    const [first, second] = bodies(fetchMock);
    expect(first).toEqual({ question: "First question?", symbols: ["NVDA", "TSLA"] }); // nothing earlier to follow up on
    expect(second).toMatchObject({ question: "Second question?" });
    expect(second).not.toHaveProperty("symbols"); // no companies chosen means all
    expect(second.history).toHaveLength(1); // the first question comes along so a follow-up can be understood
    expect(second.history[0]).toMatchObject({ question: "First question?" });
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

  describe("follow-ups", () => {
    const reply = (n: number) => copilotAnswer({ answer: `Answer ${n} [1].`, companies: ["TSLA"] });

    async function askAndWait(result: { current: ReturnType<typeof useConversation> }, q: string, symbols: string[] = []) {
      act(() => void result.current.ask(q, symbols));
      await waitFor(() => expect(result.current.busy).toBe(false));
    }

    it("sends the earlier questions of this topic so a follow-up can be understood", async () => {
      let n = 0;
      const fetchMock = mockApi({ "POST /api/copilot": () => reply(++n) });
      const { result } = renderHook(() => useConversation());
      await askAndWait(result, "How many employees does Tesla have?");
      await askAndWait(result, "And what about its risks?");
      await askAndWait(result, "What about its competition?");

      const [first, second, third] = bodies(fetchMock);
      expect(first).not.toHaveProperty("history");
      expect(second.history).toEqual([{ question: "How many employees does Tesla have?", answer: "Answer 1 .", companies: ["TSLA"] }]);
      expect(third.history.map((t: { question: string }) => t.question)).toEqual(["How many employees does Tesla have?", "And what about its risks?"]);
      expect(result.current.contextTurns).toBe(3);
    });

    it("starts a new topic: earlier questions stay on screen but are no longer sent", async () => {
      const fetchMock = mockApi({ "POST /api/copilot": () => reply(1) });
      const { result } = renderHook(() => useConversation());
      await askAndWait(result, "How many employees does Tesla have?");
      expect(result.current.contextTurns).toBe(1);

      act(() => result.current.newTopic());
      expect(result.current.topic).toBe(1);
      expect(result.current.contextTurns).toBe(0);
      expect(result.current.exchanges).toHaveLength(1); // still on screen

      await askAndWait(result, "What are NVIDIA's risks?");
      expect(bodies(fetchMock)[1]).not.toHaveProperty("history");
      expect(result.current.exchanges.map((e) => e.topic)).toEqual([0, 1]);
      expect(result.current.contextTurns).toBe(1);
    });

    it("remembers the topic after a reload, even before another question is asked", async () => {
      mockApi({ "POST /api/copilot": () => reply(1) });
      const first = renderHook(() => useConversation());
      await askAndWait(first.result, "How many employees does Tesla have?");
      act(() => first.result.current.newTopic());
      first.unmount();

      const second = renderHook(() => useConversation());
      expect(second.result.current.topic).toBe(1);
      expect(second.result.current.contextTurns).toBe(0);
    });

    it("doesn't change topic while an answer is being written", () => {
      mockApi({ "POST /api/copilot": () => new Promise(() => undefined) });
      const { result } = renderHook(() => useConversation());
      act(() => void result.current.ask("How many employees does Tesla have?", []));
      act(() => result.current.newTopic());
      expect(result.current.topic).toBe(0);
    });

    it("retries a question with only what came before it, in its own topic", async () => {
      let calls = 0;
      const fetchMock = mockApi({
        "POST /api/copilot": () => (++calls === 2 ? json({ detail: "boom" }, 500) : reply(calls)),
      });
      const { result } = renderHook(() => useConversation());
      await askAndWait(result, "First question here?");
      await askAndWait(result, "Second question here?"); // fails
      await askAndWait(result, "Third question here?");
      expect(result.current.exchanges.map((e) => e.status)).toEqual(["done", "error", "done"]);

      act(() => result.current.retry(result.current.exchanges[1].id));
      await waitFor(() => expect(result.current.exchanges[1].status).toBe("done"));
      const retryBody = bodies(fetchMock).at(-1);
      expect(retryBody.question).toBe("Second question here?");
      expect(retryBody.history.map((t: { question: string }) => t.question)).toEqual(["First question here?"]); // not the third
    });

    it("clearing resets the topic as well", async () => {
      mockApi({ "POST /api/copilot": () => reply(1) });
      const { result } = renderHook(() => useConversation());
      await askAndWait(result, "How many employees does Tesla have?");
      act(() => result.current.newTopic());
      act(() => result.current.clear());
      expect(result.current.topic).toBe(0);
      await waitFor(() => expect(window.localStorage.length).toBe(0));
    });
  });
});
