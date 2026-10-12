import { useEffect, useRef } from "react";
import type { Exchange } from "../lib/conversation";
import { formatDateTime } from "../lib/format";
import { AnswerView } from "./AnswerView";

interface Props {
  exchanges: Exchange[];
  busy: boolean;
  onRetry: (id: string) => void;
  /** Shown when there are no messages yet. */
  empty: React.ReactNode;
}

function Message({ exchange, busy, onRetry }: { exchange: Exchange; busy: boolean; onRetry: (id: string) => void }) {
  return (
    <li className="exchange">
      <div className="question">
        <p>{exchange.question}</p>
        <p className="muted small">
          {formatDateTime(exchange.askedAt)}
          {exchange.symbols.length > 0 ? ` · searching ${exchange.symbols.join(", ")}` : " · all companies"}
        </p>
      </div>

      <div className="reply">
        {exchange.status === "pending" && (
          <p className="muted">Searching the filings and writing an answer. This can take a few seconds…</p>
        )}
        {exchange.status === "done" && exchange.result && <AnswerView result={exchange.result} />}
        {exchange.status === "error" && (
          <p role="alert" className="error">
            {exchange.error}{" "}
            <button onClick={() => onRetry(exchange.id)} disabled={busy}>
              Try again
            </button>
          </p>
        )}
        {exchange.status === "stopped" && (
          <p className="muted">
            Stopped before an answer arrived.{" "}
            <button onClick={() => onRetry(exchange.id)} disabled={busy}>
              Ask again
            </button>
          </p>
        )}
      </div>
    </li>
  );
}

export function ConversationView({ exchanges, busy, onRetry, empty }: Props) {
  const end = useRef<HTMLDivElement>(null);
  const last = exchanges.at(-1);

  // Keep the newest message in view as questions are sent and answers arrive.
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [exchanges.length, last?.status]);

  if (exchanges.length === 0) return <div className="thread empty">{empty}</div>;

  return (
    <div className="thread">
      <ol role="log" aria-label="Conversation" aria-live="polite" className="exchanges">
        {exchanges.map((e) => (
          <Message key={e.id} exchange={e} busy={busy} onRetry={onRetry} />
        ))}
      </ol>
      <div ref={end} />
    </div>
  );
}
