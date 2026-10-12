import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import type { ChartRange } from "../lib/chart";
import { PriceChart } from "./PriceChart";

const RANGES: ChartRange[] = ["1M", "3M", "6M", "1Y", "5Y", "MAX"];

export function PriceHistory({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<ChartRange>("1Y");
  const prices = useApi((signal) => api.prices(symbol, range, signal), [symbol, range]);
  const shown = prices.data;

  return (
    <section className="card" aria-labelledby="chart-title">
      <div className="card-head">
        <h2 id="chart-title">Price history</h2>
        <div className="ranges" role="group" aria-label="Chart range">
          {RANGES.map((r) => (
            <button key={r} type="button" aria-pressed={r === range} className={r === range ? "range on" : "range"} onClick={() => setRange(r)}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {prices.error && (
        <p role="alert" className="error">
          {prices.error} <button onClick={prices.reload}>Try again</button>
        </p>
      )}
      {!shown && prices.loading && <p className="muted">Loading prices…</p>}
      {shown && shown.points.length < 2 && (
        <p className="muted">Not enough price history for this range yet.</p>
      )}
      {shown && shown.points.length >= 2 && (
        // The chart follows the data it was given, so labels never mismatch while a new range loads.
        <div className={prices.loading ? "loading" : undefined} aria-busy={prices.loading}>
          <PriceChart key={shown.range} symbol={symbol} range={shown.range as ChartRange} points={shown.points} />
        </div>
      )}
      <p className="muted small note">Daily closing prices. The latest day can be partial while the market is open.</p>
    </section>
  );
}
