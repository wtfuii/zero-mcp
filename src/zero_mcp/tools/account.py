"""Account slice: the cash account (Verrechnungskonto)."""

from typing import Any

from mcp.server import MCPServer

from zero_mcp.client import ClientProvider
from zero_mcp.errors import tool_errors
from zero_mcp.serialization import dump
from zero_mcp.tools._annotations import READ_ONLY


def register_account_tools(server: MCPServer[Any], provider: ClientProvider) -> None:
    """Register the cash-account tools on ``server``."""

    @server.tool(annotations=READ_ONLY)
    def get_account() -> dict[str, Any]:
        """Return the ZERO cash account (Verrechnungskonto).

        Includes buying power (with and without an available credit line),
        transfer power, IBAN, account number, last imported balance, debit
        interest and the next closing date. Amounts are EUR and are returned as
        decimal strings; timestamps are ISO 8601.
        """
        with tool_errors(), provider.session() as client:
            return dump(client.account.get())
