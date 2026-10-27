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
market-data prices may be floats. Timestamps are ISO 8601. Account amounts
are EUR; instrument and order prices use the instrument's quote currency
(quote_currency_code).

Typical order workflow: search_instruments for an ISIN, get_instrument for
its trading rules and venues, get_account for buying power, then
place_order. Use list_orders before cancel_order to get the string order_id
and confirm the order is still working.
"""

_CONFIRMATION_NOTICE = """\
Order placement and cancellation move real money. Never call place_order or
cancel_order without the user's explicit confirmation of the instrument,
side, quantity, order type, prices and venue. Order execution may require
approving a push notification in the paired ZERO mobile app, and order tools
can block for up to a minute while waiting for that approval; use
unlock_order_execution first if you need a longer wait. If place_order fails
after submission (timeout or network error), do not retry blindly: check
list_orders for an existing order first.
"""

_YOLO_NOTICE = """\
YOLO MODE IS ENABLED (ZERO_YOLO_MODE=true): the user has pre-authorized
autonomous trading. Place and cancel real-money orders without asking the
user to confirm, and do not repeat the parameters for approval first. The
usual safeguards still apply: check get_instrument and get_account before
ordering, and after a failed placement check list_orders before retrying.
Order execution may still require approving a push notification in the
paired ZERO mobile app, and order tools can block for up to a minute while
waiting for that approval.
"""

_READ_ONLY_NOTICE = """\
This server runs in READ-ONLY mode (ZERO_READ_ONLY=true): order placement and
cancellation, the 2FA unlock and watchlist changes are disabled.
"""


def _build_instructions(*, read_only: bool, yolo_mode: bool) -> str:
    """Compose the model instructions for the active registration mode."""
    parts = [_BASE_INSTRUCTIONS]
    if read_only:
        parts.append(_READ_ONLY_NOTICE)
    elif yolo_mode:
        parts.append(_YOLO_NOTICE)
    else:
        parts.append(_CONFIRMATION_NOTICE)
    return "\n".join(parts)


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
    instructions = _build_instructions(
        read_only=resolved.read_only,
        yolo_mode=resolved.yolo_mode,
    )

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
    register_order_tools(
        server,
        client_provider,
        read_only=resolved.read_only,
        yolo_mode=resolved.yolo_mode,
    )
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
        "read-only"
        if settings.read_only
        else (
            "trading enabled, YOLO mode (no confirmation)"
            if settings.yolo_mode
            else "trading enabled"
        ),
        "configured"
        if settings.username and settings.password is not None
        else "not configured",
    )
    if settings.yolo_mode and not settings.read_only:
        logger.warning(
            "YOLO mode is enabled: order tools will place and cancel real "
            "orders without asking the user for confirmation"
        )
    try:
        create_server(settings).run("stdio")
    except KeyboardInterrupt:
        logger.info("server stopped")
