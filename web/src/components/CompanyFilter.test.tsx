import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { CompanyFilter } from "./CompanyFilter";
import { stocks } from "../test/mockApi";

const six = ["AAPL", "AMZN", "GOOGL", "MSFT", "NVDA", "TSLA"].map((symbol) => ({ ...stocks[0], symbol, name: `${symbol} Inc.` }));

function Harness({ list = stocks, start = [] as string[], disabled = false }) {
  const [selected, setSelected] = useState(start);
  return (
    <>
      <CompanyFilter stocks={list} selected={selected} onChange={setSelected} disabled={disabled} />
      <output>{selected.join(",") || "all"}</output>
    </>
  );
}

const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

describe("CompanyFilter", () => {
  it("starts on all companies", () => {
    render(<Harness />);
    expect(pressed("All companies")).toBe("true");
    expect(pressed("AAPL")).toBe("false");
    expect(screen.getByRole("group", { name: "Search in" })).toBeInTheDocument();
  });

  it("picks and unpicks companies, and 'All companies' clears the choice", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "NVDA" }));
    await userEvent.click(screen.getByRole("button", { name: "TSLA" }));
    expect(screen.getByRole("status")).toHaveTextContent("NVDA,TSLA");
    expect(pressed("All companies")).toBe("false");
    expect(pressed("NVDA")).toBe("true");

    await userEvent.click(screen.getByRole("button", { name: "NVDA" }));
    expect(screen.getByRole("status")).toHaveTextContent("TSLA");

    await userEvent.click(screen.getByRole("button", { name: "All companies" }));
    expect(screen.getByRole("status")).toHaveTextContent("all");
  });

  it("stops at five companies, the most the API accepts, but still lets one be removed", async () => {
    render(<Harness list={six} start={["AAPL", "AMZN", "GOOGL", "MSFT", "NVDA"]} />);
    const sixth = screen.getByRole("button", { name: "TSLA" });
    expect(sixth).toBeDisabled();
    expect(sixth).toHaveAttribute("title", "You can pick up to 5 companies");
    expect(screen.getByRole("button", { name: "AAPL" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "AAPL" }));
    expect(screen.getByRole("button", { name: "TSLA" })).toBeEnabled();
  });

  it("can be switched off while an answer is being written", () => {
    render(<Harness disabled />);
    expect(screen.getByRole("group", { name: "Search in" })).toBeDisabled();
  });
});
