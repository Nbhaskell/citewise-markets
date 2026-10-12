CREATE TABLE news_sentiment (
    article_id text NOT NULL REFERENCES news_articles (id) ON DELETE CASCADE,
    symbol     text NOT NULL REFERENCES instruments (symbol),
    label      text NOT NULL CHECK (label IN ('positive', 'negative', 'neutral', 'irrelevant')),
    model      text NOT NULL,
    scored_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, symbol, model)
);
CREATE INDEX news_sentiment_symbol_idx ON news_sentiment (symbol);
