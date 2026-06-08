"""Shared API contract schemas between Gateway and Account Service."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ledger_common.money import MoneyAmount


class TransactionType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., alias="eventId", min_length=1, max_length=128)
    account_id: str = Field(..., alias="accountId", min_length=1, max_length=128)
    type: TransactionType
    amount: MoneyAmount
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    event_timestamp: datetime = Field(..., alias="eventTimestamp")
    metadata: dict[str, Any] | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(..., alias="eventId")
    account_id: str = Field(..., alias="accountId")
    type: TransactionType
    amount: MoneyAmount
    currency: str
    event_timestamp: datetime = Field(..., alias="eventTimestamp")
    metadata: dict[str, Any] | None = None
    status: str
    created_at: datetime = Field(..., alias="createdAt")


class ApplyTransactionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(..., alias="eventId")
    type: TransactionType
    amount: MoneyAmount
    currency: str
    event_timestamp: datetime = Field(..., alias="eventTimestamp")


class BalanceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str = Field(..., alias="accountId")
    balance: MoneyAmount
    currency: str


class TransactionRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(..., alias="eventId")
    type: TransactionType
    amount: MoneyAmount
    currency: str
    event_timestamp: datetime = Field(..., alias="eventTimestamp")
    applied_at: datetime = Field(..., alias="appliedAt")


class AccountDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str = Field(..., alias="accountId")
    balance: MoneyAmount
    currency: str
    transactions: list[TransactionRecord]


class ErrorResponse(BaseModel):
    detail: str
