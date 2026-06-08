import pytest
from pydantic import ValidationError

from ledger_common.schemas import EventCreate


def test_rejects_missing_fields():
    with pytest.raises(ValidationError):
        EventCreate.model_validate({"eventId": "evt-1"})


def test_rejects_invalid_type():
    with pytest.raises(ValidationError):
        EventCreate.model_validate(
            {
                "eventId": "evt-1",
                "accountId": "acct-1",
                "type": "TRANSFER",
                "amount": "10.00",
                "currency": "USD",
                "eventTimestamp": "2026-05-15T14:02:11Z",
            }
        )


def test_rejects_float_amount():
    with pytest.raises(ValidationError):
        EventCreate.model_validate(
            {
                "eventId": "evt-1",
                "accountId": "acct-1",
                "type": "CREDIT",
                "amount": 10.5,
                "currency": "USD",
                "eventTimestamp": "2026-05-15T14:02:11Z",
            }
        )
