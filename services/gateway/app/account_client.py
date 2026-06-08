"""Resilient HTTP client for Account Service with circuit breaker and retry."""

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ledger_common.circuit_breaker import CircuitBreaker
from ledger_common.logging import get_logger
from ledger_common.metrics import ACCOUNT_SERVICE_CALLS, CIRCUIT_BREAKER_STATE
from ledger_common.schemas import ApplyTransactionRequest, BalanceResponse
from ledger_common.tracing import TRACE_ID_HEADER, get_trace_id, trace_headers
from services.gateway.app.config import settings

logger = get_logger(__name__)


class AccountServiceUnavailable(Exception):
    """Raised when Account Service cannot be reached after retries / circuit open."""

    def __init__(self, message: str, *, circuit_open: bool = False):
        super().__init__(message)
        self.circuit_open = circuit_open


class AccountServiceError(Exception):
    """Raised for non-retryable Account Service errors."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


circuit_breaker = CircuitBreaker(
    fail_max=settings.circuit_fail_max,
    reset_timeout=float(settings.circuit_reset_timeout),
)


class AccountServiceClient:
    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or settings.account_service_url).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(trace_headers())
        return headers

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)),
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential_jitter(initial=0.5, max=10),
        reraise=True,
    )
    async def _request(self, method: str, path: str, *, json: dict | None = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            return await client.request(
                method,
                f"{self._base_url}{path}",
                json=json,
                headers=self._headers(),
            )

    async def _call_with_breaker(self, method: str, path: str, *, json: dict | None = None) -> httpx.Response:
        if circuit_breaker.is_open:
            CIRCUIT_BREAKER_STATE.labels(service="account-service").inc()
            logger.warning("circuit_breaker_opened", trace_id=get_trace_id())
            raise AccountServiceUnavailable(
                "Account Service circuit breaker is open",
                circuit_open=True,
            )
        try:
            return await self._request(method, path, json=json)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError):
            circuit_breaker.record_failure()
            raise

    async def apply_transaction(self, account_id: str, payload: ApplyTransactionRequest) -> dict:
        operation = "apply_transaction"
        body = payload.model_dump(mode="json", by_alias=True)

        try:
            response = await self._call_with_breaker(
                "POST",
                f"/accounts/{account_id}/transactions",
                json=body,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="unavailable").inc()
            raise AccountServiceUnavailable(
                "Account Service is unavailable after retries"
            ) from exc

        if response.status_code >= 500:
            ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="server_error").inc()
            circuit_breaker.record_failure()
            raise AccountServiceUnavailable(f"Account Service returned {response.status_code}")

        if response.status_code >= 400:
            ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="client_error").inc()
            detail = response.json().get("detail", response.text)
            raise AccountServiceError(response.status_code, detail)

        circuit_breaker.record_success()
        ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="success").inc()
        logger.info(
            "account_service_call_success",
            trace_id=get_trace_id(),
            operation=operation,
            account_id=account_id,
        )
        return response.json()

    async def get_balance(self, account_id: str) -> BalanceResponse:
        operation = "get_balance"
        try:
            response = await self._call_with_breaker("GET", f"/accounts/{account_id}/balance")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="unavailable").inc()
            raise AccountServiceUnavailable(
                "Account Service is unavailable"
            ) from exc

        if response.status_code >= 500:
            ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="server_error").inc()
            circuit_breaker.record_failure()
            raise AccountServiceUnavailable(f"Account Service returned {response.status_code}")

        if response.status_code >= 400:
            ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="client_error").inc()
            detail = response.json().get("detail", response.text)
            raise AccountServiceError(response.status_code, detail)

        circuit_breaker.record_success()
        ACCOUNT_SERVICE_CALLS.labels(operation=operation, status="success").inc()
        data = response.json()
        return BalanceResponse.model_validate(data)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(
                    f"{self._base_url}/health",
                    headers={TRACE_ID_HEADER: get_trace_id() or ""},
                )
            return response.status_code == 200
        except Exception:
            return False
