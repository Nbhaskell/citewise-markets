import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { formatDateTime, isStale } from "../lib/format";

/** One line telling the user how current the data is, and flagging problems instead of hiding them. */
export function FreshnessBar() {
  const status = useApi((signal) => api.status(signal));
  const health = useApi((signal) => api.health(signal));

  const warnings: string[] = [];
  let summary = "Checking data freshness…";

  if (status.error) {
    warnings.push(status.error);
    summary = "";
  } else if (status.data) {
    const latestPrice = status.data.companies.map((c) => c.last_price_date).filter(Boolean).sort().at(-1) ?? null;
    const run = status.data.runs[0];
    summary = latestPrice ? `Prices through ${latestPrice}` : "No price data yet";
    if (run) summary += ` · last refresh ${formatDateTime(run.started_at)}`;

    if (!run) warnings.push("The nightly refresh hasn't run yet, so data may be out of date.");
    else if (run.status !== "success") {
      warnings.push(`The last refresh finished as "${run.status}" with ${run.problems} problem(s). Some data may be out of date.`);
    }
    if (isStale(latestPrice)) warnings.push("Prices look out of date.");
  }

  const aiOffline = health.data && !health.data.ai_model_available;

  return (
    <div className="freshness" role="status">
      <span>{summary}</span>
      {aiOffline && <span className="flag warn">AI model offline: the copilot won't answer until Ollama is running</span>}
      {warnings.map((w) => (
        <span key={w} className="flag warn">
          {w}
        </span>
      ))}
    </div>
  );
}
