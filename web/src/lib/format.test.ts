import { directionOf, formatChangePct, formatPrice, isStale, moodFor, relativeTime, safeHttpUrl } from "./format";

const summary = (score: number | null) => ({ days: 7, positive: 1, neutral: 1, negative: 1, irrelevant: 0, score });

describe("formatPrice", () => {
  it("formats dollars and handles missing values", () => {
    expect(formatPrice(1234.5)).toBe("$1,234.50");
    expect(formatPrice(null)).toBe("n/a");
    expect(formatPrice(undefined)).toBe("n/a");
  });
});

describe("formatChangePct", () => {
  it("shows an arrow and sign so color is never the only signal", () => {
    expect(formatChangePct(1.294)).toBe("▲ +1.29%");
    expect(formatChangePct(-0.5)).toBe("▼ -0.50%");
    expect(formatChangePct(0)).toBe("– 0.00%");
    expect(formatChangePct(null)).toBe("n/a");
  });
  it("treats tiny moves as flat", () => {
    expect(directionOf(0.001)).toBe("flat");
    expect(directionOf(0.01)).toBe("up");
    expect(directionOf(-0.01)).toBe("down");
    expect(directionOf(null)).toBe("flat");
  });
});

describe("relativeTime", () => {
  const now = Date.parse("2026-10-12T12:00:00Z");
  it.each([
    ["2026-10-12T11:59:40Z", "just now"],
    ["2026-10-12T11:55:00Z", "5m ago"],
    ["2026-10-12T09:00:00Z", "3h ago"],
    ["2026-10-10T12:00:00Z", "2d ago"],
    ["2026-10-12T12:05:00Z", "just now"], // a clock slightly ahead never shows a negative time
  ])("%s -> %s", (iso, expected) => {
    expect(relativeTime(iso, now)).toBe(expected);
  });
});

describe("moodFor", () => {
  it("maps the score to a plain label", () => {
    expect(moodFor(summary(0.22))).toEqual({ label: "Positive", tone: "up" });
    expect(moodFor(summary(-0.15))).toEqual({ label: "Negative", tone: "down" });
    expect(moodFor(summary(0.127))).toEqual({ label: "Neutral", tone: "flat" });
    expect(moodFor(summary(null))).toEqual({ label: "No news", tone: "none" });
  });
});

describe("isStale", () => {
  const now = Date.parse("2026-10-12T12:00:00");
  it("tolerates a weekend but flags older data", () => {
    expect(isStale("2026-10-09", now)).toBe(false); // Friday seen on Monday
    expect(isStale("2026-10-01", now)).toBe(true);
    expect(isStale(null, now)).toBe(true);
  });
});

describe("safeHttpUrl", () => {
  it("allows web links only", () => {
    expect(safeHttpUrl("https://example.com/a?b=1")).toBe("https://example.com/a?b=1");
    expect(safeHttpUrl("http://example.com/")).toBe("http://example.com/");
    expect(safeHttpUrl("javascript:alert(1)")).toBeUndefined();
    expect(safeHttpUrl("data:text/html,<script>alert(1)</script>")).toBeUndefined();
    expect(safeHttpUrl("not a url")).toBeUndefined();
    expect(safeHttpUrl(null)).toBeUndefined();
  });
});
