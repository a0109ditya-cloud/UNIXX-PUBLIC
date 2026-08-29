from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./backend/tests/test_vigil.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("UPLOAD_DIR", "backend/tests/uploads")

import pytest
from fastapi.testclient import TestClient

from backend.app.db.base import Base
from backend.app.db.session import async_session_maker, engine
from backend.app.main import app


@pytest.fixture(scope="session")
def client():
    async def setup_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(setup_db())
    with TestClient(app) as test_client:
        yield test_client

    async def teardown_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(teardown_db())
