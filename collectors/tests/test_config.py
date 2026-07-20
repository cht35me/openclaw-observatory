"""Collector configuration tests (M003 §8)."""

from __future__ import annotations

import pytest

from observatory_collectors.config import CollectorConfig, ConfigError

BASE_ENV = {
    "OBSERVATORY_URL": "http://obs.example:8000",
    "OBSERVATORY_API_KEY": "test-key",
    "FLEET_ID": "RPSG01",
}


def test_defaults_and_required_fields() -> None:
    config = CollectorConfig.from_env(dict(BASE_ENV), default_collector_name="host-pi")
    assert config.observatory_url == "http://obs.example:8000"
    assert config.fleet_id == "RPSG01"
    assert config.collector_name == "host-pi"
    assert config.heartbeat_interval == 30.0
    assert config.telemetry_interval == 30.0  # follows heartbeat by default
    assert config.mission_poll_interval == 60.0


def test_intervals_configurable() -> None:
    env = {
        **BASE_ENV,
        "HEARTBEAT_INTERVAL": "10",
        "TELEMETRY_INTERVAL": "20",
        "MISSION_POLL_INTERVAL": "120",
        "COLLECTOR_NAME": "custom",
    }
    config = CollectorConfig.from_env(env)
    assert config.heartbeat_interval == 10.0
    assert config.telemetry_interval == 20.0
    assert config.mission_poll_interval == 120.0
    assert config.collector_name == "custom"


def test_missing_key_or_fleet_id_fails() -> None:
    with pytest.raises(ConfigError):
        CollectorConfig.from_env({**BASE_ENV, "OBSERVATORY_API_KEY": ""})
    with pytest.raises(ConfigError):
        CollectorConfig.from_env({**BASE_ENV, "FLEET_ID": " "})


def test_key_file_supported(tmp_path) -> None:
    key_file = tmp_path / "collector.key"
    key_file.write_text("file-key\n", encoding="utf-8")
    env = {**BASE_ENV, "OBSERVATORY_API_KEY": "", "OBSERVATORY_API_KEY_FILE": str(key_file)}
    assert CollectorConfig.from_env(env).api_key == "file-key"


def test_invalid_values_rejected() -> None:
    with pytest.raises(ConfigError):
        CollectorConfig.from_env({**BASE_ENV, "HEARTBEAT_INTERVAL": "zero"})
    with pytest.raises(ConfigError):
        CollectorConfig.from_env({**BASE_ENV, "HEARTBEAT_INTERVAL": "-5"})
    with pytest.raises(ConfigError):
        CollectorConfig.from_env({**BASE_ENV, "OBSERVATORY_URL": "ftp://nope"})
