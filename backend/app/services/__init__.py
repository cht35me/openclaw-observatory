"""Domain services (Mission M003).

Modules here implement behavior *between* the API layer and storage:

* ``seed`` — Fleet Registry seeding from FLEET.md-derived data;
* ``health`` — computed health score (Healthy/Warning/Critical/Offline);
* ``registry`` — read-model assembly (identity + derived telemetry);
* ``pipeline`` — per-event-type ingestion handlers (heartbeat, mission_update);
* ``offline`` — background offline detection and backend self-heartbeat.
"""
