from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import settings


# Base class for all models
class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    (settings.DATABASE_URL or "postgresql://localhost/unconfigured").replace("postgresql", "postgresql+asyncpg", 1),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,  # Test connections before using them
    echo=False,
)

SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise


def get_async_db_context():
    """Get database session context manager for background tasks."""
    return SessionLocal()
