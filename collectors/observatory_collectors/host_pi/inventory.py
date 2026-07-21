"""Host Inventory probes (Mission M003.5 §3).

Host Inventory is *information about THIS machine* — hardware identity,
operating-system identity, structured storage inventory, network interfaces,
and maintenance status. It is a distinct concept from the Fleet Registry
(information aggregated about ALL nodes): the registry holds administered
identity; the inventory is *observed* by the host collector and reported as
a ``host_inventory`` event.

Design rules (matching :mod:`observatory_collectors.host_pi.metrics`):

* **Pure parsers take file contents** and are unit-testable offline with
  canned fixtures; thin ``read_*`` wrappers do the I/O.
* **Fail soft** — a missing source yields ``None`` (or an empty list),
  never an exception; partial inventory is better than none.
* **Not Pi-specific**: Raspberry Pi sources (``/proc/device-tree``,
  ``/proc/cpuinfo`` Revision/Serial) are preferred when present, with DMI
  (``/sys/class/dmi/id``) fallbacks so generic Linux hosts report identity
  too. Multi-site scale-out needs no schema change: every section is a
  plain dict/list and extra keys are allowed (SMART data can extend the
  storage entries later).
* **Standard library only** (SD-019). ``apt list --upgradable`` and the
  read-only sysfs walks need no root and mutate nothing.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import socket
import struct
import subprocess
from pathlib import Path
from typing import Any

from observatory_collectors.host_pi import metrics

DEVICE_TREE_MODEL = Path("/proc/device-tree/model")
DEVICE_TREE_COMPATIBLE = Path("/proc/device-tree/compatible")
PROC_CPUINFO = Path("/proc/cpuinfo")
ETC_OS_RELEASE = Path("/etc/os-release")
PROC_MOUNTS = Path("/proc/mounts")
SYS_BLOCK = Path("/sys/block")
SYS_CLASS_NET = Path("/sys/class/net")
DMI_ID = Path("/sys/class/dmi/id")
APT_LISTS_DIR = Path("/var/lib/apt/lists")
APT_HISTORY_LOG = Path("/var/log/apt/history.log")
REBOOT_REQUIRED_FLAG = Path("/var/run/reboot-required")

#: ``ioctl`` request: get interface IPv4 address (Linux ``SIOCGIFADDR``).
_SIOCGIFADDR = 0x8915

#: Timeout for the (read-only, root-free) apt query.
_APT_TIMEOUT = 60.0

#: Interface name prefixes that are container/bridge plumbing, not host
#: connectivity (judgment call, docs/M003.5-notes.md): veth pairs and
#: bridges say nothing about the *host's* network identity.
_IGNORED_INTERFACE_PREFIXES = ("lo", "veth", "br-", "docker")

#: Volatile keys stripped from the change-detection signature (utilization
#: moves constantly; identity does not).
_VOLATILE_STORAGE_KEYS = frozenset({"used_bytes", "free_bytes", "used_percent"})


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# --------------------------------------------------------------------- #
# Hardware identity (§3a)
# --------------------------------------------------------------------- #


def parse_device_tree_model(text: str) -> str | None:
    """Device-tree model string (NUL-terminated), e.g. Raspberry Pi boards."""
    model = text.replace("\x00", "").strip()
    return model or None


def split_model_revision(model: str) -> tuple[str, str | None]:
    """Split a trailing ``Rev x.y`` off a device-tree model string."""
    match = re.match(r"^(.*?)\s+Rev\s+(\S+)$", model)
    if match:
        return match.group(1).strip(), match.group(2)
    return model, None


def parse_cpuinfo(text: str) -> dict[str, Any]:
    """Identity fields from ``/proc/cpuinfo`` (Pi: Model/Revision/Serial)."""
    info: dict[str, Any] = {}
    cores = 0
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "processor":
            cores += 1
        elif key == "model name" and "cpu_model" not in info:
            info["cpu_model"] = value
        elif key == "Model":
            info["model"] = value
        elif key == "Revision":
            info["revision"] = value
        elif key == "Serial":
            info["serial"] = value
        elif key == "Hardware":
            info["hardware"] = value
    if cores:
        info["cpu_cores"] = cores
    return info


def parse_device_tree_compatible(text: str) -> str | None:
    """SoC name from the last ``vendor,soc`` entry, e.g. ``BCM2711``."""
    entries = [entry for entry in text.split("\x00") if entry.strip()]
    if not entries:
        return None
    _, _, soc = entries[-1].rpartition(",")
    return soc.upper() if soc else None


def normalize_architecture(machine: str) -> str:
    """Map ``os.uname().machine`` onto the fleet-facing architecture label."""
    return {
        "aarch64": "ARM64",
        "arm64": "ARM64",
        "armv7l": "ARM32",
        "armv6l": "ARM32",
        "x86_64": "x86_64",
        "i686": "x86",
    }.get(machine, machine)


def _read_dmi(name: str, dmi_dir: Path) -> str | None:
    text = _read(dmi_dir / name)
    if text is None:
        return None
    value = text.strip()
    # Firmware placeholder junk is worse than absence.
    if not value or value.lower() in {"none", "unknown", "to be filled by o.e.m."}:
        return None
    return value


def read_hardware_identity(
    device_tree_model: Path = DEVICE_TREE_MODEL,
    device_tree_compatible: Path = DEVICE_TREE_COMPATIBLE,
    cpuinfo: Path = PROC_CPUINFO,
    dmi_dir: Path = DMI_ID,
    meminfo: Path = metrics.PROC_MEMINFO,
) -> dict[str, Any]:
    """Assemble hardware identity: device-tree/cpuinfo first, DMI fallback."""
    cpu = parse_cpuinfo(_read(cpuinfo) or "")
    dt_model_text = _read(device_tree_model)
    dt_model = parse_device_tree_model(dt_model_text) if dt_model_text else None

    model = dt_model or cpu.get("model") or _read_dmi("product_name", dmi_dir)
    revision = cpu.get("revision")
    if model:
        model, rev_suffix = split_model_revision(model)
        revision = revision or rev_suffix
    revision = revision or _read_dmi("product_version", dmi_dir)

    manufacturer = _read_dmi("sys_vendor", dmi_dir)
    if manufacturer is None and (model or "").startswith("Raspberry Pi"):
        manufacturer = "Raspberry Pi Foundation"

    compatible_text = _read(device_tree_compatible)
    cpu_model = cpu.get("cpu_model") or (
        parse_device_tree_compatible(compatible_text) if compatible_text else None
    )

    memory = metrics.parse_meminfo(_read(meminfo) or "")
    uname = os.uname()
    return {
        "manufacturer": manufacturer,
        "model": model,
        "revision": revision,
        "cpu_model": cpu_model,
        "cpu_architecture": normalize_architecture(uname.machine),
        "cpu_cores": cpu.get("cpu_cores"),
        "memory_total_bytes": memory["total_bytes"] if memory else None,
        "serial": cpu.get("serial") or _read_dmi("product_serial", dmi_dir),
    }


# --------------------------------------------------------------------- #
# Operating-system inventory (§3c)
# --------------------------------------------------------------------- #


def parse_os_release(text: str) -> dict[str, Any]:
    """``/etc/os-release`` key/value pairs (quotes stripped)."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"')
    codename = values.get("VERSION_CODENAME", "")
    return {
        "name": values.get("NAME") or values.get("PRETTY_NAME"),
        "release": codename.capitalize() or values.get("VERSION") or None,
        "version_id": values.get("VERSION_ID") or None,
        "pretty_name": values.get("PRETTY_NAME") or None,
    }


