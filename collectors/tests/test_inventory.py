"""Host Inventory parser tests (M003.5 §3) with canned fixtures."""

from __future__ import annotations

import gzip

from observatory_collectors.host_pi import inventory
from observatory_collectors.host_pi.collector import InventoryTelemetry

CPUINFO = """processor\t: 0
BogoMIPS\t: 108.00
processor\t: 1
processor\t: 2
processor\t: 3
Hardware\t: BCM2835
Revision\t: c03114
Serial\t\t: 10000000bbc78bf0
Model\t\t: Raspberry Pi 4 Model B Rev 1.4
"""

CPUINFO_X86 = """processor\t: 0
model name\t: Intel(R) Celeron(R) N5105 @ 2.00GHz
processor\t: 1
model name\t: Intel(R) Celeron(R) N5105 @ 2.00GHz
"""

OS_RELEASE = """PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
NAME="Debian GNU/Linux"
VERSION_ID="13"
VERSION="13 (trixie)"
VERSION_CODENAME=trixie
ID=debian
HOME_URL="https://www.debian.org/"
"""

MOUNTS = """/dev/mmcblk0p2 / ext4 rw,noatime 0 0
/dev/mmcblk0p1 /boot/firmware vfat rw,relatime 0 0
tmpfs /run tmpfs rw,nosuid,nodev 0 0
overlay /var/lib/docker/overlay2/abc/merged overlay rw,relatime 0 0
/dev/sda1 /mnt/data\\040disk ext4 rw 0 0
proc /proc proc rw 0 0
"""

APT_HISTORY = """Start-Date: 2026-05-23  16:21:49
Commandline: apt full-upgrade
End-Date: 2026-05-23  16:24:04

Start-Date: 2026-07-21  06:24:42
Commandline: /usr/bin/unattended-upgrade
End-Date: 2026-07-21  06:24:48
"""

APT_UPGRADABLE = """Listing...
rpi-connect/stable 2.12.1 arm64 [upgradable from: 2.12.0]
tailscale/unknown 1.98.9 arm64 [upgradable from: 1.98.8]
"""


# --------------------------------------------------------------------- #
# Hardware identity
# --------------------------------------------------------------------- #


def test_parse_device_tree_model_strips_nul() -> None:
    assert (
        inventory.parse_device_tree_model("Raspberry Pi 4 Model B Rev 1.4\x00")
        == "Raspberry Pi 4 Model B Rev 1.4"
    )
    assert inventory.parse_device_tree_model("\x00") is None


def test_split_model_revision() -> None:
    assert inventory.split_model_revision("Raspberry Pi 4 Model B Rev 1.4") == (
        "Raspberry Pi 4 Model B",
        "1.4",
    )
    assert inventory.split_model_revision("Generic Box") == ("Generic Box", None)


def test_parse_cpuinfo_pi_fields() -> None:
    info = inventory.parse_cpuinfo(CPUINFO)
    assert info["model"] == "Raspberry Pi 4 Model B Rev 1.4"
    assert info["revision"] == "c03114"
    assert info["serial"] == "10000000bbc78bf0"
    assert info["cpu_cores"] == 4


def test_parse_cpuinfo_x86_model_name() -> None:
    info = inventory.parse_cpuinfo(CPUINFO_X86)
    assert info["cpu_model"] == "Intel(R) Celeron(R) N5105 @ 2.00GHz"
    assert info["cpu_cores"] == 2
    assert "serial" not in info


def test_parse_device_tree_compatible_soc() -> None:
    assert (
        inventory.parse_device_tree_compatible("raspberrypi,4-model-b\x00brcm,bcm2711\x00")
        == "BCM2711"
    )
    assert inventory.parse_device_tree_compatible("\x00") is None


def test_normalize_architecture() -> None:
    assert inventory.normalize_architecture("aarch64") == "ARM64"
    assert inventory.normalize_architecture("x86_64") == "x86_64"
    assert inventory.normalize_architecture("riscv64") == "riscv64"


