import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ledger_common.schemas import EventCreate, TransactionType
from services.account.app.database import Base as AccountBase
from services.account.app.main import app as account_app
from services.gateway.app.database import Base as GatewayBase
from services.gateway.app.main import app as gateway_app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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


@pytest_asyncio.fixture
async def account_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=account_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def gateway_client(account_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


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


@pytest.fixture
def valid_event_create() -> EventCreate:
    return EventCreate.model_validate(sample_event())