def read_os_inventory(os_release: Path = ETC_OS_RELEASE) -> dict[str, Any]:
    info = parse_os_release(_read(os_release) or "")
    uname = os.uname()
    info["kernel"] = uname.release
    info["hostname"] = uname.nodename
    return info


# --------------------------------------------------------------------- #
# Storage inventory (§3b)
# --------------------------------------------------------------------- #


def parse_mounts(text: str) -> list[dict[str, str]]:
    """Real block-device-backed mounts from ``/proc/mounts``.

    Virtual filesystems (tmpfs, overlay, proc, …) are excluded by requiring
    a ``/dev/`` source. Octal escapes in mount points (``\\040`` = space)
    are decoded.
    """
    mounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 3 or not fields[0].startswith("/dev/"):
            continue
        device, mount_point, fstype = fields[0], fields[1], fields[2]
        mount_point = mount_point.encode().decode("unicode_escape")
        key = (device, mount_point)
        if key in seen:
            continue
        seen.add(key)
        mounts.append({"device": device, "mount": mount_point, "filesystem": fstype})
    return mounts


def base_block_device(device_name: str) -> str:
    """Whole-disk device for a partition name.

    ``mmcblk0p2`` → ``mmcblk0``; ``nvme0n1p1`` → ``nvme0n1``;
    ``sda1`` → ``sda``; whole-disk names pass through unchanged.
    """
    match = re.match(r"^(mmcblk\d+|nvme\d+n\d+)(p\d+)?$", device_name)
    if match:
        return match.group(1)
    match = re.match(r"^([a-z]+)(\d+)$", device_name)
    if match:
        return match.group(1)
    return device_name