def test_read_hardware_identity_from_fixture_tree(tmp_path) -> None:
    (tmp_path / "model").write_text("Raspberry Pi 4 Model B Rev 1.4\x00")
    (tmp_path / "compatible").write_text("raspberrypi,4-model-b\x00brcm,bcm2711\x00")
    (tmp_path / "cpuinfo").write_text(CPUINFO)
    (tmp_path / "meminfo").write_text("MemTotal:        3884096 kB\nMemAvailable: 1942048 kB\n")
    dmi = tmp_path / "dmi"
    dmi.mkdir()
    identity = inventory.read_hardware_identity(
        device_tree_model=tmp_path / "model",
        device_tree_compatible=tmp_path / "compatible",
        cpuinfo=tmp_path / "cpuinfo",
        dmi_dir=dmi,
        meminfo=tmp_path / "meminfo",
    )
    assert identity["manufacturer"] == "Raspberry Pi Foundation"
    assert identity["model"] == "Raspberry Pi 4 Model B"
    assert identity["revision"] == "c03114"
    assert identity["cpu_model"] == "BCM2711"
    assert identity["memory_total_bytes"] == 3884096 * 1024
    assert identity["serial"] == "10000000bbc78bf0"


def test_read_hardware_identity_dmi_fallback(tmp_path) -> None:
    dmi = tmp_path / "dmi"
    dmi.mkdir()
    (dmi / "sys_vendor").write_text("Dell Inc.\n")
    (dmi / "product_name").write_text("OptiPlex 3080\n")
    (dmi / "product_version").write_text("To Be Filled By O.E.M.\n")
    identity = inventory.read_hardware_identity(
        device_tree_model=tmp_path / "missing",
        device_tree_compatible=tmp_path / "missing",
        cpuinfo=tmp_path / "missing",
        dmi_dir=dmi,
        meminfo=tmp_path / "missing",
    )
    assert identity["manufacturer"] == "Dell Inc."
    assert identity["model"] == "OptiPlex 3080"
    assert identity["revision"] is None  # OEM placeholder rejected
    assert identity["memory_total_bytes"] is None


# --------------------------------------------------------------------- #
# OS inventory
# --------------------------------------------------------------------- #


def test_parse_os_release() -> None:
    info = inventory.parse_os_release(OS_RELEASE)
    assert info["name"] == "Debian GNU/Linux"
    assert info["release"] == "Trixie"
    assert info["version_id"] == "13"
    assert info["pretty_name"] == "Debian GNU/Linux 13 (trixie)"


def test_parse_os_release_empty() -> None:
    info = inventory.parse_os_release("")
    assert info["name"] is None
    assert info["release"] is None


# --------------------------------------------------------------------- #
# Storage inventory
# --------------------------------------------------------------------- #


def test_parse_mounts_filters_virtual_and_decodes_escapes() -> None:
    mounts = inventory.parse_mounts(MOUNTS)
    assert [m["device"] for m in mounts] == ["/dev/mmcblk0p2", "/dev/mmcblk0p1", "/dev/sda1"]
    assert mounts[2]["mount"] == "/mnt/data disk"
    assert mounts[0]["filesystem"] == "ext4"


def test_base_block_device() -> None:
    assert inventory.base_block_device("mmcblk0p2") == "mmcblk0"
    assert inventory.base_block_device("nvme0n1p1") == "nvme0n1"
    assert inventory.base_block_device("sda1") == "sda"
    assert inventory.base_block_device("sdb") == "sdb"
    assert inventory.base_block_device("mmcblk0") == "mmcblk0"


def test_classify_transport() -> None:
    assert inventory.classify_transport("mmcblk0", None, "SD") == "SD"
    assert inventory.classify_transport("mmcblk1", None, "MMC") == "eMMC"
    assert inventory.classify_transport("nvme0n1", None, None) == "NVMe"
    usb_link = "/sys/devices/platform/scb/fd500000.pcie/usb1/1-1"
    assert inventory.classify_transport("sda", usb_link, None) == "USB"
    assert inventory.classify_transport("sda", "/sys/devices/pci0000:00/ata1/host0", None) == "SATA"
    assert inventory.classify_transport("zram0", None, None) is None


def test_storage_type_label() -> None:
    assert inventory.storage_type_label("SD", "0") == "SD Card"
    assert inventory.storage_type_label("eMMC", "0") == "eMMC"
    assert inventory.storage_type_label("USB", "0") == "SSD"
    assert inventory.storage_type_label("SATA", "1") == "HDD"
    assert inventory.storage_type_label("NVMe", "0") == "SSD"
    assert inventory.storage_type_label(None, None) == "Disk"


