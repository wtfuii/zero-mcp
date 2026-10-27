"""Tool slices against a mocked broker client: argument mapping and output."""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, SecretStr
from zero_api.instrument.models import (
    ChartBar,
    ChartPeriod,
    InstrumentDetail,
    InstrumentSearchPage,
)
from zero_api.ordering.models import ExecType, OrdersPage
from zero_api.portfolio.models import Position
from zero_api.sessiontan.models import EnrolledDevice
from zero_api.watchlist.models import WatchlistEntry

from zero_mcp.client import ClientProvider
from zero_mcp.config import Settings
from zero_mcp.server import create_server

pytestmark = pytest.mark.anyio


class PlacedOrder(BaseModel):
    """Just enough of an order to prove the tool serializes the response."""

    order_id: str
    status: str


def make_server(provider: ClientProvider) -> MCPServer[Any]:
    return create_server(
        Settings(username="user@example.com", password=SecretStr("pass")),
        provider=provider,
    )


def result_text(result: CallToolResult) -> str:
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


async def call(
    provider: ClientProvider, name: str, args: dict[str, Any]
) -> CallToolResult:
    async with Client(make_server(provider)) as client:
        return await client.call_tool(name, args)


def sample_position() -> Position:
    return Position.model_validate(
        {
            "id": 1,
            "isin": "US0378331005",
            "depotId": "depot-1",
            "quoteTime": "2026-10-26T15:30:00Z",
            "quote": "212.50",
            "quantity": "3.0",
            "availableQuantity": "3.0",
            "avgEntryQuote": "180.00",
            "avgEntryQuoteEdited": None,
            "avgEntryQuoteOriginal": "180.00",
            "assetName": "Apple Inc.",
            "matchedImport": None,
            "entryQuoteFifo": "180.00",
            "entryQuoteFifoDateTime": "2026-01-02T09:00:00Z",
            "entryQuoteFifoInfoMarker": None,
            "orderExecutionTypesForProtection": [],
            "entryQuote": "180.00",
        }
    )


def sample_watchlist_entry() -> WatchlistEntry:
    return WatchlistEntry.model_validate(
        {
            "instrument": {
                "historicQuotes": [],
                "sparplan": False,
                "knockedOutFlag": False,
                "endfaellig": False,
                "longName": "Apple Inc.",
                "isin": "US0378331005",
                "type": "AKTIE",
                "shortName": "Apple",
            },
            "watchlistItem": {
                "id": 9,
                "wlOrder": 0,
                "isin": "US0378331005",
                "added": "2026-10-20T08:00:00Z",
                "askWhenAdded": "200.00",
                "bidWhenAdded": "199.50",
                "ask": "212.60",
                "bid": "212.40",
                "quoteTime": "2026-10-26T15:30:00Z",
                "itemName": "Apple Inc.",
                "note": "",
            },
            "instrumentAlternative": None,
        }
    )


