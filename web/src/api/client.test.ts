import { api, ApiError, isAbort } from "./client";
import { json, mockApi } from "../test/mockApi";

describe("api client", () => {
  it("explains a connection failure in plain words", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.stocks()).rejects.toMatchObject({ name: "ApiError", status: 0, message: expect.stringContaining("python -m api") });
  });

  it("passes through the API's own error message", async () => {
    mockApi({ "POST /api/copilot": json({ detail: "The AI model isn't running. Start Ollama and try again." }, 503) });
    const error = await api.copilot({ question: "hello there" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, message: "The AI model isn't running. Start Ollama and try again." });
  });

  it("does not show raw validation output to users", async () => {
    mockApi({ "GET /api/stocks": json({ detail: [{ loc: ["query", "x"], msg: "bad" }] }, 422) });
    await expect(api.stocks()).rejects.toMatchObject({ message: "That request wasn't valid." });
  });

  it("copes with an error body that isn't JSON", async () => {
    mockApi({ "GET /api/stocks": new Response("<html>oops</html>", { status: 500 }) });
    await expect(api.stocks()).rejects.toMatchObject({ status: 500, message: "The API returned an error (500)." });
  });

  it("says the API isn't running when the dev proxy can't reach it (502/504 with no message)", async () => {
    mockApi({ "GET /api/stocks": new Response("", { status: 502 }), "GET /api/news": new Response("", { status: 504 }) });
    await expect(api.stocks()).rejects.toMatchObject({ status: 502, message: expect.stringContaining("python -m api") });
    await expect(api.news({})).rejects.toMatchObject({ status: 504, message: expect.stringContaining("python -m api") });
  });

  it("still shows a message the API itself sent with a 502", async () => {
    mockApi({ "POST /api/copilot": json({ detail: "The model returned nothing." }, 502) });
    await expect(api.copilot({ question: "valid question" })).rejects.toMatchObject({ message: "The model returned nothing." });
  });

  it("builds the news query with repeated sentiment filters", async () => {
    const fetchMock = mockApi({ "GET /api/news": [] });
    await api.news({ days: 3, limit: 12, sentiment: ["positive", "negative"] });
    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.searchParams.get("days")).toBe("3");
    expect(url.searchParams.getAll("sentiment")).toEqual(["positive", "negative"]);
  });

  it("leaves aborts alone so callers can ignore them", async () => {
    const abort = new DOMException("aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));
    const error = await api.stocks().catch((e) => e);
    expect(isAbort(error)).toBe(true);
  });

  it("encodes the ticker in the path", async () => {
    const fetchMock = mockApi({});
    await api.prices("A/B", "1M").catch(() => undefined);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/stocks/A%2FB/prices?range=1M");
  });
});
