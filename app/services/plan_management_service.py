"""Plan Management Service with Razorpay integration."""

import razorpay
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.core.settings import settings
from app.db.schema import Plan, Subscription


class PlanManagementService:
    """Service for managing subscription plans with Razorpay integration."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    async def create_plan(
        self,
        name: str,
        price_usd: float,
        image_quota: int,
        validity_days: int,
        billing_interval: str | None = None,
        is_popular: bool = False,
    ) -> Plan:
        """
        Create a new plan and optionally create corresponding Razorpay plan for recurring billing.

        Args:
            name: Plan name
            price_usd: Price in USD
            image_quota: Number of images allowed
            validity_days: Plan validity in days
            billing_interval: For recurring: 'monthly', 'yearly', or None for one-time
            is_popular: Whether to mark plan as popular

        Returns:
            Created Plan object
        """
        razorpay_plan_id = None

        # Create Razorpay plan only if billing_interval is specified (recurring)
        if billing_interval:
            try:
                # Convert period to Razorpay format
                period_mapping = {
                    "monthly": "monthly",
                    "yearly": "yearly",
                }
                period = period_mapping.get(billing_interval)

                if not period:
                    raise ValueError(f"Invalid billing_interval: {billing_interval}")

                # Razorpay expects amount in smallest currency unit (paise for INR)
                # Assuming INR: 1 USD ≈ 83 INR (adjust as needed)
                amount_inr = int(price_usd * 83 * 100)  # Convert to paise

                razorpay_plan_data = {
                    "period": period,
                    "interval": 1,
                    "item": {
                        "name": name,
                        "amount": amount_inr,
                        "currency": "INR",
                    },
                    "notes": {
                        "image_quota": str(image_quota),
                        "validity_days": str(validity_days),
                    },
                }

                razorpay_response = self.razorpay_client.plan.create(razorpay_plan_data)
                razorpay_plan_id = razorpay_response["id"]

                logger.info(f"Created Razorpay plan: {razorpay_plan_id}")

            except Exception as e:
                logger.error(f"Failed to create Razorpay plan: {e}", exc_info=True)
                raise ValueError(f"Razorpay plan creation failed: {str(e)}") from None

        # Create plan in database
        new_plan = Plan(
            name=name,
            price_usd=price_usd,
            image_quota=image_quota,
            validity_days=validity_days,
            billing_interval=billing_interval,
            razorpay_plan_id=razorpay_plan_id,
            stripe_price_id="",  # TODO: Implement Stripe integration
            is_active=True,
            is_popular=is_popular,
        )

        self.db.add(new_plan)
        await self.db.commit()
        await self.db.refresh(new_plan)

        logger.info(f"Created plan: {new_plan.id} - {name}")
        return new_plan

    async def update_plan(
        self,
        plan_id: str,
        name: str | None = None,
        price_usd: float | None = None,
        image_quota: int | None = None,
        validity_days: int | None = None,
        is_active: bool | None = None,
        is_popular: bool | None = None,
    ) -> Plan | None:
        """
        Update plan details. Note: Cannot modify billing_interval or Razorpay plan after creation.
        """
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            return None

        # Update only provided fields
        if name is not None:
            plan.name = name
        if price_usd is not None:
            # Warning: This won't update Razorpay plan price
            logger.warning(f"Updating price for plan {plan_id}. Razorpay plan price not updated.")
            plan.price_usd = price_usd
        if image_quota is not None:
            plan.image_quota = image_quota
        if validity_days is not None:
            plan.validity_days = validity_days
        if is_active is not None:
            plan.is_active = is_active
        if is_popular is not None:
            plan.is_popular = is_popular

        await self.db.commit()
        await self.db.refresh(plan)

        logger.info(f"Updated plan: {plan_id}")
        return plan

    async def delete_plan(self, plan_id: str) -> bool:
        """
        Soft delete a plan by setting is_deleted to True and is_active to False.
        Cannot delete if there are active subscriptions.
        """
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            return False

        if plan.is_deleted:
            raise ValueError("Plan is already deleted")

        # Check for active subscriptions
        active_subs_query = (
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.plan_id == plan_id, Subscription.status == "active")
        )
        result = await self.db.execute(active_subs_query)
        active_count = result.scalar() or 0

        if active_count > 0:
            raise ValueError(f"Cannot delete plan with {active_count} active subscriptions")

        # Soft delete - mark as deleted and inactive
        plan.is_deleted = True
        plan.is_active = False
        await self.db.commit()

        logger.info(f"Soft deleted plan: {plan_id}")
        return True

    async def get_plan(self, plan_id: str) -> Plan | None:
        """Get single plan by ID. Returns None if plan is deleted."""
        plan = await self.db.get(Plan, plan_id)
        if plan and plan.is_deleted:
            return None
        return plan

    async def get_all_plans(self, include_inactive: bool = False) -> list[Plan]:
        """
        Get all plans, optionally including inactive ones.
        Deleted plans are always excluded.
        """
        query = select(Plan).where(not Plan.is_deleted).order_by(Plan.created_at.desc())

        if not include_inactive:
            query = query.where(Plan.is_active)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_plan_stats(self, plan_id: str) -> dict | None:
        """
        Get statistics for a specific plan.
        """
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            return None

        # Get subscription counts by status
        status_query = (
            select(Subscription.status, func.count(Subscription.id).label("count"))
            .where(Subscription.plan_id == plan_id)
            .group_by(Subscription.status)
        )

        status_result = await self.db.execute(status_query)
        status_counts = {row.status: row.count for row in status_result}

        # Get total revenue (requires Transaction table)
        # This will be None until transactions are backfilled

        return {
            "plan_id": str(plan.id),
            "plan_name": plan.name,
            "total_subscriptions": sum(status_counts.values()),
            "active_subscriptions": status_counts.get("active", 0),
            "canceled_subscriptions": status_counts.get("canceled", 0),
            "expired_subscriptions": status_counts.get("expired", 0),
            "quota_exhausted_subscriptions": status_counts.get("quota_exhausted", 0),
            "is_active": plan.is_active,
            "razorpay_plan_id": plan.razorpay_plan_id,
        }
