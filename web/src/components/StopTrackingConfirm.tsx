import { useState } from "react";
import { api } from "../api/client";
import type { RemoveOut } from "../api/types";

type State = { kind: "confirm" } | { kind: "removing" } | { kind: "error"; message: string };

/**
 * The "Are you sure?" for switching a company off. Removing deletes nothing: the company is switched off and its stored data is kept,
 * so switching it back on later brings it back with that history. Nothing is sent until the reader confirms.
 */
export function StopTrackingConfirm({
  symbol,
  name,
  onRemoved,
  onCancel,
}: {
  symbol: string;
  name: string | null | undefined;
  onRemoved: (result: RemoveOut) => void;
  onCancel: () => void;
}) {
  const [state, setState] = useState<State>({ kind: "confirm" });
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

  if (state.kind === "error") {
    return (
      <div role="alert" className="warning confirm-box">
        <p>{state.message}</p>
        <button type="button" onClick={remove}>
          Try again
        </button>{" "}
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div role="group" aria-label={`Confirm: stop tracking ${symbol}`} className="confirm-box">
      <p>
        <strong>Stop tracking {label}?</strong>
      </p>
      <p className="small">
        Nothing is deleted. It leaves the dashboard, the nightly refresh, "What changed", and the copilot, but its prices, filings,
        headlines, and figures stay stored. You can switch {symbol} back on from the "Not tracked" list on the dashboard.
      </p>
      <button type="button" onClick={remove} disabled={state.kind === "removing"}>
        {state.kind === "removing" ? "Removing..." : `Yes, stop tracking ${symbol}`}
      </button>{" "}
      <button type="button" onClick={onCancel} disabled={state.kind === "removing"}>
        Cancel
      </button>
    </div>
  );
}
