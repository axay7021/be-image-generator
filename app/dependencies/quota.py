from datetime import date, datetime, timezone
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
                detail="Daily free limit reached (1 image/day). Please sign in or subscribe for more quota.",
            )

        return limit - usage_count

    # 2. Authenticated User
    print(f"DEBUG: Authenticated user {user.id} check.")

    # Fetch ALL active subscriptions
    # We also include 'quota_exhausted' to perform checks if they have renewed or just to catch them
    # But checks below filter them.
    query = (
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.created_at.asc())
    )

    result = await db.execute(query)
    subscriptions = result.scalars().all()

    total_remaining = 0
    active_plans_count = 0

    for sub in subscriptions:
        # Check expiry
        if sub.period_end < datetime.now(timezone.utc):
            sub.status = "expired"
            print(f"DEBUG: Subscription {sub.id} expired on {sub.period_end}")
            continue

        # Check quota
        if sub.quota_used >= sub.image_generation_limit:
            sub.status = "quota_exhausted"
            print(f"DEBUG: Subscription {sub.id} quota exhausted ({sub.quota_used}/{sub.image_generation_limit})")
            continue

        # Valid active sub
        await db.refresh(sub, ["plan"])
        remaining = sub.image_generation_limit - sub.quota_used
        total_remaining += remaining
        active_plans_count += 1

    await db.commit()

    if active_plans_count > 0:
        print(f"DEBUG: User has {active_plans_count} active plans. Total remaining quota: {total_remaining}")
        return total_remaining

    # If no active plans (or all expired/exhausted), fall back to Free Tier logic

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
        # Authenticated - Increment on oldest active subscription (FIFO)
        query = (
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "active",
            )
            .order_by(Subscription.created_at.asc())
        )

        result = await db.execute(query)
        subscriptions = result.scalars().all()

        quota_incremented = False

        for sub in subscriptions:
            if sub.quota_used < sub.image_generation_limit:
                sub.quota_used += 1
                quota_incremented = True

                # Check for exhaustion immediately
                if sub.quota_used >= sub.image_generation_limit:
                    sub.status = "quota_exhausted"
                    print(f"DEBUG: Subscription {sub.id} exhausted after usage.")

                print(
                    f"DEBUG: Incremented quota for subscription {sub.id}. Used: {sub.quota_used}/{sub.image_generation_limit}"
                )
                break

        if not quota_incremented:
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
