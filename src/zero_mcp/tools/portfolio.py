"""Portfolio slice: the securities account (Depot) positions."""

from typing import Any

from mcp.server import MCPServer

from zero_mcp.client import ClientProvider
from zero_mcp.errors import tool_errors
from zero_mcp.serialization import dump_many
from zero_mcp.tools._annotations import READ_ONLY


def register_portfolio_tools(server: MCPServer[Any], provider: ClientProvider) -> None:
    """Register the depot-position tools on ``server``."""

    @server.tool(annotations=READ_ONLY)
    def get_positions() -> dict[str, Any]:
        """Return the positions currently held in the ZERO depot.

        Each position carries the quantity, available quantity, latest quote and
        the average/FIFO entry quotes. Quotes are in the instrument's currency
        and are returned as decimal strings; timestamps are ISO 8601.
        """
        with tool_errors(), provider.session() as client:
            positions = client.portfolio.get_positions()
            return {
                "count": len(positions),
                "positions": dump_many(positions),
            }
