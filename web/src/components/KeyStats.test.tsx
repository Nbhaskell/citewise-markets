import { render, screen } from "@testing-library/react";
import { KeyStats } from "./KeyStats";
import { stockDetail } from "../test/mockApi";

describe("KeyStats", () => {
  it("shows price, volume, company facts and the news mood", () => {
    render(<KeyStats stock={stockDetail} />);
    expect(screen.getByText("$340.97")).toBeInTheDocument();
    expect(screen.getByText("▲ +1.29%")).toHaveClass("up");
    expect(screen.getByText("53.2M")).toBeInTheDocument();
    expect(screen.getByText("NMS")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("Consumer Electronics")).toBeInTheDocument();
    expect(screen.getByText("Oct 12, 2026")).toBeInTheDocument();
    expect(screen.getByText("Neutral")).toBeInTheDocument();
    expect(screen.getByText("8 positive · 9 negative · 90 routine · 3 off-topic")).toBeInTheDocument();
    expect(screen.getByText(/News mood, last 7 days/)).toBeInTheDocument();
  });

  it("places the price on the 52-week range bar and says where it sits in words", () => {
    render(<KeyStats stock={{ ...stockDetail, last_price: 340.97, low_52w: 200, high_52w: 360 }} />);
    const bar = screen.getByRole("img", { name: /percent of the way from the 52-week low to the high/ });
    expect(bar).toHaveAccessibleName("The price is 88 percent of the way from the 52-week low to the high");
    expect(bar.querySelector(".range-marker")).toHaveStyle({ left: "88.1%" });
    expect(screen.getByText("$200.00")).toBeInTheDocument();
    expect(screen.getByText("$360.00")).toBeInTheDocument();
  });

  it("keeps the marker on the bar if the price is outside the 52-week range", () => {
    render(<KeyStats stock={{ ...stockDetail, last_price: 400, low_52w: 200, high_52w: 360 }} />);
    expect(screen.getByRole("img").querySelector(".range-marker")).toHaveStyle({ left: "100%" });
  });

  it("copes with missing data instead of showing nonsense", () => {
    render(
      <KeyStats
        stock={{ ...stockDetail, last_price: null, change_pct: null, change: null, high_52w: null, low_52w: null,
          volume: null, exchange: null, sector: null, industry: null, as_of: null }}
      />,
    );
    expect(screen.getByText("Not enough history")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getAllByText("n/a").length).toBeGreaterThanOrEqual(6);
  });
});