def test_assign_logical_names_groups_partitions_by_physical_device() -> None:
    entries = [
        {"device": "/dev/mmcblk0p2", "physical_device": "/dev/mmcblk0", "type": "SD Card"},
        {"device": "/dev/mmcblk0p1", "physical_device": "/dev/mmcblk0", "type": "SD Card"},
        {"device": "/dev/sda1", "physical_device": "/dev/sda", "type": "SSD"},
        {"device": "/dev/nvme0n1p1", "physical_device": "/dev/nvme0n1", "type": "SSD"},
    ]
    inventory.assign_logical_names(entries)
    assert [e["name"] for e in entries] == ["SD1", "SD1", "SSD1", "SSD2"]


def test_read_storage_inventory_with_fake_sysfs(tmp_path) -> None:
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/mmcblk0p2 / ext4 rw 0 0\n/dev/mmcblk0p1 /boot/firmware vfat rw 0 0\n")
    block = tmp_path / "block"
    mmc = block / "mmcblk0"
    (mmc / "device").mkdir(parents=True)
    (mmc / "queue").mkdir()
    (mmc / "size").write_text("121468928\n")
    (mmc / "device" / "type").write_text("SD\n")
    (mmc / "device" / "name").write_text("SPCC\n")
    (mmc / "queue" / "rotational").write_text("0\n")

    entries = inventory.read_storage_inventory(mounts=mounts, sys_block=block)
    assert len(entries) == 2
    root = entries[0]
    assert root["name"] == "SD1"
    assert root["device"] == "/dev/mmcblk0p2"
    assert root["transport"] == "SD"
    assert root["type"] == "SD Card"
    assert root["brand"] == "SPCC"
    assert root["capacity_bytes"] == 121468928 * 512
    assert root["filesystem"] == "ext4"
    # statvfs on the real "/" mount point: usage fields must be present.
    assert root["total_bytes"] > 0
    assert 0.0 <= root["used_percent"] <= 100.0
    # Both partitions share the physical device name.
    assert entries[1]["name"] == "SD1"


# --------------------------------------------------------------------- #
# Interfaces
# --------------------------------------------------------------------- #


def test_relevant_interface_filter() -> None:
    assert inventory.relevant_interface("eth0")
    assert inventory.relevant_interface("wlan0")
    assert inventory.relevant_interface("tailscale0")
    assert not inventory.relevant_interface("lo")
    assert not inventory.relevant_interface("veth8eedd33")
    assert not inventory.relevant_interface("br-e6c9c16cb5bf")
    assert not inventory.relevant_interface("docker0")


def test_read_interfaces_with_fake_sysfs(tmp_path) -> None:
    net = tmp_path / "net"
    for name, state in (("eth0", "up"), ("wlan0", "down"), ("tailscale0", "unknown"), ("lo", "up")):
        (net / name).mkdir(parents=True)
        (net / name / "operstate").write_text(f"{state}\n")
    route = tmp_path / "route"
    route.write_text(
        "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\n"
        "eth0\t00000000\t0100A8C0\t0003\t0\t0\t100\t00000000\n"
    )
    result = inventory.read_interfaces(
        sys_class_net=net,
        route=route,
        ipv4_fn=lambda name: {"eth0": "192.168.0.2"}.get(name),
    )
    names = {i["name"]: i for i in result["interfaces"]}
    assert set(names) == {"eth0", "wlan0", "tailscale0"}  # lo filtered out
    assert names["eth0"]["ipv4"] == "192.168.0.2"
    assert names["eth0"]["link_state"] == "up"
    assert names["wlan0"]["link_state"] == "down"
    assert result["default_route"] == {"gateway": "192.168.0.1", "interface": "eth0"}


# --------------------------------------------------------------------- #
# Maintenance
# --------------------------------------------------------------------- #


def test_parse_apt_history_upgrade_kinds() -> None:
    result = inventory.parse_apt_history(APT_HISTORY)
    assert result["last_full_upgrade"] == "2026-05-23 16:21:49"
    assert result["last_upgrade"] == "2026-07-21 06:24:42"  # unattended counts


def test_parse_apt_history_empty() -> None:
    assert inventory.parse_apt_history("") == {
        "last_upgrade": None,
        "last_full_upgrade": None,
    }


