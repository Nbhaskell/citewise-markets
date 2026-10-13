import { copilotAnswer } from "../test/mockApi";
import {
  loadExchanges, MAX_SAVED, newExchangeId, questionProblem, saveExchanges, STORAGE_KEY, type Exchange,
} from "./conversation";

const done = (n: number): Exchange => ({
  id: `id-${n}`, question: `Question ${n}?`, symbols: [], askedAt: "2026-10-12T20:00:00.000Z", status: "done", result: copilotAnswer(),
});
const stored = () => window.localStorage.getItem(STORAGE_KEY);

describe("saving and loading", () => {
  it("round-trips finished exchanges in order", () => {
    const list: Exchange[] = [
      done(1),
      { id: "e", question: "Bad one?", symbols: ["NVDA"], askedAt: "2026-10-12T20:01:00.000Z", status: "error", error: "boom" },
      { id: "s", question: "Stopped?", symbols: [], askedAt: "2026-10-12T20:02:00.000Z", status: "stopped" },
    ];
    expect(saveExchanges(list)).toBe(true);
    expect(loadExchanges()).toEqual(list);
  });

  it("never saves a question that is still waiting for its answer", () => {
    const pending: Exchange = { id: "p", question: "Waiting?", symbols: [], askedAt: "2026-10-12T20:00:00.000Z", status: "pending" };
    saveExchanges([done(1), pending]);
    // Look at the raw saved data: loading also discards unfinished entries, which would hide a bug in saving.
    expect(JSON.parse(stored()!).map((e: Exchange) => e.id)).toEqual(["id-1"]);
    saveExchanges([pending]);
    expect(stored()).toBeNull();
  });

  it("keeps only the newest 20", () => {
    saveExchanges(Array.from({ length: 25 }, (_, i) => done(i)));
    const loaded = loadExchanges();
    expect(loaded).toHaveLength(MAX_SAVED);
    expect(loaded[0].id).toBe("id-5");
    expect(loaded.at(-1)?.id).toBe("id-24");
  });

  it("removes the saved copy when there is nothing left to save", () => {
    saveExchanges([done(1)]);
    expect(stored()).not.toBeNull();
    saveExchanges([]);
    expect(stored()).toBeNull();
  });
});

describe("saved data can't be trusted", () => {
  it.each([
    ["nothing saved", null],
    ["not JSON", "{{{ nope"],
    ["JSON of the wrong shape", JSON.stringify({ hello: "world" })],
    ["null", "null"],
  ])("returns an empty list for %s", (_name, raw) => {
    if (raw !== null) window.localStorage.setItem(STORAGE_KEY, raw);
    expect(loadExchanges()).toEqual([]);
  });

  it("drops damaged entries and keeps the good ones", () => {
    const good = done(1);
    const damaged = [
      42,
      null,
      { ...good, id: 7 },
      { ...good, symbols: "NVDA" },
      { ...good, status: "weird" },
      { ...good, result: undefined },
      { ...good, result: { ...good.result, sources: [{ number: "1" }] } },
      { ...good, result: { ...good.result, companies: [1, 2] } },
      { id: "e", question: "q", symbols: [], askedAt: "t", status: "error" }, // an error with no message
      { ...good, status: "pending" }, // pending entries are never valid on disk
    ];
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([damaged[0], damaged[1], ...damaged.slice(2), good, done(2)]));
    expect(loadExchanges().map((e) => e.id)).toEqual(["id-1", "id-2"]);
  });

  it("copes with storage that is blocked or throws", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("Access denied");
    });
    expect(loadExchanges()).toEqual([]);
    expect(saveExchanges([done(1)])).toBe(false);
  });

  it("reports a failed save when storage is full", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    expect(saveExchanges([done(1)])).toBe(false);
  });
});

describe("questionProblem", () => {
  it("accepts reasonable questions and explains why it rejects others", () => {
    expect(questionProblem("What are the risks?")).toBeNull();
    expect(questionProblem("   hi ")).toMatch(/at least 3 characters/);
    expect(questionProblem("")).toMatch(/at least 3 characters/);
    expect(questionProblem("x".repeat(501))).toMatch(/under 500 characters/);
    expect(questionProblem("x".repeat(500))).toBeNull();
  });
});

