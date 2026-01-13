from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.schema import User, Subscription, DailyUsage
from app.dependencies.auth import get_current_active_admin
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", status_code=status.HTTP_200_OK)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[Any, Depends(get_current_active_admin)],
    skip: int = 0,
    limit: int = 50,
):
    """List users with their subscription status"""
    query = select(User).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    # We might want to join subscriptions, but let's keep it simple for now
    # Or fetch subs for these users

    users_data = []
    for user in users:
        user_info = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
        users_data.append(user_info)

    return success_response(data=users_data, message="Users retrieved successfully")


@router.post("/users/{user_id}/reset-quota", status_code=status.HTTP_200_OK)
async def reset_user_quota(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[Any, Depends(get_current_active_admin)],
):
    """
    Reset quota for a specific user.
    Resets usage in Subscription (if active) OR DailyUsage.
    """
    # 1. Check Subscription
    sub_query = select(Subscription).where(Subscription.user_id == user_id, Subscription.status == "active")
    result = await db.execute(sub_query)
    sub = result.scalar_one_or_none()

    if sub:
        sub.quota_used = 0
        await db.commit()
        return success_response(data=None, message="Subscription quota reset")

    # 2. Check DailyUsage
    daily_query = select(DailyUsage).where(
        DailyUsage.identifier == user_id,
        # Reset for TODAY? Or just delete the record?
        # Deleting the record effectively resets for today (or future if date matches)
        # But wait, DailyUsage has a date.
        # If we want to reset today's usage:
        DailyUsage.date == func.current_date(),
    )
    # Actually just delete all daily usage entries for this user might be cleaner or just today.
    # Let's target today.
    pass  # Implementation detail: safer to find and update

    # Simpler: Delete all daily usage for this user
    # stmt = delete(DailyUsage).where(DailyUsage.identifier == user_id)
    # await db.execute(stmt)

    # Better: Update today's record
    today = date.today()
    daily_query = select(DailyUsage).where(DailyUsage.identifier == user_id, DailyUsage.date == today)
    result = await db.execute(daily_query)
    daily = result.scalar_one_or_none()
    if daily:
        daily.usage_count = 0
        await db.commit()
        return success_response(data=None, message="Daily free quota reset")

    return success_response(data=None, message="No active quota usage found to reset")


@router.get("/dashboard", status_code=status.HTTP_200_OK)
async def dashboard_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[Any, Depends(get_current_active_admin)],
):
    """Get high level stats"""
    # Count users
    user_count = await db.scalar(select(func.count(User.id)))
    # Count active subscriptions
    sub_count = await db.scalar(select(func.count(Subscription.id)).where(Subscription.status == "active"))

    return success_response(
        data={"total_users": user_count, "active_subscriptions": sub_count}, message="Dashboard stats"
    )
