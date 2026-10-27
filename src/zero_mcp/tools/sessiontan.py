"""2FA order-execution slice: session status, devices and the app-push unlock."""

from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from zero_mcp.client import ClientProvider
from zero_mcp.errors import tool_errors
from zero_mcp.serialization import dump_many
from zero_mcp.tools._annotations import ADDITIVE, READ_ONLY


def register_sessiontan_tools(
    server: MCPServer[Any],
    provider: ClientProvider,
    *,
    read_only: bool,
) -> None:
    """Register the 2FA tools on ``server``; unlock only when allowed."""

    @server.tool(annotations=READ_ONLY)
    def get_session_status() -> dict[str, Any]:
        """Report whether this ZERO session is unlocked for order execution.

        Read-only tools work regardless; placing or cancelling orders requires
        an unlocked session, which is obtained through the ZERO app push.
        """
        with tool_errors(), provider.session() as client:
            return {"authorized": client.sessiontan.is_authorized()}

    @server.tool(annotations=READ_ONLY)
    def list_enrolled_devices() -> dict[str, Any]:
        """List the devices that can receive the ZERO 2FA push.

        Each device's ``serial`` can be passed to the order tools or to
        ``unlock_order_execution`` when several devices are enrolled.
        """
        with tool_errors(), provider.session() as client:
            devices = client.sessiontan.enrolled_devices()
            return {
                "count": len(devices),
                "devices": dump_many(devices),
            }

    if read_only:
        return

    @server.tool(annotations=ADDITIVE)
    def unlock_order_execution(
        device_serial: Annotated[
            str | None,
            Field(
                description=(
                    "Device serial from list_enrolled_devices. Omit to use "
                    "ZERO_DEFAULT_DEVICE or the only enrolled device."
                )
            ),
        ] = None,
        timeout_seconds: Annotated[
            int,
            Field(
                ge=5,
                le=300,
                description="How long to wait for the user to approve the push.",
            ),
        ] = 60,
    ) -> dict[str, Any]:
        """Unlock order execution via a push notification to the ZERO app.

        The user must approve the notification on the paired phone. This call
        blocks until approval or the timeout, so the MCP client's tool timeout
        must be at least ``timeout_seconds``. If the session is already
        unlocked, no push is sent.
        """
        with tool_errors(), provider.session() as client:
            if client.sessiontan.is_authorized():
                return {"unlocked": True, "already_authorized": True}
            client.sessiontan.unlock(
                device_serial or None,
                timeout=float(timeout_seconds),
            )
            return {"unlocked": True, "already_authorized": False}