async def test_search_instruments_maps_query_and_size(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.instrument.search.return_value = InstrumentSearchPage.model_validate(
        {"stats": {"took": 4, "hits": {"AKTIE": 1}}, "results": []}
    )

    result = await call(provider, "search_instruments", {"query": "Apple", "size": 5})

    assert result.is_error is False
    broker_mock.instrument.search.assert_called_once_with("Apple", size=5)
    assert result.structured_content == {
        "stats": {"took": 4, "hits": {"AKTIE": 1}},
        "results": [],
    }


async def test_get_chart_normalizes_isin_and_maps_period(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.instrument.chart.return_value = [
        ChartBar.model_validate({"Date": "2026-10-24", "Close": 210.5, "Volume": 1000})
    ]

    result = await call(
        provider,
        "get_chart",
        {"isin": " us0378331005 ", "period": "OneMonth"},
    )

    assert result.is_error is False
    broker_mock.instrument.chart.assert_called_once_with(
        "US0378331005", period=ChartPeriod.ONE_MONTH
    )
    payload = result.structured_content
    assert payload is not None
    assert payload["isin"] == "US0378331005"
    assert payload["period"] == "OneMonth"
    assert payload["bars"] == [
        {
            "date": "2026-10-24",
            "open": None,
            "high": None,
            "low": None,
            "close": 210.5,
            "volume": 1000.0,
        }
    ]


async def test_get_positions_wraps_the_list_with_a_count(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.portfolio.get_positions.return_value = [sample_position()]

    result = await call(provider, "get_positions", {})

    assert result.is_error is False
    payload = result.structured_content
    assert payload is not None
    assert payload["count"] == 1
    assert payload["positions"][0]["isin"] == "US0378331005"
    assert payload["positions"][0]["quote"] == "212.50"


async def test_list_orders_returns_page_metadata(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.orders.list.return_value = OrdersPage.model_validate(
        {"list": [], "hasNext": True}
    )

    result = await call(
        provider, "list_orders", {"status": "Open", "page": 1, "size": 50}
    )

    assert result.is_error is False
    broker_mock.orders.list.assert_called_once_with("Open", page=1, size=50)
    assert result.structured_content == {
        "orders": [],
        "count": 0,
        "has_next": True,
    }


@pytest.mark.parametrize("status", ["Open", "Filled", "Canceled"])
async def test_list_orders_forwards_each_history_tab(
    provider: ClientProvider,
    broker_mock: Mock,
    status: str,
) -> None:
    broker_mock.orders.list.return_value = OrdersPage.model_validate(
        {"list": [], "hasNext": False}
    )

    result = await call(provider, "list_orders", {"status": status})

    assert result.is_error is False
    broker_mock.orders.list.assert_called_once_with(status, page=0, size=100)


async def test_list_orders_rejects_an_unknown_status_without_a_broker_call(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    result = await call(provider, "list_orders", {"status": "Rejected"})

    assert result.is_error is True
    assert "Open" in result_text(result)
    assert "Filled" in result_text(result)
    assert "Canceled" in result_text(result)
    broker_mock.orders.list.assert_not_called()


async def test_add_to_watchlist_normalizes_isin(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.watchlist.add_to_watchlist.return_value = sample_watchlist_entry()

    result = await call(provider, "add_to_watchlist", {"isin": "us0378331005"})

    assert result.is_error is False
    broker_mock.watchlist.add_to_watchlist.assert_called_once_with("US0378331005")
    payload = result.structured_content
    assert payload is not None
    assert payload["watchlist_item"]["isin"] == "US0378331005"


async def test_remove_from_watchlist_reports_success(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.watchlist.remove_from_watchlist.return_value = None

    result = await call(provider, "remove_from_watchlist", {"isin": "US0378331005"})

    assert result.is_error is False
    broker_mock.watchlist.remove_from_watchlist.assert_called_once_with("US0378331005")
    assert result.structured_content == {"isin": "US0378331005", "removed": True}


async def test_place_order_uses_default_venue_and_maps_every_field(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.instrument.get.return_value = SimpleNamespace(
        trading_venues=[
            SimpleNamespace(
                default_venue=False,
                mic_code="MUNC",
                trading_venue_name="München",
            ),
            SimpleNamespace(
                default_venue=True,
                mic_code="XETR",
                trading_venue_name="Xetra",
            ),
        ]
    )
    broker_mock.orders.place.return_value = PlacedOrder(
        order_id="ORDER-1", status="Created"
    )

    result = await call(
        provider,
        "place_order",
        {
            "isin": " us0378331005 ",
            "direction": "buy",
            "exec_type": "limit",
            "quantity": "2.5",
            "limit_price": "123.45",
            "valid_to_date": "2026-12-31T23:59:59Z",
            "device_serial": "device-1",
        },
    )

    assert result.is_error is False
    broker_mock.instrument.get.assert_called_once_with("US0378331005")
    broker_mock.orders.place.assert_called_once()
    request, kwargs = broker_mock.orders.place.call_args
    order_request = request[0]
    assert order_request.isin == "US0378331005"
    assert order_request.direction == "buy"
    assert order_request.exec_type is ExecType.LIMIT
    assert order_request.quantity == Decimal("2.5")
    assert order_request.limit_price == Decimal("123.45")
    assert order_request.mic_code == "XETR"
    assert order_request.valid_to_date is not None
    assert kwargs == {"device": "device-1"}
    assert result.structured_content == {"order_id": "ORDER-1", "status": "Created"}


async def test_place_order_honours_explicit_mic_without_a_master_data_call(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.orders.place.return_value = PlacedOrder(
        order_id="ORDER-2", status="Created"
    )

    result = await call(
        provider,
        "place_order",
        {
            "isin": "US0378331005",
            "direction": "sell",
            "exec_type": "market",
            "quantity": 1,
            "mic_code": "XGAT",
        },
    )

    assert result.is_error is False
    broker_mock.instrument.get.assert_not_called()
    order_request = broker_mock.orders.place.call_args.args[0]
    assert order_request.mic_code == "XGAT"


async def test_place_order_reports_when_no_default_venue_exists(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.instrument.get.return_value = SimpleNamespace(trading_venues=[])

    result = await call(
        provider,
        "place_order",
        {
            "isin": "US0378331005",
            "direction": "buy",
            "exec_type": "market",
            "quantity": 1,
        },
    )

    assert result.is_error is True
    assert "No default trading venue" in result_text(result)
    broker_mock.orders.place.assert_not_called()


async def test_cancel_order_passes_the_string_order_id(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.orders.cancel.return_value = PlacedOrder(
        order_id="ORDER-1", status="Open_CreatedCancel"
    )

    result = await call(
        provider,
        "cancel_order",
        {"order_id": "ORDER-1", "device_serial": "device-1"},
    )

    assert result.is_error is False
    broker_mock.orders.cancel.assert_called_once_with("ORDER-1", device="device-1")
    assert result.structured_content == {
        "order_id": "ORDER-1",
        "status": "Open_CreatedCancel",
    }


async def test_session_status_is_reported(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.sessiontan.is_authorized.return_value = True

    result = await call(provider, "get_session_status", {})

    assert result.structured_content == {"authorized": True}


async def test_list_enrolled_devices(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.sessiontan.enrolled_devices.return_value = [
        EnrolledDevice.model_validate(
            {
                "serial": "device-1",
                "customerDeviceName": "iPhone 16 Pro",
                "deviceManufacturer": "Apple",
                "deviceModel": "iPhone 16 Pro",
                "enrolled": "2026-01-01T12:00:00Z",
            }
        )
    ]

    result = await call(provider, "list_enrolled_devices", {})

    assert result.is_error is False
    payload = result.structured_content
    assert payload is not None
    assert payload["count"] == 1
    assert payload["devices"][0]["serial"] == "device-1"


async def test_unlock_requests_a_push_when_locked(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.sessiontan.is_authorized.return_value = False
    broker_mock.sessiontan.unlock.return_value = None

    result = await call(
        provider,
        "unlock_order_execution",
        {"device_serial": "device-1", "timeout_seconds": 30},
    )

    assert result.is_error is False
    broker_mock.sessiontan.unlock.assert_called_once_with("device-1", timeout=30.0)
    assert result.structured_content == {
        "authorized": True,
        "already_authorized": False,
    }


async def test_unlock_is_a_no_op_when_already_authorized(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.sessiontan.is_authorized.return_value = True

    result = await call(provider, "unlock_order_execution", {})

    assert result.is_error is False
    broker_mock.sessiontan.unlock.assert_not_called()
    assert result.structured_content == {
        "authorized": True,
        "already_authorized": True,
    }


async def test_get_instrument_detail_forwards_normalized_isin(
    provider: ClientProvider,
    broker_mock: Mock,
) -> None:
    broker_mock.instrument.detail.return_value = InstrumentDetail.model_validate(
        {
            "name": "Apple Inc.",
            "isin": "US0378331005",
            "high": 215.0,
            "last": 212.5,
            "low": 211.0,
            "netChange": 1.5,
            "percent": 0.71,
            "prevDay": 211.0,
            "instrumentType": 1,
            "currency": "USD",
            "date": "2026-10-26",
            "exchange": "NASDAQ",
            "pushIdentifier": "push-1",
            "time": "22:00:00",
            "tkIdentifier": "TK-1",
            "branches": ["Technology"],
            "dividends": [],
        }
    )

    result = await call(provider, "get_instrument_detail", {"isin": " us0378331005 "})

    assert result.is_error is False
    broker_mock.instrument.detail.assert_called_once_with("US0378331005")
    payload = result.structured_content
    assert payload is not None
    assert payload["last"] == 212.5
    assert payload["dividends"] == []
