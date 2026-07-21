"""OpenClaw Observatory collectors (Mission M003).

Push-based telemetry producers (SD-002) that submit events to the
Observatory's authenticated REST API (SD-004, SD-017). Two collectors ship
with M003:

* ``observatory_collectors.host_pi`` — Raspberry Pi host telemetry
  (CPU, temperature, RAM, disk, load, uptime, network, Docker);
* ``observatory_collectors.openclaw_agent`` — OpenClaw agent self-monitoring
  (agent status, mission state, Claude Code availability, runtime).

Design rules:

* **Standard library only** (SD-019, proposed): no third-party dependencies
  on fleet hosts — nothing to pin, audit, or compromise.
* **Collectors never define identity**: ``FLEET_ID`` is configuration, keys
  are bound to one identity (SD-017), and the backend refuses telemetry for
  identities the Fleet Registry does not know.
* **Fail soft**: every probe degrades gracefully; failures are counted and
  self-reported in heartbeats (``failures_total``) so the backend's health
  score can see a struggling collector.
"""

__version__ = "1.0.0"
