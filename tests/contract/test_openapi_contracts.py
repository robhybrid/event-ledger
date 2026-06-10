"""Verify OpenAPI specs expose shared contract schemas."""

import pytest

from ledger_common.schemas import (
    ApplyTransactionRequest,
    BalanceResponse,
    EventCreate,
    EventResponse,
    TransactionRecord,
)


@pytest.mark.parametrize(
    "schema_name",
    [
        "EventCreate",
        "EventResponse",
        "ApplyTransactionRequest",
        "TransactionRecord",
        "BalanceResponse",
        "AccountDetailResponse",
        "ErrorResponse",
    ],
)
def test_gateway_openapi_includes_contract_schema(schema_name):
    from services.gateway.app.main import app

    components = app.openapi()["components"]["schemas"]
    assert schema_name in components, f"{schema_name} missing from Gateway OpenAPI"


@pytest.mark.parametrize(
    "schema_name",
    [
        "ApplyTransactionRequest",
        "TransactionRecord",
        "BalanceResponse",
        "AccountDetailResponse",
        "ErrorResponse",
    ],
)
def test_account_openapi_includes_contract_schema(schema_name):
    from services.account.app.main import app

    components = app.openapi()["components"]["schemas"]
    assert schema_name in components, f"{schema_name} missing from Account OpenAPI"


def test_contract_models_include_examples():
    from ledger_common.schemas import AccountDetailResponse, ErrorResponse

    for model in (
        EventCreate,
        EventResponse,
        ApplyTransactionRequest,
        TransactionRecord,
        BalanceResponse,
        AccountDetailResponse,
        ErrorResponse,
    ):
        schema = model.model_json_schema()
        assert "examples" in schema, f"{model.__name__} has no OpenAPI examples"
