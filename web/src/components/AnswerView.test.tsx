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

  it("labels financial figures in words, links nothing, and shows the caution that goes with them", () => {
    const figures: CopilotSource = {
      number: 1, kind: "fundamentals", symbol: "GOOGL", title: "GOOGL financial figures from SEC filings (calculated), latest period ends 2026-06-30",
      as_of: "2026-06-30", url: null, excerpt: "P/E ratio: 17.7 (the latest stored close divided by diluted earnings per share).",
    };
    const caution = "Caution for GOOGL: net income is 1.7 times operating income, which usually means gains outside the core business.";
    render(<AnswerView result={copilotAnswer({
      answer: "Alphabet's P/E ratio is 17.7 [1].", companies: ["GOOGL"], evidence_kinds: ["fundamentals"], sources: [figures],
      cautions: [caution],
    })} />);
    expect(screen.getByText("Looked at financial figures for GOOGL")).toBeInTheDocument();
    const [item] = within(screen.getByRole("list", { name: "Sources" })).getAllByRole("listitem");
    expect(item).toHaveTextContent("Financial figures GOOGL financial figures from SEC filings");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    // a warning says so in words ("Caution for ...") and is announced as an alert, not just coloured
    expect(screen.getByRole("alert")).toHaveTextContent(/^Caution for GOOGL: net income is 1\.7 times operating income/);
  });

  it("keeps the original wording when only filings were used", () => {
    render(<AnswerView result={copilotAnswer()} />);
    expect(screen.getByText("Searched filings for NVDA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View filing" })).toBeInTheDocument();
  });

  it("says when the local model, not the keyword rules, chose what to look at", () => {
    render(<AnswerView result={marketAnswer({ model_route: ["price", "headline"] })} />);
    expect(screen.getByText(
      "The app's keyword rules found no specific kind of data for this question, so the local model chose: prices and headlines.",
    )).toBeInTheDocument();
    expect(screen.getByText("Looked at prices and headlines for NVDA")).toBeInTheDocument();      // what was looked at is still said
  });

  it("names every kind the model chose, in words", () => {
    render(<AnswerView result={marketAnswer({ model_route: ["price", "fundamentals", "sentiment", "headline", "filing"] })} />);
    expect(screen.getByText(/so the local model chose: prices, financial figures, headline sentiment, headlines and filings\./)).toBeInTheDocument();
  });

  it("says nothing about the model when the keyword rules decided", () => {
    render(<AnswerView result={marketAnswer({ model_route: [] })} />);
    expect(screen.queryByText(/local model chose/)).not.toBeInTheDocument();
  });

  it("also says it on a refusal, so a surprising 'which company?' can be explained", () => {
    render(<AnswerView result={copilotAnswer({ refused: true, grounded: false, companies: [], evidence_kinds: [], sources: [],
      answer: "Tell me which company you mean.", model_route: ["price"] })} />);
    expect(screen.getByText("No matching data found")).toBeInTheDocument();
    expect(screen.getByText(/so the local model chose: prices\./)).toBeInTheDocument();
  });

  it("says plainly when no company was named for a market question", () => {
    render(<AnswerView result={copilotAnswer({ refused: true, grounded: false, companies: [], evidence_kinds: [], sources: [],
      answer: "Tell me which company you mean." })} />);
    expect(screen.getByText("No matching data found")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
