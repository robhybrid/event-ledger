"""Shared OpenAPI metadata and response definitions for Swagger docs."""

from typing import TYPE_CHECKING

from ledger_common.schemas import (
    AccountDetailResponse,
    ApplyTransactionRequest,
    BalanceResponse,
    ErrorResponse,
    EventCreate,
    EventResponse,
    TransactionRecord,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

CONTRACT_MODELS = (
    EventCreate,
    EventResponse,
    ApplyTransactionRequest,
    TransactionRecord,
    BalanceResponse,
    AccountDetailResponse,
    ErrorResponse,
)

TAG_EVENTS = "Events"
TAG_ACCOUNTS = "Accounts"
TAG_HEALTH = "Health"
TAG_METRICS = "Metrics"

OPENAPI_TAGS = [
    {
        "name": TAG_EVENTS,
        "description": "Submit and query financial transaction events.",
    },
    {
        "name": TAG_ACCOUNTS,
        "description": "Account balance and transaction operations.",
    },
    {
        "name": TAG_HEALTH,
        "description": "Liveness and dependency health checks.",
    },
    {
        "name": TAG_METRICS,
        "description": "Prometheus metrics exposition.",
    },
]

ERROR_RESPONSES: dict[int, dict] = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    422: {"model": ErrorResponse, "description": "Business rule violation"},
    503: {"model": ErrorResponse, "description": "Dependency unavailable"},
}


def enrich_openapi_with_contracts(schema: dict) -> dict:
    """Add all shared contract schemas to an OpenAPI components section."""
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in CONTRACT_MODELS:
        model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        defs = model_schema.pop("$defs", {})
        components.update(defs)
        components[model.__name__] = model_schema
    return schema


def install_contract_openapi(app: "FastAPI") -> None:
    """Wrap FastAPI OpenAPI generation to include the full shared contract set."""
    base_openapi = app.openapi

    def openapi_with_contracts() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = base_openapi()
        app.openapi_schema = enrich_openapi_with_contracts(schema)
        return app.openapi_schema

    app.openapi = openapi_with_contracts
