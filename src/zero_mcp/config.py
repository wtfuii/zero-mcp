"""Server configuration, read from ``ZERO_*`` environment variables.

Credentials are only validated when the first tool call needs the broker, so
``tools/list`` works before (or without) configuring an account. The MCP host
passes the variables to the stdio process, e.g. in ``claude_desktop_config.json``.
"""

from enum import StrEnum

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Required configuration is missing or invalid."""


class TradeMode(StrEnum):
    """How much of the broker surface the server exposes.

    The three modes are mutually exclusive: a single switch is easier to
    reason about than two independent booleans, where the combination
    "read-only and YOLO" could only ever mean read-only.
    """

    READ = "READ"
    """Register no mutating tool at all (orders, 2FA unlock, watchlist edits)."""

    WRITE = "WRITE"
    """Register the mutating tools; the model must obtain explicit confirmation."""

    YOLO = "YOLO"
    """Register the mutating tools without the model-level confirmation requirement."""


class Settings(BaseSettings):
    """Configuration of the zero-mcp server.

    Environment variables (case-insensitive):

    - ``ZERO_USERNAME`` — the e-mail address of the ZERO account (required for
      any broker call).
    - ``ZERO_PASSWORD`` — the account password (required for any broker call).
    - ``ZERO_DEFAULT_DEVICE`` — optional serial of the device that receives the
      2FA order-execution push when several devices are enrolled.
    - ``ZERO_MODE`` — ``READ``, ``WRITE`` (default) or ``YOLO``. ``READ`` does
      not register the mutating tools (orders, 2FA unlock, watchlist changes)
      at all; ``WRITE`` registers them and requires explicit confirmation for
      real-money orders; ``YOLO`` registers them and tells the model to trade
      without asking. Values are case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_prefix="ZERO_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    username: str | None = Field(
        default=None,
        description="E-mail address used to log in to Finanzen.net ZERO.",
    )
    password: SecretStr | None = Field(
        default=None,
        description="Password used to log in to Finanzen.net ZERO.",
    )
    default_device: str | None = Field(
        default=None,
        description="Serial of the 2FA device to use when several are enrolled.",
    )
    mode: TradeMode = Field(
        default=TradeMode.WRITE,
        description=(
            "How much of the broker surface to expose: READ removes every "
            "mutating tool, WRITE requires per-order confirmation, YOLO skips "
            "that confirmation."
        ),
    )

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: object) -> object:
        """Accept ``read``/``Read`` as well as ``READ`` from the environment."""
        return value.strip().upper() if isinstance(value, str) else value

    def require_credentials(self) -> tuple[str, str]:
        """Return ``(username, password)`` or raise :class:`ConfigurationError`.

        Whitespace-only values are treated as missing. The password is never
        included in the error message.
        """
        username = (self.username or "").strip()
        password = self.password.get_secret_value() if self.password is not None else ""

        missing: list[str] = []
        if not username:
            missing.append("ZERO_USERNAME")
        if not password.strip():
            missing.append("ZERO_PASSWORD")
        if missing:
            raise ConfigurationError(
                "missing " + " and ".join(missing) + "; set them in the MCP server's "
                "environment (the username is the ZERO login e-mail address)"
            )
        return username, password
