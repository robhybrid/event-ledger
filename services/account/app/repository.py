from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ledger_common.money import MAX_AMOUNT
from services.account.app.models import Account, Transaction


class DuplicateTransactionError(Exception):
    pass


class AccountRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_transaction_by_event_id(self, event_id: str) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def ensure_account(self, account_id: str, currency: str) -> Account:
        result = await self._session.execute(
            select(Account).where(Account.account_id == account_id)
        )
        account = result.scalar_one_or_none()
        if account:
            if account.currency != currency:
                raise ValueError(
                    f"Currency mismatch for account {account_id}: "
                    f"expected {account.currency}, got {currency}"
                )
            return account

        account = Account(account_id=account_id, currency=currency)
        self._session.add(account)
        await self._session.flush()
        return account

    async def apply_transaction(
        self,
        *,
        event_id: str,
        account_id: str,
        tx_type: str,
        amount: Decimal,
        currency: str,
        event_timestamp: datetime,
    ) -> Transaction:
        existing = await self.get_transaction_by_event_id(event_id)
        if existing:
            raise DuplicateTransactionError(event_id)

        await self.ensure_account(account_id, currency)

        tx = Transaction(
            event_id=event_id,
            account_id=account_id,
            type=tx_type,
            amount=amount,
            currency=currency,
            event_timestamp=event_timestamp,
        )
        self._session.add(tx)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateTransactionError(event_id) from exc
        await self._session.refresh(tx)
        return tx

    async def compute_balance(self, account_id: str) -> tuple[Decimal, str] | None:
        result = await self._session.execute(
            select(Account).where(Account.account_id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            return None

        result = await self._session.execute(
            select(Transaction).where(Transaction.account_id == account_id)
        )
        transactions = result.scalars().all()

        balance = Decimal("0")
        for tx in transactions:
            if tx.type == "CREDIT":
                new_balance = balance + tx.amount
            else:
                new_balance = balance - tx.amount
            if abs(new_balance) > MAX_AMOUNT:
                raise OverflowError("Balance would exceed maximum allowed value")
            balance = new_balance

        return balance, account.currency

    async def list_transactions(
        self, account_id: str, limit: int = 50
    ) -> list[Transaction]:
        result = await self._session.execute(
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.event_timestamp.asc(), Transaction.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
