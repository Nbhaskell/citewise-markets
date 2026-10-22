import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CopilotPage } from "./CopilotPage";
import { copilotAnswer, defaultRoutes, json, mockApi } from "../test/mockApi";

const page = () => (
  <MemoryRouter initialEntries={["/copilot"]}>
    <CopilotPage />
  </MemoryRouter>
);
const ask = async (text: string) => {
  await userEvent.type(screen.getByRole("textbox", { name: "Your question" }), `${text}{Enter}`);
};
const posts = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => JSON.parse(String(init?.body)));

describe("CopilotPage", () => {
  it("explains what it is, including that earlier questions only help understand a follow-up", async () => {
    mockApi(defaultRoutes());
    render(page());
    expect(screen.getByRole("heading", { level: 1, name: "Copilot" })).toBeInTheDocument();
    expect(screen.getByText(/You can follow up on your last few questions/)).toBeInTheDocument();
    expect(screen.getByText(/only to understand what you mean, never as evidence/)).toBeInTheDocument();
    expect(screen.getByText(/saved in this browser only/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask about your companies" })).toBeInTheDocument();
    expect(document.title).toBe("Copilot · Citewise for Markets");
  });

  it("answers an example question with one click and then shows the conversation", async () => {
    const fetchMock = mockApi({ ...defaultRoutes(), "POST /api/copilot": copilotAnswer() });
    render(page());
    await userEvent.click(screen.getByRole("button", { name: "What are NVIDIA's biggest risks?" }));
    expect(await screen.findByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ask about your companies" })).not.toBeInTheDocument();
    expect(posts(fetchMock)).toEqual([{ question: "What are NVIDIA's biggest risks?" }]);
  });

  it("keeps several questions in order, each with its own answer and sources", async () => {
    let n = 0;
    mockApi({ ...defaultRoutes(), "POST /api/copilot": () => copilotAnswer({ answer: `Answer number ${++n} [1].` }) });
    render(page());
    await ask("First question here");
    await screen.findByText(/Answer number 1/);
    await ask("Second question here");
    await screen.findByText(/Answer number 2/);

    const log = screen.getByRole("log", { name: "Conversation" });
    const text = log.textContent ?? "";
    expect(text.indexOf("First question here")).toBeLessThan(text.indexOf("Answer number 1"));
    expect(text.indexOf("Answer number 1")).toBeLessThan(text.indexOf("Second question here"));
    expect(text.indexOf("Second question here")).toBeLessThan(text.indexOf("Answer number 2"));
    expect(within(log).getAllByRole("list", { name: "Sources" })).toHaveLength(2);
  });

  it("limits questions to the selected companies and shows them on the message", async () => {
    const fetchMock = mockApi({ ...defaultRoutes(), "POST /api/copilot": copilotAnswer() });
    render(page());
    await userEvent.click(await screen.findByRole("button", { name: "NVDA" }));
    await userEvent.click(screen.getByRole("button", { name: "AAPL" }));
    await ask("Compare their risks");
    await screen.findByText(/As of fiscal 2026 NVIDIA had/);
    expect(posts(fetchMock)).toEqual([{ question: "Compare their risks", symbols: ["NVDA", "AAPL"] }]);
    expect(screen.getByText("Compare their risks").closest(".exchange")).toHaveTextContent("searching NVDA, AAPL");
  });

  it("still works when the company list can't load, just without the filter", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/stocks": json({ detail: "boom" }, 500), "POST /api/copilot": copilotAnswer() });
    render(page());
    await ask("What are the risks?");
    expect(await screen.findByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Search in" })).not.toBeInTheDocument();
  });

  it("shows the API's message when something fails and lets the user retry", async () => {
    let calls = 0;
    mockApi({
      ...defaultRoutes(),
      "POST /api/copilot": () => (++calls === 1 ? json({ detail: "The AI model isn't running. Start Ollama and try again." }, 503) : copilotAnswer()),
    });
    render(page());
    await ask("What are the risks?");
    expect(await screen.findByRole("alert")).toHaveTextContent("Start Ollama");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
    expect(screen.getAllByText("What are the risks?")).toHaveLength(1); // retried in place, not duplicated
  });

  it("can stop a slow answer and ask again", async () => {
    mockApi({ ...defaultRoutes(), "POST /api/copilot": () => new Promise(() => undefined) });
    render(page());
    await ask("What are the risks?");
    await userEvent.click(await screen.findByRole("button", { name: "Stop" }));
    expect(await screen.findByText(/Stopped before an answer arrived/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("locks the company filter and examples while an answer is being written", async () => {
    mockApi({ ...defaultRoutes(), "POST /api/copilot": () => new Promise(() => undefined) });
    render(page());
    await userEvent.click(screen.getByRole("button", { name: "How many employees does Tesla have?" }));
    expect(await screen.findByRole("group", { name: "Search in" })).toBeDisabled();
  });

  it("remembers the conversation after the page is closed and reopened", async () => {
    mockApi({ ...defaultRoutes(), "POST /api/copilot": copilotAnswer() });
    const first = render(page());
    await ask("What are the risks?");
    await screen.findByText(/As of fiscal 2026 NVIDIA had/);
    first.unmount();

    render(page());
    expect(screen.getByText("What are the risks?")).toBeInTheDocument();
    expect(screen.getByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
  });

  it("asks before clearing, and cancelling keeps everything", async () => {
    mockApi({ ...defaultRoutes(), "POST /api/copilot": copilotAnswer() });
    render(page());
    await ask("What are the risks?");
    await screen.findByText(/As of fiscal 2026 NVIDIA had/);

    await userEvent.click(screen.getByRole("button", { name: "Clear conversation" }));
    expect(screen.getByText(/Clear all 1 saved question\?/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("What are the risks?")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear conversation" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, clear" }));
    expect(screen.queryByText("What are the risks?")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask about your companies" })).toBeInTheDocument();
    await waitFor(() => expect(window.localStorage.length).toBe(0));
  });

  it("warns when the browser won't save the history", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    mockApi({ ...defaultRoutes(), "POST /api/copilot": copilotAnswer() });
    render(page());
    await ask("What are the risks?");
    expect(await screen.findByText(/won't let us save your history/)).toBeInTheDocument();
    expect(screen.getByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument(); // the answer still shows
  });

  it("shows warnings on an answer whose numbers don't check out", async () => {
    mockApi({
      ...defaultRoutes(),
      "POST /api/copilot": copilotAnswer({ unverified_numbers: ["49.9"], answer: "Revenue grew $49.9 billion [1]." }),
    });
    render(page());
    await ask("How much did revenue grow?");
    expect(await screen.findByRole("alert")).toHaveTextContent(/figures in this answer weren't found.*49\.9/);
  });

  it("ignores a saved conversation that has been tampered with", async () => {
    window.localStorage.setItem("stockmarket.copilot.v1", JSON.stringify([{ id: 1, question: { evil: true }, status: "done" }, "junk", null]));
    mockApi(defaultRoutes());
    render(page());
    expect(screen.getByRole("heading", { name: "Ask about your companies" })).toBeInTheDocument();
  });

  it("flags an answer to a follow-up that named no company, instead of letting it pass as about the last one", async () => {
    mockApi({
      ...defaultRoutes(),
      "POST /api/copilot": copilotAnswer({
        companies: [],
        answer: "Amazon's biggest risks include economic conditions [1].",
        sources: [{ ...copilotAnswer().sources[0], symbol: "AMZN" }],
      }),
    });
    render(page());
    await ask("And what about its biggest risks?");
    expect(await screen.findByText(/No company was named.*drew on AMZN/)).toBeInTheDocument();
  });

  it("lets a follow-up through with the earlier question, and shows how it was understood", async () => {
    let n = 0;
    const fetchMock = mockApi({
      ...defaultRoutes(),
      "POST /api/copilot": () =>
        ++n === 1
          ? copilotAnswer({ answer: "Tesla had 134,785 employees [1].", companies: ["TSLA"] })
          : copilotAnswer({ answer: "Tesla's risks include X [1].", companies: ["TSLA"], interpreted_question: "What are Tesla's biggest risks?" }),
    });
    render(page());
    await ask("How many employees does Tesla have?");
    await screen.findByText(/Tesla had 134,785 employees/);
    await ask("And what about its risks?");
    expect(await screen.findByText(/Understood as:/)).toBeInTheDocument();
    expect(document.querySelector(".interpreted")).toHaveTextContent("What are Tesla's biggest risks?");
    expect(posts(fetchMock)[1].history).toEqual([
      { question: "How many employees does Tesla have?", answer: "Tesla had 134,785 employees .", companies: ["TSLA"] },
    ]);
  });

  it("says how many earlier questions a follow-up can use, and lets the user start a new topic", async () => {
    const fetchMock = mockApi({ ...defaultRoutes(), "POST /api/copilot": copilotAnswer() });
    render(page());
    expect(screen.queryByRole("button", { name: "Start a new topic" })).not.toBeInTheDocument(); // nothing to continue yet

    await ask("First question here");
    await screen.findByText(/As of fiscal 2026 NVIDIA had/);
    expect(screen.getByText("Follow-ups can use your last 1 question in this topic.")).toBeInTheDocument();
    await ask("Second question here");
    await waitFor(() => expect(screen.getByText("Follow-ups can use your last 2 questions in this topic.")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Start a new topic" }));
    expect(screen.getByText(/nothing earlier in this topic to follow up on/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start a new topic" })).toBeDisabled();

    await ask("Third question here");
    await waitFor(() => expect(posts(fetchMock)).toHaveLength(3));
    expect(posts(fetchMock)[2]).not.toHaveProperty("history");
    expect(screen.getByLabelText("New topic")).toBeInTheDocument();
  });
});
