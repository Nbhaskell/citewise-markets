import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { directionOf, formatChangePct, formatShortDate } from "../lib/format";

const MAX_MOVES = 3;

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The latest trading day's changes in a few lines, with a link to the full page. */
export function ChangesTeaser() {
  const changes = useApi((signal) => api.changes({ days: 1 }, signal), []);
  const data = changes.data;
  const headlineCount = data ? data.headlines.reduce((n, c) => n + c.positive + c.negative, 0) : 0;

  return (
    <section className="card" aria-labelledby="teaser-title">
      <div className="card-head">
        <h2 id="teaser-title">What changed</h2>
        {data?.as_of && <span className="muted small">Latest trading day: {formatShortDate(data.as_of)}</span>}
      </div>

      {changes.loading && !data && <p className="muted">Loading…</p>}
      {changes.error && (
        <p role="alert" className="error">
          {changes.error} <button onClick={changes.reload}>Try again</button>
        </p>
      )}
      {data && data.as_of == null && <p className="muted">No prices are stored yet.</p>}
      {data && data.as_of != null && (
        <>
          <p>
            {count(data.moves.length, "big move", "big moves")} · {count(data.filings.length, "new filing", "new filings")}{" "}
            · {count(headlineCount, "positive or negative headline", "positive or negative headlines")}
          </p>
          {data.stale.length > 0 && (
            <p className="flag warn">
              No price yet for the latest day for {data.stale.map((s) => s.symbol).join(", ")}.
            </p>
          )}
          {data.moves.length > 0 && (
            <ul className="news-list" aria-label="Biggest moves">
              {data.moves.slice(0, MAX_MOVES).map((m) => (
                <li key={`${m.symbol}:${m.date}`}>
                  <Link className="symbol" to={`/stocks/${m.symbol}`}>
                    {m.symbol}
                  </Link>
                  <strong className={directionOf(m.change_pct)}>{formatChangePct(m.change_pct)}</strong>{" "}
                  {m.market_wide && <span className="pill flat">Market-wide day</span>}
                </li>
              ))}
            </ul>
          )}
          {data.moves.length > MAX_MOVES && (
            <p className="muted small">and {data.moves.length - MAX_MOVES} more</p>
          )}
        </>
      )}
      <p className="muted small note">
        <Link className="tap" to="/changes">See everything that changed →</Link>
      </p>
    </section>
  );
}
