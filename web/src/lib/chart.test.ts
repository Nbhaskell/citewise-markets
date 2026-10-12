import {
  areaPath, axisLabel, axisPrice, labelIndices, linePath, nearestIndex, niceTicks, plotHeight, plotWidth, xAt, yAt, yDomain,
  type Box,
} from "./chart";

const box: Box = { width: 400, height: 200, left: 50, right: 10, top: 10, bottom: 20 }; // plot: 340 x 170

describe("niceTicks", () => {
  it("picks round numbers inside the range", () => {
    expect(niceTicks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(331, 345, 5)).toEqual([335, 340, 345]);
    const ticks = niceTicks(197.3, 261.8, 5);
    expect(ticks.every((t) => t >= 197.3 && t <= 261.8)).toBe(true);
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    expect(ticks.length).toBeLessThanOrEqual(7);
    expect(ticks.every((t) => t % 10 === 0 || t % 5 === 0)).toBe(true);
  });
  it("has no floating-point noise", () => {
    expect(niceTicks(0.1, 0.5, 5)).toEqual([0.1, 0.2, 0.3, 0.4, 0.5]);
  });
  it("copes with a flat or invalid range", () => {
    expect(niceTicks(5, 5)).toEqual([5]);
    expect(niceTicks(NaN, 5)).toHaveLength(1);
  });
});

describe("scales", () => {
  it("maps the first and last points to the plot's left and right edges", () => {
    expect(plotWidth(box)).toBe(340);
    expect(plotHeight(box)).toBe(170);
    expect(xAt(0, 10, box)).toBe(50);
    expect(xAt(9, 10, box)).toBe(390);
    expect(xAt(0, 1, box)).toBe(50);
  });
  it("puts higher prices higher up the chart (smaller y)", () => {
    const domain: [number, number] = [100, 200];
    expect(yAt(200, domain, box)).toBe(10);
    expect(yAt(100, domain, box)).toBe(180);
    expect(yAt(150, domain, box)).toBe(95);
  });
  it("pads the domain and survives a flat series", () => {
    const [lo, hi] = yDomain([100, 200]);
    expect(lo).toBeLessThan(100);
    expect(hi).toBeGreaterThan(200);
    const [flatLo, flatHi] = yDomain([50, 50, 50]);
    expect(flatHi).toBeGreaterThan(flatLo);
  });
});

describe("nearestIndex", () => {
  it("snaps a pointer position to the closest day, clamped to the data", () => {
    expect(nearestIndex(50, 11, box)).toBe(0);
    expect(nearestIndex(390, 11, box)).toBe(10);
    expect(nearestIndex(220, 11, box)).toBe(5);
    expect(nearestIndex(-100, 11, box)).toBe(0);
    expect(nearestIndex(9999, 11, box)).toBe(10);
    expect(nearestIndex(200, 1, box)).toBe(0);
  });
});

describe("paths", () => {
  it("draws a line through every point", () => {
    const d = linePath([1, 2, 3], [0, 4], box);
    expect(d.startsWith("M50.0,")).toBe(true);
    expect(d.match(/L/g)).toHaveLength(2);
  });
  it("closes the area down to the bottom of the plot", () => {
    const d = areaPath([1, 2, 3], [0, 4], box);
    expect(d.endsWith("Z")).toBe(true);
    expect(d).toContain("180.0"); // top 10 + plot height 170
    expect(areaPath([1], [0, 4], box)).toBe("");
  });
});

describe("labels", () => {
  it("spreads date labels evenly including both ends", () => {
    expect(labelIndices(101, 5)).toEqual([0, 25, 50, 75, 100]);
    expect(labelIndices(3, 5)).toEqual([0, 1, 2]);
    expect(labelIndices(1, 5)).toEqual([0]);
  });
  it("uses short dates for short ranges and years for long ones", () => {
    expect(axisLabel("2026-10-12", "1M")).toBe("Oct 12");
    expect(axisLabel("2026-10-12", "1Y")).toBe("Oct 2026");
    expect(axisLabel("2026-10-12", "5Y")).toBe("2026");
    expect(axisLabel("2021-01-04", "MAX")).toBe("2021");
  });
  it("shortens big prices on the axis", () => {
    expect(axisPrice(4321.6)).toBe("4,322");
    expect(axisPrice(226.3)).toBe("226");
    expect(axisPrice(12.345)).toBe("12.35");
  });
});
