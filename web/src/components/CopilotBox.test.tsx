import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CopilotBox } from "./CopilotBox";
import { AnswerText } from "./AnswerText";
import { copilotAnswer, json, mockApi } from "../test/mockApi";

async function ask(text: string) {
  await userEvent.type(screen.getByRole("textbox", { name: "Your question" }), text);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("CopilotBox", () => {
  it("shows a cited answer with its sources and the disclaimer", async () => {
    const fetchMock = mockApi({ "POST /api/copilot": copilotAnswer() });
    render(<CopilotBox />);
    await ask("How many employees does NVIDIA have?");

    expect(await screen.findByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
    expect(screen.getByText("Searched filings for NVDA")).toBeInTheDocument();
    const source = screen.getByRole("list", { name: "Sources" });
    expect(source).toHaveTextContent("NVDA 10-K filed 2026-02-25 · Part I, Item 1");
    expect(screen.getByRole("link", { name: "View filing" })).toHaveAttribute("href", "https://www.sec.gov/x");
    expect(screen.getByText(/not financial advice/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ question: "How many employees does NVIDIA have?" });
  });

  it("highlights the source when a citation is clicked", async () => {
    mockApi({ "POST /api/copilot": copilotAnswer() });
    render(<CopilotBox />);
    await ask("How many employees does NVIDIA have?");
    await userEvent.click(await screen.findByRole("button", { name: "Show source 1" }));
    expect(screen.getByRole("list", { name: "Sources" }).querySelector("li")).toHaveClass("highlight");
  });

  it("warns when figures aren't found in the cited passages", async () => {
    mockApi({ "POST /api/copilot": copilotAnswer({ unverified_numbers: ["49.9"], answer: "Revenue grew $49.9 billion [1]." }) });
    render(<CopilotBox />);
    await ask("How much did revenue grow?");
    expect(await screen.findByRole("alert")).toHaveTextContent(/figures in this answer weren't found.*49\.9/);
  });

  it("warns when an answer cites nothing", async () => {
    mockApi({ "POST /api/copilot": copilotAnswer({ grounded: false, answer: "Probably fine.", sources: [] }) });
    render(<CopilotBox />);
    await ask("Is it fine?");
    expect(await screen.findByRole("alert")).toHaveTextContent("doesn't cite any filing passages");
  });

  it("treats a refusal as information, not an error or a warning", async () => {
    mockApi({
      "POST /api/copilot": copilotAnswer({
        refused: true, grounded: false, companies: [], sources: [],
        answer: "I couldn't find passages in the stored filings that address that question, so I won't guess.",
      }),
    });
    render(<CopilotBox />);
    await ask("What is the best pizza recipe?");
    expect(await screen.findByText(/I won't guess/)).toBeInTheDocument();
    expect(screen.getByText("No matching passages found")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the API's message when the AI model is offline", async () => {
    mockApi({ "POST /api/copilot": json({ detail: "The AI model isn't running. Start Ollama and try again." }, 503) });
    render(<CopilotBox />);
    await ask("What are the risks?");
    expect(await screen.findByRole("alert")).toHaveTextContent("Start Ollama");
  });

  it("asks for a longer question without calling the API", async () => {
    const fetchMock = mockApi({ "POST /api/copilot": copilotAnswer() });
    render(<CopilotBox />);
    await ask("hi");
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 3 characters");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("runs an example question with one click", async () => {
    const fetchMock = mockApi({ "POST /api/copilot": copilotAnswer() });
    render(<CopilotBox />);
    await userEvent.click(screen.getByRole("button", { name: "What are NVIDIA's biggest risks?" }));
    await screen.findByText(/As of fiscal 2026 NVIDIA had/);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).question).toBe("What are NVIDIA's biggest risks?");
    expect(screen.getByRole("textbox", { name: "Your question" })).toHaveValue("What are NVIDIA's biggest risks?");
  });

  it("disables asking while an answer is on its way, and a newer answer replaces an older one", async () => {
    let release!: (r: unknown) => void;
    mockApi({ "POST /api/copilot": () => new Promise((resolve) => (release = resolve)) });
    render(<CopilotBox />);
    await ask("What are the risks?");
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    expect(screen.getByText(/This can take a few seconds/)).toBeInTheDocument();
    release(copilotAnswer());
    expect(await screen.findByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });
});

describe("AnswerText", () => {
  it("renders bold and citations but never raw HTML", () => {
    const onCite = vi.fn();
    const { container } = render(
      <AnswerText text={'**Apple**: risk [1][2] <img src=x onerror="alert(1)"> <b>bold?</b>'} onCite={onCite} />,
    );
    expect(screen.getByText("Apple").tagName).toBe("STRONG");
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)"> <b>bold?</b>');
  });

  it("reports which citation was clicked", async () => {
    const onCite = vi.fn();
    render(<AnswerText text="Fact [3]." onCite={onCite} />);
    await userEvent.click(screen.getByRole("button", { name: "Show source 3" }));
    expect(onCite).toHaveBeenCalledWith(3);
  });
});
