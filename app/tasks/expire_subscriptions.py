"""Task to expire subscriptions that have passed their validity period"""

import logging
from datetime import datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.db.schema import Subscription

logger = logging.getLogger(__name__)


async def expire_old_subscriptions():
    """
    Check for subscriptions that have passed their period_end date
    and mark them as expired if they're still active or quota_exhausted.

    Runs daily via APScheduler.
    """
    try:
        async with SessionLocal() as db:
            # Find all subscriptions that should be expired
            now = datetime.now()
            query = select(Subscription).where(
                Subscription.period_end < now, Subscription.status.in_(["active", "quota_exhausted"])
            )

            result = await db.execute(query)
            expired_subs = result.scalars().all()

            count = 0
            for sub in expired_subs:
                sub.status = "expired"
                count += 1
                logger.info(f"Expired subscription {sub.id} for user {sub.user_id} (expired on {sub.period_end})")

            if count > 0:
                await db.commit()
                logger.info(f"Expired {count} subscriptions")
            else:
                logger.info("No subscriptions to expire")

    except Exception as e:
        logger.error(f"Error expiring subscriptions: {e}", exc_info=True)
