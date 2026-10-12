import type { SentimentSummary } from "../api/types";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatPrice(value: number | null | undefined): string {
  return value == null ? "n/a" : money.format(value);
}

export type Direction = "up" | "down" | "flat";

export function directionOf(value: number | null | undefined): Direction {
  if (value == null || Math.abs(value) < 0.005) return "flat";
  return value > 0 ? "up" : "down";
}

/** "▲ +1.29%": the arrow and sign carry the meaning, so it never relies on color alone. */
export function formatChangePct(pct: number | null | undefined): string {
  if (pct == null) return "n/a";
  const arrow = { up: "▲", down: "▼", flat: "–" }[directionOf(pct)];
  return `${arrow} ${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export type Mood = { label: "Positive" | "Negative" | "Neutral" | "No news"; tone: "up" | "down" | "flat" | "none" };

const MOOD_THRESHOLD = 0.15;

/** A plain-English reading of the -1..+1 news score. The score is a rough indicator, not a signal. */
export function moodFor(s: SentimentSummary): Mood {
  if (s.score == null) return { label: "No news", tone: "none" };
  if (s.score >= MOOD_THRESHOLD) return { label: "Positive", tone: "up" };
  if (s.score <= -MOOD_THRESHOLD) return { label: "Negative", tone: "down" };
  return { label: "Neutral", tone: "flat" };
}

/** True if the latest price date is old enough that something is probably wrong (a weekend is fine). */
export function isStale(dateIso: string | null, now: number = Date.now(), maxDays = 4): boolean {
  if (!dateIso) return true;
  return (now - new Date(`${dateIso}T00:00:00`).getTime()) / 86_400_000 > maxDays;
}

/** Links come from outside data (news feeds), so only plain web links are allowed; anything else is dropped. */
export function safeHttpUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
