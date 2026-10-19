import { useEffect, useState } from "react";
import { api, isAbort } from "../api/client";
import type { AddJobOut } from "../api/types";

const LIVE = new Set(["queued", "running"]);

type State =
  | { kind: "confirm" }
  | { kind: "starting" }
  | { kind: "job"; job: AddJobOut; pollError?: string }
  | { kind: "error"; message: string };

/**
 * The "Are you sure?" for switching a removed company back on. It runs the same add the "Add a company" box runs (so the data is
 * brought up to date, which takes a few minutes), shows its progress, and calls `onDone` when the company is tracked again. Nothing
 * starts until the reader confirms. `pollMs` is only for tests.
 */
export function TrackAgainConfirm({
  symbol,
  name,
  onDone,
  onCancel,
  onRunning,
  pollMs = 3000,
}: {
  symbol: string;
  name: string | null | undefined;
  onDone: (job: AddJobOut) => void;
  onCancel: () => void;
  /** Called with true while the update is starting or running, and false otherwise, so the page can show its switch as busy. */
  onRunning?: (running: boolean) => void;
  pollMs?: number;
}) {
  const [state, setState] = useState<State>({ kind: "confirm" });
  const label = name ? `${name} (${symbol})` : symbol;
  const running = state.kind === "starting" || state.kind === "job";
  useEffect(() => {
    onRunning?.(running);
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps

  // While the update runs, ask the API for its progress every few seconds; when it ends, report it.
  useEffect(() => {
    if (state.kind !== "job") return;
    const job = state.job;
    if (!LIVE.has(job.status)) {
      if (job.status === "success" || job.status === "partial") {
        onDone(job);
      } else {
        // failed or interrupted: the company is still switched off
        setState({ kind: "error", message: job.message ?? `${symbol} was not switched back on. Try again.` });
      }
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setState({ kind: "job", job: await api.addJob(job.job_id, controller.signal) });
      } catch (err) {
        if (isAbort(err)) return;
        setState({ kind: "job", job, pollError: "Couldn't get the latest progress. Trying again..." });
      }
    }, pollMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [state]); // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setState({ kind: "starting" });
    try {
      setState({ kind: "job", job: await api.startAdd(symbol) });
    } catch (err) {
      // 409 means another update holds the lock; the API's own message says so.
      setState({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }

  if (state.kind === "error") {
    return (
      <div role="alert" className="warning confirm-box">
        <p>{state.message}</p>
        <button type="button" onClick={start}>
          Try again
        </button>{" "}
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    );
  }

  if (state.kind === "starting" || state.kind === "job") {
    const step = state.kind === "job" ? state.job.step : null;
    return (
      <div role="status" className="confirm-box" aria-live="polite">
        <p>
          <strong>Updating {symbol}…</strong> {step ? `Working on: ${step}. ` : ""}This takes a few minutes. Keep this page open; it
          switches {symbol} back on when the update finishes.
        </p>
        {state.kind === "job" && state.pollError && <p className="small muted">{state.pollError}</p>}
      </div>
    );
  }

  return (
    <div role="group" aria-label={`Confirm: track ${symbol} again`} className="confirm-box">
      <p>
        <strong>Track {label} again?</strong>
      </p>
      <p className="small">
        This brings its data up to date first, which takes a few minutes and needs Ollama running. Its earlier prices, filings, and
        headlines are still stored, so nothing starts from scratch.
      </p>
      <button type="button" onClick={start}>
        Yes, track {symbol} again
      </button>{" "}
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}