def test_read_apt_history_falls_back_to_rotated_gz(tmp_path) -> None:
    history = tmp_path / "history.log"
    history.write_text(
        "Start-Date: 2026-07-21  06:24:42\nCommandline: /usr/bin/unattended-upgrade\n"
    )
    archive = tmp_path / "history.log.1.gz"
    archive.write_bytes(
        gzip.compress(b"Start-Date: 2026-05-23  16:21:49\nCommandline: apt full-upgrade\n")
    )
    result = inventory.read_apt_history(history)
    assert result["last_upgrade"] == "2026-07-21 06:24:42"  # current log wins
    assert result["last_full_upgrade"] == "2026-05-23 16:21:49"  # from rotation


def test_parse_upgradable_count() -> None:
    assert inventory.parse_upgradable_count(APT_UPGRADABLE) == 2
    assert inventory.parse_upgradable_count("Listing...\n") == 0


def test_read_maintenance_with_fixtures(tmp_path) -> None:
    lists = tmp_path / "lists"
    (lists / "partial").mkdir(parents=True)
    history = tmp_path / "history.log"
    history.write_text(APT_HISTORY)
    result = inventory.read_maintenance(
        apt_lists=lists,
        history_log=history,
        reboot_flag=tmp_path / "reboot-required",  # absent
        updates_fn=lambda: 2,
    )
    assert isinstance(result["last_apt_update_epoch"], int)
    assert result["last_apt_full_upgrade"] == "2026-05-23 16:21:49"
    assert result["updates_available"] == 2
    assert result["reboot_required"] is False


# --------------------------------------------------------------------- #
# Change detection / emission cadence
# --------------------------------------------------------------------- #


def test_stable_signature_ignores_utilization_changes() -> None:
    payload = {
        "hardware": {"model": "Pi"},
        "os": {"kernel": "6.18"},
        "storage": [{"name": "SD1", "used_percent": 28.0, "free_bytes": 100, "used_bytes": 50}],
        "network": {"interfaces": []},
        "maintenance": {"updates_available": 2},
    }
    drifted = {
        "hardware": {"model": "Pi"},
        "os": {"kernel": "6.18"},
        "storage": [{"name": "SD1", "used_percent": 33.0, "free_bytes": 90, "used_bytes": 60}],
        "network": {"interfaces": []},
        "maintenance": {"updates_available": 5},
    }
    changed = {
        "hardware": {"model": "Pi"},
        "os": {"kernel": "6.19"},
        "storage": [{"name": "SD1", "used_percent": 28.0, "free_bytes": 100, "used_bytes": 50}],
        "network": {"interfaces": []},
    }
    assert inventory.stable_signature(payload) == inventory.stable_signature(drifted)
    assert inventory.stable_signature(payload) != inventory.stable_signature(changed)


def test_inventory_telemetry_emits_on_start_change_and_interval(monkeypatch) -> None:
    from observatory_collectors.host_pi import collector as host_collector

    identities = iter(
        [
            {"hardware": {"model": "Pi"}, "storage": []},
            {"hardware": {"model": "Pi"}, "storage": []},  # unchanged, not due
            {"hardware": {"model": "Pi rev2"}, "storage": []},  # changed -> emit
            {"hardware": {"model": "Pi rev2"}, "storage": []},  # unchanged, due -> emit
        ]
    )
    monkeypatch.setattr(host_collector.inventory, "collect_identity", lambda: next(identities))
    monkeypatch.setattr(
        host_collector.inventory, "read_maintenance", lambda: {"reboot_required": False}
    )

    clock = {"now": 0.0}
    telemetry = InventoryTelemetry(interval=3600.0, now_fn=lambda: clock["now"])

    first = telemetry.produce()
    assert len(first) == 1
    event_type, payload, schema = first[0]
    assert event_type == "host_inventory"
    assert schema == host_collector.HOST_INVENTORY_SCHEMA
    assert payload["maintenance"] == {"reboot_required": False}

    clock["now"] = 30.0
    assert telemetry.produce() == []  # unchanged and not due

    clock["now"] = 60.0
    assert len(telemetry.produce()) == 1  # identity changed

    clock["now"] = 60.0 + 3601.0
    assert len(telemetry.produce()) == 1  # interval elapsed
