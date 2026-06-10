"""Integration tests exercising Gateway → Account Service end-to-end."""

from datetime import datetime, timezone
from decimal import Decimal
import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ledger_common.tracing import TRACE_ID_HEADER
from services.account.app.database import Base as AccountBase
from services.account.app.main import app as account_app
from services.gateway.app.database import Base as GatewayBase
from services.gateway.app.main import app as gateway_app
from services.gateway.app.account_client import circuit_breaker
from services.gateway.app.routes import get_account_client
from services.gateway.app.repository import EventRepository
from tests.conftest import sample_event


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    circuit_breaker.reset()
    yield
    circuit_breaker.reset()


@pytest_asyncio.fixture(autouse=True)
async def setup_databases(monkeypatch, tmp_path):
    account_db = tmp_path / "account_test.db"
    gateway_db = tmp_path / "gateway_test.db"

    account_url = f"sqlite+aiosqlite:///{account_db}"
    gateway_url = f"sqlite+aiosqlite:///{gateway_db}"

    import services.account.app.database as account_db_mod
    import services.gateway.app.database as gateway_db_mod
    import services.gateway.app.main as gateway_main

    account_engine = create_async_engine(account_url, connect_args={"check_same_thread": False})
    gateway_engine = create_async_engine(gateway_url, connect_args={"check_same_thread": False})

    async with account_engine.begin() as conn:
        await conn.run_sync(AccountBase.metadata.create_all)
    async with gateway_engine.begin() as conn:
        await conn.run_sync(GatewayBase.metadata.create_all)

    account_db_mod.engine = account_engine
    account_db_mod.SessionLocal = async_sessionmaker(account_engine, expire_on_commit=False)
    gateway_db_mod.engine = gateway_engine
    gateway_db_mod.SessionLocal = async_sessionmaker(gateway_engine, expire_on_commit=False)

    monkeypatch.setenv("GATEWAY_QUEUE_PROCESSING_ENABLED", "false")

    gateway_main._stop_event = None
    gateway_main._worker_task = None

    yield gateway_db_mod

    await account_engine.dispose()
    await gateway_engine.dispose()


@pytest_asyncio.fixture
async def integrated_clients():
    account_transport = ASGITransport(app=account_app)
    gateway_transport = ASGITransport(app=gateway_app)

    async with AsyncClient(transport=account_transport, base_url="http://test-account") as account:
        async with AsyncClient(transport=gateway_transport, base_url="http://test") as gateway:
            yield gateway, account


def make_asgi_account_client():
    account_transport = ASGITransport(app=account_app)

    class TestAccountClient:
        def __init__(self, *args, **kwargs):
            pass

        def _headers(self):
            from ledger_common.tracing import trace_headers

            return trace_headers()

        async def apply_transaction(self, account_id, payload):
            async with AsyncClient(transport=account_transport, base_url="http://test-account") as c:
                r = await c.post(
                    f"/accounts/{account_id}/transactions",
                    json=payload.model_dump(mode="json", by_alias=True),
                    headers=self._headers(),
                )
            if r.status_code >= 400:
                from services.gateway.app.account_client import AccountServiceError

                raise AccountServiceError(r.status_code, r.json().get("detail", ""))
            return r.json()

        async def get_balance(self, account_id):
            async with AsyncClient(transport=account_transport, base_url="http://test-account") as c:
                r = await c.get(f"/accounts/{account_id}/balance", headers=self._headers())
            from ledger_common.schemas import BalanceResponse

            return BalanceResponse.model_validate(r.json())

    return TestAccountClient()


@pytest.mark.asyncio
async def test_full_event_flow(integrated_clients):
    gateway, _ = integrated_clients

    gateway_app.dependency_overrides[get_account_client] = make_asgi_account_client
    try:
        event = sample_event("evt-flow-1", amount="100.00")
        response = await gateway.post("/events", json=event)
        assert response.status_code == 201
        trace_id = response.headers.get(TRACE_ID_HEADER)
        assert trace_id and len(trace_id) == 32 and trace_id.isalnum()

        dup = await gateway.post("/events", json=event)
        assert dup.status_code == 200

        balance = await gateway.get("/accounts/acct-123/balance")
        assert balance.status_code == 200
        assert balance.json()["balance"] == "100.0000"

        listed = await gateway.get("/events", params={"account": "acct-123"})
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    finally:
        gateway_app.dependency_overrides.pop(get_account_client, None)


