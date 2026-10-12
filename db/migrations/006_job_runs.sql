CREATE TABLE job_runs (
    id          bigserial PRIMARY KEY,
    job         text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    details     jsonb
);
CREATE INDEX job_runs_started_idx ON job_runs (job, started_at DESC);
