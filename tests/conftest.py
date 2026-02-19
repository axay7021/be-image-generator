import asyncio
import sys
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.modules["cv2"] = MagicMock()
sys.modules["mediapipe"] = MagicMock()
sys.modules["stripe"] = MagicMock()
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# Use SQLite for testing to avoid external dependencies
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession]:
    """
    Creates a fresh sqlalchemy session for each test.
    For SQLite in-memory, we need to create tables first.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    # Check if we need to drop all. unique to StaticPool+memory might persist?
    # Actually StaticPool maintains ONE connection.
    # If we close it, data is lost?
    # But AsyncEngine manages it.

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Create a new FastAPI TestClient that uses the `db_session` fixture to override
    the `get_db` dependency that is injected into routes.
    """

    async def override_get_db():
        try:
            yield db_session
        except Exception:
            # Re-raise exception to let FastAPI middleware handle it or fail the test
            raise

    app.dependency_overrides[get_db] = override_get_db

    # Create AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as ac:
        yield ac

    del app.dependency_overrides[get_db]
