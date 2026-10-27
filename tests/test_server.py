"""Server surface: tool registration, annotations, output and error mapping."""

import sys
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic import SecretStr
from zero_api.account.models import MoneyTransactionAccount
from zero_api.core.exceptions import AuthenticationError, BrokerApiError, TwoFactorError

from zero_mcp.client import ClientProvider
from zero_mcp.config import Settings
from zero_mcp.server import create_server

pytestmark = pytest.mark.anyio

WRITE_TOOLS = {
    "add_to_watchlist",
    "remove_from_watchlist",
    "place_order",
    "cancel_order",
    "unlock_order_execution",
}
READ_TOOLS = {
    "get_account",
    "search_instruments",
    "get_instrument",
    "get_instrument_detail",
    "get_chart",
    "get_positions",
    "get_watchlist",
    "list_orders",
    "get_session_status",
    "list_enrolled_devices",
}


def make_server(provider: ClientProvider, *, read_only: bool = False) -> MCPServer[Any]:
    return create_server(
        Settings(
            username="user@example.com", password=SecretStr("pass"), read_only=read_only
        ),
        provider=provider,
    )


def result_text(result: CallToolResult) -> str:
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


async def test_lists_all_tools_without_credentials_or_network() -> None:
    server = create_server(Settings())

    async with Client(server) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools.tools} == READ_TOOLS | WRITE_TOOLS
    assert all(tool.description for tool in tools.tools)


async def test_read_only_mode_hides_every_write_tool(provider: ClientProvider) -> None:
    server = make_server(provider, read_only=True)

    async with Client(server) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools.tools} == READ_TOOLS


async def test_list_orders_filter_is_enumerated_in_the_tool_schema(
    provider: ClientProvider,
) -> None:
    server = make_server(provider)

    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    status = tools["list_orders"].input_schema["properties"]["status"]
    assert status["enum"] == ["Open", "Filled", "Canceled"]
    assert status["default"] == "Open"


async def test_tool_annotations_mark_real_money_operations(
    provider: ClientProvider,
) -> None:
    server = make_server(provider)

    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    place = tools["place_order"].annotations
    assert place is not None
    assert place.read_only_hint is False
    assert place.destructive_hint is True

    account = tools["get_account"].annotations
    assert account is not None
    assert account.read_only_hint is True
    assert account.destructive_hint is not True


async def test_get_account_returns_json_safe_structured_output(
    provider: ClientProvider,
    broker_mock: Mock,
    account: MoneyTransactionAccount,
) -> None:
    broker_mock.account.get.return_value = account
    server = make_server(provider)

    async with Client(server) as client:
        result = await client.call_tool("get_account", {})

    assert result.is_error is False
    assert result.structured_content == account.model_dump(mode="json")
    payload = result.structured_content
    assert payload is not None
    assert payload["buying_power"] == "1000.50"  # Decimal as a precision-safe string
    assert payload["intraday_timestamp"] == "2026-10-26T10:00:00Z"


async def test_broker_rejection_becomes_an_actionable_tool_error(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.account.get.side_effect = BrokerApiError(
        status=422,
        message="Order rejected",
        error_code="LIMIT_TOO_LOW",
        errors=["limit price below minimum"],
    )
    server = make_server(provider)

    async with Client(server) as client:
        result = await client.call_tool("get_account", {})

    assert result.is_error is True
    text = result_text(result)
    assert "HTTP 422" in text
    assert "Order rejected" in text
    assert "LIMIT_TOO_LOW" in text
    assert "limit price below minimum" in text


async def test_missing_credentials_is_reported_by_the_tool() -> None:
    # The real provider: it fails before any broker client is built.
    server = create_server(Settings())

    async with Client(server) as client:
        result = await client.call_tool("get_account", {})

    assert result.is_error is True
    assert "not configured" in result_text(result)
    assert "ZERO_USERNAME" in result_text(result)


async def test_invalid_isin_is_rejected_before_any_broker_call(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    server = make_server(provider)

    async with Client(server) as client:
        result = await client.call_tool("get_instrument", {"isin": "not-an-isin"})

    assert result.is_error is True
    assert "Invalid ISIN" in result_text(result)
    broker_mock.instrument.get.assert_not_called()


async def test_stdio_entrypoint_starts_and_lists_tools() -> None:
    """The real ``python -m zero_mcp`` process must keep stdout protocol-clean."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "zero_mcp"],
        env={"ZERO_READ_ONLY": "true"},
    )

    async with Client(params, read_timeout_seconds=30) as client:
        tools = await client.list_tools()
        instructions = client.instructions

    assert {tool.name for tool in tools.tools} == READ_TOOLS
    assert instructions is not None
    assert "READ-ONLY" in instructions


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AuthenticationError("invalid credentials"), "ZERO_USERNAME and ZERO_PASSWORD"),
        (TwoFactorError("push declined"), "Approve the push notification"),
        (httpx.ConnectError("connection refused"), "Network error"),
    ],
)
async def test_known_failures_are_actionable_tool_errors(
    provider: ClientProvider,
    broker_mock: Mock,
    error: Exception,
    expected: str,
) -> None:
    broker_mock.account.get.side_effect = error
    server = make_server(provider)

    async with Client(server) as client:
        result = await client.call_tool("get_account", {})

    assert result.is_error is True
    assert expected in result_text(result)