def classify_transport(
    base_device: str,
    device_link: str | None,
    mmc_type: str | None,
) -> str | None:
    """Transport per M003.5 §3b: ``SD | USB | NVMe | SATA | eMMC``.

    * ``mmcblk*`` — the MMC subsystem reports card type (``SD`` vs ``MMC``);
    * ``nvme*`` — NVMe by construction;
    * ``sd*`` — a USB path component in the resolved sysfs device link means
      a USB bridge; otherwise the SCSI disk is assumed SATA.
    """
    if base_device.startswith("mmcblk"):
        if mmc_type and mmc_type.strip().upper() == "MMC":
            return "eMMC"
        return "SD"
    if base_device.startswith("nvme"):
        return "NVMe"
    if base_device.startswith(("sd", "vd", "hd")):
        if device_link and "/usb" in device_link:
            return "USB"
        return "SATA"
    return None


def storage_type_label(transport: str | None, rotational: str | None) -> str:
    """Human storage type: transport first, rotational flag for disks."""
    if transport == "SD":
        return "SD Card"
    if transport == "eMMC":
        return "eMMC"
    if rotational and rotational.strip() == "1":
        return "HDD"
    if transport in ("USB", "NVMe", "SATA"):
        return "SSD"
    return "Disk"


def assign_logical_names(entries: list[dict[str, Any]]) -> None:
    """Stable logical names (``SD1``, ``SSD1``, …) per *physical* device.

    Names are assigned by transport-derived prefix and ordinal, in device
    order; multiple partitions/mounts of one physical device share its name.
    """
    prefixes = {"SD Card": "SD", "eMMC": "EMMC", "SSD": "SSD", "HDD": "HDD", "Disk": "DISK"}
    counters: dict[str, int] = {}
    named: dict[str, str] = {}
    for entry in entries:
        physical = entry.get("physical_device") or entry.get("device", "")
        if physical not in named:
            prefix = prefixes.get(str(entry.get("type")), "DISK")
            counters[prefix] = counters.get(prefix, 0) + 1
            named[physical] = f"{prefix}{counters[prefix]}"
        entry["name"] = named[physical]


def _statvfs_usage(mount_point: str) -> dict[str, Any] | None:
    try:
        stats = os.statvfs(mount_point)
    except OSError:
        return None
    total = stats.f_frsize * stats.f_blocks
    free = stats.f_frsize * stats.f_bavail
    if total <= 0:
        return None
    used = total - free
    return {
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_percent": round(100.0 * used / total, 2),
    }


def _device_brand(base: str, sys_block: Path) -> str | None:
    device_dir = sys_block / base / "device"
    parts = []
    for name in ("vendor", "model", "name"):
        text = _read(device_dir / name)
        if text and text.strip():
            parts.append(text.strip())
    if not parts:
        return None
    # vendor + model when both exist; the MMC `name` field stands alone.
    return " ".join(dict.fromkeys(parts[:2]))


