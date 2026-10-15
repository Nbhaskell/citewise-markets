import { useEffect, useState, type FormEvent } from "react";
import { api, isAbort } from "../api/client";
import type { AddJobOut, AddLookupOut, ReportCompany } from "../api/types";

const POLL_MS = 3000;
const LIVE = new Set(["queued", "running"]);
const RETRY = new Set(["partial", "failed", "interrupted"]);

type State =
  | { kind: "idle" }
  | { kind: "looking"; ticker: string }
  | { kind: "confirm"; info: AddLookupOut }
  | { kind: "starting"; symbol: string }
  | { kind: "job"; job: AddJobOut; pollError?: string }
  | { kind: "error"; message: string; symbol?: string };

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function headline(job: AddJobOut): string {
  const verdicts = job.companies.map((c) => c.verdict);
  switch (job.status) {
    case "queued":
      return "Starting...";
    case "running":
      return job.message ?? "Working...";
    case "success":
      return verdicts.some((v) => v.startsWith("UPDATED")) ? `${job.symbol} is up to date` : `${job.symbol} was added`;
    case "partial":
      return `${job.symbol} was added, with gaps`;
    case "failed":
      return `${job.symbol} was not added`;
    case "interrupted":
      return `${job.symbol}: the add stopped early`;
  }
}

function CompanyReport({ company }: { company: ReportCompany }) {
  return (
    <div className="add-report">
      <h4>
        {company.symbol}
        {company.name ? ` - ${company.name}` : ""}: {company.verdict}
      </h4>
      <ul>
        {company.lines.map((line) => (
          <li key={line.step}>
            <strong>{line.step}</strong> {line.status}: {line.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AddCompanyBox() {
  const [ticker, setTicker] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  // While an add runs, ask the API for its progress every few seconds.
  useEffect(() => {
    if (state.kind !== "job" || !LIVE.has(state.job.status)) return;
    const jobId = state.job.job_id;
    const job = state.job;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setState({ kind: "job", job: await api.addJob(jobId, controller.signal) });
      } catch (err) {
        if (isAbort(err)) return;
        setState({ kind: "job", job, pollError: "Couldn't get the latest progress. Trying again..." });
      }
    }, POLL_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [state]);

  async function look(event: FormEvent) {
    event.preventDefault();
    const value = ticker.trim();
    if (!value) return;
    setState({ kind: "looking", ticker: value });
    try {
      setState({ kind: "confirm", info: await api.addLookup(value) });
    } catch (err) {
      setState({ kind: "error", message: errorText(err) });
    }
  }

  async function start(symbol: string) {
    setState({ kind: "starting", symbol });
    try {
      setState({ kind: "job", job: await api.startAdd(symbol) });
    } catch (err) {
      // 409 means another update holds the lock; the API's own message says so.
      setState({ kind: "error", message: errorText(err), symbol });
    }
  }

  function reset() {
    setTicker("");
    setState({ kind: "idle" });
  }

  return (
    <section className="card add-company" aria-labelledby="add-company-title">
      <h2 id="add-company-title">Add a company</h2>
      <p className="muted small">
        Adds prices, filings, headlines, and figures for a US-listed company. It can take a few minutes. There is no
        remove button yet, so check the name before you confirm.
      </p>

      {(state.kind === "idle" || state.kind === "looking") && (
        <form onSubmit={look} className="add-form">
          <label htmlFor="add-ticker">Ticker</label>
          <input
            id="add-ticker"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="e.g. TSLA"
            maxLength={12}
            autoComplete="off"
            disabled={state.kind === "looking"}
          />
          <button type="submit" disabled={state.kind === "looking" || !ticker.trim()}>
            {state.kind === "looking" ? "Looking up..." : "Look up"}
          </button>
        </form>
      )}

      {state.kind === "confirm" && (
        <div role="group" aria-label="Confirm the company">
          <p>
            <strong>Add {state.info.name} ({state.info.symbol})?</strong>
          </p>
          {state.info.tracked && <p className="small">It is already tracked. Adding it again brings its data up to date.</p>}
          <button type="button" onClick={() => start(state.info.symbol)}>
            Yes, add {state.info.symbol}
          </button>{" "}
          <button type="button" onClick={reset}>
            Cancel
          </button>
        </div>
      )}

      {state.kind === "starting" && <p role="status">Starting the add for {state.symbol}...</p>}

      {state.kind === "error" && (
        <div role="alert" className="warning">
          <p>{state.message}</p>
          {state.symbol && (
            <button type="button" onClick={() => start(state.symbol!)}>
              Try again
            </button>
          )}{" "}
          <button type="button" onClick={reset}>
            Start over
          </button>
        </div>
      )}

      {state.kind === "job" && (
        <div aria-live="polite">
          <h3>{headline(state.job)}</h3>
          {state.job.message && !state.job.companies.length && <p>{state.job.message}</p>}
          {state.job.companies.map((company) => (
            <CompanyReport key={company.symbol} company={company} />
          ))}
          {state.pollError && <p className="small muted">{state.pollError}</p>}
          {RETRY.has(state.job.status) && (
            <p>
              <button type="button" onClick={() => start(state.job.symbol)}>
                Retry {state.job.symbol}
              </button>{" "}
              <span className="small">Retrying is safe: a company already added is just brought up to date.</span>
            </p>
          )}
          {!LIVE.has(state.job.status) && (
            <button type="button" onClick={reset}>
              Add another company
            </button>
          )}
        </div>
      )}
    </section>
  );
}
