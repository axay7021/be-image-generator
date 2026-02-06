"""Daily analytics aggregation task."""

import logging
from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.db import get_async_db_context
from app.db.schema import DailyAnalytics
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)


async def aggregate_daily_analytics():
    """
    Aggregate analytics data for yesterday.

    This task runs daily to pre-compute analytics statistics,
    improving dashboard performance by avoiding expensive queries.
    """
    try:
        # Get yesterday's date
        yesterday = date.today() - timedelta(days=1)

        logger.info(f"Starting daily analytics aggregation for {yesterday}")

        async with get_async_db_context() as db:
            # Compute statistics for yesterday
            stats = await AnalyticsService.compute_daily_stats(yesterday, db)

            # Upsert into daily_analytics table
            stmt = insert(DailyAnalytics).values(**stats)
            stmt = stmt.on_conflict_do_update(
                index_elements=["date"],
                set_={
                    "total_revenue": stmt.excluded.total_revenue,
                    "new_users": stmt.excluded.new_users,
                    "new_subscriptions": stmt.excluded.new_subscriptions,
                    "active_subscriptions": stmt.excluded.active_subscriptions,
                    "total_quota_used": stmt.excluded.total_quota_used,
                    "razorpay_revenue": stmt.excluded.razorpay_revenue,
                    "stripe_revenue": stmt.excluded.stripe_revenue,
                    "failed_transactions": stmt.excluded.failed_transactions,
                },
            )

            await db.execute(stmt)
            await db.commit()

            logger.info(
                f"Daily analytics aggregation completed for {yesterday}: "
                f"Revenue={stats['total_revenue']}, New Users={stats['new_users']}, "
                f"New Subscriptions={stats['new_subscriptions']}"
            )

    except Exception as e:
        logger.error(f"Error during daily analytics aggregation: {e}", exc_info=True)
        raise
