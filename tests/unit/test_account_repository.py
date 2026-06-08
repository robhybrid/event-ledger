from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.account.app.repository import AccountRepository, DuplicateTransactionError


@pytest.mark.asyncio
async def test_apply_transaction_and_balance(account_db):
    repo = AccountRepository(account_db)
    ts = datetime(2026, 5, 15, 14, 2, 11, tzinfo=timezone.utc)

    await repo.apply_transaction(
        event_id="evt-1",
        account_id="acct-1",
        tx_type="CREDIT",
        amount=Decimal("100.0000"),
        currency="USD",
        event_timestamp=ts,
    )
    await repo.apply_transaction(
        event_id="evt-2",
        account_id="acct-1",
        tx_type="DEBIT",
        amount=Decimal("30.0000"),
        currency="USD",
        event_timestamp=ts,
    )

    balance, currency = await repo.compute_balance("acct-1")
    assert balance == Decimal("70.0000")
    assert currency == "USD"


@pytest.mark.asyncio
async def test_idempotent_transaction(account_db):
    repo = AccountRepository(account_db)
    ts = datetime(2026, 5, 15, 14, 2, 11, tzinfo=timezone.utc)

    await repo.apply_transaction(
        event_id="evt-dup",
        account_id="acct-1",
        tx_type="CREDIT",
        amount=Decimal("50.0000"),
        currency="USD",
        event_timestamp=ts,
    )
    with pytest.raises(DuplicateTransactionError):
        await repo.apply_transaction(
            event_id="evt-dup",
            account_id="acct-1",
            tx_type="CREDIT",
            amount=Decimal("50.0000"),
            currency="USD",
            event_timestamp=ts,
        )

    balance, _ = await repo.compute_balance("acct-1")
    assert balance == Decimal("50.0000")


@pytest.mark.asyncio
async def test_out_of_order_balance_correct(account_db):
    repo = AccountRepository(account_db)

    await repo.apply_transaction(
        event_id="evt-later",
        account_id="acct-1",
        tx_type="CREDIT",
        amount=Decimal("200.0000"),
        currency="USD",
        event_timestamp=datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc),
    )
    await repo.apply_transaction(
        event_id="evt-earlier",
        account_id="acct-1",
        tx_type="DEBIT",
        amount=Decimal("50.0000"),
        currency="USD",
        event_timestamp=datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc),
    )

    balance, _ = await repo.compute_balance("acct-1")
    assert balance == Decimal("150.0000")

    txs = await repo.list_transactions("acct-1")
    assert [tx.event_id for tx in txs] == ["evt-earlier", "evt-later"]
