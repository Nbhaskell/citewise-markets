import {
  directionOf, formatBigMoney, formatChangePct, formatFraction, formatShareCount, formatLongDate, formatPrice, formatShortDate, formatVolume, isStale, moodFor,
  positionInRange, relativeTime, safeHttpUrl,
} from "./format";

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

describe("formatVolume", () => {
  it("abbreviates large numbers", () => {
    expect(formatVolume(53_200_000)).toBe("53.2M");
    expect(formatVolume(1_250_000_000)).toBe("1.3B");
    expect(formatVolume(48_500)).toBe("48.5K");
    expect(formatVolume(950)).toBe("950");
    expect(formatVolume(null)).toBe("n/a");
  });
});

describe("dates", () => {
  it("formats plain dates without shifting them by time zone", () => {
    expect(formatLongDate("2026-10-12")).toBe("Mon, Oct 12, 2026");
    expect(formatShortDate("2026-01-01")).toBe("Jan 1, 2026");
    expect(formatShortDate(null)).toBe("n/a");
  });
});

describe("positionInRange", () => {
  it("places a price between the low and high, clamped to the bar", () => {
    expect(positionInRange(150, 100, 200)).toBe(50);
    expect(positionInRange(50, 100, 200)).toBe(0);
    expect(positionInRange(250, 100, 200)).toBe(100);
  });
  it("gives nothing when the range is unknown or empty", () => {
    expect(positionInRange(null, 100, 200)).toBeNull();
    expect(positionInRange(150, null, 200)).toBeNull();
    expect(positionInRange(150, 200, 200)).toBeNull();
  });
});

describe("company-sized numbers", () => {
  it("writes dollars in words", () => {
    expect(formatBigMoney(466_800_000_000)).toBe("$466.8 billion");
    expect(formatBigMoney(4_976_000_000_000)).toBe("$4.98 trillion");
    expect(formatBigMoney(3_800_000_000)).toBe("$3.8 billion");
    expect(formatBigMoney(41_300_000)).toBe("$41.3 million");
    expect(formatBigMoney(-2_500_000_000)).toBe("-$2.5 billion");
    expect(formatBigMoney(null)).toBe("n/a");
  });

  it("writes fractions as percentages and share counts in words", () => {
    expect(formatFraction(0.2763)).toBe("27.6%");
    expect(formatFraction(-0.05)).toBe("-5.0%");
    expect(formatFraction(null)).toBe("n/a");
    expect(formatShareCount(14_594_180_000)).toBe("14.59 billion");
    expect(formatShareCount(250_000_000)).toBe("250.0 million");
    expect(formatShareCount(undefined)).toBe("n/a");
  });
});
