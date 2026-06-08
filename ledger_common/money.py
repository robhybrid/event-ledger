"""Financial amount handling — Decimal only, no floats."""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

# Max safe amount: 10^15 with 4 decimal places (well within Decimal precision)
MAX_AMOUNT = Decimal("999999999999999.9999")
MIN_AMOUNT = Decimal("0.0001")


def parse_amount(value: object) -> Decimal:
    """Parse and validate a monetary amount from string or int (never float)."""
    if isinstance(value, float):
        raise ValueError("Floating-point amounts are not permitted; use a string or integer")
    if isinstance(value, bool):
        raise ValueError("Invalid amount type")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid amount: {value}") from exc

    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    if amount > MAX_AMOUNT:
        raise ValueError(f"Amount exceeds maximum allowed value ({MAX_AMOUNT})")
    if amount < MIN_AMOUNT:
        raise ValueError(f"Amount must be at least {MIN_AMOUNT}")

    # Normalize to 4 decimal places for consistency
    return amount.quantize(Decimal("0.0001"))


def serialize_amount(value: Decimal) -> str:
    return format(value, "f")


MoneyAmount = Annotated[
    Decimal,
    BeforeValidator(parse_amount),
    PlainSerializer(serialize_amount, return_type=str),
]
