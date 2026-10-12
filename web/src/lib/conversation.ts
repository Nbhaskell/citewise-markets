import type { CopilotResponse } from "../api/types";

export type ExchangeStatus = "pending" | "done" | "error" | "stopped";

/** One question and what came of it. */
export interface Exchange {
  id: string;
  question: string;
  symbols: string[];
  askedAt: string; // ISO time
  status: ExchangeStatus;
  result?: CopilotResponse;
  error?: string;
}

export const STORAGE_KEY = "stockmarket.copilot.v1";
export const MAX_SAVED = 20;
export const MIN_QUESTION = 3;
export const MAX_QUESTION = 500;

const isObject = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const isStrings = (x: unknown): x is string[] => Array.isArray(x) && x.every((s) => typeof s === "string");

function isSource(x: unknown): boolean {
  return (
    isObject(x) &&
    typeof x.number === "number" &&
    typeof x.symbol === "string" &&
    typeof x.form === "string" &&
    typeof x.filed_at === "string" &&
    typeof x.url === "string" &&
    typeof x.excerpt === "string"
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
    Array.isArray(x.sources) &&
    x.sources.every(isSource)
  );
}

/** Saved data can be edited by anything with access to the browser, so every field the screen reads is checked. */
function isSavedExchange(x: unknown): x is Exchange {
  if (!isObject(x)) return false;
  if (typeof x.id !== "string" || typeof x.question !== "string" || typeof x.askedAt !== "string") return false;
  if (!isStrings(x.symbols)) return false;
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
    return data.filter(isSavedExchange).slice(-MAX_SAVED);
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
