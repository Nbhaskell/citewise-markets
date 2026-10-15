/** The newest trading date the reader has seen on the "What changed" page, kept in this browser only (there are no
 * accounts). Anything unreadable, malformed, or not a real date is treated as "no earlier visit". */
export const LAST_VISIT_KEY = "stockmarket.changes.lastVisit.v1";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !DATE_RE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function readLastVisit(): string | null {
  try {
    const value = window.localStorage.getItem(LAST_VISIT_KEY);
    return isIsoDate(value) ? value : null;
  } catch {
    return null; // storage blocked or unavailable
  }
}

/** Remembers `date` unless an equal or newer one is already saved. Never throws. */
export function writeLastVisit(date: string): void {
  if (!isIsoDate(date)) return;
  try {
    const current = readLastVisit();
    if (current === null || date > current) window.localStorage.setItem(LAST_VISIT_KEY, date);
  } catch {
    // storage full or blocked: the page still works, it just can't offer "since last visit" next time
  }
}
