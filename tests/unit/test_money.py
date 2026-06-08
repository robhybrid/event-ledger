from decimal import Decimal

import pytest

from ledger_common.money import MAX_AMOUNT, MIN_AMOUNT, parse_amount


class TestParseAmount:
    def test_accepts_string(self):
        assert parse_amount("150.00") == Decimal("150.0000")

    def test_accepts_integer(self):
        assert parse_amount(100) == Decimal("100.0000")

    def test_rejects_float(self):
        with pytest.raises(ValueError, match="Floating-point"):
            parse_amount(150.00)

    def test_rejects_zero(self):
        with pytest.raises(ValueError, match="greater than zero"):
            parse_amount("0")

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="greater than zero"):
            parse_amount("-10.00")

    def test_rejects_overflow(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            parse_amount(str(MAX_AMOUNT + Decimal("0.0001")))

    def test_rejects_too_small(self):
        with pytest.raises(ValueError, match="at least"):
            parse_amount("0.00001")

    def test_normalizes_precision(self):
        assert parse_amount("10.5") == Decimal("10.5000")