def read_storage_inventory(
    mounts: Path = PROC_MOUNTS,
    sys_block: Path = SYS_BLOCK,
) -> list[dict[str, Any]]:
    """One entry per mounted, block-device-backed filesystem.

    Extra keys are allowed by the backend (dict-per-device model), so SMART
    attributes can be added later without a schema change.
    """
    entries: list[dict[str, Any]] = []
    for mount in parse_mounts(_read(mounts) or ""):
        device_name = mount["device"].rsplit("/", 1)[-1]
        base = base_block_device(device_name)
        block_dir = sys_block / base

        device_link: str | None = None
        try:
            device_link = str((block_dir / "device").resolve())
        except OSError:
            device_link = None
        mmc_type = _read(block_dir / "device" / "type")
        transport = classify_transport(base, device_link, mmc_type)
        rotational = _read(block_dir / "queue" / "rotational")

        size_text = _read(block_dir / "size")
        capacity = None
        if size_text and size_text.strip().isdigit():
            capacity = int(size_text.strip()) * 512  # sysfs sizes are 512-byte sectors

        entry: dict[str, Any] = {
            "device": mount["device"],
            "physical_device": f"/dev/{base}",
            "type": storage_type_label(transport, rotational),
            "transport": transport,
            "capacity_bytes": capacity,
            "mount": mount["mount"],
            "brand": _device_brand(base, sys_block),
            "filesystem": mount["filesystem"],
        }
        usage = _statvfs_usage(mount["mount"])
        if usage:
            entry.update(usage)
        entries.append(entry)
    assign_logical_names(entries)
    return entries


# --------------------------------------------------------------------- #
# Network interfaces (§3-monitor: Interfaces)
# --------------------------------------------------------------------- #


def relevant_interface(name: str) -> bool:
    """Host-level interfaces only: skip loopback and container plumbing."""
    return not name.startswith(_IGNORED_INTERFACE_PREFIXES)


def read_ipv4_address(name: str) -> str | None:
    """IPv4 address of one interface via ``SIOCGIFADDR`` (stdlib, no exec)."""
    try:
        import fcntl  # Linux-only; imported lazily so parsers stay portable

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            packed = fcntl.ioctl(
                sock.fileno(),
                _SIOCGIFADDR,
                struct.pack("256s", name.encode("utf-8")[:15]),
            )
        return socket.inet_ntoa(packed[20:24])
    except (OSError, ImportError):
        return None


def read_interfaces(
    sys_class_net: Path = SYS_CLASS_NET,
    route: Path = metrics.PROC_ROUTE,
    ipv4_fn: Any = None,
) -> dict[str, Any]:
    """Interface list + default route (gateway/interface from /proc/net/route)."""
    ipv4_fn = ipv4_fn or read_ipv4_address
    interfaces: list[dict[str, Any]] = []
    try:
        names = sorted(entry.name for entry in sys_class_net.iterdir())
    except OSError:
        names = []
    for name in names:
        if not relevant_interface(name):
            continue
        operstate = _read(sys_class_net / name / "operstate")
        interfaces.append(
            {
                "name": name,
                "ipv4": ipv4_fn(name),
                "link_state": (operstate or "unknown").strip().lower(),
            }
        )
    route_text = _read(route) or ""
    gateway = metrics.parse_default_gateway(route_text)
    interface = metrics.parse_default_interface(route_text)
    default_route = {"gateway": gateway, "interface": interface} if gateway or interface else None
    return {"interfaces": interfaces, "default_route": default_route}


# --------------------------------------------------------------------- #
# Maintenance status (§3d)
# --------------------------------------------------------------------- #


def parse_apt_history(text: str) -> dict[str, str | None]:
    """Latest upgrade timestamps from an apt ``history.log``.

    Returns ISO-ish timestamps (as logged, ``YYYY-MM-DD HH:MM:SS``) for:

    * ``last_upgrade`` — any upgrade activity (``upgrade``, ``full-upgrade``,
      ``dist-upgrade``, ``unattended-upgrade``);
    * ``last_full_upgrade`` — full/dist upgrades only (§3d "last apt
      full-upgrade").
    """
    last_upgrade: str | None = None
    last_full: str | None = None
    start: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Start-Date:"):
            start = " ".join(line.split(":", 1)[1].split())
        elif line.startswith("Commandline:") and start:
            command = line.split(":", 1)[1]
            if "full-upgrade" in command or "dist-upgrade" in command:
                last_full = start
                last_upgrade = start
            elif "upgrade" in command:  # includes unattended-upgrade
                last_upgrade = start
    return {"last_upgrade": last_upgrade, "last_full_upgrade": last_full}


