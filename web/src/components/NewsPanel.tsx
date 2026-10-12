import { useState } from "react";
import { api } from "../api/client";
import type { NewsLabel } from "../api/types";
import { useApi } from "../hooks/useApi";
import { relativeTime, safeHttpUrl } from "../lib/format";
import { NewsLabelPill } from "./SentimentPill";

const DAYS = 3;
const MOVERS: NewsLabel[] = ["positive", "negative"];

export function NewsPanel() {
  // Most headlines are routine (quote pages, "X vs Y" comparisons), so start with the ones labeled good or bad.
  const [moversOnly, setMoversOnly] = useState(true);
  const news = useApi(
    (signal) => api.news({ days: DAYS, limit: 12, sentiment: moversOnly ? MOVERS : undefined }, signal),
    [moversOnly],
  );

  return (
    <section className="card" aria-labelledby="news-title">
      <div className="card-head">
        <h2 id="news-title">Latest news</h2>
        <label className="toggle">
          <input type="checkbox" checked={moversOnly} onChange={(e) => setMoversOnly(e.target.checked)} />
          Positive and negative only
        </label>
      </div>

      {news.loading && <p className="muted">Loading headlines…</p>}
      {news.error && (
        <p role="alert" className="error">
          {news.error} <button onClick={news.reload}>Try again</button>
        </p>
      )}
      {news.data && news.data.length === 0 && (
        <p className="muted">
          {moversOnly
            ? `No positive or negative headlines in the last ${DAYS} days.`
            : `No headlines in the last ${DAYS} days.`}
        </p>
      )}
      {news.data && news.data.length > 0 && (
        <ul className="news-list">
          {news.data.map((item) => (
            <li key={`${item.id}:${item.symbol}`}>
              <div className="news-meta">
                <span className="symbol">{item.symbol}</span>
                <NewsLabelPill label={item.sentiment} />
                <span className="muted small">
                  {item.publisher ?? "Unknown source"} · {relativeTime(item.published_at)}
                </span>
              </div>
              {safeHttpUrl(item.url) ? (
                <a href={safeHttpUrl(item.url)} target="_blank" rel="noopener noreferrer">
                  {item.title}
                </a>
              ) : (
                <span>{item.title}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
