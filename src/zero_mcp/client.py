"""Lazy, serialized access to the one :class:`zero_api.ZeroClient` used by all tools.

The MCP server must answer ``tools/list`` without credentials and without a
network call, so the client (and therefore the broker login) is created on the
first tool call. ``ZeroClient`` itself logs in lazily on its first API call.

MCP hosts may issue tool calls concurrently and the client keeps mutable
in-memory session state (cookies, refresh, 2FA unlock), so every broker call
runs while holding one process-wide lock. That trades parallelism for a
session that cannot be logged in twice or refreshed concurrently.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from threading import RLock
from typing import Protocol

from zero_api import ZeroClient

from zero_mcp.config import Settings


class ClientProvider(Protocol):
    """Supplies the shared broker client; replaced by a fake in tests."""

    def session(self) -> AbstractContextManager[ZeroClient]:
        """Yield the client while holding the broker-call lock."""
        ...


class ZeroClientProvider:
    """Creates, caches and serializes access to the broker client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: ZeroClient | None = None
        self._lock = RLock()

    @contextmanager
    def session(self) -> Iterator[ZeroClient]:
        """Yield the shared client, constructing it on first use.

        The lock is held for the whole broker interaction, so concurrent tool
        calls cannot interleave a login, refresh, unlock or order flow.
        """
        with self._lock:
            if self._client is None:
                username, password = self._settings.require_credentials()
                self._client = ZeroClient(
                    email=username,
                    password=password,
                    default_device=self._settings.default_device,
                )
            yield self._client