@pytest.mark.asyncio
async def test_out_of_order_events(integrated_clients):
    gateway, _ = integrated_clients

    gateway_app.dependency_overrides[get_account_client] = make_asgi_account_client
    try:
        later = sample_event("evt-later", timestamp="2026-05-16T10:00:00Z", amount="200.00")
        earlier = sample_event(
            "evt-earlier", timestamp="2026-05-15T10:00:00Z", amount="50.00", tx_type="DEBIT"
        )

        await gateway.post("/events", json=later)
        await gateway.post("/events", json=earlier)

        balance = await gateway.get("/accounts/acct-123/balance")
        assert balance.json()["balance"] == "150.0000"

        listed = await gateway.get("/events", params={"account": "acct-123"})
        ids = [e["eventId"] for e in listed.json()]
        assert ids == ["evt-earlier", "evt-later"]
    finally:
        gateway_app.dependency_overrides.pop(get_account_client, None)


@pytest.mark.asyncio
async def test_graceful_degradation_reads(integrated_clients, setup_databases):
    gateway, _ = integrated_clients
    gateway_db_mod = setup_databases

    async with gateway_db_mod.SessionLocal() as session:
        repo = EventRepository(session)
        await repo.create_event(
            event_id="evt-read-1",
            account_id="acct-99",
            tx_type="CREDIT",
            amount=Decimal("10"),
            currency="USD",
            event_timestamp=datetime.now(timezone.utc),
            metadata=None,
            status="APPLIED",
        )

    response = await gateway.get("/events/evt-read-1")
    assert response.status_code == 200


@pytest.mark.asyncio
@respx.mock
async def test_account_service_unavailable_returns_503(integrated_clients):
    gateway, _ = integrated_clients
    respx.post(url__regex=r".*/accounts/.*/transactions").mock(
        return_value=httpx.Response(503, json={"detail": "down"})
    )

    from services.gateway.app.account_client import AccountServiceClient

    gateway_app.dependency_overrides[get_account_client] = lambda: AccountServiceClient(
        "http://unreachable:8001"
    )
    try:
        response = await gateway.post("/events", json=sample_event("evt-503"))
        assert response.status_code == 503

        stored = await gateway.get("/events/evt-503")
        assert stored.status_code == 200
        assert stored.json()["status"] == "QUEUED"
    finally:
        gateway_app.dependency_overrides.pop(get_account_client, None)


@pytest.mark.asyncio
async def test_trace_id_propagation(integrated_clients):
    gateway, _ = integrated_clients
    captured_headers: list[dict] = []

    class TracingAccountClient:
        def __init__(self, *args, **kwargs):
            pass

        def _headers(self):
            from ledger_common.tracing import trace_headers

            return trace_headers()

        async def apply_transaction(self, account_id, payload):
            headers = self._headers()
            captured_headers.append(headers)
            account_transport = ASGITransport(app=account_app)
            async with AsyncClient(transport=account_transport, base_url="http://test-account") as c:
                r = await c.post(
                    f"/accounts/{account_id}/transactions",
                    json=payload.model_dump(mode="json", by_alias=True),
                    headers=headers,
                )
            return r.json()

    gateway_app.dependency_overrides[get_account_client] = lambda: TracingAccountClient()
    try:
        response = await gateway.post("/events", json=sample_event("evt-trace"))
        assert response.status_code == 201
        trace_id = response.headers.get(TRACE_ID_HEADER)
        assert trace_id and len(trace_id) == 32
        assert captured_headers
        assert captured_headers[0].get(TRACE_ID_HEADER) == trace_id
        traceparent = captured_headers[0].get("traceparent", "")
        assert traceparent.startswith("00-") and traceparent.split("-")[1] == trace_id
    finally:
        gateway_app.dependency_overrides.pop(get_account_client, None)
