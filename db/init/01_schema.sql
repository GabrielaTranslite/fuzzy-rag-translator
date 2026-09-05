-- Canonical schema for the monitoring table. Single source of truth shared by:
--   * the Streamlit app (writes one row per inference, updates feedback)
--   * scripts/seed_monitoring.py (loads historical eval rows so charts are not empty)
--   * Grafana (reads for the dashboard)
-- Mounted into Postgres at /docker-entrypoint-initdb.d so the table exists on first boot,
-- before the app or the seed run. db.ensure_schema() in the app must match this exactly.

CREATE TABLE IF NOT EXISTS repair_logs (
    id               TEXT PRIMARY KEY,          -- app-generated uuid; lets feedback update the row
    ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_text      TEXT NOT NULL,             -- the English input (normalized query is fine)
    output_text      TEXT NOT NULL,             -- the model output shown to the user
    tm_source        TEXT,                      -- retrieved approved source (source_norm), null if fell back
    tm_target        TEXT,                      -- retrieved approved target, null if fell back
    retrieval_score  DOUBLE PRECISION,          -- fuzzy similarity 0..100
    preservation     DOUBLE PRECISION,          -- normalized edit distance output vs tm_target (repair only)
    context          TEXT,                      -- gettext context hint if any
    model            TEXT,                      -- e.g. gpt-4o / gpt-4o-mini
    prompt_tokens    INTEGER,
    completion_tokens INTEGER,
    cost_usd         DOUBLE PRECISION,          -- computed from usage x price table
    latency_ms       INTEGER,
    condition        TEXT,                      -- 'repair' or 'scratch_context' (the fallback below threshold)
    fell_back        BOOLEAN DEFAULT FALSE,     -- true when retrieval_score < threshold -> from-scratch
    feedback         TEXT,                      -- 'good' / 'needs_fixing' / NULL
    user_correction  TEXT
);

CREATE INDEX IF NOT EXISTS repair_logs_ts_idx ON repair_logs (ts);
