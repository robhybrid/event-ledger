from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ledger_common.logging import get_logger
from ledger_common.schemas import (
    AccountDetailResponse,
    ApplyTransactionRequest,
    BalanceResponse,
    ErrorResponse,
    TransactionRecord,
    TransactionType,
)
from ledger_common.tracing import get_trace_id
from services.account.app.database import get_db
from services.account.app.repository import AccountRepository, DuplicateTransactionError

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/accounts/{account_id}/transactions",
    response_model=TransactionRecord,
    responses={409: {"model": ErrorResponse}},
)
async def apply_transaction(
    account_id: str,
    body: ApplyTransactionRequest,
    db: AsyncSession = Depends(get_db),
):
    log = logger.bind(trace_id=get_trace_id(), account_id=account_id, event_id=body.event_id)
    repo = AccountRepository(db)

    try:
        tx = await repo.apply_transaction(
            event_id=body.event_id,
            account_id=account_id,
            tx_type=body.type.value,
            amount=body.amount,
            currency=body.currency,
            event_timestamp=body.event_timestamp,
        )
    except DuplicateTransactionError:
        existing = await repo.get_transaction_by_event_id(body.event_id)
        log.info("duplicate_transaction_ignored")
        return TransactionRecord(
            eventId=existing.event_id,
            type=TransactionType(existing.type),
            amount=existing.amount,
            currency=existing.currency,
            eventTimestamp=existing.event_timestamp,
            appliedAt=existing.applied_at,
        )
    except ValueError as exc:
        log.warning("transaction_validation_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OverflowError as exc:
        log.error("balance_overflow", error=str(exc))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    log.info("transaction_applied", type=body.type.value, amount=str(body.amount))
    return TransactionRecord(
        eventId=tx.event_id,
        type=TransactionType(tx.type),
        amount=tx.amount,
        currency=tx.currency,
        eventTimestamp=tx.event_timestamp,
        appliedAt=tx.applied_at,
    )


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
async def get_balance(account_id: str, db: AsyncSession = Depends(get_db)):
    logger.info("balance_requested", trace_id=get_trace_id(), account_id=account_id)
    repo = AccountRepository(db)
    result = await repo.compute_balance(account_id)
    if result is None:
        return BalanceResponse(accountId=account_id, balance=0, currency="USD")
    balance, currency = result
    return BalanceResponse(accountId=account_id, balance=balance, currency=currency)


@router.get("/accounts/{account_id}", response_model=AccountDetailResponse)
async def get_account(account_id: str, db: AsyncSession = Depends(get_db)):
    logger.info("account_detail_requested", trace_id=get_trace_id(), account_id=account_id)
    repo = AccountRepository(db)
    result = await repo.compute_balance(account_id)
    transactions = await repo.list_transactions(account_id)

    if result is None:
        balance, currency = 0, "USD"
    else:
        balance, currency = result

    return AccountDetailResponse(
        accountId=account_id,
        balance=balance,
        currency=currency,
        transactions=[
            TransactionRecord(
                eventId=tx.event_id,
                type=TransactionType(tx.type),
                amount=tx.amount,
                currency=tx.currency,
                eventTimestamp=tx.event_timestamp,
                appliedAt=tx.applied_at,
            )
            for tx in transactions
        ],
    )
