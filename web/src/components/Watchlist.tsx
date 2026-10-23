import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { RemoveOut, RemovedCompany, StockSummary } from "../api/types";
import { useApi } from "../hooks/useApi";
import { directionOf, formatChangePct, formatPrice, moodFor } from "../lib/format";
import { MoodPill } from "./SentimentPill";
import { Sparkline } from "./Sparkline";
import { StopTrackingConfirm } from "./StopTrackingConfirm";
import { TrackAgainConfirm } from "./TrackAgainConfirm";
import { TrackingSwitch } from "./TrackingSwitch";

const COLUMNS = 5;

/** The one question that is open: stop tracking a company in the table, or track a removed one again. */
type Pending = { symbol: string; kind: "stop" | "track" };

function TrendCell({ symbol }: { symbol: string }) {
  const prices = useApi((signal) => api.prices(symbol, "1M", signal), [symbol]);
  const closes = prices.data?.points.map((p) => p.close) ?? [];
  return <Sparkline values={closes} label={`${symbol} price, last month`} />;
}

function Row({ stock, switchDisabled, onToggle }: { stock: StockSummary; switchDisabled: boolean; onToggle: () => void }) {
  const s = stock.sentiment;
  const dir = directionOf(stock.change_pct);
  return (
    <tr>
      <th scope="row">
        <Link className="symbol" to={`/stocks/${stock.symbol}`}>
          {stock.symbol}
        </Link>
        <span className="muted block">{stock.name}</span>
        <TrackingSwitch symbol={stock.symbol} tracked disabled={switchDisabled} onToggle={onToggle} />
      </th>
      <td className="num">{formatPrice(stock.last_price)}</td>
      <td className={`num ${dir}`}>{formatChangePct(stock.change_pct)}</td>
      <td className="trend-col watch-optional">
        <TrendCell symbol={stock.symbol} />
      </td>
      <td className="watch-optional">
        <MoodPill mood={moodFor(s)} />
        <span className="muted block small" title={`Headlines in the last ${s.days} days`}>
          {s.positive} positive · {s.negative} negative · {s.neutral} routine
        </span>
      </td>
    </tr>
  );
}

/** `pollMs` is only for tests: how often a "track again" update is checked on. */
export function Watchlist({ pollMs }: { pollMs?: number } = {}) {
  const stocks = useApi((signal) => api.stocks(signal));
  const removed = useApi((signal) => api.removedCompanies(signal));
  const [pending, setPending] = useState<Pending | null>(null);
  const [updating, setUpdating] = useState(false); // a "track again" update is running
  // Companies removed during this visit. They stay on screen even when the Not tracked list can't be loaded (an API that is out of date,
  // or a failed request), so a removed company never just vanishes and can always be switched back on.
  const [justRemoved, setJustRemoved] = useState<RemovedCompany[]>([]);

  // While any question is open (or an update is running) every switch is off: one thing at a time, so a running update is never lost.
  const switchesOff = pending !== null;

  const notTracked = [...new Map([...(removed.data ?? []), ...justRemoved].map((c) => [c.symbol, c] as const)).values()].sort((a, b) =>
    a.symbol.localeCompare(b.symbol),
  );

  function close() {
    setPending(null);
    setUpdating(false);
  }

  function refresh() {
    close();
    stocks.reload();
    removed.reload();
  }

  function wasRemoved(result: RemoveOut) {
    setJustRemoved((list) => [...list.filter((c) => c.symbol !== result.symbol), { symbol: result.symbol, name: result.name }]);
    refresh();
  }

  function trackedAgain(symbol: string) {
    setJustRemoved((list) => list.filter((c) => c.symbol !== symbol));
    refresh();
  }

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
                <th scope="col" className="watch-optional">1 month</th>
                <th scope="col" className="watch-optional">News mood</th>
              </tr>
            </thead>
            <tbody>
              {stocks.data.map((stock) => (
                <RowWithQuestion
                  key={stock.symbol}
                  stock={stock}
                  asking={pending?.kind === "stop" && pending.symbol === stock.symbol}
                  switchDisabled={switchesOff}
                  onAsk={() => setPending({ symbol: stock.symbol, kind: "stop" })}
                  onCancel={close}
                  onRemoved={wasRemoved}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {removed.error && (
        <div role="alert" className="confirm-box warning">
          {removed.errorStatus === 404 ? (
            <p>
              The API is out of date: it doesn't have the "Not tracked" list yet, so companies you removed earlier can't be shown here.
              Restart it (run scripts\stop.ps1, then scripts\start.ps1 in PowerShell). Companies you remove during this visit stay listed
              below until you reload the page.
            </p>
          ) : (
            <p>
              Couldn't load the list of companies that aren't tracked. Companies you remove during this visit stay listed below until you
              reload the page.
            </p>
          )}
          <button type="button" onClick={removed.reload}>
            Try again
          </button>
        </div>
      )}
      {notTracked.length > 0 && (
        <div className="not-tracked">
          <h3>Not tracked</h3>
          <p className="muted small">
            Switched off and left out of the nightly refresh, "What changed", and the copilot. Their stored data is kept; switch one back on
            to bring it up to date.
          </p>
          <ul aria-label="Companies not tracked">
            {notTracked.map((company) => {
              const mine = pending?.kind === "track" && pending.symbol === company.symbol;
              return (
                <li key={company.symbol} className="removed-item">
                  <div className="removed-line">
                    <span className="symbol">{company.symbol}</span>
                    <span className="muted">{company.name}</span>
                    <TrackingSwitch
                      symbol={company.symbol}
                      tracked={false}
                      busy={mine && updating}
                      disabled={switchesOff}
                      onToggle={() => setPending({ symbol: company.symbol, kind: "track" })}
                    />
                  </div>
                  {mine && (
                    <TrackAgainConfirm
                      symbol={company.symbol}
                      name={company.name}
                      pollMs={pollMs}
                      onCancel={close}
                      onRunning={setUpdating}
                      onDone={() => trackedAgain(company.symbol)}
                    />
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <p className="muted small note">
        News mood comes from headlines labeled by a local AI model over the last 7 days. Treat it as a rough
        indicator, not a signal. The latest day can be partial while the market is open.
      </p>
    </section>
  );
}

function RowWithQuestion({
  stock,
  asking,
  switchDisabled,
  onAsk,
  onCancel,
  onRemoved,
}: {
  stock: StockSummary;
  asking: boolean;
  switchDisabled: boolean;
  onAsk: () => void;
  onCancel: () => void;
  onRemoved: (result: RemoveOut) => void;
}) {
  return (
    <>
      <Row stock={stock} switchDisabled={switchDisabled} onToggle={onAsk} />
      {asking && (
        <tr className="confirm-row">
          <td colSpan={COLUMNS}>
            <StopTrackingConfirm symbol={stock.symbol} name={stock.name} onRemoved={onRemoved} onCancel={onCancel} />
          </td>
        </tr>
      )}
    </>
  );
}
