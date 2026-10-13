import { useCallback, useEffect, useRef, useState } from "react";
import { api, isAbort } from "../api/client";
import type { HistoryTurn } from "../api/types";
import {
  buildHistory,
  loadExchanges,
  loadTopic,
  newExchangeId,
  questionProblem,
  saveExchanges,
  saveTopic,
  topicOf,
  type Exchange,
} from "../lib/conversation";

export interface Conversation {
  exchanges: Exchange[];
  busy: boolean;
  /** The current topic. A new question can only follow up on earlier questions in the same topic. */
  topic: number;
  /** How many earlier questions the next question will be able to follow up on (0 to 3). */
  contextTurns: number;
  /** True if the browser wouldn't let us save the history (private window, full storage). */
  saveFailed: boolean;
  /** Returns why the question was rejected, or null if it was sent. */
  ask: (question: string, symbols: string[]) => string | null;
  stop: () => void;
  retry: (id: string) => void;
  /** Start a fresh topic: earlier questions stay on screen but are no longer used to understand new ones. */
  newTopic: () => void;
  clear: () => void;
}

/**
 * A running list of questions and answers, saved in this browser.
 * One question is in flight at a time (the AI model answers one at a time). Earlier questions in the current topic
 * are sent along so a follow-up can be understood; the copilot still answers only from the stored sources.
 */
export function useConversation(): Conversation {
  const [initial] = useState(() => {
    const saved = loadExchanges();
    return { saved, topic: loadTopic(saved) };
  });
  const [exchanges, setExchanges] = useState<Exchange[]>(initial.saved);
  const [topic, setTopic] = useState(initial.topic);
  const [saveFailed, setSaveFailed] = useState(false);
  const inFlight = useRef<{ id: string; controller: AbortController } | null>(null);

  useEffect(() => {
    setSaveFailed(!saveExchanges(exchanges));
  }, [exchanges]);

  useEffect(() => saveTopic(topic), [topic]);

  useEffect(() => () => inFlight.current?.controller.abort(), []);

  const busy = exchanges.some((e) => e.status === "pending");

  const patch = useCallback((id: string, changes: Partial<Exchange>) => {
    setExchanges((all) => all.map((e) => (e.id === id ? { ...e, ...changes } : e)));
  }, []);

  const run = useCallback(
    async (id: string, question: string, symbols: string[], history: HistoryTurn[]) => {
      const controller = new AbortController();
      inFlight.current = { id, controller };
      try {
        const result = await api.copilot(
          {
            question,
            symbols: symbols.length > 0 ? symbols : undefined,
            history: history.length > 0 ? history : undefined,
          },
          controller.signal,
        );
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
      const history = buildHistory(exchanges, topic);
      const exchange: Exchange = {
        id: newExchangeId(), question: q, symbols, topic, askedAt: new Date().toISOString(), status: "pending",
      };
      setExchanges((all) => [...all, exchange]);
      void run(exchange.id, q, symbols, history);
      return null;
    },
    [busy, exchanges, topic, run],
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
      const index = exchanges.findIndex((e) => e.id === id);
      if (index < 0 || busy) return;
      const exchange = exchanges[index];
      // A retry follows up on what came before it in its own topic, not on later questions.
      const history = buildHistory(exchanges.slice(0, index), topicOf(exchange));
      patch(id, { status: "pending", error: undefined, result: undefined });
      void run(id, exchange.question, exchange.symbols, history);
    },
    [exchanges, busy, patch, run],
  );

  const newTopic = useCallback(() => {
    if (!busy) setTopic((t) => t + 1);
  }, [busy]);

  const clear = useCallback(() => {
    inFlight.current?.controller.abort();
    inFlight.current = null;
    setExchanges([]);
    setTopic(0);
  }, []);

  const contextTurns = buildHistory(exchanges, topic).length;

  return { exchanges, busy, topic, contextTurns, saveFailed, ask, stop, retry, newTopic, clear };
}
