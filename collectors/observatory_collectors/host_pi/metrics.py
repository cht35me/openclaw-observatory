"""Host telemetry probes for Linux/Raspberry Pi (Mission M003 §2).

Pure parse functions take file *contents* (unit-testable offline with canned
fixtures); thin ``read_*`` wrappers do the I/O. Every probe fails soft —
a missing sensor yields ``None``, never an exception, so one broken source
cannot silence the rest of the telemetry.
"""

from __future__ import annotations

import os
import shutil
import socket
import struct
from pathlib import Path
from typing import Any

PROC_STAT = Path("/proc/stat")
PROC_MEMINFO = Path("/proc/meminfo")
PROC_UPTIME = Path("/proc/uptime")
PROC_ROUTE = Path("/proc/net/route")
THERMAL_ZONE = Path("/sys/class/thermal/thermal_zone0/temp")


# --------------------------------------------------------------------- #
# Pure parsers (tested with canned /proc contents)
# --------------------------------------------------------------------- #


def parse_cpu_times(stat_text: str) -> tuple[int, int] | None:
    """Return ``(idle, total)`` jiffies from ``/proc/stat``'s ``cpu`` line."""
    for line in stat_text.splitlines():
        if line.startswith("cpu "):
            fields = [int(part) for part in line.split()[1:]]
            if len(fields) < 4:
                return None
            idle = fields[3] + (fields[4] if len(fields) > 4 else 0)  # idle+iowait
            return idle, sum(fields)
    return None


def cpu_percent_from_samples(
    first: tuple[int, int] | None, second: tuple[int, int] | None
) -> float | None:
    """CPU utilization between two ``(idle, total)`` samples."""
    if first is None or second is None:
        return None
    idle_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return round(100.0 * (1.0 - idle_delta / total_delta), 2)


def parse_cpu_temperature(thermal_text: str) -> float | None:
    """Millidegrees from the thermal zone → °C."""
    try:
        return round(int(thermal_text.strip()) / 1000.0, 2)
    except ValueError:
        return None


def parse_meminfo(meminfo_text: str) -> dict[str, Any] | None:
    """RAM totals from ``/proc/meminfo`` (kB fields → bytes)."""
    values: dict[str, int] = {}
    for line in meminfo_text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key.strip()] = int(parts[0]) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    used = total - available
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "used_percent": round(100.0 * used / total, 2),
    }


def parse_uptime(uptime_text: str) -> float | None:
    """Seconds since boot from ``/proc/uptime``."""
    try:
        return float(uptime_text.split()[0])
    except (ValueError, IndexError):
        return None


def parse_default_interface(route_text: str) -> str | None:
    """Interface of the default route (destination ``00000000``) or None."""
    for line in route_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "00000000":
            return fields[0]
    return None


def parse_default_gateway(route_text: str) -> str | None:
    """Gateway IP of the default route, dotted-quad."""
    for line in route_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 3 and fields[1] == "00000000":
            try:
                return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
            except (ValueError, struct.error):
                return None
    return None


# --------------------------------------------------------------------- #
# I/O wrappers (fail soft)
# --------------------------------------------------------------------- #


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def read_cpu_sample() -> tuple[int, int] | None:
    text = _read(PROC_STAT)
    return parse_cpu_times(text) if text else None


def read_cpu_temperature() -> float | None:
    text = _read(THERMAL_ZONE)
    return parse_cpu_temperature(text) if text else None


def read_memory() -> dict[str, Any] | None:
    text = _read(PROC_MEMINFO)
    return parse_meminfo(text) if text else None


def read_uptime() -> float | None:
    text = _read(PROC_UPTIME)
    return parse_uptime(text) if text else None


def read_load_avg() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except OSError:
        return None


def read_disk(path: str = "/") -> dict[str, Any] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return {
        "path": path,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round(100.0 * usage.used / usage.total, 2),
    }


def read_network() -> dict[str, Any]:
    """Default-route presence, interface, and primary IP (no packets sent)."""
    route_text = _read(PROC_ROUTE) or ""
    interface = parse_default_interface(route_text)
    ip_address: str | None = None
    try:
        # Connectionless UDP "connect" picks the outbound source address
        # without transmitting anything.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.0)
            sock.connect(("8.8.8.8", 80))
            ip_address = sock.getsockname()[0]
    except OSError:
        pass
    return {
        "online": interface is not None,
        "default_interface": interface,
        "ip_address": ip_address,
    }
