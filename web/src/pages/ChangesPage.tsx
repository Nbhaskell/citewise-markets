import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ChangesFilings } from "../components/ChangesFilings";
import { ChangesHeadlines } from "../components/ChangesHeadlines";
import { ChangesMoves } from "../components/ChangesMoves";
import { FreshnessBar } from "../components/FreshnessBar";
import { useApi } from "../hooks/useApi";
import { formatShortDate } from "../lib/format";
import { readLastVisit, writeLastVisit } from "../lib/lastVisit";

const WINDOWS = [
  { days: 1, label: "Latest day" },
  { days: 3, label: "3 days" },
  { days: 7, label: "7 days" },
];

type Window = { kind: "days"; days: number } | { kind: "since" };

/** What changed lately: new filings, unusually big moves, notable headlines. All worked out from stored data. */
export function ChangesPage() {
  const [view, setView] = useState<Window>({ kind: "days", days: 1 });
  // The date of the newest trading day seen on an earlier visit, read once when the page opens (this visit then
  // saves a newer one, which would otherwise make the option disappear while it is being used).
  const [lastVisit] = useState(readLastVisit);
  const since = view.kind === "since" ? lastVisit : null;
  const changes = useApi(
    (signal) => api.changes(since ? { since } : { days: view.kind === "days" ? view.days : 1 }, signal),
    [view, since],
  );
  const data = changes.data;

  const saved = useRef(false);
  useEffect(() => {
    if (data?.as_of && !saved.current) {
      saved.current = true;
      writeLastVisit(data.as_of);
    }
  }, [data]);

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
              {WINDOWS.map((w) => {
                const on = view.kind === "days" && view.days === w.days;
                return (
                  <button
                    key={w.days}
                    type="button"
                    aria-pressed={on}
                    className={on ? "range on" : "range"}
                    onClick={() => setView({ kind: "days", days: w.days })}
                  >
                    {w.label}
                  </button>
                );
              })}
              {lastVisit && (
                <button
                  type="button"
                  aria-pressed={view.kind === "since"}
                  className={view.kind === "since" ? "range on" : "range"}
                  onClick={() => setView({ kind: "since" })}
                >
                  Since last visit ({formatShortDate(lastVisit)})
                </button>
              )}
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
              {data.since
                ? data.days === 0
                  ? `No new trading days since ${formatShortDate(data.since)}. Filings and headlines are those from after that date.`
                  : `Since your last visit (${formatShortDate(data.since)}): ${data.days} trading ${data.days === 1 ? "day" : "days"}, ${formatShortDate(data.window_start)} to ${formatShortDate(data.as_of)}.`
                : data.days === 1
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
