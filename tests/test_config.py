"""Configuration is environment-only and credentials stay hidden."""

import pytest
from pydantic import SecretStr

from zero_mcp.config import ConfigurationError, Settings


def test_defaults_are_read_only_and_unconfigured() -> None:
    settings = Settings()
    assert settings.read_only is False
    assert settings.default_device is None
    with pytest.raises(ConfigurationError, match="ZERO_USERNAME and ZERO_PASSWORD"):
        settings.require_credentials()


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERO_USERNAME", "  klaus@example.com ")
    monkeypatch.setenv("ZERO_PASSWORD", "s3cret")
    monkeypatch.setenv("ZERO_DEFAULT_DEVICE", "device-1")
    monkeypatch.setenv("ZERO_READ_ONLY", "true")

    settings = Settings()

    assert settings.require_credentials() == ("klaus@example.com", "s3cret")
    assert settings.default_device == "device-1"
    assert settings.read_only is True


def test_values_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("zero_username", "user@example.com")
    monkeypatch.setenv("zero_password", "pass")
    monkeypatch.setenv("zero_read_only", "TRUE")

    settings = Settings()

    assert settings.require_credentials() == ("user@example.com", "pass")
    assert settings.read_only is True


def test_missing_password_is_named() -> None:
    settings = Settings(username="user@example.com", password=None)
    with pytest.raises(ConfigurationError, match="ZERO_PASSWORD"):
        settings.require_credentials()


def test_whitespace_password_is_missing() -> None:
    settings = Settings(username="user@example.com", password=SecretStr("   "))
    with pytest.raises(ConfigurationError, match="ZERO_PASSWORD"):
        settings.require_credentials()


def test_password_never_appears_in_repr() -> None:
    settings = Settings(username="user@example.com", password=SecretStr("super-secret"))
    assert "super-secret" not in repr(settings)


def test_invalid_boolean_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERO_READ_ONLY", "sometimes")
    with pytest.raises(ValueError):
        Settings()
