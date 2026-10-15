import { Link } from "react-router-dom";
import type { ChangeFiling } from "../api/types";
import { formatShortDate, safeHttpUrl } from "../lib/format";

/** Filings filed inside the window. When there are none, says what the newest stored one is, so an empty list is not a mystery. */
export function ChangesFilings({ filings, newest }: { filings: ChangeFiling[]; newest: ChangeFiling | null | undefined }) {
  return (
    <section className="card" aria-labelledby="changes-filings-title">
      <h2 id="changes-filings-title">New filings</h2>
      {filings.length === 0 ? (
        <p className="muted">
          Nothing was filed in this window.
          {newest
            ? ` The newest stored filing is ${newest.symbol}'s ${newest.form}, filed ${formatShortDate(newest.filed_at)}.`
            : " No filings are stored yet."}
        </p>
      ) : (
        <ul className="news-list">
          {filings.map((f) => (
            <li key={f.accession_number}>
              <div className="news-meta">
                <Link className="symbol" to={`/stocks/${f.symbol}`}>
                  {f.symbol}
                </Link>
                <span>{f.form}</span>
                <span className="muted small">
                  filed {formatShortDate(f.filed_at)}
                  {f.period_of_report ? ` · period ended ${formatShortDate(f.period_of_report)}` : ""}
                </span>
              </div>
              {safeHttpUrl(f.url) && (
                <a href={safeHttpUrl(f.url)} target="_blank" rel="noopener noreferrer">
                  View on SEC
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
