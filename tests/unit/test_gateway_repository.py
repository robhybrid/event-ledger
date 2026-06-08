from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.gateway.app.repository import EventRepository


@pytest.mark.asyncio
async def test_events_ordered_by_timestamp(gateway_db):
    repo = EventRepository(gateway_db)

    await repo.create_event(
        event_id="evt-2",
        account_id="acct-1",
        tx_type="CREDIT",
        amount=Decimal("100"),
        currency="USD",
        event_timestamp=datetime(2026, 5, 16, tzinfo=timezone.utc),
        metadata=None,
        status="APPLIED",
    )
    await repo.create_event(
        event_id="evt-1",
        account_id="acct-1",
        tx_type="CREDIT",
        amount=Decimal("50"),
        currency="USD",
        event_timestamp=datetime(2026, 5, 15, tzinfo=timezone.utc),
        metadata=None,
        status="APPLIED",
    )

    events = await repo.list_by_account("acct-1")
    assert [e.event_id for e in events] == ["evt-1", "evt-2"]
