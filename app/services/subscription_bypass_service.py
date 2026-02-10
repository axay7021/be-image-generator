"""Helpers for free bypass subscription flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import Plan, Subscription, User

BASIC_PLAN_NAME = "Basic Plan"
FREE_BYPASS_PROVIDER = "free_bypass"
FREE_BYPASS_COOLDOWN_DAYS = 30


@dataclass(frozen=True)
class PurchaseGateState:
    total_remaining: int
    active_count: int
    last_free_bypass_at: datetime | None


def _now_like(reference: datetime) -> datetime:
    if reference.tzinfo is None:
        return datetime.now()
    return datetime.now(timezone.utc)


async def get_purchase_gate_state(db: AsyncSession, user_id: str) -> PurchaseGateState:
    query = (
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == "active")
        .order_by(Subscription.created_at.asc())
    )
    result = await db.execute(query)
    subscriptions = result.scalars().all()

    total_remaining = 0
    active_count = 0

    for sub in subscriptions:
        now = _now_like(sub.period_end)

        if sub.period_end < now:
            sub.status = "expired"
            continue

        if sub.quota_used >= sub.image_generation_limit:
            sub.status = "quota_exhausted"
            continue

        total_remaining += sub.image_generation_limit - sub.quota_used
        active_count += 1

    await db.commit()

    last_free_bypass_at = await get_last_free_bypass_at(db, user_id)

    return PurchaseGateState(
        total_remaining=total_remaining,
        active_count=active_count,
        last_free_bypass_at=last_free_bypass_at,
    )


async def get_last_free_bypass_at(db: AsyncSession, user_id: str) -> datetime | None:
    query = (
        select(Subscription.created_at)
        .where(Subscription.user_id == user_id, Subscription.payment_provider == FREE_BYPASS_PROVIDER)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


def cooldown_elapsed(last_free_bypass_at: datetime | None, now: datetime) -> bool:
    if last_free_bypass_at is None:
        return True
    if last_free_bypass_at.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return now >= last_free_bypass_at + timedelta(days=FREE_BYPASS_COOLDOWN_DAYS)


def purchase_block_reason(state: PurchaseGateState, now: datetime) -> str | None:
    # Block ANY purchase if user has an active subscription (already has basic plan or other)
    if state.active_count > 0:
        return "You already have an active plan. You cannot purchase another plan."

    # Additional check: if they have remaining quota but exhausted, check cooldown
    if state.total_remaining == 0 and state.last_free_bypass_at:
        if not cooldown_elapsed(state.last_free_bypass_at, now):
            return "Next free access is available after 30 days from the last free grant."

    return None


async def get_basic_plan(db: AsyncSession) -> Plan | None:
    """Get the Basic Plan by name"""
    query = select(Plan).where(Plan.name == BASIC_PLAN_NAME)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def grant_free_bypass(db: AsyncSession, user: User, plan: Plan) -> Subscription:
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=plan.validity_days)

    subscription = Subscription(
        user_id=str(user.id),
        plan_id=str(plan.id),
        payment_provider=FREE_BYPASS_PROVIDER,
        status="active",
        quota_used=0,
        period_start=now,
        period_end=period_end,
        image_generation_limit=plan.image_quota,
    )

    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    return subscription


async def grant_basic_plan_to_new_user(db: AsyncSession, user: User) -> Subscription | None:
    """Auto-grant basic plan to new user on first login"""
    # Check if user already has any subscription
    query = select(Subscription).where(Subscription.user_id == str(user.id)).limit(1)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        return None  # User already has a subscription

    # Get the basic plan
    basic_plan = await get_basic_plan(db)
    if not basic_plan:
        return None  # Basic plan not found

    # Grant the basic plan
    return await grant_free_bypass(db, user, basic_plan)
