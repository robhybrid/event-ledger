from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ledger_common.tracing import shutdown_tracing
from services.account.app.database import Base as AccountBase
from services.gateway.app.account_client import circuit_breaker
from services.gateway.app.database import Base as GatewayBase


@pytest.fixture(scope="session", autouse=True)
def _shutdown_tracing_after_session():
    yield
    shutdown_tracing()


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    circuit_breaker.reset()
    yield
    circuit_breaker.reset()


@pytest_asyncio.fixture
async def account_db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(AccountBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def gateway_db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(GatewayBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def sample_event(
    event_id: str = "evt-001",
    account_id: str = "acct-123",
    tx_type: str = "CREDIT",
    amount: str = "150.00",
    timestamp: str = "2026-05-15T14:02:11Z",
) -> dict:
    return {
        "eventId": event_id,
        "accountId": account_id,
        "type": tx_type,
        "amount": amount,
        "currency": "USD",
        "eventTimestamp": timestamp,
        "metadata": {"source": "test"},
    }
