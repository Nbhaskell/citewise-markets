CREATE TABLE instruments (
    symbol      text PRIMARY KEY,
    name        text,
    exchange    text,
    sector      text,
    industry    text,
    currency    text NOT NULL DEFAULT 'USD',
    active      boolean NOT NULL DEFAULT true,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE prices_daily (
    symbol      text NOT NULL REFERENCES instruments (symbol),
    ts          date NOT NULL,
    open        numeric(18, 6),
    high        numeric(18, 6),
    low         numeric(18, 6),
    close       numeric(18, 6) NOT NULL,
    adj_close   numeric(18, 6),
    volume      bigint,
    source      text NOT NULL,
    PRIMARY KEY (symbol, ts)
);

SELECT create_hypertable('prices_daily', 'ts', chunk_time_interval => INTERVAL '1 year');

CREATE TABLE ingestion_runs (
    id          bigserial PRIMARY KEY,
    source      text NOT NULL,
    symbol      text,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    rows_written integer,
    error       text
);
