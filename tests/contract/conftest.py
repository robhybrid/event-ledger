"""Shared fixtures for contract and Pact tests."""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ledger_common.tracing import shutdown_tracing
from services.account.app.database import Base as AccountBase
from services.account.app.main import app as account_app
from services.account.app.repository import AccountRepository
PACT_DIR = Path(__file__).resolve().parent.parent / "pacts"
PACT_ACCOUNT_ID = "acct-pact-001"
PACT_EVENT_ID = "evt-pact-001"
PACT_TIMESTAMP = datetime(2026, 5, 15, 14, 2, 11, tzinfo=timezone.utc)


@pytest.fixture
def pact_dir() -> Path:
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    return PACT_DIR


def _run_uvicorn(host: str, port: int) -> None:
    config = uvicorn.Config(account_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


@pytest.fixture
def account_service_url(tmp_path, monkeypatch) -> Generator[str, None, None]:
    """Run Account Service over HTTP for Pact provider verification."""
    db_path = tmp_path / "pact_account.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    import services.account.app.database as account_db_mod

    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    account_db_mod.engine = engine
    account_db_mod.SessionLocal = session_factory

    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(AccountBase.metadata.create_all)

    asyncio.run(init())

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("localhost", 0))
    port = sock.getsockname()[1]
    sock.close()

    thread = threading.Thread(
        target=_run_uvicorn,
        args=("localhost", port),
        daemon=True,
    )
    thread.start()

    yield f"http://localhost:{port}"

    shutdown_tracing()
    asyncio.run(engine.dispose())


async def _reset_account_db() -> None:
    import services.account.app.database as account_db_mod

    async with account_db_mod.engine.begin() as conn:
        await conn.run_sync(AccountBase.metadata.drop_all)
        await conn.run_sync(AccountBase.metadata.create_all)


async def _seed_account_balance() -> None:
    import services.account.app.database as account_db_mod

    await _reset_account_db()
    async with account_db_mod.SessionLocal() as session:
        repo = AccountRepository(session)
        await repo.apply_transaction(
            event_id=PACT_EVENT_ID,
            account_id=PACT_ACCOUNT_ID,
            tx_type="CREDIT",
            amount=Decimal("100.0000"),
            currency="USD",
            event_timestamp=PACT_TIMESTAMP,
        )
        await session.commit()


def reset_account_state() -> None:
    asyncio.run(_reset_account_db())


def seed_account_balance_state() -> None:
    asyncio.run(_seed_account_balance())
