import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CompanyFilter } from "../components/CompanyFilter";
import { Composer } from "../components/Composer";
import { ConversationView } from "../components/ConversationView";
import { useApi } from "../hooks/useApi";
import { useConversation } from "../hooks/useConversation";

const EXAMPLES = [
  "What are NVIDIA's biggest risks?",
  "How many employees does Tesla have?",
  "Compare Apple's and Microsoft's biggest risks.",
  "What does Amazon say about legal proceedings?",
  "How did Microsoft's revenue change in its latest annual report?",
];

export function CopilotPage() {
  const chat = useConversation();
  const stocks = useApi((signal) => api.stocks(signal));
  const [companies, setCompanies] = useState<string[]>([]);
  const [confirmingClear, setConfirmingClear] = useState(false);

  useEffect(() => {
    document.title = "Copilot · stockMarket";
    return () => {
      document.title = "stockMarket";
    };
  }, []);

  const empty = (
    <>
      <h2>Ask about the filings</h2>
      <p className="muted">Try one of these, or type your own below.</p>
      <div className="chips">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" className="chip" disabled={chat.busy} onClick={() => chat.ask(example, companies)}>
            {example}
          </button>
        ))}
      </div>
    </>
  );

  return (
    <div className="copilot-page">
      <h1 className="page-title">Copilot</h1>
      <p className="muted">
        Answers come only from the 10-K and 10-Q filings stored here, with numbered sources you can check. Not financial
        advice. <strong>Each question is answered on its own</strong>: the copilot doesn't remember earlier ones, so name
        the company every time.
      </p>

      {stocks.data && stocks.data.length > 0 && (
        <CompanyFilter stocks={stocks.data} selected={companies} onChange={setCompanies} disabled={chat.busy} />
      )}

      <section className="card chat" aria-label="Conversation">
        <ConversationView exchanges={chat.exchanges} busy={chat.busy} onRetry={chat.retry} empty={empty} />
        <Composer busy={chat.busy} onAsk={(q) => chat.ask(q, companies)} onStop={chat.stop} />
      </section>

      <div className="chat-footer muted small">
        <span>Enter sends, Shift+Enter adds a line.</span>
        <span>Your questions are saved in this browser only (the last 20).</span>
        {chat.saveFailed && (
          <span className="flag warn">This browser won't let us save your history, so it will be lost when you leave.</span>
        )}
        {chat.exchanges.length > 0 &&
          (confirmingClear ? (
            <span>
              Clear all {chat.exchanges.length} saved {chat.exchanges.length === 1 ? "question" : "questions"}?{" "}
              <button
                onClick={() => {
                  chat.clear();
                  setConfirmingClear(false);
                }}
              >
                Yes, clear
              </button>{" "}
              <button onClick={() => setConfirmingClear(false)}>Cancel</button>
            </span>
          ) : (
            <button onClick={() => setConfirmingClear(true)}>Clear conversation</button>
          ))}
      </div>
    </div>
  );
}
