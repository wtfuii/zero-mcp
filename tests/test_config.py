"""Configuration is environment-only and credentials stay hidden."""

import pytest
from pydantic import SecretStr

from zero_mcp.config import ConfigurationError, Settings, TradeMode


def test_defaults_are_write_mode_and_unconfigured() -> None:
    settings = Settings()
    assert settings.mode is TradeMode.WRITE
    assert settings.default_device is None
    with pytest.raises(ConfigurationError, match="ZERO_USERNAME and ZERO_PASSWORD"):
        settings.require_credentials()


@pytest.mark.parametrize("mode", ["READ", "WRITE", "YOLO", "read", "Write", " yolo "])
def test_mode_is_read_from_the_environment_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.setenv("ZERO_MODE", mode)

    assert Settings().mode is TradeMode[mode.strip().upper()]


def test_mode_rejects_an_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERO_MODE", "readonly")

    with pytest.raises(ValueError):
        Settings()


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERO_USERNAME", "  klaus@example.com ")
    monkeypatch.setenv("ZERO_PASSWORD", "s3cret")
    monkeypatch.setenv("ZERO_DEFAULT_DEVICE", "device-1")
    monkeypatch.setenv("ZERO_MODE", "READ")

    settings = Settings()

    assert settings.require_credentials() == ("klaus@example.com", "s3cret")
    assert settings.default_device == "device-1"
    assert settings.mode is TradeMode.READ


def test_values_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("zero_username", "user@example.com")
    monkeypatch.setenv("zero_password", "pass")
    monkeypatch.setenv("zero_mode", "read")

    settings = Settings()

    assert settings.require_credentials() == ("user@example.com", "pass")
    assert settings.mode is TradeMode.READ


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
