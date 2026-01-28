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


def get_client_ip(request: Request) -> str:
    """Helper to get the real client IP, considering proxies"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_quota(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
    cost: int = 1,
) -> int:
    """
    Check if the user (or anonymous IP) has sufficient quota.
    Returns the remaining quota count or raises 429.
    """
    # Bypass quota check in development environment - OPTIONAL: Toggle off if testing quota
    # if settings.ENVIRONMENT == "development":
    #     print("DEBUG: Dev mode, quota bypassed.")
    #     return 999999

    today = date.today()
    client_ip = get_client_ip(request)

    # 1. Anonymous User
    if not user:
        if cost > 1:
            raise QuotaLimitExceeded(
                detail="High-resolution features require an active subscription. Please sign in or subscribe."
            )
        print(f"DEBUG: Anonymous user check for IP {client_ip}.")

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
        if total_remaining < cost:
            raise QuotaLimitExceeded(
                detail=f"Insufficient quota. This action requires {cost} credits, but you only have {total_remaining} remaining."
            )
        print(f"DEBUG: User has {active_plans_count} active plans. Total remaining quota: {total_remaining}")
        return total_remaining

    # If no active plans (or all expired/exhausted), fall back to Free Tier logic

    # 3. Authenticated User without Subscription (Free Tier fallback)
    print("DEBUG: No active subscription found. Falling back to free tier.")
    # Check daily usage for user_id
    query_user = select(DailyUsage).where(DailyUsage.identifier == str(user.id), DailyUsage.date == today)
    result_user = await db.execute(query_user)
    daily_usage_user = result_user.scalar_one_or_none()
    usage_user = daily_usage_user.usage_count if daily_usage_user else 0

    # Check daily usage for IP (to prevent anonymous -> logged-in loophole)
    # limit check to ensure we don't double count if IP is utilized by multiple users (NAT issue)
    # For now, we keep it but warn if it blocks many users.
    client_ip = get_client_ip(request)
    query_ip = select(DailyUsage).where(DailyUsage.identifier == client_ip, DailyUsage.date == today)
    result_ip = await db.execute(query_ip)
    daily_usage_ip = result_ip.scalar_one_or_none()
    usage_ip = daily_usage_ip.usage_count if daily_usage_ip else 0

    usage_count = usage_user + usage_ip
    limit = 1

    print(f"DEBUG: Free tier usage: {usage_count}/{limit} (User: {usage_user}, IP: {usage_ip})")

    if usage_count >= limit:
        raise QuotaLimitExceeded(
            detail="Daily free limit reached. Subscribe to increase your quota.",
        )

    return limit - usage_count


async def increment_quota(
    request: Request,
    db: AsyncSession,
    user: User | None,
    cost: int = 1,
):
    """
    Increment usage counter after successful generation.
    """
    today = date.today()
    client_ip = get_client_ip(request)

    if not user:
        # Anonymous: Increment DailyUsage by IP
        query = select(DailyUsage).where(DailyUsage.identifier == client_ip, DailyUsage.date == today)
        result = await db.execute(query)
        daily_usage = result.scalar_one_or_none()

        if daily_usage:
            daily_usage.usage_count += cost
        else:
            daily_usage = DailyUsage(identifier=client_ip, date=today, usage_count=cost)
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
        remaining_cost = cost

        for sub in subscriptions:
            # How much can we take from this plan?
            available_in_sub = sub.image_generation_limit - sub.quota_used

            if available_in_sub > 0:
                deduction = min(remaining_cost, available_in_sub)
                sub.quota_used += deduction
                remaining_cost -= deduction
                quota_incremented = True

                # Check for exhaustion
                if sub.quota_used >= sub.image_generation_limit:
                    sub.status = "quota_exhausted"
                    print(f"DEBUG: Subscription {sub.id} exhausted after usage.")

                print(
                    f"DEBUG: Deducted {deduction} from subscription {sub.id}. Used: {sub.quota_used}/{sub.image_generation_limit}"
                )

                if remaining_cost <= 0:
                    break

        if not quota_incremented or remaining_cost > 0:
            # Fallback to daily usage by User ID (only if paid quota wasn't enough)
            query = select(DailyUsage).where(DailyUsage.identifier == str(user.id), DailyUsage.date == today)
            result = await db.execute(query)
            daily_usage = result.scalar_one_or_none()

            if daily_usage:
                daily_usage.usage_count += cost
            else:
                daily_usage = DailyUsage(identifier=str(user.id), date=today, usage_count=cost)
                db.add(daily_usage)

    await db.commit()
