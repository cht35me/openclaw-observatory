-- 0004_host_inventory.sql — Host Inventory projection + environment (M003.5 §3).
--
-- Host Inventory is *information about THIS machine* (hardware identity,
-- OS identity, structured storage inventory, interfaces, maintenance
-- status), reported by host collectors as `host_inventory` events. The
-- durable record is the event stream; this table is the latest-state
-- projection per host — same versioned-row pattern as `fleet_registry`
-- and `missions` (SD-018): every update inserts a higher `revision`,
-- reads use FINAL.
--
-- The payload is stored as a JSON String (like `events.payload`): inventory
-- sections are collector-versioned dicts designed to gain keys (SMART data,
-- new hardware families, multi-site metadata) WITHOUT schema changes —
-- the M003.5 scale-out requirement. Typed/materialized columns can be added
-- later if query patterns demand them.

CREATE TABLE IF NOT EXISTS `{database}`.`host_inventory` (
    fleet_id LowCardinality(String),
    payload String,
    -- Source timestamp of the inventory event (collector clock).
    reported_at DateTime64(3, 'UTC'),
    -- When the backend projected this revision.
    updated_at DateTime64(3, 'UTC'),
    revision UInt64
)
ENGINE = ReplacingMergeTree(revision)
ORDER BY fleet_id;

-- Fleet Registry environment classification (M003.5 §3e): every asset
-- carries a deployment environment (Production | Staging | Development |
-- Test). Existing rows default to 'Development'; seeding/administration
-- sets real values.

ALTER TABLE `{database}`.`fleet_registry`
    ADD COLUMN IF NOT EXISTS environment LowCardinality(String) DEFAULT 'Development';