describe("newExchangeId", () => {
  it("never repeats", () => {
    expect(new Set(Array.from({ length: 100 }, newExchangeId)).size).toBe(100);
  });
});

// ---- history for follow-ups ----
import { buildHistory, loadTopic, saveTopic, TOPIC_KEY } from "./conversation";

const withTopic = (n: number, topic: number, over: Partial<Exchange> = {}): Exchange => ({ ...done(n), topic, ...over });
const answerOf = (text: string, over = {}) => copilotAnswer({ answer: text, companies: ["TSLA"], ...over });

describe("buildHistory", () => {
  it("sends the newest three finished answers from the current topic, oldest first", () => {
    const list = [0, 1, 2, 3, 4].map((n) => withTopic(n, 0));
    expect(buildHistory(list, 0).map((t) => t.question)).toEqual(["Question 2?", "Question 3?", "Question 4?"]);
  });

  it("ignores other topics, unfinished or failed questions, and refusals", () => {
    const list: Exchange[] = [
      withTopic(1, 0),
      withTopic(2, 1),
      withTopic(3, 0, { status: "error", result: undefined, error: "boom" }),
      withTopic(4, 0, { status: "stopped", result: undefined }),
      withTopic(5, 0, { status: "pending", result: undefined }),
      withTopic(6, 0, { result: copilotAnswer({ refused: true, answer: "I couldn't find passages" }) }),
      withTopic(7, 0),
    ];
    expect(buildHistory(list, 0).map((t) => t.question)).toEqual(["Question 1?", "Question 7?"]);
    expect(buildHistory(list, 1).map((t) => t.question)).toEqual(["Question 2?"]);
  });

  it("treats saved questions with no topic as topic 0", () => {
    expect(buildHistory([done(1)], 0)).toHaveLength(1);
    expect(buildHistory([done(1)], 1)).toHaveLength(0);
  });

  it("removes citation markers, trims long answers, and passes the companies along", () => {
    const long = "word ".repeat(600);
    const [turn] = buildHistory([withTopic(1, 0, { result: answerOf(`Tesla had 134,785 employees [1][2, 3]. ${long}`) })], 0);
    expect(turn.answer).not.toMatch(/\[\d/);
    expect(turn.answer.startsWith("Tesla had 134,785 employees .")).toBe(true);
    expect(turn.answer.length).toBeLessThanOrEqual(1500);
    expect(turn.companies).toEqual(["TSLA"]);
  });

  it("never sends more than five companies for a turn", () => {
    const six = ["A", "B", "C", "D", "E", "F"];
    expect(buildHistory([withTopic(1, 0, { result: answerOf("x", { companies: six }) })], 0)[0].companies).toHaveLength(5);
  });

  it("is empty when there is nothing to follow up on", () => {
    expect(buildHistory([], 0)).toEqual([]);
  });
});

describe("topic storage", () => {
  it("continues the newest topic seen in saved questions, or the saved marker if that is higher", () => {
    expect(loadTopic([])).toBe(0);
    expect(loadTopic([withTopic(1, 0), withTopic(2, 3)])).toBe(3);
    saveTopic(5);
    expect(loadTopic([withTopic(1, 0)])).toBe(5);
    expect(window.localStorage.getItem(TOPIC_KEY)).toBe("5");
  });

  it("forgets the marker at topic zero and ignores a damaged one", () => {
    saveTopic(2);
    saveTopic(0);
    expect(window.localStorage.getItem(TOPIC_KEY)).toBeNull();
    window.localStorage.setItem(TOPIC_KEY, "banana");
    expect(loadTopic([])).toBe(0);
    window.localStorage.setItem(TOPIC_KEY, "-4");
    expect(loadTopic([])).toBe(0);
  });

  it("survives storage that throws", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("Access denied");
    });
    expect(loadTopic([withTopic(1, 2)])).toBe(2);
    expect(() => saveTopic(3)).not.toThrow();
  });

  it("rejects saved questions whose topic isn't a whole number", () => {
    const base = done(1);
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ ...base, id: "a", topic: 2 }, { ...base, id: "b", topic: "x" }, { ...base, id: "c", topic: -1 }, { ...base, id: "d", topic: 1.5 }]),
    );
    expect(loadExchanges().map((e) => e.id)).toEqual(["a"]);
  });
});
