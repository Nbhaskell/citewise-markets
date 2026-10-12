import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "./Composer";

const box = () => screen.getByRole("textbox", { name: "Your question" });

describe("Composer", () => {
  it("sends on the Ask button and clears the box", async () => {
    const onAsk = vi.fn(() => null);
    render(<Composer busy={false} onAsk={onAsk} onStop={vi.fn()} />);
    await userEvent.type(box(), "What are the risks?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(onAsk).toHaveBeenCalledWith("What are the risks?");
    expect(box()).toHaveValue("");
  });

  it("sends on Enter, and Shift+Enter adds a line instead", async () => {
    const onAsk = vi.fn(() => null);
    render(<Composer busy={false} onAsk={onAsk} onStop={vi.fn()} />);
    await userEvent.type(box(), "line one{Shift>}{Enter}{/Shift}line two");
    expect(onAsk).not.toHaveBeenCalled();
    expect(box()).toHaveValue("line one\nline two");
    await userEvent.type(box(), "{Enter}");
    expect(onAsk).toHaveBeenCalledWith("line one\nline two");
  });

  it("keeps what was typed and says why when the question is rejected", async () => {
    const onAsk = vi.fn(() => "Ask a question of at least 3 characters.");
    render(<Composer busy={false} onAsk={onAsk} onStop={vi.fn()} />);
    await userEvent.type(box(), "hi{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 3 characters");
    expect(box()).toHaveValue("hi");
    await userEvent.type(box(), "x"); // the message goes away once they edit
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("turns Ask into Stop while an answer is on its way, and Enter does nothing then", async () => {
    const onAsk = vi.fn(() => null);
    const onStop = vi.fn();
    render(<Composer busy onAsk={onAsk} onStop={onStop} />);
    expect(screen.queryByRole("button", { name: "Ask" })).not.toBeInTheDocument();
    await userEvent.type(box(), "Another question?{Enter}");
    expect(onAsk).not.toHaveBeenCalled();
    expect(box()).toHaveValue("Another question?");
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("shows a character count only near the limit and never lets the text pass it", async () => {
    render(<Composer busy={false} onAsk={vi.fn(() => null)} onStop={vi.fn()} />);
    expect(screen.queryByText(/\/500/)).not.toBeInTheDocument();
    await userEvent.click(box());
    await userEvent.paste("x".repeat(450));
    expect(screen.getByText("450/500")).toBeInTheDocument();
    await userEvent.paste("y".repeat(100));
    expect((box() as HTMLTextAreaElement).value).toHaveLength(500);
  });
});
