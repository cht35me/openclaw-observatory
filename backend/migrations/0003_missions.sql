-- 0003_missions.sql — mission current-state projection (Mission M003 §4).
--
-- Same versioned-row pattern as 0002 (SD-018, proposed): the full transition
-- history lives in the events table (`event_type = 'mission_update'`); this
-- table keeps only the latest state per mission for fast reads. Every state
-- change inserts a new row with a higher `revision`; reads use FINAL.

CREATE TABLE IF NOT EXISTS `{database}`.`missions` (
    mission_id LowCardinality(String),
    title String,
    assigned_agent String DEFAULT '',
    state LowCardinality(String),
    created_at DateTime64(3, 'UTC'),
    started_at Nullable(DateTime64(3, 'UTC')),
    completed_at Nullable(DateTime64(3, 'UTC')),
    pr_ref String DEFAULT '',
    commit_sha String DEFAULT '',
    updated_at DateTime64(3, 'UTC'),
    revision UInt64
)
ENGINE = ReplacingMergeTree(revision)
ORDER BY mission_id;
