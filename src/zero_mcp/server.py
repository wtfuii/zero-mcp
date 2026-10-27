"""The zero-mcp MCP server: one object, one lazy broker session, many tools.

The server speaks MCP over **stdio** (the transport MCP hosts start locally).
stdout therefore belongs to the protocol: all diagnostics go to stderr and no
tool ever prints.
"""

import logging
import sys
from typing import Any

from mcp.server import MCPServer
from pydantic import ValidationError

from zero_mcp import __version__
from zero_mcp.client import ClientProvider, ZeroClientProvider
from zero_mcp.config import Settings
from zero_mcp.tools import (
    register_account_tools,
    register_instrument_tools,
    register_order_tools,
    register_portfolio_tools,
    register_sessiontan_tools,
    register_watchlist_tools,
)

SERVER_NAME = "finanzen-zero"
SERVER_TITLE = "Finanzen.net ZERO"

_BASE_INSTRUCTIONS = """\
Unofficial MCP server for the German broker Finanzen.net ZERO.

Credentials come from the ZERO_USERNAME (login e-mail) and ZERO_PASSWORD
environment variables; the first broker call performs the login. Account,
position, order and watchlist amounts are returned as decimal strings;
market-data prices may be floats. Timestamps are ISO 8601 and the currency is
EUR unless the instrument says otherwise.

Order placement and cancellation move real money. Never call place_order or
cancel_order without the user's explicit confirmation of the instrument, side,
quantity, order type, prices and venue. Order execution may require approving
a push notification in the paired ZERO mobile app, and order tools can block
for up to a minute while waiting for that approval.
"""

_READ_ONLY_NOTICE = """\
This server runs in READ-ONLY mode (ZERO_READ_ONLY=true): order placement and
cancellation, the 2FA unlock and watchlist changes are disabled.
"""


def create_server(
    settings: Settings | None = None,
    *,
    provider: ClientProvider | None = None,
) -> MCPServer[Any]:
    """Build the MCP server, registering tools according to ``settings``.

    Neither the settings nor the provider touch the broker, so constructing the
    server (and answering ``tools/list``) works before credentials exist. The
    client is created lazily on the first tool call.
    """
    resolved = settings if settings is not None else Settings()
    client_provider = provider if provider is not None else ZeroClientProvider(resolved)
    instructions = _BASE_INSTRUCTIONS
    if resolved.read_only:
        instructions += "\n" + _READ_ONLY_NOTICE

    server: MCPServer[Any] = MCPServer(
        name=SERVER_NAME,
        title=SERVER_TITLE,
        description="Access a Finanzen.net ZERO brokerage account over MCP.",
        instructions=instructions,
        version=__version__,
    )

    register_account_tools(server, client_provider)
    register_instrument_tools(server, client_provider)
    register_portfolio_tools(server, client_provider)
    register_watchlist_tools(server, client_provider, read_only=resolved.read_only)
    register_order_tools(server, client_provider, read_only=resolved.read_only)
    register_sessiontan_tools(server, client_provider, read_only=resolved.read_only)
    return server


def main() -> None:
    """Run the server over stdio until the MCP host closes the process."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("zero_mcp")

    try:
        settings = Settings()
    except ValidationError as exc:
        # Never write to stdout: it is the MCP protocol channel.
        print(f"zero-mcp: invalid configuration: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    logger.info(
        "starting %s %s over stdio (%s, credentials %s)",
        SERVER_TITLE,
        __version__,
        "read-only" if settings.read_only else "trading enabled",
        "configured"
        if settings.username and settings.password is not None
        else "not configured",
    )
    try:
        create_server(settings).run("stdio")
    except KeyboardInterrupt:
        logger.info("server stopped")
