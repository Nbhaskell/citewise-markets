import { useState } from "react";
import { api } from "../api/client";
import type { RemoveOut } from "../api/types";

type State = { kind: "idle" } | { kind: "confirm" } | { kind: "removing" } | { kind: "error"; message: string };

/**
 * "Stop tracking" for one company, with a confirmation step. Removing deletes nothing: the company is switched off and its
 * stored data is kept, so adding it again brings it back. The page hides the company once `onRemoved` is called.
 */
export function RemoveCompany({
  symbol,
  name,
  onRemoved,
}: {
  symbol: string;
  name: string | null | undefined;
  onRemoved: (result: RemoveOut) => void;
}) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const label = name ? `${name} (${symbol})` : symbol;

  async function remove() {
    setState({ kind: "removing" });
    try {
      onRemoved(await api.removeCompany(symbol));
    } catch (err) {
      // 404 (already removed) and 409 (another update is running) arrive with the API's own plain message.
      setState({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }

  return (
    <section className="card remove-company" aria-labelledby="remove-company-title">
      <h2 id="remove-company-title">Stop tracking {symbol}</h2>
      {state.kind === "idle" && (
        <>
          <p className="muted small">
            Takes {symbol} off the dashboard, the nightly refresh, "What changed", and the copilot.
          </p>
          <button type="button" onClick={() => setState({ kind: "confirm" })}>
            Stop tracking {symbol}
          </button>
        </>
      )}

      {(state.kind === "confirm" || state.kind === "removing") && (
        <div role="group" aria-label="Confirm removing the company">
          <p>
            <strong>Stop tracking {label}?</strong>
          </p>
          <p className="small">
            Nothing is deleted. Its prices, filings, headlines, and figures stay stored, and adding {symbol} again from the
            dashboard brings it back with that history.
          </p>
          <button type="button" onClick={remove} disabled={state.kind === "removing"}>
            {state.kind === "removing" ? "Removing..." : `Yes, stop tracking ${symbol}`}
          </button>{" "}
          <button type="button" onClick={() => setState({ kind: "idle" })} disabled={state.kind === "removing"}>
            Cancel
          </button>
        </div>
      )}

      {state.kind === "error" && (
        <div role="alert" className="warning">
          <p>{state.message}</p>
          <button type="button" onClick={remove}>
            Try again
          </button>{" "}
          <button type="button" onClick={() => setState({ kind: "idle" })}>
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}
