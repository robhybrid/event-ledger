"""Pact consumer tests: Event Gateway expectations of Account Service."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pact import Pact, match

from ledger_common.schemas import ApplyTransactionRequest, TransactionType
from services.gateway.app.account_client import AccountServiceClient
from tests.contract.conftest import PACT_ACCOUNT_ID, PACT_EVENT_ID, PACT_TIMESTAMP

APPLY_BODY = {
    "eventId": PACT_EVENT_ID,
    "type": "CREDIT",
    "amount": "100.0000",
    "currency": "USD",
    "eventTimestamp": "2026-05-15T14:02:11Z",
}

TRANSACTION_RESPONSE = {
    "eventId": PACT_EVENT_ID,
    "type": "CREDIT",
    "amount": match.regex("100.0000", regex=r"^\d+\.\d{4}$"),
    "currency": "USD",
    "eventTimestamp": match.regex(
        "2026-05-15T14:02:11Z",
        regex=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    ),
    "appliedAt": match.regex(
        "2026-05-15T14:02:12Z",
        regex=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    ),
}

BALANCE_RESPONSE = {
    "accountId": PACT_ACCOUNT_ID,
    "balance": match.regex("100.0000", regex=r"^\d+\.\d{4}$"),
    "currency": "USD",
}


@pytest.mark.asyncio
async def test_apply_transaction_contract(pact_dir):
    pact = Pact("event-gateway", "account-service")

    (
        pact.upon_receiving("a request to apply a credit transaction")
        .given("account has no prior transactions")
        .with_request("POST", f"/accounts/{PACT_ACCOUNT_ID}/transactions")
        .with_header("Content-Type", "application/json")
        .with_body(APPLY_BODY)
        .will_respond_with(200)
        .with_header("Content-Type", "application/json")
        .with_body(TRANSACTION_RESPONSE)
    )

    with pact.serve() as server:
        client = AccountServiceClient(base_url=str(server.url))
        payload = ApplyTransactionRequest(
            eventId=PACT_EVENT_ID,
            type=TransactionType.CREDIT,
            amount=Decimal("100.0000"),
            currency="USD",
            eventTimestamp=PACT_TIMESTAMP,
        )
        result = await client.apply_transaction(PACT_ACCOUNT_ID, payload)

    assert result.event_id == PACT_EVENT_ID
    assert result.type == TransactionType.CREDIT
    pact.write_file(pact_dir, overwrite=True)


@pytest.mark.asyncio
async def test_get_balance_contract(pact_dir):
    pact = Pact("event-gateway", "account-service")

    (
        pact.upon_receiving("a request for account balance")
        .given("account has a credit balance")
        .with_request("GET", f"/accounts/{PACT_ACCOUNT_ID}/balance")
        .will_respond_with(200)
        .with_header("Content-Type", "application/json")
        .with_body(BALANCE_RESPONSE)
    )

    with pact.serve() as server:
        client = AccountServiceClient(base_url=str(server.url))
        balance = await client.get_balance(PACT_ACCOUNT_ID)

    assert balance.account_id == PACT_ACCOUNT_ID
    assert balance.currency == "USD"
    pact.write_file(pact_dir, overwrite=False)
