import httpx
import pytest
import respx

from ledger_common.schemas import ApplyTransactionRequest, TransactionType
from services.gateway.app.account_client import (
    AccountServiceClient,
    AccountServiceUnavailable,
    circuit_breaker,
)


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    circuit_breaker.reset()
    yield
    circuit_breaker.reset()


@pytest.mark.asyncio
@respx.mock
async def test_apply_transaction_success():
    respx.post("http://account:8001/accounts/acct-1/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "eventId": "evt-1",
                "type": "CREDIT",
                "amount": "100.0000",
                "currency": "USD",
                "eventTimestamp": "2026-05-15T14:02:11Z",
                "appliedAt": "2026-05-15T14:02:12Z",
            },
        )
    )
    client = AccountServiceClient("http://account:8001")
    request = ApplyTransactionRequest(
        eventId="evt-1",
        type=TransactionType.CREDIT,
        amount="100.00",
        currency="USD",
        eventTimestamp="2026-05-15T14:02:11Z",
    )
    result = await client.apply_transaction("acct-1", request)
    assert result.event_id == "evt-1"


@pytest.mark.asyncio
@respx.mock
async def test_circuit_breaker_opens_on_repeated_failures():
    respx.post("http://account:8001/accounts/acct-1/transactions").mock(
        return_value=httpx.Response(503, json={"detail": "down"})
    )
    client = AccountServiceClient("http://account:8001")
    request = ApplyTransactionRequest(
        eventId="evt-1",
        type=TransactionType.CREDIT,
        amount="100.00",
        currency="USD",
        eventTimestamp="2026-05-15T14:02:11Z",
    )

    for _ in range(5):
        with pytest.raises(AccountServiceUnavailable):
            await client.apply_transaction("acct-1", request)

    with pytest.raises(AccountServiceUnavailable) as exc:
        await client.apply_transaction("acct-1", request)
    assert exc.value.circuit_open is True
