import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ledger_common.logging import get_logger
from ledger_common.schemas import (
    ApplyTransactionRequest,
    ErrorResponse,
    EventCreate,
    EventResponse,
    TransactionType,
)
from ledger_common.tracing import get_trace_id
from services.gateway.app.account_client import (
    AccountServiceClient,
    AccountServiceError,
    AccountServiceUnavailable,
)
from services.gateway.app.database import get_db
from services.gateway.app.limiter import limiter
from services.gateway.app.repository import EventRepository

logger = get_logger(__name__)
router = APIRouter()


def get_account_client() -> AccountServiceClient:
    return AccountServiceClient()


def _to_response(record) -> EventResponse:
    metadata = json.loads(record.metadata_json) if record.metadata_json else None
    return EventResponse(
        eventId=record.event_id,
        accountId=record.account_id,
        type=TransactionType(record.type),
        amount=record.amount,
        currency=record.currency,
        eventTimestamp=record.event_timestamp,
        metadata=metadata,
        status=record.status,
        createdAt=record.created_at,
    )


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": EventResponse, "description": "Duplicate event (idempotent)"},
        503: {"model": ErrorResponse},
    },
)
@limiter.limit("100/minute")
async def submit_event(
    request: Request,
    body: EventCreate,
    db: AsyncSession = Depends(get_db),
    client: AccountServiceClient = Depends(get_account_client),
):
    log = logger.bind(trace_id=get_trace_id(), event_id=body.event_id)
    repo = EventRepository(db)

    existing = await repo.get_by_id(body.event_id)
    if existing:
        log.info("duplicate_event_returned")
        return JSONResponse(
            content=_to_response(existing).model_dump(mode="json", by_alias=True),
            status_code=status.HTTP_200_OK,
        )

    apply_request = ApplyTransactionRequest(
        eventId=body.event_id,
        type=body.type,
        amount=body.amount,
        currency=body.currency,
        eventTimestamp=body.event_timestamp,
    )

    event_status = "APPLIED"
    try:
        await client.apply_transaction(body.account_id, apply_request)
    except AccountServiceUnavailable as exc:
        log.warning("account_service_unavailable", error=str(exc), circuit_open=exc.circuit_open)
        # Store event locally and queue for later processing (graceful degradation + async fallback)
        record = await repo.create_event(
            event_id=body.event_id,
            account_id=body.account_id,
            tx_type=body.type.value,
            amount=body.amount,
            currency=body.currency,
            event_timestamp=body.event_timestamp,
            metadata=body.metadata,
            status="QUEUED",
        )
        await repo.enqueue_pending(
            body.event_id,
            body.account_id,
            body.model_dump(mode="json", by_alias=True),
        )
        from ledger_common.metrics import QUEUED_EVENTS

        QUEUED_EVENTS.labels(status="enqueued").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account Service is unavailable; event stored and queued for processing",
        ) from exc
    except AccountServiceError as exc:
        log.warning("account_service_error", status=exc.status_code, detail=exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    record = await repo.create_event(
        event_id=body.event_id,
        account_id=body.account_id,
        tx_type=body.type.value,
        amount=body.amount,
        currency=body.currency,
        event_timestamp=body.event_timestamp,
        metadata=body.metadata,
        status=event_status,
    )
    log.info("event_created", account_id=body.account_id)
    return _to_response(record)


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    logger.info("event_requested", trace_id=get_trace_id(), event_id=event_id)
    repo = EventRepository(db)
    record = await repo.get_by_id(event_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return _to_response(record)


@router.get("/events", response_model=list[EventResponse])
async def list_events(
    account: str = Query(..., alias="account", min_length=1),
    db: AsyncSession = Depends(get_db),
):
    logger.info("events_list_requested", trace_id=get_trace_id(), account_id=account)
    repo = EventRepository(db)
    records = await repo.list_by_account(account)
    return [_to_response(r) for r in records]


@router.get("/accounts/{account_id}/balance")
async def get_balance_proxy(
    account_id: str,
    client: AccountServiceClient = Depends(get_account_client),
):
    logger.info("balance_proxy_requested", trace_id=get_trace_id(), account_id=account_id)
    try:
        return await client.get_balance(account_id)
    except AccountServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account Service is unreachable; balance unavailable",
        ) from exc
    except AccountServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
