"""MCP tool registration, one function per vertical slice.

Each slice owns its tools and talks to the broker only through the shared
:class:`~zero_mcp.client.ClientProvider`. Slices that contain both read and
write tools skip the writes entirely under ``ZERO_MODE=READ``, so those tools
are never advertised; the order slice also needs the mode to pick its
confirmation rule, while the others only need the ``read_only`` decision.
"""

from zero_mcp.tools.account import register_account_tools
from zero_mcp.tools.instrument import register_instrument_tools
from zero_mcp.tools.orders import register_order_tools
from zero_mcp.tools.portfolio import register_portfolio_tools
from zero_mcp.tools.sessiontan import register_sessiontan_tools
from zero_mcp.tools.watchlist import register_watchlist_tools

__all__ = [
    "register_account_tools",
    "register_instrument_tools",
    "register_order_tools",
    "register_portfolio_tools",
    "register_sessiontan_tools",
    "register_watchlist_tools",
]
