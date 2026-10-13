import { api } from "../api/client";
import type { FundamentalFigure, Fundamentals as FundamentalsData } from "../api/types";
import { useApi } from "../hooks/useApi";
import {
  directionOf, formatBigMoney, formatChangePct, formatFraction, formatPrice, formatShareCount, formatShortDate,
} from "../lib/format";

/** The recipe behind one number, one click away: how it was built and which filings it came from. */
function Recipe({ how, sources }: { how: string; sources?: string[] }) {
  return (
    <details className="recipe">
      <summary>How this was calculated</summary>
      <p className="small">{how}</p>
      {sources && sources.length > 0 && (
        <ul className="small">
          {sources.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}
    </details>
  );
}

function FigureRow({ label, figure, format }: { label: string; figure: FundamentalFigure; format: (v: number) => string }) {
  const growth = figure.growth;
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {format(figure.value)}
        {growth != null && (
          <span className="block small">
            <span className={directionOf(growth * 100)}>{formatChangePct(growth * 100)}</span>{" "}
            <span className="muted">{figure.growth_label}</span>
          </span>
        )}
        <Recipe how={figure.how} sources={figure.sources} />
      </dd>
    </div>
  );
}

function Margin({ label, value, of }: { label: string; value: number | null | undefined; of: string }) {
  if (value == null) return null;
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {formatFraction(value)}
        <span className="muted small block">{of} ÷ revenue, last 12 months</span>
      </dd>
    </div>
  );
}

function Figures({ f }: { f: FundamentalsData }) {
  const price = f.price != null ? formatPrice(f.price) : null;
  const eps = f.diluted_eps;
  return (
    <>
      <p className="muted small">
        Last 12 months, through {formatShortDate(f.period_end)}. Price {price ?? "n/a"}
        {f.price_date ? ` on ${formatShortDate(f.price_date)}` : ""}.
      </p>
      {f.cautions.map((caution) => (
        <p key={caution} role="note" className="flag warn">
          <strong>Caution:</strong> {caution}
        </p>
      ))}
      <dl className="stats">
        <div>
          <dt>Market value</dt>
          <dd>
            {f.market_value != null ? formatBigMoney(f.market_value) : <span className="muted">n/a</span>}
            {f.market_value != null && f.shares && price && (
              <Recipe how={`${formatShareCount(f.shares.value)} shares (from ${f.shares.source}) × ${price}, the latest close`} />
            )}
          </dd>
        </div>
        <div>
          <dt>P/E</dt>
          <dd>
            {f.pe != null ? f.pe.toFixed(1) : <span className="muted">n/a</span>}
            {f.pe != null && eps && price && (
              <Recipe how={`${price}, the latest close, ÷ ${formatPrice(eps.value)}, diluted earnings per share over the last 12 months`} />
            )}
            {f.pe == null && f.pe_note && <span className="muted small block">{f.pe_note}</span>}
          </dd>
        </div>
        {f.revenue && <FigureRow label="Revenue" figure={f.revenue} format={formatBigMoney} />}
        {f.net_income && <FigureRow label="Net income" figure={f.net_income} format={formatBigMoney} />}
        {eps && <FigureRow label="Diluted EPS" figure={eps} format={formatPrice} />}
        {f.operating_income && <FigureRow label="Operating income" figure={f.operating_income} format={formatBigMoney} />}
        <Margin label="Gross margin" value={f.gross_margin} of="Gross profit" />
        <Margin label="Operating margin" value={f.operating_margin} of="Operating income" />
        <Margin label="Net margin" value={f.net_margin} of="Net income" />
        {f.shares && (
          <div>
            <dt>Shares outstanding</dt>
            <dd>
              {formatShareCount(f.shares.value)}
              <span className="muted small block">as of {formatShortDate(f.shares.as_of)}</span>
              <Recipe how={`Read from ${f.shares.source}.`} />
            </dd>
          </div>
        )}
      </dl>
      <p className="muted small">Worked out from the company's SEC filings. A summary of public data, not financial advice.</p>
    </>
  );
}

export function Fundamentals({ symbol }: { symbol: string }) {
  const result = useApi((signal) => api.fundamentals(symbol, signal), [symbol]);
  const data = result.data;

  return (
    <section className="card" aria-labelledby="fundamentals-title">
      <h2 id="fundamentals-title">Fundamentals</h2>
      {result.loading && !data && <p className="muted">Loading fundamentals…</p>}
      {result.error && (
        <p role="alert" className="error">
          {result.error} <button onClick={result.reload}>Try again</button>
        </p>
      )}
      {data && !data.available && (
        <>
          <p className="muted">No fundamentals for {symbol}: {data.unavailable_reason}.</p>
          <p className="muted small">To fetch them: python -m data.ingest_fundamentals {symbol}</p>
        </>
      )}
      {data && data.available && <Figures f={data} />}
    </section>
  );
}
