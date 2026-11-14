-- Bảng etl_log.run_history, etl_log.error_queue và etl_log.quality_check.

CREATE TABLE IF NOT EXISTS etl_log.run_history (
    run_id                          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at                      TIMESTAMP NOT NULL DEFAULT now(),
    finished_at                     TIMESTAMP,
    "status"                        TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    "data_source"                   TEXT,
    "message"                       TEXT
);

CREATE TABLE IF NOT EXISTS etl_log.error_queue (
    error_id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id                          INTEGER NOT NULL REFERENCES etl_log.run_history(run_id),
    rule_code                       TEXT NOT NULL,
    source_table                    TEXT NOT NULL,
    record_key                      TEXT,
    "column_name"                   TEXT,
    raw_value                       TEXT,
    reason                          TEXT,
    created_at                      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl_log.quality_check (
    check_id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id                          INTEGER NOT NULL REFERENCES etl_log.run_history(run_id),
    category                        TEXT NOT NULL,
    check_name                      TEXT NOT NULL,
    expected                        NUMERIC,
    actual                          NUMERIC,
    passed                          BOOLEAN GENERATED ALWAYS AS (expected IS NOT DISTINCT FROM actual) STORED,
    checked_at                      TIMESTAMP NOT NULL DEFAULT now()
);