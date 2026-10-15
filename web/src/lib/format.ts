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
  return moodForScore(s.score);
}

export function moodForScore(score: number | null | undefined): Mood {
  if (score == null) return { label: "No news", tone: "none" };
  if (score >= MOOD_THRESHOLD) return { label: "Positive", tone: "up" };
  if (score <= -MOOD_THRESHOLD) return { label: "Negative", tone: "down" };
  return { label: "Neutral", tone: "flat" };
}

/** -0.3333 -> "-0.33", 0.6 -> "+0.60". */
export function formatScore(score: number): string {
  return `${score > 0 ? "+" : ""}${score.toFixed(2)}`;
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

/** "Mon, Oct 12, 2026" from a "YYYY-MM-DD" date. */
export function formatLongDate(date: string): string {
  return new Date(`${date}T00:00:00`).toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

export function formatShortDate(date: string | null | undefined): string {
  if (!date) return "n/a";
  return new Date(`${date}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** 53_200_000 -> "53.2M". */
export function formatVolume(value: number | null | undefined): string {
  if (value == null) return "n/a";
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(value);
}

/** Where a price sits between the low and high, 0 to 100, for the 52-week range bar. */
export function positionInRange(price: number | null, low: number | null, high: number | null): number | null {
  if (price == null || low == null || high == null || high <= low) return null;
  return Math.min(100, Math.max(0, ((price - low) / (high - low)) * 100));
}

/** 466_800_000_000 -> "$466.8 billion"; 4_976e9 -> "$4.98 trillion". Company-sized dollar amounts. */
export function formatBigMoney(value: number | null | undefined): string {
  if (value == null) return "n/a";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)} trillion`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)} billion`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)} million`;
  return `${sign}$${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/** 0.276 -> "27.6%". */
export function formatFraction(value: number | null | undefined): string {
  return value == null ? "n/a" : `${(value * 100).toFixed(1)}%`;
}

/** 14_594_180_000 -> "14.59 billion". */
export function formatShareCount(value: number | null | undefined): string {
  if (value == null) return "n/a";
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)} billion`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} million`;
  return value.toLocaleString("en-US");
}
