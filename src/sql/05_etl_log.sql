-- Bảng etl_log.run_history và etl_log.error_queue.

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