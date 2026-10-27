"""Server configuration, read from ``ZERO_*`` environment variables.

Credentials are only validated when the first tool call needs the broker, so
``tools/list`` works before (or without) configuring an account. The MCP host
passes the variables to the stdio process, e.g. in ``claude_desktop_config.json``.
"""

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Required configuration is missing or invalid."""


class Settings(BaseSettings):
    """Configuration of the zero-mcp server.

    Environment variables (case-insensitive):

    - ``ZERO_USERNAME`` — the e-mail address of the ZERO account (required for
      any broker call).
    - ``ZERO_PASSWORD`` — the account password (required for any broker call).
    - ``ZERO_DEFAULT_DEVICE`` — optional serial of the device that receives the
      2FA order-execution push when several devices are enrolled.
    - ``ZERO_READ_ONLY`` — when true, mutating tools (orders, 2FA unlock,
      watchlist changes) are not registered at all. Default: false.
    - ``ZERO_YOLO_MODE`` (alias ``YOLO_MODE``) — when true, the server tells
      the model to place and cancel orders without asking the user for
      confirmation first. Default: false. Ignored when ``ZERO_READ_ONLY`` is
      true, because the order tools are not registered then.
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
    read_only: bool = Field(
        default=False,
        description="Disable every tool that changes broker state.",
    )
    yolo_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("ZERO_YOLO_MODE", "YOLO_MODE"),
        description=(
            "Skip the model-level confirmation for real-money orders. The "
            "prefixed name wins if both aliases are set. Ignored in read-only "
            "mode."
        ),
    )

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
