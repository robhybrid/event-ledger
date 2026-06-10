"""Contract tests verifying Gateway ↔ Account Service API schema alignment."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

CONTRACT_DIR = Path(__file__).parent / "schemas"


@pytest.fixture
def apply_transaction_schema():
    return json.loads((CONTRACT_DIR / "apply_transaction.json").read_text())


@pytest.fixture
def event_payload_schema():
    return json.loads((CONTRACT_DIR / "event_payload.json").read_text())


def test_gateway_event_payload_matches_contract(event_payload_schema):
    from ledger_common.schemas import EventCreate

    event = EventCreate.model_validate(
        {
            "eventId": "evt-001",
            "accountId": "acct-123",
            "type": "CREDIT",
            "amount": "150.00",
            "currency": "USD",
            "eventTimestamp": "2026-05-15T14:02:11Z",
            "metadata": {"source": "batch"},
        }
    )
    payload = event.model_dump(mode="json", by_alias=True)
    validator = Draft7Validator(event_payload_schema)
    errors = list(validator.iter_errors(payload))
    assert not errors, [e.message for e in errors]


def test_gateway_to_account_request_matches_contract(apply_transaction_schema):
    from ledger_common.schemas import ApplyTransactionRequest, EventCreate

    event = EventCreate.model_validate(
        {
            "eventId": "evt-001",
            "accountId": "acct-123",
            "type": "DEBIT",
            "amount": "25.50",
            "currency": "USD",
            "eventTimestamp": "2026-05-15T14:02:11Z",
        }
    )
    request = ApplyTransactionRequest(
        eventId=event.event_id,
        type=event.type,
        amount=event.amount,
        currency=event.currency,
        eventTimestamp=event.event_timestamp,
    )
    payload = request.model_dump(mode="json", by_alias=True)
    validator = Draft7Validator(apply_transaction_schema)
    errors = list(validator.iter_errors(payload))
    assert not errors, [e.message for e in errors]
