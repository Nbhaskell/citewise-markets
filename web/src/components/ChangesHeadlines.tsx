import { Link } from "react-router-dom";
import type { ChangesOut } from "../api/types";
import { formatScore, moodForScore, relativeTime, safeHttpUrl } from "../lib/format";
import { NewsLabelPill } from "./SentimentPill";

/** Positive and negative headlines in the window (a few per company), and companies whose week-over-week news mood moved. */
export function ChangesHeadlines({ data }: { data: ChangesOut }) {
  const { headlines, mood_shifts: shifts, rules } = data;
  return (
    <section className="card" aria-labelledby="changes-news-title">
      <h2 id="changes-news-title">Notable headlines</h2>
      <p className="muted small">
        Only headlines labeled positive or negative, each story once, newest first. The labels come from a small local
        model and lean neutral, so "notable" means "labeled", not "important".
      </p>

      {shifts.length > 0 ? (
        <ul className="news-list" aria-label="Mood shifts">
          {shifts.map((s) => (
            <li key={s.symbol}>
              <Link className="symbol" to={`/stocks/${s.symbol}`}>
                {s.symbol}
              </Link>
              News mood moved: {moodForScore(s.score_now).label} ({formatScore(s.score_now)}, {s.stories_now} stories) over
              the last {rules.mood_days} days, against {moodForScore(s.score_before).label} ({formatScore(s.score_before)},{" "}
              {s.stories_before} stories) the {rules.mood_days} days before.
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">
          No company's news mood moved much from the week before. (Needs at least 10 stories in each week.)
        </p>
      )}

      {headlines.length === 0 ? (
        <p className="muted">No positive or negative headlines in this window.</p>
      ) : (
        headlines.map((c) => {
          const total = c.positive + c.negative;
          return (
            <div key={c.symbol}>
              <h3>
                <Link className="symbol" to={`/stocks/${c.symbol}`}>
                  {c.symbol}
                </Link>{" "}
                <span className="muted small">
                  {c.positive} positive, {c.negative} negative
                  {total > c.items.length ? ` · showing the newest ${c.items.length}` : ""}
                </span>
              </h3>
              <ul className="news-list">
                {c.items.map((h) => (
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
            </div>
          );
        })
      )}
    </section>
  );
}
