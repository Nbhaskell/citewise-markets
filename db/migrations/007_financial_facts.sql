-- Raw figures from companies' SEC filings (the "company facts" feed). Ratios are never stored: Python computes them
-- from these rows when asked, so every number can be traced to a filing and recomputed.
CREATE TABLE financial_facts (
    id               bigserial PRIMARY KEY,
    symbol           text NOT NULL REFERENCES instruments (symbol),
    taxonomy         text NOT NULL,             -- 'us-gaap' or 'dei' (cover-page facts)
    concept          text NOT NULL,             -- e.g. 'NetIncomeLoss'
    unit             text NOT NULL,             -- 'USD', 'USD/shares', or 'shares'
    period_start     date,                      -- null for a point in time (a share count, a balance)
    period_end       date NOT NULL,
    value            numeric NOT NULL,
    accession_number text NOT NULL,             -- the filing this value came from
    form             text NOT NULL,             -- 10-K, 10-Q, or an amendment
    filed_at         date NOT NULL,
    fetched_at       timestamptz NOT NULL DEFAULT now()
);

-- A value is the same fact when concept, period, and filing match. A restated value arrives in a later filing and is
-- kept as its own row; the newest filing wins when figures are computed.
CREATE UNIQUE INDEX financial_facts_unique_idx ON financial_facts
    (symbol, concept, unit, (COALESCE(period_start, DATE '0001-01-01')), period_end, accession_number);
CREATE INDEX financial_facts_symbol_idx ON financial_facts (symbol, concept, period_end DESC);
