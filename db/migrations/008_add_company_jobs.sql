-- Add-company jobs (the web app's "Add company" box). Extra columns on job_runs so a running add can say which
-- company and step it is on, when it last reported in, and what each company ended with. All nullable: the nightly
-- refresh rows leave them empty.
ALTER TABLE job_runs
    ADD COLUMN symbols      text[],
    ADD COLUMN current_step text,
    ADD COLUMN heartbeat_at timestamptz,
    ADD COLUMN report       jsonb;
