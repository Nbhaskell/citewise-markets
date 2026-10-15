import { Link } from "react-router-dom";
import type { ChangesOut } from "../api/types";
import { directionOf, formatChangePct, formatPrice, formatShortDate, relativeTime, safeHttpUrl } from "../lib/format";
import { NewsLabelPill } from "./SentimentPill";

function marketDayText(d: ChangesOut["market_days"][number]): string {
  const way = d.direction === "up" ? "rose" : "fell";
  return `${formatShortDate(d.date)}: ${d.moved_that_way} of ${d.companies} companies ${way} by more than 1%. Moves that day may reflect the whole market, not the company.`;
}

/** Days with an unusually large close-to-close move, measured against each company's own usual day. */
export function ChangesMoves({ data }: { data: ChangesOut }) {
  const { moves, market_days: marketDays, rules } = data;
  return (
    <section className="card" aria-labelledby="changes-moves-title">
      <h2 id="changes-moves-title">Big moves</h2>
      <p className="muted small">
        Listed when a day's move is at least {rules.min_move_pct}% and at least {rules.typical_multiple} times the company's
        usual daily move (the median over the {rules.baseline_days} days before the window).
      </p>
      {marketDays.map((d) => (
        <p key={`${d.date}${d.direction}`} className="flag warn" role="note">
          Market-wide day. {marketDayText(d)}
        </p>
      ))}
      {moves.length === 0 ? (
        <p className="muted">No unusually big moves in this window.</p>
      ) : (
        <ul className="news-list">
          {moves.map((m) => (
            <li key={`${m.symbol}:${m.date}`}>
              <div className="news-meta">
                <Link className="symbol" to={`/stocks/${m.symbol}`}>
                  {m.symbol}
                </Link>
                <strong className={directionOf(m.change_pct)}>{formatChangePct(m.change_pct)}</strong>
                <span className="muted small">
                  {formatShortDate(m.date)} · closed {formatPrice(m.close)}, against {formatPrice(m.previous_close)} on{" "}
                  {formatShortDate(m.previous_date)}
                </span>
                {m.market_wide && <span className="pill flat">Market-wide day</span>}
              </div>
              <p className="muted small">
                {m.typical_pct == null
                  ? "Not enough earlier history to know this company's usual move."
                  : `Usual day: ±${m.typical_pct.toFixed(2)}%.`}{" "}
                Listed at {m.threshold_pct.toFixed(2)}% or more.
              </p>
              {m.headlines.length === 0 ? (
                <p className="muted small">No stored headlines were published about it that day.</p>
              ) : (
                <>
                  <p className="muted small">Headlines published that day (timing only; they don't show why it moved):</p>
                  <ul className="news-list">
                    {m.headlines.map((h) => (
                      <li key={h.id}>
                        <div className="news-meta">
                          <NewsLabelPill label={h.sentiment} />
                          <span className="muted small">
                            {h.publisher ?? "Unknown source"} · {relativeTime(h.published_at)}
                          </span>
                        </div>
                        {safeHttpUrl(h.url) ? (
                          <a href={safeHttpUrl(h.url)} target="_blank" rel="noopener noreferrer">
                            {h.title}
                          </a>
                        ) : (
                          <span>{h.title}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
