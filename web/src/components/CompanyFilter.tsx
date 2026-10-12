import type { StockSummary } from "../api/types";

export const MAX_COMPANIES = 5; // the API accepts at most five tickers per question

interface Props {
  stocks: StockSummary[];
  selected: string[];
  onChange: (symbols: string[]) => void;
  disabled?: boolean;
}

/** Which companies' filings to search. Nothing selected means "all of them". */
export function CompanyFilter({ stocks, selected, onChange, disabled }: Props) {
  const full = selected.length >= MAX_COMPANIES;

  function toggle(symbol: string) {
    onChange(selected.includes(symbol) ? selected.filter((s) => s !== symbol) : [...selected, symbol]);
  }

  return (
    <fieldset className="filter" disabled={disabled}>
      <legend>Search in</legend>
      <div className="chips">
        <button type="button" className="chip" aria-pressed={selected.length === 0} onClick={() => onChange([])}>
          All companies
        </button>
        {stocks.map((s) => {
          const on = selected.includes(s.symbol);
          return (
            <button
              key={s.symbol}
              type="button"
              className="chip"
              aria-pressed={on}
              disabled={full && !on}
              title={full && !on ? `You can pick up to ${MAX_COMPANIES} companies` : s.name ?? undefined}
              onClick={() => toggle(s.symbol)}
            >
              {s.symbol}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
