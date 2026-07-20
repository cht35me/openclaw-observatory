-- 0002_fleet_registry.sql — Fleet Registry identity table (Mission M003 §1).
--
-- Mutable current-state data in ClickHouse uses versioned rows on a
-- ReplacingMergeTree (SD-018, proposed): every update inserts a new row with
-- a higher `revision`; reads use FINAL so the latest revision per `fleet_id`
-- wins. Registry churn is low (seeding, lifecycle changes), so background
-- merges keep the table tiny.
--
-- Telemetry-derived fields (last heartbeat, connectivity, health) are NOT
-- stored here — they are computed from the events table at read time,
-- keeping identity and telemetry cleanly separated (M003 supervisor
-- guidance).
--
-- Optional text fields (nickname, software_version) use the empty string as
-- the "not set" sentinel; the application maps '' <-> None.

CREATE TABLE IF NOT EXISTS `{database}`.`fleet_registry` (
    fleet_id LowCardinality(String),
    nickname String DEFAULT '',
    hostname String,
    role String,
    location String,
    platform String,
    os String,
    software_version String DEFAULT '',
    capabilities Array(String),
    tags Array(String),
    status LowCardinality(String),
    registered_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    revision UInt64
)
ENGINE = ReplacingMergeTree(revision)
ORDER BY fleet_id;
