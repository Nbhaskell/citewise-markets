// Pure helpers for drawing the price chart. No React here, so the math can be tested directly.

export interface Box {
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export const plotWidth = (b: Box) => Math.max(1, b.width - b.left - b.right);
export const plotHeight = (b: Box) => Math.max(1, b.height - b.top - b.bottom);

/** Rounds a span to a "nice" number (1, 2, 5 times a power of ten), the usual way to pick axis steps. */
function niceNumber(value: number, round: boolean): number {
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / 10 ** exponent;
  let nice: number;
  if (round) nice = fraction < 1.5 ? 1 : fraction < 3 ? 2 : fraction < 7 ? 5 : 10;
  else nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * 10 ** exponent;
}

/** Round-number tick values that fall inside [min, max], about `count` of them. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [min];
  const step = niceNumber(niceNumber(max - min, false) / (count - 1), true);
  const ticks: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) {
    ticks.push(Number(t.toPrecision(12))); // strip floating-point noise like 0.30000000000000004
  }
  return ticks;
}

/** The value range to draw, padded a little so the line never touches the edges. */
export function yDomain(values: number[]): [number, number] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min || Math.abs(max) * 0.02 || 1) * 0.06;
  return [min - pad, max + pad];
}

export const xAt = (i: number, n: number, b: Box) => b.left + (n <= 1 ? 0 : (i / (n - 1)) * plotWidth(b));

export const yAt = (v: number, [lo, hi]: [number, number], b: Box) =>
  b.top + (1 - (v - lo) / (hi - lo || 1)) * plotHeight(b);

/** Index of the data point nearest to a horizontal position, clamped to the data. */
export function nearestIndex(x: number, n: number, b: Box): number {
  if (n <= 1) return 0;
  const i = Math.round(((x - b.left) / plotWidth(b)) * (n - 1));
  return Math.min(n - 1, Math.max(0, i));
}

export function linePath(values: number[], domain: [number, number], b: Box): string {
  return values
    .map((v, i) => `${i === 0 ? "M" : "L"}${xAt(i, values.length, b).toFixed(1)},${yAt(v, domain, b).toFixed(1)}`)
    .join(" ");
}

/** The line closed down to the bottom of the plot, for the soft fill under it. */
export function areaPath(values: number[], domain: [number, number], b: Box): string {
  if (values.length < 2) return "";
  const bottom = (b.top + plotHeight(b)).toFixed(1);
  const first = xAt(0, values.length, b).toFixed(1);
  const last = xAt(values.length - 1, values.length, b).toFixed(1);
  return `${linePath(values, domain, b)} L${last},${bottom} L${first},${bottom} Z`;
}

/** Evenly spread indices for the date labels, including both ends. */
export function labelIndices(n: number, count: number): number[] {
  if (n <= 1) return [0];
  const k = Math.min(count, n);
  return [...new Set(Array.from({ length: k }, (_, j) => Math.round((j / (k - 1)) * (n - 1))))];
}

export type ChartRange = "1M" | "3M" | "6M" | "1Y" | "5Y" | "MAX";

/** Short dates for short ranges, month and year for long ones. Dates are "YYYY-MM-DD". */
export function axisLabel(date: string, range: ChartRange): string {
  const d = new Date(`${date}T00:00:00`);
  if (range === "1M" || range === "3M" || range === "6M") {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  if (range === "1Y") return d.toLocaleDateString("en-US", { month: "short", year: "numeric" }); // "Oct 2025", never the ambiguous "Oct 25"
  return d.toLocaleDateString("en-US", { year: "numeric" });
}

export function axisPrice(value: number): string {
  return value >= 1000 ? value.toLocaleString("en-US", { maximumFractionDigits: 0 }) : value.toFixed(value >= 100 ? 0 : 2);
}
