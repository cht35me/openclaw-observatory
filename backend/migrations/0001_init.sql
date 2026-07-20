-- 0001_init.sql — canonical events table (Mission M002, SD-005).
--
-- Migration files are plain SQL, applied in filename order (SD-016).
-- `{database}` is replaced with the configured CLICKHOUSE_DATABASE
-- (identifier-validated) by the migration runner. Files are immutable once
-- merged; schema changes go into a new NNNN_name.sql file.

CREATE TABLE IF NOT EXISTS `{database}`.`events` (
    id UUID,
    collector_id LowCardinality(String),
    timestamp DateTime64(3, 'UTC'),
    event_type LowCardinality(String),
    payload String CODEC(ZSTD(3)),
    schema_version UInt32,
    received_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (collector_id, event_type, timestamp);
