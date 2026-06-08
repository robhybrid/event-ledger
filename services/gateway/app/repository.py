import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.gateway.app.models import EventRecord, PendingEvent


class EventRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, event_id: str) -> EventRecord | None:
        result = await self._session.execute(
            select(EventRecord).where(EventRecord.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def create_event(
        self,
        *,
        event_id: str,
        account_id: str,
        tx_type: str,
        amount: Decimal,
        currency: str,
        event_timestamp: datetime,
        metadata: dict | None,
        status: str,
    ) -> EventRecord:
        record = EventRecord(
            event_id=event_id,
            account_id=account_id,
            type=tx_type,
            amount=amount,
            currency=currency,
            event_timestamp=event_timestamp,
            metadata_json=json.dumps(metadata) if metadata else None,
            status=status,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def list_by_account(self, account_id: str) -> list[EventRecord]:
        result = await self._session.execute(
            select(EventRecord)
            .where(EventRecord.account_id == account_id)
            .order_by(EventRecord.event_timestamp.asc(), EventRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def enqueue_pending(self, event_id: str, account_id: str, payload: dict) -> PendingEvent:
        pending = PendingEvent(
            event_id=event_id,
            account_id=account_id,
            payload_json=json.dumps(payload),
        )
        self._session.add(pending)
        await self._session.commit()
        await self._session.refresh(pending)
        return pending

    async def list_pending(self, limit: int = 100) -> list[PendingEvent]:
        result = await self._session.execute(
            select(PendingEvent).order_by(PendingEvent.created_at.asc()).limit(limit)
        )
        return list(result.scalars().all())

    async def remove_pending(self, pending: PendingEvent) -> None:
        await self._session.delete(pending)
        await self._session.commit()

    async def increment_pending_attempt(self, pending: PendingEvent) -> None:
        pending.attempts += 1
        pending.last_attempt_at = datetime.now(__import__("datetime").timezone.utc)
        await self._session.commit()
