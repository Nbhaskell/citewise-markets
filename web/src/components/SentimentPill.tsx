import type { Mood } from "../lib/format";

const NEWS_LABELS: Record<string, string> = {
  positive: "Positive",
  negative: "Negative",
  neutral: "Neutral",
  irrelevant: "Off-topic",
};

/** A text label with a color. The words carry the meaning, so it is readable without color. */
export function MoodPill({ mood }: { mood: Mood }) {
  return <span className={`pill ${mood.tone}`}>{mood.label}</span>;
}

export function NewsLabelPill({ label }: { label: string | null | undefined }) {
  const tone = label === "positive" ? "up" : label === "negative" ? "down" : "flat";
  return <span className={`pill ${tone}`}>{label ? (NEWS_LABELS[label] ?? label) : "Unscored"}</span>;
}
