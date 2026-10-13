import { render, screen, within } from "@testing-library/react";
import { AnswerView } from "./AnswerView";
import { copilotAnswer } from "../test/mockApi";
import type { CopilotSource } from "../api/types";

const price: CopilotSource = {
  number: 1, kind: "price", symbol: "NVDA", title: "NVDA price data (stored daily closes), as of 2026-10-12", as_of: "2026-10-12",
  url: null, excerpt: "Latest close: 226.32 on 2026-10-12.\nChange over the window: +8.03 (+3.68%), a rise.",
};
const headline: CopilotSource = {
  number: 2, kind: "headline", symbol: "NVDA", title: "NVDA headline, Reuters, 2026-10-12, automatic label: neutral",
  as_of: "2026-10-12", url: "https://example.com/story", excerpt: "Nvidia sees a dip",
};

const marketAnswer = (over = {}) => copilotAnswer({
  answer: "Nvidia rose 3.68% [1]. A headline was published [2].",
  evidence_kinds: ["price", "headline"], sources: [price, headline], ...over,
});

describe("AnswerView with prices and headlines", () => {
  it("says what was looked at and labels each source in words", () => {
    render(<AnswerView result={marketAnswer()} />);
    expect(screen.getByText("Looked at prices and headlines for NVDA")).toBeInTheDocument();
    const items = within(screen.getByRole("list", { name: "Sources" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Price data NVDA price data (stored daily closes), as of 2026-10-12");
    expect(items[1]).toHaveTextContent("Headline NVDA headline, Reuters, 2026-10-12, automatic label: neutral");
  });

  it("links a headline to its article but gives a price source no link", () => {
    render(<AnswerView result={marketAnswer()} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent("Read headline");
    expect(links[0]).toHaveAttribute("href", "https://example.com/story");
  });

  it("never links an unsafe address from a headline", () => {
    render(<AnswerView result={marketAnswer({ sources: [price, { ...headline, url: "javascript:alert(1)" }] })} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows the figures a price source was built from", () => {
    render(<AnswerView result={marketAnswer()} />);
    expect(screen.getByText(/Latest close: 226\.32 on 2026-10-12\./)).toBeInTheDocument();
  });

  it("shows every caution the server sends as a visible alert", () => {
    render(<AnswerView result={marketAnswer({ cautions: ["This answer may suggest a reason for the price move."] })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("may suggest a reason for the price move");
  });

  it("keeps the original wording when only filings were used", () => {
    render(<AnswerView result={copilotAnswer()} />);
    expect(screen.getByText("Searched filings for NVDA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View filing" })).toBeInTheDocument();
  });

  it("says plainly when no company was named for a market question", () => {
    render(<AnswerView result={copilotAnswer({ refused: true, grounded: false, companies: [], evidence_kinds: [], sources: [],
      answer: "Tell me which company you mean." })} />);
    expect(screen.getByText("No matching data found")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
