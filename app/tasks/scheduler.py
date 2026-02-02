"""Scheduled tasks using APScheduler"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.tasks.cleanup import cleanup_all
from app.tasks.expire_subscriptions import expire_old_subscriptions

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


def start_scheduler():
    """
    Start the background scheduler for periodic tasks.

    This should be called on application startup.
    """
    if scheduler.running:
        logger.warning("Scheduler is already running")
        return

    # Schedule cleanup to run daily at 3 AM
    scheduler.add_job(
        cleanup_all,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_expired_tokens",
        name="Cleanup expired access tokens",
        replace_existing=True,
    )

    # Schedule subscription expiration check to run daily at 2 AM
    scheduler.add_job(
        expire_old_subscriptions,
        trigger=CronTrigger(hour=2, minute=0),
        id="expire_subscriptions",
        name="Expire old subscriptions",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started - Cleanup will run daily at 3:00 AM, Subscription expiration at 2:00 AM")


def stop_scheduler():
    """
    Stop the background scheduler.

    This should be called on application shutdown.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


def run_cleanup_now():
    """
    Manually trigger cleanup job immediately.

    Useful for testing or manual cleanup.
    """
    scheduler.add_job(
        cleanup_all,
        id="manual_cleanup",
        name="Manual cleanup trigger",
        replace_existing=True,
    )
    logger.info("Manual cleanup job queued")
