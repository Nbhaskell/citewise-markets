import type { CopilotResponse, HistoryTurn } from "../api/types";

export type ExchangeStatus = "pending" | "done" | "error" | "stopped";

/** One question and what came of it. */
export interface Exchange {
  id: string;
  question: string;
  symbols: string[];
  askedAt: string; // ISO time
  status: ExchangeStatus;
  /** Which topic it belongs to. Follow-ups only use earlier questions from the same topic. Older saves have none (0). */
  topic?: number;
  result?: CopilotResponse;
  error?: string;
}

export const STORAGE_KEY = "stockmarket.copilot.v1";
export const TOPIC_KEY = "stockmarket.copilot.topic.v1";
export const MAX_HISTORY_TURNS = 3; // how many earlier questions are sent along; the server uses the newest three
const MAX_HISTORY_ANSWER = 1500; // the server accepts up to 2000 characters per answer
export const MAX_SAVED = 20;
export const MIN_QUESTION = 3;
export const MAX_QUESTION = 500;

const isObject = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const isStrings = (x: unknown): x is string[] => Array.isArray(x) && x.every((s) => typeof s === "string");

const KINDS = ["filing", "price", "headline", "sentiment", "fundamentals"];
const isKinds = (x: unknown): boolean => Array.isArray(x) && x.every((k) => typeof k === "string" && KINDS.includes(k));
const isTextOrAbsent = (x: unknown): boolean => x === undefined || x === null || typeof x === "string";

function isSource(x: unknown): boolean {
  return (
    isObject(x) &&
    typeof x.number === "number" &&
    typeof x.symbol === "string" &&
    typeof x.kind === "string" &&
    KINDS.includes(x.kind) &&
    typeof x.title === "string" &&
    typeof x.as_of === "string" &&
    typeof x.excerpt === "string" &&
    isTextOrAbsent(x.url) &&
    isTextOrAbsent(x.form) &&
    isTextOrAbsent(x.filed_at) &&
    isTextOrAbsent(x.section)
  );
}

function isResult(x: unknown): x is CopilotResponse {
  return (
    isObject(x) &&
    typeof x.answer === "string" &&
    typeof x.refused === "boolean" &&
    typeof x.grounded === "boolean" &&
    typeof x.disclaimer === "string" &&
    isStrings(x.companies) &&
    isStrings(x.unverified_numbers) &&
    isStrings(x.cautions) &&
    isKinds(x.evidence_kinds) &&
    isKinds(x.model_route) &&
    Array.isArray(x.sources) &&
    x.sources.every(isSource)
  );
}

/**
 * Answers saved before the copilot used prices and headlines only had filing sources and no cautions. Give them the
 * newer fields (filled in the only way they could have been) so they still show; the strict checks then run as usual.
 */
function upgradeSaved(x: unknown): unknown {
  if (!isObject(x) || !isObject(x.result)) return x;
  const r = x.result;
  if (!Array.isArray(r.sources)) return x;
  const sources = r.sources.map((s: unknown) => {
    if (!isObject(s) || s.kind !== undefined) return s;
    const title = typeof s.symbol === "string" && typeof s.form === "string" && typeof s.filed_at === "string"
      ? `${s.symbol} ${s.form} filed ${s.filed_at}`
      : undefined;
    return { ...s, kind: "filing", title, as_of: s.filed_at };
  });
  return {
    ...x,
    result: {
      ...r, sources, cautions: r.cautions ?? [], evidence_kinds: r.evidence_kinds ?? (r.refused ? [] : ["filing"]),
      model_route: r.model_route === undefined ? [] : r.model_route, // saved before the app said what the model chose (null is damage, not old)
    },
  };
}

/** Saved data can be edited by anything with access to the browser, so every field the screen reads is checked. */
function isSavedExchange(x: unknown): x is Exchange {
  if (!isObject(x)) return false;
  if (typeof x.id !== "string" || typeof x.question !== "string" || typeof x.askedAt !== "string") return false;
  if (!isStrings(x.symbols)) return false;
  if (x.topic !== undefined && (typeof x.topic !== "number" || !Number.isInteger(x.topic) || x.topic < 0)) return false;
  if (x.status === "done") return isResult(x.result);
  if (x.status === "error") return typeof x.error === "string";
  return x.status === "stopped";
}

function storage(): Storage | null {
  try {
    return window.localStorage; // can throw in private windows or when site data is blocked
  } catch {
    return null;
  }
}

/** The saved conversation, oldest first. Anything missing, corrupt, or unexpected is dropped, never thrown. */
export function loadExchanges(): Exchange[] {
  try {
    const raw = storage()?.getItem(STORAGE_KEY);
    if (!raw) return [];
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data.map(upgradeSaved).filter(isSavedExchange).slice(-MAX_SAVED);
  } catch {
    return [];
  }
}

/** Saves finished exchanges only (a pending one can't be resumed). Returns false if the browser refused. */
export function saveExchanges(exchanges: Exchange[]): boolean {
  const store = storage();
  if (!store) return false;
  try {
    const finished = exchanges.filter((e) => e.status !== "pending").slice(-MAX_SAVED);
    if (finished.length === 0) store.removeItem(STORAGE_KEY);
    else store.setItem(STORAGE_KEY, JSON.stringify(finished));
    return true;
  } catch {
    return false; // storage full, or blocked
  }
}

export const topicOf = (e: Exchange): number => e.topic ?? 0;

/**
 * The earlier questions to send with a new one, so a follow-up like "and its risks?" can be understood.
 * Only finished, real answers from the same topic count, newest three, with citation markers removed.
 * The server uses this only to understand the question; answers are still written from the stored sources alone.
 */
export function buildHistory(earlier: Exchange[], topic: number): HistoryTurn[] {
  return earlier
    .filter((e) => topicOf(e) === topic && e.status === "done" && e.result && !e.result.refused)
    .slice(-MAX_HISTORY_TURNS)
    .map((e) => ({
      question: e.question,
      answer: e.result!.answer.replace(/\[\d+(?:\s*,\s*\d+)*\]/g, "").trim().slice(0, MAX_HISTORY_ANSWER),
      companies: e.result!.companies.slice(0, 5),
    }));
}

/** The topic to continue in after a reload: the saved one, or the newest topic seen in the saved questions. */
export function loadTopic(exchanges: Exchange[]): number {
  let saved = 0;
  try {
    saved = Number.parseInt(storage()?.getItem(TOPIC_KEY) ?? "0", 10);
  } catch {
    saved = 0;
  }
  return Math.max(Number.isInteger(saved) && saved > 0 ? saved : 0, ...exchanges.map(topicOf), 0);
}

export function saveTopic(topic: number): void {
  try {
    if (topic > 0) storage()?.setItem(TOPIC_KEY, String(topic));
    else storage()?.removeItem(TOPIC_KEY);
  } catch {
    // losing the topic marker only means a reload continues the previous topic
  }
}

let counter = 0;
export function newExchangeId(): string {
  return `${Date.now().toString(36)}-${(counter += 1)}`;
}

/** Why a question can't be sent, or null if it's fine. */
export function questionProblem(question: string): string | null {
  const q = question.trim();
  if (q.length < MIN_QUESTION) return `Ask a question of at least ${MIN_QUESTION} characters.`;
  if (q.length > MAX_QUESTION) return `Keep questions under ${MAX_QUESTION} characters.`;
  return null;
}
