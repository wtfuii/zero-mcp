"""Shared offline fixtures: no test ever touches the broker or the network."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import cast
from unittest.mock import Mock

import pytest
from zero_api import ZeroClient
from zero_api.account.models import MoneyTransactionAccount

from zero_mcp.client import ClientProvider


class FakeProvider:
    """A :class:`ClientProvider` handing out a mock client."""

    def __init__(self, client: ZeroClient) -> None:
        self._client = client

    def session(self) -> AbstractContextManager[ZeroClient]:
        return self._session()

    @contextmanager
    def _session(self) -> Iterator[ZeroClient]:
        yield self._client


@pytest.fixture(autouse=True)
def clean_zero_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the developer's real ZERO_* variables out of the tests."""
    for name in (
        "ZERO_USERNAME",
        "ZERO_PASSWORD",
        "ZERO_DEFAULT_DEVICE",
        "ZERO_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def broker_mock() -> Mock:
    """A dynamic mock; tests configure only the slices they exercise."""
    return Mock()


@pytest.fixture
def provider(broker_mock: Mock) -> ClientProvider:
    return FakeProvider(cast(ZeroClient, broker_mock))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def account() -> MoneyTransactionAccount:
    """A realistic cash-account record (all required fields populated)."""
    return MoneyTransactionAccount.model_validate(
        {
            "id": 42,
            "accountNr": "0001234567",
            "customerId": "customer-1",
            "intradayAmount": "0.00",
            "intradayTimestamp": "2026-10-26T10:00:00Z",
            "buyingPower": "1000.50",
            "buyingPowerTimestamp": "2026-10-26T10:00:00Z",
            "transferPower": "950.25",
            "transferPowerTimestamp": "2026-10-26T10:00:00Z",
            "lastSaldoImportDate": "2026-10-25",
            "lastImportedSaldo": "900.00",
            "lastImportMatch": None,
            "accountIban": "DE02120300000000202051",
            "creditAmount": "0.00",
            "creditAmountTimestamp": "2026-10-26T09:00:00Z",
            "closingPeriod": "monthly",
            "nextClosingDate": "2026-11-01",
            "debitInterest": "0.00",
            "depotId": 7,
            "buyingPowerWithoutCredit": "1000.50",
            "transferPowerWithoutCredit": "950.25",
            "overdrawn": False,
            "transferPowerBlocked": "0.00",
        }
    )
