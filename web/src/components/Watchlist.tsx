import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { StockSummary } from "../api/types";
import { useApi } from "../hooks/useApi";
import { directionOf, formatChangePct, formatPrice, moodFor } from "../lib/format";
import { MoodPill } from "./SentimentPill";
import { Sparkline } from "./Sparkline";

function TrendCell({ symbol }: { symbol: string }) {
  const prices = useApi((signal) => api.prices(symbol, "1M", signal), [symbol]);
  const closes = prices.data?.points.map((p) => p.close) ?? [];
  return <Sparkline values={closes} label={`${symbol} price, last month`} />;
}

function Row({ stock }: { stock: StockSummary }) {
  const s = stock.sentiment;
  const dir = directionOf(stock.change_pct);
  return (
    <tr>
      <th scope="row">
        <Link className="symbol" to={`/stocks/${stock.symbol}`}>
          {stock.symbol}
        </Link>
        <span className="muted block">{stock.name}</span>
      </th>
      <td className="num">{formatPrice(stock.last_price)}</td>
      <td className={`num ${dir}`}>{formatChangePct(stock.change_pct)}</td>
      <td className="trend-col">
        <TrendCell symbol={stock.symbol} />
      </td>
      <td>
        <MoodPill mood={moodFor(s)} />
        <span className="muted block small" title={`Headlines in the last ${s.days} days`}>
          {s.positive} positive · {s.negative} negative · {s.neutral} routine
        </span>
      </td>
    </tr>
  );
}

export function Watchlist() {
  const stocks = useApi((signal) => api.stocks(signal));

  return (
    <section className="card" aria-labelledby="watchlist-title">
      <h2 id="watchlist-title">Watchlist</h2>
      {stocks.loading && <p className="muted">Loading companies…</p>}
      {stocks.error && (
        <p role="alert" className="error">
          {stocks.error} <button onClick={stocks.reload}>Try again</button>
        </p>
      )}
      {stocks.data && stocks.data.length === 0 && (
        <p className="muted">No companies yet. Add one with the "Add a company" box below, or with: python -m jobs.add_company TICKER</p>
      )}
      {stocks.data && stocks.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col" className="num">Price</th>
                <th scope="col" className="num">Day</th>
                <th scope="col">1 month</th>
                <th scope="col">News mood</th>
              </tr>
            </thead>
            <tbody>
              {stocks.data.map((stock) => (
                <Row key={stock.symbol} stock={stock} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small note">
        News mood comes from headlines labeled by a local AI model over the last 7 days. Treat it as a rough
        indicator, not a signal. The latest day can be partial while the market is open.
      </p>
    </section>
  );
}
