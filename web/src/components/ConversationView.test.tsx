import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConversationView } from "./ConversationView";
import { AnswerView } from "./AnswerView";
import type { Exchange } from "../lib/conversation";
import { copilotAnswer } from "../test/mockApi";

const base = { askedAt: "2026-10-12T20:00:00.000Z", symbols: [] as string[] };
const exchanges: Exchange[] = [
  { ...base, id: "1", question: "How many employees does NVIDIA have?", symbols: ["NVDA"], status: "done", result: copilotAnswer() },
  { ...base, id: "2", question: "What is the weather?", status: "error", error: "The AI model isn't running. Start Ollama and try again." },
  { ...base, id: "3", question: "Compare risks", status: "stopped" },
  { ...base, id: "4", question: "Still thinking?", status: "pending" },
];

describe("ConversationView", () => {
  it("shows the empty state when there are no messages", () => {
    render(<ConversationView exchanges={[]} busy={false} onRetry={vi.fn()} empty={<p>Nothing yet</p>} />);
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
  });

  it("shows each question with when it was asked and where it searched", () => {
    render(<ConversationView exchanges={exchanges} busy onRetry={vi.fn()} empty={null} />);
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log.querySelectorAll(":scope > li")).toHaveLength(4); // one message per exchange
    const first = screen.getByText("How many employees does NVIDIA have?").closest(".exchange") as HTMLElement;
    expect(first).toHaveTextContent("searching NVDA");
    expect(screen.getByText("What is the weather?").closest(".exchange")).toHaveTextContent("all companies");
  });

  it("shows each state: answer, error with retry, stopped with ask-again, and waiting", async () => {
    const onRetry = vi.fn();
    render(<ConversationView exchanges={exchanges} busy={false} onRetry={onRetry} empty={null} />);
    expect(screen.getByText(/As of fiscal 2026 NVIDIA had/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Start Ollama");
    expect(screen.getByText(/Stopped before an answer arrived/)).toBeInTheDocument();
    expect(screen.getByText(/Searching the filings and writing an answer/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenLastCalledWith("2");
    await userEvent.click(screen.getByRole("button", { name: "Ask again" }));
    expect(onRetry).toHaveBeenLastCalledWith("3");
  });

  it("won't offer a retry while another question is being answered", () => {
    render(<ConversationView exchanges={exchanges} busy onRetry={vi.fn()} empty={null} />);
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask again" })).toBeDisabled();
  });

  it("keeps the newest message in view", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const { rerender } = render(<ConversationView exchanges={exchanges.slice(0, 1)} busy={false} onRetry={vi.fn()} empty={null} />);
    const calls = scroll.mock.calls.length;
    rerender(<ConversationView exchanges={exchanges.slice(0, 2)} busy={false} onRetry={vi.fn()} empty={null} />);
    expect(scroll.mock.calls.length).toBeGreaterThan(calls);
    // @ts-expect-error restoring jsdom's missing implementation
    delete Element.prototype.scrollIntoView;
  });
});

describe("several answers on one page", () => {
  it("gives each answer its own source ids, so clicking a citation highlights only its own source", async () => {
    render(
      <>
        <AnswerView result={copilotAnswer({ answer: "First answer [1]." })} />
        <AnswerView result={copilotAnswer({ answer: "Second answer [1]." })} />
      </>,
    );
    const lists = screen.getAllByRole("list", { name: "Sources" });
    const ids = lists.map((l) => l.querySelector("li")!.id);
    expect(ids[0]).not.toBe(ids[1]);

    await userEvent.click(screen.getAllByRole("button", { name: "Show source 1" })[1]);
    expect(lists[1].querySelector("li")).toHaveClass("highlight");
    expect(lists[0].querySelector("li")).not.toHaveClass("highlight");
  });
});

describe("AnswerView when no company was named", () => {
  const src = (symbol: string, number: number) => ({ ...copilotAnswer().sources[0], symbol, number });

  it("says it searched every company and which ones the answer used", () => {
    render(<AnswerView result={copilotAnswer({ companies: [], sources: [src("AMZN", 1), src("AMZN", 2), src("TSLA", 3)] })} />);
    expect(screen.getByText(/No company was named, so this searched every company's filings and drew on AMZN, TSLA/)).toBeInTheDocument();
    expect(screen.getByText(/name it in your question/)).toBeInTheDocument();
  });

  it("stays quiet when a company was named or chosen", () => {
    render(<AnswerView result={copilotAnswer({ companies: ["NVDA"] })} />);
    expect(screen.queryByText(/No company was named/)).not.toBeInTheDocument();
  });

  it("stays quiet when nothing was found at all", () => {
    render(<AnswerView result={copilotAnswer({ companies: [], refused: true, grounded: false, sources: [] })} />);
    expect(screen.queryByText(/No company was named/)).not.toBeInTheDocument();
  });
});
