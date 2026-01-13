"""Background tasks for database cleanup"""

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.schema import ActiveToken


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """
    Delete expired access tokens from the whitelist.

    This should be run periodically (e.g., daily via cron job) to prevent
    the active_tokens table from growing indefinitely.

    Returns:
        int: Number of tokens deleted
    """
    now = datetime.now(timezone.utc)

    # Delete all tokens that have expired
    result = await db.execute(delete(ActiveToken).where(ActiveToken.expires_at < now))

    deleted_count = result.rowcount
    await db.commit()

    return deleted_count


async def cleanup_all():
    """
    Run all cleanup tasks.

    This is the main entry point for the cleanup cron job.
    """
    async for db in get_db():
        try:
            deleted_tokens = await cleanup_expired_tokens(db)
            print(f"Cleanup complete: Deleted {deleted_tokens} expired tokens")
            return deleted_tokens
        finally:
            await db.close()


if __name__ == "__main__":
    """
    Run cleanup directly: python -m app.tasks.cleanup
    """
    import asyncio

    asyncio.run(cleanup_all())
