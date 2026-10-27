"""Watchlist slice: read, add and remove watchlist entries."""

from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from zero_mcp.client import ClientProvider
from zero_mcp.errors import tool_errors
from zero_mcp.serialization import dump, dump_many
from zero_mcp.tools._annotations import ADDITIVE, DESTRUCTIVE, READ_ONLY
from zero_mcp.tools._helpers import normalize_isin


def register_watchlist_tools(
    server: MCPServer[Any],
    provider: ClientProvider,
    *,
    read_only: bool,
) -> None:
    """Register the watchlist tools on ``server``; writes only when allowed."""

    @server.tool(annotations=READ_ONLY)
    def get_watchlist() -> dict[str, Any]:
        """Return the ZERO watchlist with quotes and watchlist metadata."""
        with tool_errors(), provider.session() as client:
            entries = client.watchlist.get()
            return {
                "count": len(entries),
                "entries": dump_many(entries),
            }

    if read_only:
        return

    @server.tool(annotations=ADDITIVE)
    def add_to_watchlist(
        isin: Annotated[str, Field(description="ISIN, e.g. US0378331005.")],
    ) -> dict[str, Any]:
        """Add an instrument to the ZERO watchlist by ISIN.

        Returns the created watchlist entry. This changes the user's watchlist
        but moves no money.
        """
        with tool_errors(), provider.session() as client:
            entry = client.watchlist.add_to_watchlist(normalize_isin(isin))
            return dump(entry)

    @server.tool(annotations=DESTRUCTIVE)
    def remove_from_watchlist(
        isin: Annotated[str, Field(description="ISIN, e.g. US0378331005.")],
    ) -> dict[str, Any]:
        """Remove an instrument from the ZERO watchlist by ISIN.

        The broker answers with a literal ``true``; this tool reports that
        result instead of the removed entry. This changes the user's watchlist
        but moves no money.
        """
        with tool_errors(), provider.session() as client:
            cleaned = normalize_isin(isin)
            client.watchlist.remove_from_watchlist(cleaned)
            return {"isin": cleaned, "removed": True}
