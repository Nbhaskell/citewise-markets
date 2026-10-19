import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { TrackingSwitch } from "./TrackingSwitch";

describe("TrackingSwitch", () => {
  it("is a switch that says tracked, in words as well as the mark", () => {
    render(<TrackingSwitch symbol="TSLA" tracked onToggle={vi.fn()} />);
    const toggle = screen.getByRole("switch", { name: "TSLA: tracked" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(toggle).toHaveTextContent("Tracked");
    expect(toggle).toHaveTextContent("✓");
    expect(toggle).toHaveClass("on");
  });

  it("says not tracked when it is off", () => {
    render(<TrackingSwitch symbol="TSLA" tracked={false} onToggle={vi.fn()} />);
    const toggle = screen.getByRole("switch", { name: "TSLA: not tracked" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(toggle).toHaveTextContent("Not tracked");
    expect(toggle).toHaveTextContent("✕");
    expect(toggle).toHaveClass("off");
  });

  it("asks to be toggled when pressed, and does nothing by itself", async () => {
    const onToggle = vi.fn();
    render(<TrackingSwitch symbol="TSLA" tracked onToggle={onToggle} />);
    expect(onToggle).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("can be pressed with the keyboard", async () => {
    const onToggle = vi.fn();
    render(<TrackingSwitch symbol="TSLA" tracked onToggle={onToggle} />);
    await userEvent.tab();
    expect(screen.getByRole("switch")).toHaveFocus();
    await userEvent.keyboard(" ");
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("cannot be pressed while disabled or updating, and says Updating while busy", async () => {
    const onToggle = vi.fn();
    const { rerender } = render(<TrackingSwitch symbol="TSLA" tracked={false} disabled onToggle={onToggle} />);
    await userEvent.click(screen.getByRole("switch"));
    rerender(<TrackingSwitch symbol="TSLA" tracked={false} busy onToggle={onToggle} />);
    expect(screen.getByRole("switch", { name: "TSLA: updating" })).toBeDisabled();
    expect(screen.getByRole("switch")).toHaveTextContent("Updating…");
    await userEvent.click(screen.getByRole("switch"));
    expect(onToggle).not.toHaveBeenCalled();
  });
});
