"""Host telemetry parser tests (M003 §2) with canned /proc fixtures."""

from __future__ import annotations

from observatory_collectors.host_pi import metrics

PROC_STAT = """cpu  100 0 100 700 100 0 0 0 0 0
cpu0 25 0 25 175 25 0 0 0 0 0
intr 12345
"""

PROC_STAT_LATER = """cpu  150 0 150 900 100 0 0 0 0 0
cpu0 40 0 40 220 25 0 0 0 0 0
"""

MEMINFO = """MemTotal:        3884096 kB
MemFree:          204800 kB
MemAvailable:    1942048 kB
Buffers:          102400 kB
"""

ROUTE = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\n"
    "eth0\t00000000\t0100A8C0\t0003\t0\t0\t100\t00000000\n"
    "eth0\t0000A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\n"
)


def test_cpu_percent_from_two_samples() -> None:
    first = metrics.parse_cpu_times(PROC_STAT)
    second = metrics.parse_cpu_times(PROC_STAT_LATER)
    assert first == (800, 1000)  # idle+iowait, total
    assert second == (1000, 1300)
    percent = metrics.cpu_percent_from_samples(first, second)
    # 300 total delta, 200 idle delta -> 33.33% busy
    assert percent == 33.33


def test_cpu_percent_handles_bad_samples() -> None:
    assert metrics.cpu_percent_from_samples(None, (1, 2)) is None
    assert metrics.cpu_percent_from_samples((800, 1000), (800, 1000)) is None
    assert metrics.parse_cpu_times("no cpu line here") is None


def test_cpu_temperature_millidegrees() -> None:
    assert metrics.parse_cpu_temperature("48534\n") == 48.53
    assert metrics.parse_cpu_temperature("garbage") is None


def test_meminfo_parsing() -> None:
    memory = metrics.parse_meminfo(MEMINFO)
    assert memory["total_bytes"] == 3884096 * 1024
    assert memory["available_bytes"] == 1942048 * 1024
    assert memory["used_bytes"] == (3884096 - 1942048) * 1024
    assert memory["used_percent"] == 50.0
    assert metrics.parse_meminfo("MemFree: 1 kB") is None


def test_uptime_parsing() -> None:
    assert metrics.parse_uptime("12345.67 45678.90\n") == 12345.67
    assert metrics.parse_uptime("") is None


def test_default_route_parsing() -> None:
    assert metrics.parse_default_interface(ROUTE) == "eth0"
    assert metrics.parse_default_gateway(ROUTE) == "192.168.0.1"
    assert metrics.parse_default_interface("Iface\tDestination\n") is None


def test_disk_usage_real_filesystem() -> None:
    disk = metrics.read_disk("/")
    assert disk is not None
    assert disk["total_bytes"] > 0
    assert 0 <= disk["used_percent"] <= 100
    assert disk["free_bytes"] + disk["used_bytes"] <= disk["total_bytes"]
