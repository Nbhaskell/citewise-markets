import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ChangesFilings } from "../components/ChangesFilings";
import { ChangesHeadlines } from "../components/ChangesHeadlines";
import { ChangesMoves } from "../components/ChangesMoves";
import { FreshnessBar } from "../components/FreshnessBar";
import { useApi } from "../hooks/useApi";
import { formatShortDate } from "../lib/format";

const WINDOWS = [
  { days: 1, label: "Latest day" },
  { days: 3, label: "3 days" },
  { days: 7, label: "7 days" },
];

/** What changed lately: new filings, unusually big moves, notable headlines. All worked out from stored data. */
export function ChangesPage() {
  const [days, setDays] = useState(1);
  const changes = useApi((signal) => api.changes(days, signal), [days]);
  const data = changes.data;

  useEffect(() => {
    document.title = "What changed · stockMarket";
    return () => {
      document.title = "stockMarket";
    };
  }, []);

  return (
    <>
      <FreshnessBar />
      <div className="col changes">
        <section className="card" aria-labelledby="changes-title">
          <div className="card-head">
            <h1 className="page-title" id="changes-title">
              What changed
            </h1>
            <div className="ranges" role="group" aria-label="Look back">
              {WINDOWS.map((w) => (
                <button
                  key={w.days}
                  type="button"
                  aria-pressed={w.days === days}
                  className={w.days === days ? "range on" : "range"}
                  onClick={() => setDays(w.days)}
                >
                  {w.label}
                </button>
              ))}
            </div>
          </div>
          <p className="muted small">
            Worked out from the stored filings, prices, and headlines, with no AI summary. It shows what happened and
            when, never why. Not financial advice.
          </p>
          {changes.error && (
            <p role="alert" className="error">
              {changes.error} <button onClick={changes.reload}>Try again</button>
            </p>
          )}
          {!data && changes.loading && <p className="muted">Loading…</p>}
          {data && data.as_of == null && (
            <p className="muted">No prices are stored yet, so there is nothing to compare.</p>
          )}
          {data && data.as_of != null && (
            <p className="small" role="status">
              {data.days === 1
                ? `Latest trading day: ${formatShortDate(data.as_of)}.`
                : `The last ${data.days} trading days: ${formatShortDate(data.window_start)} to ${formatShortDate(data.as_of)}.`}
            </p>
          )}
          {data && data.stale.length > 0 && (
            <p className="flag warn" role="alert">
              No price yet for {formatShortDate(data.as_of)} for{" "}
              {data.stale.map((s) => `${s.symbol} (latest ${s.as_of ? formatShortDate(s.as_of) : "none"})`).join(", ")},
              so their latest moves may be missing.
            </p>
          )}
        </section>

        {data && (
          <div className={changes.loading ? "col loading" : "col"} aria-busy={changes.loading}>
            <ChangesFilings filings={data.filings} newest={data.newest_filing} />
            <ChangesMoves data={data} />
            <ChangesHeadlines data={data} />
          </div>
        )}
        <p className="muted small">
          <Link to="/">Back to the dashboard</Link>
        </p>
      </div>
    </>
  );
}
