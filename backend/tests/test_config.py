"""Tests for environment-driven configuration parsing."""

from __future__ import annotations

import pytest

from app.config import Settings


def _settings(api_keys: str) -> Settings:
    return Settings(_env_file=None, api_keys=api_keys)


def test_api_keys_comma_separated() -> None:
    assert _settings("key-a,key-b").api_key_list == ("key-a", "key-b")


def test_api_keys_comma_separated_with_whitespace() -> None:
    assert _settings(" key-a , key-b ,").api_key_list == ("key-a", "key-b")


def test_api_keys_json_array() -> None:
    assert _settings('["key-a", "key-b"]').api_key_list == ("key-a", "key-b")


def test_api_keys_empty() -> None:
    assert _settings("").api_key_list == ()


def test_api_keys_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="failed to parse"):
        _ = _settings("[not-json").api_key_list


def test_api_keys_json_must_be_string_array() -> None:
    with pytest.raises(ValueError, match="array of strings"):
        _ = _settings("[1, 2]").api_key_list


def test_secrets_not_exposed_in_repr() -> None:
    settings = Settings(
        _env_file=None, api_keys="very-secret-key", clickhouse_password="db-secret"
    )
    rendered = repr(settings) + str(settings)
    assert "very-secret-key" not in rendered
    assert "db-secret" not in rendered


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.clickhouse_port == 8123
    assert settings.clickhouse_database == "observatory"
    assert settings.max_request_bytes == 1_048_576
