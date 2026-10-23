import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { formatShortDate, safeHttpUrl } from "../lib/format";

export function FilingsList({ symbol }: { symbol: string }) {
  const filings = useApi((signal) => api.filings(symbol, signal), [symbol]);

  return (
    <section className="card" aria-labelledby="filings-title">
      <h2 id="filings-title">SEC filings</h2>
      {filings.loading && !filings.data && <p className="muted">Loading filings…</p>}
      {filings.error && (
        <p role="alert" className="error">
          {filings.error} <button onClick={filings.reload}>Try again</button>
        </p>
      )}
      {filings.data && filings.data.length === 0 && (
        <p className="muted">No filings stored for {symbol} yet. Add them with: python -m data.ingest_filings {symbol}</p>
      )}
      {filings.data && filings.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Form</th>
                <th scope="col">Filed</th>
                <th scope="col">Period ended</th>
                <th scope="col">Copilot</th>
                <th scope="col">
                  <span className="sr-only">Link</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filings.data.map((f) => (
                <tr key={f.accession_number}>
                  <th scope="row">{f.form}</th>
                  <td>{formatShortDate(f.filed_at)}</td>
                  <td>{formatShortDate(f.period_of_report)}</td>
                  <td>
                    {f.searchable ? (
                      <span className="pill up">Searchable</span>
                    ) : (
                      <span className="pill flat" title="Not embedded yet, so the copilot can't use it">
                        Not indexed
                      </span>
                    )}
                  </td>
                  <td>
                    {safeHttpUrl(f.url) && (
                      <a className="tap" href={safeHttpUrl(f.url)} target="_blank" rel="noopener noreferrer">
                        View on SEC
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
