"""Mapping of broker/client failures to actionable MCP tool errors.

The MCP SDK turns :class:`~mcp.server.mcpserver.exceptions.ToolError` into an
``isError`` result whose text is shown to the model. Anything else becomes a
generic "Error executing tool" message, so the failures users actually hit
(missing configuration, bad credentials, 2FA timeouts, broker rejections,
network trouble) are translated explicitly here.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import NoReturn

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError
from zero_api.core.exceptions import (
    AuthenticationError,
    BrokerApiError,
    TwoFactorError,
    ZeroApiError,
)

from zero_mcp.config import ConfigurationError


@contextmanager
def tool_errors() -> Iterator[None]:
    """Translate known failures inside the ``with`` block into ``ToolError``.

    ``ToolError`` raised by a tool itself passes through unchanged. Unknown
    exceptions are deliberately not caught, so programming errors stay visible
    as unexpected tool failures.
    """
    try:
        yield
    except ToolError:
        raise
    except ConfigurationError as exc:
        raise ToolError(f"Finanzen.net ZERO is not configured: {exc}.") from exc
    except AuthenticationError as exc:
        raise ToolError(
            "Login to Finanzen.net ZERO failed: "
            f"{exc}. Check ZERO_USERNAME and ZERO_PASSWORD, and make sure the "
            "system clock is accurate (the login signs a UTC timestamp)."
        ) from exc
    except TwoFactorError as exc:
        raise ToolError(
            f"Finanzen.net ZERO 2FA failed: {exc}. Approve the push notification "
            "in the paired ZERO app, then retry."
        ) from exc
    except BrokerApiError as exc:
        _raise_broker_error(exc)
    except ZeroApiError as exc:
        raise ToolError(f"Finanzen.net ZERO API error: {exc}") from exc
    except ValidationError as exc:
        raise ToolError(
            "Unexpected response shape from Finanzen.net ZERO (the broker's API "
            f"may have changed): {exc}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Network error talking to Finanzen.net ZERO: {exc}") from exc
    except ValueError as exc:
        raise ToolError(f"Unexpected response from Finanzen.net ZERO: {exc}") from exc


def _raise_broker_error(exc: BrokerApiError) -> NoReturn:
    """Format the broker's apiError body, including per-field validation errors."""
    details = [exc.message]
    if exc.error_code:
        details.append(f"error code: {exc.error_code}")
    if exc.errors:
        details.append("details: " + "; ".join(exc.errors))
    raise ToolError(
        f"Finanzen.net ZERO rejected the request (HTTP {exc.status}): "
        + " | ".join(details)
    ) from exc
