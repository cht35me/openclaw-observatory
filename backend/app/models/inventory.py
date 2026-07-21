"""Host Inventory models (Mission M003.5 §3).

Host Inventory is *information about THIS machine* — hardware identity, OS
identity, structured storage inventory, network interfaces, and maintenance
status — observed by the host collector and reported as ``host_inventory``
events. It is deliberately distinct from the Fleet Registry (*information
aggregated about ALL nodes*): the registry holds administered identity;
inventory is observed fact and may change with every boot or hardware swap.

The payload is intentionally schema-flexible (a validated-but-open dict):
sections are collector-versioned and designed to gain keys — SMART data per
storage device, new hardware families, site metadata — without backend
schema changes (the M003.5 single-node → multi-site scale-out requirement).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.registry import FleetId

#: Event type carrying host inventory reports.
HOST_INVENTORY_EVENT_TYPE = "host_inventory"


class HostInventoryRecord(BaseModel):
    """Latest host inventory projection for one node.

    ``payload`` sections (all optional, collector fail-soft):

    * ``hardware`` — manufacturer, model, revision, cpu_model,
      cpu_architecture, cpu_cores, memory_total_bytes, serial;
    * ``os`` — name, release, version_id, pretty_name, kernel, hostname;
    * ``storage`` — list of device dicts (name, device, type, transport,
      capacity_bytes, mount, brand, filesystem, usage fields; extra keys
      such as future SMART attributes are preserved verbatim);
    * ``network`` — interfaces (name, ipv4, link_state) + default_route;
    * ``maintenance`` — last_apt_update_epoch, last_apt_upgrade,
      last_apt_full_upgrade, updates_available, reboot_required.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_id: FleetId
    payload: dict[str, Any]
    #: Source timestamp of the inventory event (collector clock).
    reported_at: datetime
    #: When the backend projected this revision.
    updated_at: datetime
