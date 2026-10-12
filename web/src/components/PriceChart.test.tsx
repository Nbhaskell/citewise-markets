import { fireEvent, render, screen } from "@testing-library/react";
import { PriceChart } from "./PriceChart";

const pts = (closes: number[]) =>
  closes.map((close, i) => ({ date: `2026-10-0${i + 1}`, open: close, high: close, low: close, close, volume: 1_000_000 * (i + 1) }));

const UP = pts([100, 110, 105, 120, 130]);
// With no real layout in the test browser the chart is 640 wide: the plot runs from x=54 to x=628, 5 points.
const X = { first: 54, middle: 341, last: 628 };

const readout = () => screen.getByRole("status");
const svg = () => screen.getByRole("img");

describe("PriceChart", () => {
  it("describes the chart in words for screen readers", () => {
    render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    expect(svg()).toHaveAttribute("aria-label", "AAPL closing price over 1M: from $100.00 to $130.00");
  });

  it("starts on the latest day with the change since the start of the range", () => {
    render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    expect(readout()).toHaveTextContent("Mon, Oct 5, 2026");
    expect(readout()).toHaveTextContent("$130.00");
    expect(readout()).toHaveTextContent("▲ +30.00% since Thu, Oct 1, 2026");
    expect(readout()).toHaveTextContent("Volume 5.0M");
  });

  it("follows the pointer to the nearest day and returns to the latest day when it leaves", () => {
    render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    fireEvent.pointerMove(svg(), { clientX: X.first });
    expect(readout()).toHaveTextContent("$100.00");
    expect(readout()).toHaveTextContent("Volume 1.0M");

    fireEvent.pointerMove(svg(), { clientX: X.middle });
    expect(readout()).toHaveTextContent("$105.00");
    expect(readout()).toHaveTextContent("▲ +5.00% since");

    fireEvent.pointerLeave(svg());
    expect(readout()).toHaveTextContent("$130.00");
  });

  it("can be driven from the keyboard", () => {
    render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    const chart = screen.getByRole("group");
    chart.focus();
    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    expect(readout()).toHaveTextContent("$120.00");
    fireEvent.keyDown(chart, { key: "Home" });
    expect(readout()).toHaveTextContent("$100.00");
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(readout()).toHaveTextContent("$110.00");
    fireEvent.keyDown(chart, { key: "End" });
    expect(readout()).toHaveTextContent("$130.00");
    fireEvent.keyDown(chart, { key: "ArrowLeft", shiftKey: true }); // ten days back, stops at the first
    expect(readout()).toHaveTextContent("$100.00");
    fireEvent.keyDown(chart, { key: "ArrowRight", shiftKey: true });
    expect(readout()).toHaveTextContent("$130.00");
  });

  it("ignores other keys and resets when focus leaves", () => {
    render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    const chart = screen.getByRole("group");
    fireEvent.keyDown(chart, { key: "Home" });
    expect(readout()).toHaveTextContent("$100.00");
    fireEvent.keyDown(chart, { key: "a" });
    expect(readout()).toHaveTextContent("$100.00");
    fireEvent.blur(chart);
    expect(readout()).toHaveTextContent("$130.00");
  });

  it("colors the line by whether the range ended up or down", () => {
    const { rerender } = render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    expect(svg()).toHaveClass("up");
    rerender(<PriceChart symbol="AAPL" range="1M" points={pts([130, 120, 100])} />);
    expect(svg()).toHaveClass("down");
    expect(readout()).toHaveTextContent("▼ -23.08% since");
  });

  it("draws price and date labels along the axes", () => {
    const { container } = render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    const labels = [...container.querySelectorAll("text.axis")].map((t) => t.textContent);
    expect(labels).toContain("Oct 1"); // first date on the left
    expect(labels).toContain("Oct 5"); // last date on the right
    expect(labels.some((l) => /^\d+$/.test(l ?? ""))).toBe(true); // at least one price tick
    expect(container.querySelector("path.line")).not.toBeNull();
    expect(container.querySelector("path.area")).not.toBeNull();
  });

  it("shows a guide line only while a day is picked", () => {
    const { container } = render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    expect(container.querySelector("line.guide")).toBeNull();
    fireEvent.pointerMove(svg(), { clientX: X.middle });
    expect(container.querySelector("line.guide")).not.toBeNull();
  });

  it("keeps working when the data shrinks under the selected day", () => {
    const { rerender } = render(<PriceChart symbol="AAPL" range="1M" points={UP} />);
    fireEvent.keyDown(screen.getByRole("group"), { key: "End" });
    rerender(<PriceChart symbol="AAPL" range="1M" points={pts([100, 101])} />);
    expect(readout()).toHaveTextContent("$101.00");
  });
});
