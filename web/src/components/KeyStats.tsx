import type { StockDetail } from "../api/types";
import { directionOf, formatChangePct, formatPrice, formatShortDate, formatVolume, moodFor, positionInRange } from "../lib/format";
import { MoodPill } from "./SentimentPill";

export function KeyStats({ stock }: { stock: StockDetail }) {
  const position = positionInRange(stock.last_price, stock.low_52w, stock.high_52w);
  const s = stock.sentiment;

  return (
    <section className="card" aria-labelledby="stats-title">
      <h2 id="stats-title">Key stats</h2>
      <dl className="stats">
        <div>
          <dt>Last price</dt>
          <dd>
            {formatPrice(stock.last_price)}{" "}
            <span className={directionOf(stock.change_pct)}>{formatChangePct(stock.change_pct)}</span>
          </dd>
        </div>
        <div>
          <dt>As of</dt>
          <dd>{formatShortDate(stock.as_of)}</dd>
        </div>
        <div className="wide">
          <dt>52-week range</dt>
          <dd>
            <div className="range-labels">
              <span>{formatPrice(stock.low_52w)}</span>
              <span>{formatPrice(stock.high_52w)}</span>
            </div>
            {position !== null ? (
              <div
                className="range-bar"
                role="img"
                aria-label={`The price is ${Math.round(position)} percent of the way from the 52-week low to the high`}
              >
                <span className="range-marker" style={{ left: `${position.toFixed(1)}%` }} />
              </div>
            ) : (
              <span className="muted small">Not enough history</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Volume</dt>
          <dd>{formatVolume(stock.volume)}</dd>
        </div>
        <div>
          <dt>Exchange</dt>
          <dd>{stock.exchange ?? "n/a"}</dd>
        </div>
        <div>
          <dt>Sector</dt>
          <dd>{stock.sector ?? "n/a"}</dd>
        </div>
        <div>
          <dt>Industry</dt>
          <dd>{stock.industry ?? "n/a"}</dd>
        </div>
        <div className="wide">
          <dt>News mood, last {s.days} days</dt>
          <dd>
            <MoodPill mood={moodFor(s)} />
            <span className="muted small block">
              {s.positive} positive · {s.negative} negative · {s.neutral} routine · {s.irrelevant} off-topic
            </span>
          </dd>
        </div>
      </dl>
    </section>
  );
}
