import { useCallback, useEffect, useRef, useState } from "react";
import { api, isAbort } from "../api/client";
import {
  loadExchanges,
  newExchangeId,
  questionProblem,
  saveExchanges,
  type Exchange,
} from "../lib/conversation";

export interface Conversation {
  exchanges: Exchange[];
  busy: boolean;
  /** True if the browser wouldn't let us save the history (private window, full storage). */
  saveFailed: boolean;
  /** Returns why the question was rejected, or null if it was sent. */
  ask: (question: string, symbols: string[]) => string | null;
  stop: () => void;
  retry: (id: string) => void;
  clear: () => void;
}

/**
 * A running list of questions and answers, saved in this browser.
 * One question is in flight at a time (the AI model answers one at a time). The copilot itself has no memory of
 * earlier questions, so this is a record for the reader, not context for the model.
 */
export function useConversation(): Conversation {
  const [exchanges, setExchanges] = useState<Exchange[]>(() => loadExchanges());
  const [saveFailed, setSaveFailed] = useState(false);
  const inFlight = useRef<{ id: string; controller: AbortController } | null>(null);

  useEffect(() => {
    setSaveFailed(!saveExchanges(exchanges));
  }, [exchanges]);

  useEffect(() => () => inFlight.current?.controller.abort(), []);

  const busy = exchanges.some((e) => e.status === "pending");

  const patch = useCallback((id: string, changes: Partial<Exchange>) => {
    setExchanges((all) => all.map((e) => (e.id === id ? { ...e, ...changes } : e)));
  }, []);

  const run = useCallback(
    async (id: string, question: string, symbols: string[]) => {
      const controller = new AbortController();
      inFlight.current = { id, controller };
      try {
        const result = await api.copilot({ question, symbols: symbols.length > 0 ? symbols : undefined }, controller.signal);
        patch(id, { status: "done", result, error: undefined });
      } catch (err) {
        if (isAbort(err)) return; // stop() already marked it
        patch(id, { status: "error", error: err instanceof Error ? err.message : "Something went wrong." });
      } finally {
        if (inFlight.current?.id === id) inFlight.current = null;
      }
    },
    [patch],
  );

  const ask = useCallback(
    (question: string, symbols: string[]) => {
      const problem = questionProblem(question);
      if (problem) return problem;
      if (busy || inFlight.current) return "Wait for the current answer first."; // the ref updates instantly; state may lag one render
      const q = question.trim();
      const exchange: Exchange = { id: newExchangeId(), question: q, symbols, askedAt: new Date().toISOString(), status: "pending" };
      setExchanges((all) => [...all, exchange]);
      void run(exchange.id, q, symbols);
      return null;
    },
    [busy, run],
  );

  const stop = useCallback(() => {
    const current = inFlight.current;
    if (!current) return;
    current.controller.abort();
    inFlight.current = null;
    patch(current.id, { status: "stopped" });
  }, [patch]);

  const retry = useCallback(
    (id: string) => {
      const exchange = exchanges.find((e) => e.id === id);
      if (!exchange || busy) return;
      patch(id, { status: "pending", error: undefined, result: undefined });
      void run(id, exchange.question, exchange.symbols);
    },
    [exchanges, busy, patch, run],
  );

  const clear = useCallback(() => {
    inFlight.current?.controller.abort();
    inFlight.current = null;
    setExchanges([]);
  }, []);

  return { exchanges, busy, saveFailed, ask, stop, retry, clear };
}
