from datetime import date
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db import get_db
from app.db.schema import DailyUsage, Subscription, User
from app.dependencies.user_auth import get_current_user_optional
from app.exceptions.quota_exception import QuotaLimitExceeded


async def check_quota(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> int:
    """
    Check if the user (or anonymous IP) has sufficient quota.
    Returns the remaining quota count or raises 429.
    """
    # Bypass quota check in development environment
    if settings.ENVIRONMENT == "development":
        print("DEBUG: Dev mode, quota bypassed.")
        return 999999  # Return a high number to indicate unlimited quota

    today = date.today()

    # 1. Anonymous User
    if not user:
        print("DEBUG: Anonymous user check.")
        client_ip = request.client.host if request.client else "unknown"
        # Check daily usage
        query = select(DailyUsage).where(DailyUsage.identifier == client_ip, DailyUsage.date == today)
        result = await db.execute(query)
        daily_usage = result.scalar_one_or_none()

        usage_count = daily_usage.usage_count if daily_usage else 0
        limit = 1  # Free tier limit

        print(f"DEBUG: Anonymous usage: {usage_count}/{limit}")

        if usage_count >= limit:
            raise QuotaLimitExceeded(
                detail="Daily free limit reached. Please login or subscribe for more.",
            )

        return limit - usage_count

    # 2. Authenticated User
    print(f"DEBUG: Authenticated user {user.id} check.")
    # Check for active subscription
    query = select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
    result = await db.execute(query)
    subscription = result.scalar_one_or_none()

    if subscription:
        # User has a subscription
        # We need to fetch the plan to know the limit
        await db.refresh(subscription, ["plan"])
        limit = subscription.plan.image_quota
        used = subscription.quota_used
        print(f"DEBUG: Subscription found. Used: {used}/{limit}")

        if used >= limit:
            raise QuotaLimitExceeded(detail="Subscription plan quota exceeded.")
        return limit - used

    # 3. Authenticated User without Subscription (Free Tier fallback)
    print("DEBUG: No active subscription found. Falling back to free tier.")
    # Check daily usage for user_id
    query = select(DailyUsage).where(DailyUsage.identifier == str(user.id), DailyUsage.date == today)
    result = await db.execute(query)
    daily_usage = result.scalar_one_or_none()

    usage_count = daily_usage.usage_count if daily_usage else 0
    limit = 1

    print(f"DEBUG: Free tier usage: {usage_count}/{limit}")

    if usage_count >= limit:
        raise QuotaLimitExceeded(
            detail="Daily free limit reached. Subscribe to increase your quota.",
        )

    return limit - usage_count


async def increment_quota(
    request: Request,
    db: AsyncSession,
    user: User | None,
):
    """
    Increment usage counter after successful generation.
    """
    today = date.today()

    if not user:
        # Anonymous: Increment DailyUsage by IP
        client_ip = request.client.host if request.client else "unknown"
        query = select(DailyUsage).where(DailyUsage.identifier == client_ip, DailyUsage.date == today)
        result = await db.execute(query)
        daily_usage = result.scalar_one_or_none()

        if daily_usage:
            daily_usage.usage_count += 1
        else:
            daily_usage = DailyUsage(identifier=client_ip, date=today, usage_count=1)
            db.add(daily_usage)

    else:
        # Authenticated
        query = select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
        result = await db.execute(query)
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.quota_used += 1
        else:
            # Fallback to daily usage by User ID
            query = select(DailyUsage).where(DailyUsage.identifier == str(user.id), DailyUsage.date == today)
            result = await db.execute(query)
            daily_usage = result.scalar_one_or_none()

            if daily_usage:
                daily_usage.usage_count += 1
            else:
                daily_usage = DailyUsage(identifier=str(user.id), date=today, usage_count=1)
                db.add(daily_usage)

    await db.commit()
