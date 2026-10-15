import { vi } from "vitest";
import { LAST_VISIT_KEY, isIsoDate, readLastVisit, writeLastVisit } from "./lastVisit";


describe("isIsoDate", () => {
  it("accepts real dates only", () => {
    expect(isIsoDate("2026-10-15")).toBe(true);
    expect(isIsoDate("2026-02-30")).toBe(false);
    expect(isIsoDate("2026-13-01")).toBe(false);
    expect(isIsoDate("10/15/2026")).toBe(false);
    expect(isIsoDate("2026-10-15T00:00:00Z")).toBe(false);
    expect(isIsoDate("")).toBe(false);
    expect(isIsoDate(20261015)).toBe(false);
    expect(isIsoDate(null)).toBe(false);
  });
});

describe("last visit", () => {
  it("is empty until something is saved, then returns it", () => {
    expect(readLastVisit()).toBeNull();
    writeLastVisit("2026-10-14");
    expect(readLastVisit()).toBe("2026-10-14");
    expect(window.localStorage.getItem(LAST_VISIT_KEY)).toBe("2026-10-14");
  });

  it("only moves forward", () => {
    writeLastVisit("2026-10-14");
    writeLastVisit("2026-10-10");
    expect(readLastVisit()).toBe("2026-10-14");
    writeLastVisit("2026-10-15");
    expect(readLastVisit()).toBe("2026-10-15");
  });

  it("ignores a saved value that is not a real date", () => {
    for (const bad of ["garbage", "2026-02-30", "{\"a\":1}", ""]) {
      window.localStorage.setItem(LAST_VISIT_KEY, bad);
      expect(readLastVisit()).toBeNull();
    }
    writeLastVisit("2026-10-15"); // a bad saved value doesn't block saving a good one
    expect(readLastVisit()).toBe("2026-10-15");
  });

  it("refuses to save something that is not a date", () => {
    writeLastVisit("tomorrow");
    expect(window.localStorage.getItem(LAST_VISIT_KEY)).toBeNull();
  });

  it("never throws when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("full");
    });
    expect(readLastVisit()).toBeNull();
    expect(() => writeLastVisit("2026-10-15")).not.toThrow();
  });
});
