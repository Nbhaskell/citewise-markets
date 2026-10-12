ALTER TABLE instruments ADD COLUMN cik text;

CREATE TABLE filings (
    accession_number text PRIMARY KEY,
    symbol           text NOT NULL REFERENCES instruments (symbol),
    cik              text NOT NULL,
    form             text NOT NULL,
    filed_at         date NOT NULL,
    period_of_report date,
    url              text NOT NULL,
    text             text NOT NULL,
    fetched_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX filings_symbol_filed_idx ON filings (symbol, filed_at DESC);

CREATE TABLE news_articles (
    id           text PRIMARY KEY,
    source       text NOT NULL,
    title        text NOT NULL,
    publisher    text,
    url          text NOT NULL,
    published_at timestamptz NOT NULL,
    fetched_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX news_articles_published_idx ON news_articles (published_at DESC);

CREATE TABLE news_article_symbols (
    article_id text NOT NULL REFERENCES news_articles (id) ON DELETE CASCADE,
    symbol     text NOT NULL REFERENCES instruments (symbol),
    PRIMARY KEY (article_id, symbol)
);
CREATE INDEX news_article_symbols_symbol_idx ON news_article_symbols (symbol);
