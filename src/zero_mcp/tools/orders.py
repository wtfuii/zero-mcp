"""Ordering slice: list, place and cancel orders.

Placing and cancelling are real-money operations. The library's ``place()``
runs the broker's own submit flow (2FA unlock, ``/verify`` precheck, ex-ante
cost document) and blocks while the push notification is approved.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from zero_api import ZeroClient
from zero_api.ordering.models import ExecType, OrderRequest

from zero_mcp.client import ClientProvider
from zero_mcp.errors import tool_errors
from zero_mcp.serialization import dump, dump_many
from zero_mcp.tools._annotations import DESTRUCTIVE, READ_ONLY
from zero_mcp.tools._helpers import normalize_isin

_DEVICE_HELP = (
    "Serial of the enrolled 2FA device that receives the push, from "
    "list_enrolled_devices. Omit to use ZERO_DEFAULT_DEVICE or the only "
    "enrolled device. If several are enrolled and none is configured, the "
    "call fails; pass a serial explicitly."
)

# The broker's order-list filter buckets, sent verbatim as the ``status`` query
# parameter and matching its UI tabs. ``Open`` is the tab the site loads first;
# ``Filled`` and ``Canceled`` are the closed-order tabs. This is a coarser filter
# than the per-order ``OrderStatus`` the broker returns on each order.
_OrderFilter = Literal["Open", "Filled", "Canceled"]

_STATUS_HELP = (
    "Order filter bucket (case-sensitive), matching the broker's UI tabs. "
    "'Open' (default) = orders still working; 'Filled' = executed orders; "
    "'Canceled' = canceled orders. These are the only accepted values; the "
    "exact per-order state (e.g. 'Open_CreatedCancel') is reported in each "
    "order's 'status' field."
)


def register_order_tools(
    server: MCPServer[Any],
    provider: ClientProvider,
    *,
    read_only: bool,
) -> None:
    """Register the order tools on ``server``; writes only when allowed."""

    @server.tool(annotations=READ_ONLY)
    def list_orders(
        status: Annotated[
            _OrderFilter,
            Field(description=_STATUS_HELP),
        ] = "Open",
        page: Annotated[int, Field(ge=0, description="Zero-based page.")] = 0,
        size: Annotated[
            int,
            Field(ge=1, le=1000, description="Maximum orders in the page."),
        ] = 100,
    ) -> dict[str, Any]:
        """List orders from one of the broker's three order-list buckets.

        The broker's UI tabs map to the ``status`` filter, and only these three
        values are accepted: ``Open`` (default; orders still working), ``Filled``
        (executed orders) and ``Canceled`` (canceled orders). There is no "all
        orders" filter, so call the tool once per bucket to cover the full
        history; an empty result for a bucket is normal.

        The bucket is coarse. Each returned order also carries its exact broker
        ``status`` (for example ``Open``, ``Open_CreatedCancel``,
        ``PartiallyFilled``, ``PartiallyFilled_Filled`` or ``Expired``); use
        that field when a specific state matters, e.g. to distinguish a live
        order from one still in its cancellation phase.

        Use this to find an order's ``order_id`` for cancellation. ``has_next``
        reports whether more pages exist.
        """
        with tool_errors(), provider.session() as client:
            page_result = client.orders.list(status, page=page, size=size)
            return {
                "orders": dump_many(page_result.list),
                "count": len(page_result.list),
                "has_next": page_result.has_next,
            }

    if read_only:
        return

    @server.tool(annotations=DESTRUCTIVE)
    def place_order(
        isin: Annotated[str, Field(description="ISIN, e.g. US0378331005.")],
        direction: Annotated[
            Literal["buy", "sell"],
            Field(description="Order side: 'buy' acquires, 'sell' disposes."),
        ],
        exec_type: Annotated[
            ExecType,
            Field(
                description=(
                    "Order type. Price fields per type: market = none; limit = "
                    "limit_price; stoplimit/oco = limit_price + stop_price; tsl = "
                    "stop_price + exactly one of trailing_price_pct/"
                    "trailing_price_abs. Plain 'stop' (stop-loss) is not placeable."
                )
            ),
        ],
        quantity: Annotated[
            Decimal,
            Field(
                gt=0,
                description=(
                    "Number of shares/units: at least min_qty and a multiple of "
                    "qty_incr from get_instrument; fractional values only when the "
                    "instrument and venue allow them. Call get_instrument first."
                ),
            ),
        ],
        mic_code: Annotated[
            str | None,
            Field(
                description=(
                    "MIC of the trading venue (from get_instrument). Omit to use "
                    "the instrument's default trading venue."
                )
            ),
        ] = None,
        limit_price: Annotated[
            Decimal | None,
            Field(
                gt=0,
                description=(
                    "Limit price per unit in the instrument's quote currency (not "
                    "necessarily EUR), in price_incr steps; required for "
                    "limit/stoplimit/oco."
                ),
            ),
        ] = None,
        stop_price: Annotated[
            Decimal | None,
            Field(
                gt=0,
                description=(
                    "Stop price per unit in the instrument's quote currency; "
                    "required for stoplimit/oco/tsl."
                ),
            ),
        ] = None,
        trailing_price_abs: Annotated[
            Decimal | None,
            Field(
                gt=0,
                description=(
                    "Trailing-stop distance per unit in the instrument's quote "
                    "currency; tsl only; set exactly one of this or "
                    "trailing_price_pct."
                ),
            ),
        ] = None,
        trailing_price_pct: Annotated[
            Decimal | None,
            Field(
                gt=0,
                le=100,
                description=(
                    "Trailing-stop distance in percent (0-100); tsl only; set "
                    "exactly one of this or trailing_price_abs."
                ),
            ),
        ] = None,
        minimum_quantity_surcharge: Annotated[
            int,
            Field(
                ge=0,
                description=(
                    "Flag for ZERO's minimum-quantity surcharge (e.g. the EUR 1 "
                    "charged on stock/ETF/fund orders below EUR 500 notional). "
                    "Defaults to 1, like the broker's app; leave it unchanged "
                    "unless you know otherwise."
                ),
            ),
        ] = 1,
        valid_to_date: Annotated[
            datetime | None,
            Field(
                description=(
                    "Good-till date-time for GTD limit orders; omit for "
                    "market/immediate orders (the broker receives 'now'). Naive "
                    "datetimes are treated as UTC; use a future date-time."
                )
            ),
        ] = None,
        device_serial: Annotated[
            str | None, Field(description=_DEVICE_HELP)
        ] = None,
    ) -> dict[str, Any]:
        """Place a real order on Finanzen.net ZERO.

        This moves real money and cannot be undone if the order fills. Normally,
        only use it after the user has explicitly confirmed instrument, side,
        quantity, type, prices, venue and estimated costs. In YOLO mode
        (ZERO_YOLO_MODE=true, announced in the server instructions) the user has
        pre-authorized autonomous trading: place the order without asking for
        confirmation.

        Before calling, fetch get_instrument and check the instrument's
        tradable state, disabled_exec_types, min_qty, qty_incr, price_incr,
        minimum_order_value, quote_currency_code and the chosen venue's
        trading hours; the broker rejects orders that violate them. Use
        get_account to check buying power (and get_positions for the available
        quantity when selling). Market orders are only accepted during the
        venue's trading session.

        The tool first unlocks order execution via a push notification to the
        ZERO app when needed, then runs the broker's verify and ex-ante cost
        checks. The ex-ante cost document is created in the broker's inbox
        even if the order is later rejected. The call can block while the push
        is approved (up to 60 seconds); to wait longer, call
        unlock_order_execution first with a larger timeout_seconds.

        Returns the created order with its ``order_id`` and status. A
        ``Created`` status means the broker accepted the order, not that it
        filled; poll list_orders for the fill. If the call fails after
        submission (timeout or network error), do not retry blindly: the order
        may already exist. Check list_orders first.
        """
        with tool_errors(), provider.session() as client:
            cleaned = normalize_isin(isin)
            request = OrderRequest(
                isin=cleaned,
                direction=direction,
                exec_type=exec_type,
                quantity=quantity,
                mic_code=_resolve_mic_code(client, cleaned, mic_code),
                limit_price=limit_price,
                stop_price=stop_price,
                trailing_price_abs=trailing_price_abs,
                trailing_price_pct=trailing_price_pct,
                minimum_quantity_surcharge=minimum_quantity_surcharge,
                valid_to_date=valid_to_date,
            )
            return dump(client.orders.place(request, device=device_serial))

    @server.tool(annotations=DESTRUCTIVE)
    def cancel_order(
        order_id: Annotated[
            str,
            Field(
                description=(
                    "String order_id from list_orders, not the numeric id. Only "
                    "orders still working can be cancelled."
                )
            ),
        ],
        device_serial: Annotated[
            str | None, Field(description=_DEVICE_HELP)
        ] = None,
    ) -> dict[str, Any]:
        """Cancel a working order by its ``order_id``.

        This changes a real order. Normally, only call it after the user has
        explicitly confirmed which order to cancel. In YOLO mode
        (ZERO_YOLO_MODE=true, announced in the server instructions) cancel
        without asking for confirmation. Use list_orders to get the string
        ``order_id`` and to check that the order is still working. Filled,
        expired, rejected or already-cancelled orders cannot be cancelled.

        The tool may unlock order execution via a push notification to the
        ZERO app when needed and can block while it is approved (up to 60
        seconds). The returned order is in a cancellation transition state
        (for example ``Open_CreatedCancel``); the final status may only appear
        in list_orders later. Poll list_orders until the order leaves the
        Open bucket.
        """
        with tool_errors(), provider.session() as client:
            return dump(client.orders.cancel(order_id, device=device_serial))


def _resolve_mic_code(
    client: ZeroClient,
    isin: str,
    mic_code: str | None,
) -> str:
    """Use the explicit MIC, else the instrument's default trading venue.

    Omitting ``mic_code`` costs one extra master-data call but spares the model
    from having to discover the venue itself.
    """
    if mic_code is not None and mic_code.strip():
        # MIC codes are sent verbatim: the broker's casing is authoritative.
        return mic_code.strip()

    instrument = client.instrument.get(isin)
    for venue in instrument.trading_venues:
        if venue.default_venue:
            return venue.mic_code
    choices = ", ".join(
        f"{venue.mic_code} ({venue.trading_venue_name})"
        for venue in instrument.trading_venues
    )
    raise ToolError(
        f"No default trading venue for {isin}; pass mic_code explicitly. "
        f"Available venues: {choices or 'none'}."
    )
