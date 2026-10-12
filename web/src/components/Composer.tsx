import { useState, type FormEvent } from "react";
import { MAX_QUESTION } from "../lib/conversation";

interface Props {
  busy: boolean;
  /** Returns why the question was rejected, or null if it was sent. */
  onAsk: (question: string) => string | null;
  onStop: () => void;
}

/** The message box. Enter sends, Shift+Enter adds a line. While an answer is on its way, the button becomes Stop. */
export function Composer({ busy, onAsk, onStop }: Props) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function submit() {
    const rejected = onAsk(text);
    setProblem(rejected);
    if (!rejected) setText(""); // keep what they typed if it wasn't sent
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    submit();
  }

  return (
    <form onSubmit={onSubmit} className="composer">
      <label htmlFor="composer-input" className="sr-only">
        Your question
      </label>
      <textarea
        id="composer-input"
        rows={2}
        maxLength={MAX_QUESTION}
        value={text}
        placeholder="Ask about a company's filings…"
        onChange={(e) => {
          setText(e.target.value);
          setProblem(null);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!busy) submit();
          }
        }}
      />
      {busy ? (
        <button type="button" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="primary">
          Ask
        </button>
      )}
      {problem && (
        <p role="alert" className="error small composer-note">
          {problem}
        </p>
      )}
      {text.length > MAX_QUESTION - 100 && (
        <p className="muted small composer-note">
          {text.length}/{MAX_QUESTION}
        </p>
      )}
    </form>
  );
}
