"""Tests for environment-driven configuration parsing."""

from __future__ import annotations

import pytest

from app.config import Settings
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
