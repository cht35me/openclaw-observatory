"""Tests for environment-driven configuration parsing."""

from __future__ import annotations

import os

import pytest

from app.config import ConfigurationError, Settings, load_settings
from app.models.registry import Environment


def _settings(api_keys: str) -> Settings:
    return Settings(_env_file=None, api_keys=api_keys)


def test_api_keys_comma_separated_pairs() -> None:
    assert _settings("RPSG01:key-a,BITAXE01:key-b").api_key_bindings == (
        ("RPSG01", "key-a"),
        ("BITAXE01", "key-b"),
    )


def test_api_keys_pairs_with_whitespace() -> None:
    assert _settings(" RPSG01 : key-a , BITAXE01:key-b ,").api_key_bindings == (
        ("RPSG01", "key-a"),
        ("BITAXE01", "key-b"),
    )


def test_api_keys_json_object() -> None:
    assert _settings('{"RPSG01": "key-a", "BITAXE01": "key-b"}').api_key_bindings == (
        ("RPSG01", "key-a"),
        ("BITAXE01", "key-b"),
    )


def test_api_keys_json_object_rotation_list() -> None:
    """One identity may hold several keys (rotation) — SD-017 still holds."""
    assert _settings('{"RPSG01": ["key-old", "key-new"]}').api_key_bindings == (
        ("RPSG01", "key-old"),
        ("RPSG01", "key-new"),
    )


def test_api_keys_empty() -> None:
    assert _settings("").api_key_bindings == ()


def test_api_keys_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="failed to parse"):
        _ = _settings("{not-json").api_key_bindings


def test_api_keys_json_values_must_be_strings() -> None:
    with pytest.raises(ValueError, match="strings or string arrays"):
        _ = _settings('{"RPSG01": 1}').api_key_bindings


def test_api_keys_bare_key_rejected() -> None:
    """SD-017: a key without an identity binding is a configuration error."""
    with pytest.raises(ValueError, match="collector_id:key"):
        _ = _settings("just-a-key").api_key_bindings


def test_api_keys_key_bound_to_two_identities_rejected() -> None:
    """SD-017: one key must belong to exactly one Fleet identity."""
    with pytest.raises(ValueError, match="multiple collector identities"):
        _ = _settings("RPSG01:same-key,BITAXE01:same-key").api_key_bindings


def test_api_keys_empty_identity_or_key_rejected() -> None:
    with pytest.raises(ValueError, match="empty collector_id or key"):
        _ = _settings("RPSG01:").api_key_bindings


def test_secrets_not_exposed_in_repr() -> None:
    settings = Settings(
        _env_file=None, api_keys="demo:very-secret-key", clickhouse_password="db-secret"
    )
    rendered = repr(settings) + str(settings)
    assert "very-secret-key" not in rendered
    assert "db-secret" not in rendered


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.clickhouse_port == 8123
    assert settings.clickhouse_database == "observatory"
    assert settings.max_request_bytes == 1_048_576


def test_deployment_environment_default_and_parsing() -> None:
    """M003.5 §3e/§6: Development by default; Production is explicit."""
    assert Settings(_env_file=None).deployment_environment is Environment.DEVELOPMENT
    settings = Settings(_env_file=None, deployment_environment="Production")
    assert settings.deployment_environment is Environment.PRODUCTION

    with pytest.raises(ValueError):
        Settings(_env_file=None, deployment_environment="prod")  # exact values only


# --- Fail-fast startup validation (M003.5 §2) --------------------------------


def _valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Minimal valid environment for load_settings(), isolated from the host."""
    prefixes = ("CLICKHOUSE_", "API_KEYS", "LOG_LEVEL", "APP_", "HEARTBEAT_", "OFFLINE_", "DEPLOYMENT_")
    for name in list(os.environ):
        if name.startswith(prefixes):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("API_KEYS", "RPSG01:test-key")


def test_startup_problems_empty_for_valid_settings() -> None:
    assert _settings("RPSG01:key-a").startup_problems() == []


def test_startup_problems_empty_api_keys() -> None:
    problems = _settings("").startup_problems()
    assert any("API_KEYS is required" in p for p in problems)


def test_startup_problems_placeholder_api_key() -> None:
    """An unedited example env file must not reach serving state."""
    problems = _settings("RPSG01:change-me-host-collector-key").startup_problems()
    assert any("placeholder" in p for p in problems)


def test_startup_problems_invalid_log_level() -> None:
    settings = Settings(_env_file=None, api_keys="RPSG01:k", log_level="LOUD")
    assert any("LOG_LEVEL" in p for p in settings.startup_problems())


def test_startup_problems_offline_timeout_vs_heartbeat() -> None:
    settings = Settings(
        _env_file=None, api_keys="RPSG01:k", offline_timeout=30.0, heartbeat_interval=30.0
    )
    assert any("OFFLINE_TIMEOUT" in p for p in settings.startup_problems())


def test_load_settings_valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    settings = load_settings()
    assert settings.api_key_bindings == (("RPSG01", "test-key"),)


def test_load_settings_fails_fast_on_missing_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    monkeypatch.delenv("API_KEYS", raising=False)
    with pytest.raises(ConfigurationError, match="API_KEYS is required"):
        load_settings()


def test_load_settings_fails_fast_on_bad_field_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pydantic field errors surface as env-var-named messages, no traceback."""
    _valid_env(monkeypatch)
    monkeypatch.setenv("CLICKHOUSE_PORT", "not-a-port")
    with pytest.raises(ConfigurationError, match="CLICKHOUSE_PORT"):
        load_settings()


def test_load_settings_error_never_leaks_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("API_KEYS", "RPSG01:super-secret,RPSG01:")
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "super-secret" not in str(excinfo.value)


def test_build_app_exits_with_clear_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The uvicorn factory dies with status 2 before binding (M003.5 §2)."""
    from app.main import build_app

    _valid_env(monkeypatch)
    monkeypatch.delenv("API_KEYS", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        build_app()
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "observatory-backend" in err
    assert "API_KEYS" in err
