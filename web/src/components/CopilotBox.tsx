import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, isAbort } from "../api/client";
import type { CopilotResponse } from "../api/types";
import { AnswerView } from "./AnswerView";

const DEFAULT_EXAMPLES = [
  "What are NVIDIA's biggest risks?",
  "How many employees does Tesla have?",
  "Compare Apple's and Microsoft's biggest risks.",
];
const MIN_LENGTH = 3;

type State =
  | { kind: "idle" }
  | { kind: "loading"; question: string }
  | { kind: "error"; message: string }
  | { kind: "done"; result: CopilotResponse };

interface Props {
  /** Limit every question to this company's filings. */
  symbol?: string;
  examples?: string[];
}

export function CopilotBox({ symbol, examples = DEFAULT_EXAMPLES }: Props) {
  const [question, setQuestion] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => () => inFlight.current?.abort(), []);

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < MIN_LENGTH) {
      setHint(`Ask a question of at least ${MIN_LENGTH} characters.`);
      return;
    }
    setHint(null);
    inFlight.current?.abort(); // a newer question replaces an older one still running
    const controller = new AbortController();
    inFlight.current = controller;
    setState({ kind: "loading", question: q });
    try {
      const result = await api.copilot({ question: q, symbols: symbol ? [symbol] : undefined }, controller.signal);
      setState({ kind: "done", result });
    } catch (err) {
      if (isAbort(err)) return;
      setState({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  const loading = state.kind === "loading";

  return (
    <section className="card" aria-labelledby="copilot-title">
      <h2 id="copilot-title">{symbol ? `Ask about ${symbol}` : "Ask the filings"}</h2>
      <p className="muted small">
        Answers come only from the 10-K and 10-Q filings stored here, with numbered sources. Not financial advice.
      </p>

      <form onSubmit={onSubmit} className="ask-form">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          rows={2}
          maxLength={500}
          value={question}
          placeholder={symbol ? "e.g. What are the biggest risks?" : "e.g. What are Nvidia's biggest risks?"}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(question);
            }
          }}
        />
        <button type="submit" className="primary" disabled={loading}>
          {loading ? "Working…" : "Ask"}
        </button>
      </form>
      {hint && <p role="alert" className="error small">{hint}</p>}

      <div className="chips" aria-label="Example questions">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            className="chip"
            disabled={loading}
            onClick={() => {
              setQuestion(example);
              void ask(example);
            }}
          >
            {example}
          </button>
        ))}
      </div>

      <div aria-live="polite">
        {state.kind === "loading" && (
          <p className="muted">Searching the filings and writing an answer. This can take a few seconds…</p>
        )}
        {state.kind === "error" && (
          <p role="alert" className="error">
            {state.message}
          </p>
        )}
        {state.kind === "done" && <AnswerView result={state.result} />}
      </div>
    </section>
  );
}
