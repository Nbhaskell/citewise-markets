CREATE TABLE filing_chunks (
    id               bigserial PRIMARY KEY,
    accession_number text NOT NULL REFERENCES filings (accession_number) ON DELETE CASCADE,
    chunk_index      integer NOT NULL,
    section          text,
    text             text NOT NULL,
    embedding        vector(384) NOT NULL,
    embedding_model  text NOT NULL,
    UNIQUE (accession_number, chunk_index)
);

CREATE INDEX filing_chunks_embedding_idx
    ON filing_chunks USING hnsw (embedding vector_cosine_ops);