def parse_upgradable_count(text: str) -> int:
    """Count upgradable packages in ``apt list --upgradable`` output."""
    return sum(1 for line in text.splitlines() if "[upgradable from" in line)


def read_apt_history(history_log: Path = APT_HISTORY_LOG) -> dict[str, str | None]:
    """Rotation-aware history scan: current log first, then newest ``.gz``.

    Best effort (documented judgment): older archives are consulted only
    until both timestamps are found; a host that never ran a full-upgrade
    honestly reports ``None``.
    """
    result = parse_apt_history(_read(history_log) or "")

    def merged(parsed: dict[str, str | None]) -> None:
        for key, value in parsed.items():
            if result.get(key) is None and value is not None:
                result[key] = value

    if any(value is None for value in result.values()):
        rotated = sorted(
            history_log.parent.glob(history_log.name + ".*.gz"),
            key=lambda p: p.name,
        )
        for archive in rotated:  # .1.gz is the newest rotation
            try:
                merged(parse_apt_history(gzip.decompress(archive.read_bytes()).decode()))
            except OSError:
                continue
            if all(value is not None for value in result.values()):
                break
    return result


def read_updates_available() -> int | None:
    """Upgradable package count — read-only, root-free, no ``apt update``.

    ``apt list --upgradable`` inspects the *existing* package lists (kept
    fresh by unattended-upgrades on this fleet); it never mutates state.
    ``None`` when apt is unavailable or times out.
    """
    try:
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            timeout=_APT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return parse_upgradable_count(result.stdout)


def read_maintenance(
    apt_lists: Path = APT_LISTS_DIR,
    history_log: Path = APT_HISTORY_LOG,
    reboot_flag: Path = REBOOT_REQUIRED_FLAG,
    updates_fn: Any = None,
) -> dict[str, Any]:
    updates_fn = updates_fn or read_updates_available
    last_update: float | None = None
    try:
        last_update = apt_lists.stat().st_mtime
        partial = apt_lists / "partial"
        if partial.exists():
            last_update = max(last_update, partial.stat().st_mtime)
    except OSError:
        last_update = None
    history = read_apt_history(history_log)
    return {
        "last_apt_update_epoch": int(last_update) if last_update else None,
        "last_apt_upgrade": history["last_upgrade"],
        "last_apt_full_upgrade": history["last_full_upgrade"],
        "updates_available": updates_fn(),
        "reboot_required": reboot_flag.exists(),
    }


# --------------------------------------------------------------------- #
# Assembly + change detection
# --------------------------------------------------------------------- #


def collect_identity() -> dict[str, Any]:
    """Cheap inventory sections (file reads only; no subprocesses)."""
    return {
        "hardware": read_hardware_identity(),
        "os": read_os_inventory(),
        "storage": read_storage_inventory(),
        "network": read_interfaces(),
    }


def collect() -> dict[str, Any]:
    """Full host_inventory payload (identity + maintenance)."""
    payload = collect_identity()
    payload["maintenance"] = read_maintenance()
    return payload


def stable_signature(payload: dict[str, Any]) -> str:
    """Identity signature ignoring volatile utilization numbers.

    Used to re-send inventory early when something durable changed (a disk
    appeared, an address moved, a kernel booted) without re-sending on every
    free-space fluctuation.
    """
    stable = dict(payload)
    stable.pop("maintenance", None)
    stable["storage"] = [
        {k: v for k, v in entry.items() if k not in _VOLATILE_STORAGE_KEYS}
        for entry in payload.get("storage", [])
    ]
    return json.dumps(stable, sort_keys=True, default=str)
