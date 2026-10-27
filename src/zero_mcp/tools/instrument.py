"""Instrument slice: search, master data, market detail and chart series."""

from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field
from zero_api.instrument.models import ChartPeriod

from zero_mcp.client import ClientProvider
from zero_mcp.errors import tool_errors
from zero_mcp.serialization import dump
from zero_mcp.tools._annotations import READ_ONLY
from zero_mcp.tools._helpers import normalize_isin


def register_instrument_tools(server: MCPServer[Any], provider: ClientProvider) -> None:
    """Register the instrument tools on ``server``."""

    @server.tool(annotations=READ_ONLY)
    def search_instruments(
        query: Annotated[
            str,
            Field(min_length=1, description="Free text: name, WKN or ISIN."),
        ],
        size: Annotated[
            int,
            Field(
                ge=1,
                le=50,
                description="Maximum hits returned per asset-class bucket.",
            ),
        ] = 10,
    ) -> dict[str, Any]:
        """Search for tradable instruments by name, WKN or ISIN.

        Returns the hits plus per-asset-class match counts (stocks, ETF/ETC,
        funds, derivatives, crypto). Use an ISIN from the results with the
        other instrument and order tools.
        """
        with tool_errors(), provider.session() as client:
            return dump(client.instrument.search(query, size=size))

    @server.tool(annotations=READ_ONLY)
    def get_instrument(
        isin: Annotated[str, Field(description="ISIN, e.g. US0378331005.")],
    ) -> dict[str, Any]:
        """Return the instrument master record for an ISIN.

        Includes the asset class, trading state, quote currency, disabled
        execution types, order increments and limits, fees, and all trading
        venues with their MIC codes, trading hours and default-venue flag.
        Call this before place_order to check tradable, disabled_exec_types,
        min_qty, qty_incr, price_incr, minimum_order_value and
        quote_currency_code; use a venue's mic_code when placing an order.
        """
        with tool_errors(), provider.session() as client:
            return dump(client.instrument.get(normalize_isin(isin)))

    @server.tool(annotations=READ_ONLY)
    def get_instrument_detail(
        isin: Annotated[str, Field(description="ISIN, e.g. US0378331005.")],
    ) -> dict[str, Any]:
        """Return market data and fundamentals for an ISIN.

        Includes last/high/low, daily change, 52-week range, volume, currency,
        exchange and, where available, country, business branches, profile and
        dividend history. The available fields vary by asset class.
        """
        with tool_errors(), provider.session() as client:
            return dump(client.instrument.detail(normalize_isin(isin)))

    @server.tool(annotations=READ_ONLY)
    def get_chart(
        isin: Annotated[str, Field(description="ISIN, e.g. US0378331005.")],
        period: Annotated[
            ChartPeriod,
            Field(description="Chart scale; defaults to one year."),
        ] = ChartPeriod.ONE_YEAR,
    ) -> dict[str, Any]:
        """Return a historical price chart for an ISIN.

        The bars carry a date and a close; open/high/low/volume are present when
        the broker provides them for the chosen period. Intraday bars have a
        date-time label, daily and longer bars have a date label.
        """
        with tool_errors(), provider.session() as client:
            cleaned = normalize_isin(isin)
            bars = client.instrument.chart(cleaned, period=period)
            return {
                "isin": cleaned,
                "period": period.value,
                "bars": [
                    {
                        "date": bar.date,
                        "open": bar.open_,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ],
            }
