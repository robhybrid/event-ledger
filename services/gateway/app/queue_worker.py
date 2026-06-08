"""Background worker to process queued events when Account Service recovers."""

import asyncio
import json

from ledger_common.logging import get_logger
from ledger_common.metrics import QUEUED_EVENTS
from ledger_common.schemas import ApplyTransactionRequest, TransactionType
from services.gateway.app.account_client import AccountServiceClient, AccountServiceUnavailable
from services.gateway.app.config import settings
from services.gateway.app.database import SessionLocal
from services.gateway.app.repository import EventRepository

logger = get_logger(__name__)


async def process_pending_queue(client: AccountServiceClient | None = None) -> int:
    """Attempt to apply all pending events. Returns count of successfully processed."""
    client = client or AccountServiceClient()
    processed = 0

    async with SessionLocal() as session:
        repo = EventRepository(session)
        pending_events = await repo.list_pending()

        for pending in pending_events:
            payload = json.loads(pending.payload_json)
            request = ApplyTransactionRequest(
                eventId=payload["eventId"],
                type=TransactionType(payload["type"]),
                amount=payload["amount"],
                currency=payload["currency"],
                eventTimestamp=payload["eventTimestamp"],
            )
            try:
                await client.apply_transaction(pending.account_id, request)
                await repo.remove_pending(pending)
                event = await repo.get_by_id(pending.event_id)
                if event and event.status == "QUEUED":
                    event.status = "APPLIED"
                    await session.commit()
                processed += 1
                QUEUED_EVENTS.labels(status="processed").inc()
                logger.info("queued_event_processed", event_id=pending.event_id)
            except AccountServiceUnavailable:
                await repo.increment_pending_attempt(pending)
                logger.warning("queued_event_retry_later", event_id=pending.event_id)
                break
            except Exception as exc:
                await repo.increment_pending_attempt(pending)
                QUEUED_EVENTS.labels(status="failed").inc()
                logger.error("queued_event_failed", event_id=pending.event_id, error=str(exc))

    return processed


async def queue_worker_loop(stop_event: asyncio.Event) -> None:
    client = AccountServiceClient()
    logger.info("queue_worker_started")
    while not stop_event.is_set():
        if settings.queue_processing_enabled:
            healthy = await client.health_check()
            if healthy:
                count = await process_pending_queue(client)
                if count:
                    logger.info("queue_batch_processed", count=count)
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.queue_poll_interval_seconds,
            )
        except asyncio.TimeoutError:
            pass
    logger.info("queue_worker_stopped")
