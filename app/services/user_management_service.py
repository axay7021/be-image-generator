"""User Management Service for admin operations."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.logger import logger
from app.db.schema import ActivityAction, ActivityLog, ImageLog, PerformedByType, Plan, Subscription, Transaction, User
from app.dto.subscription_dto import PlanResponse, SubscriptionResponse
from app.dto.transaction_dto import TransactionResponse
from app.dto.user_management_dto import (
    QuotaSummary,
    UserActivityLogItem,
    UserActivityResponse,
    UserDetailResponse,
    UserListFilters,
    UserListItem,
    UserListResponse,
)


class UserManagementService:
    """Service for managing users from admin perspective."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_users(self, filters: UserListFilters) -> UserListResponse:
        """
        Get paginated list of users with optional filters.
        """
        query = select(User)
        count_query = select(func.count()).select_from(User)

        # Apply search filter
        if filters.search:
            search_term = f"%{filters.search}%"
            search_filter = or_(
                User.email.ilike(search_term),
                User.phone_number.ilike(search_term),
                User.full_name.ilike(search_term),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Apply is_active filter
        if filters.is_active is not None:
            query = query.where(User.is_active == filters.is_active)
            count_query = count_query.where(User.is_active == filters.is_active)

        # Apply created_via filter
        if filters.created_via is not None:
            query = query.where(User.created_via == filters.created_via)
            count_query = count_query.where(User.created_via == filters.created_via)

        # Apply subscription filter (requires join)
        if filters.has_active_subscription is not None:
            if filters.has_active_subscription:
                # Users with at least one active subscription
                subquery = select(Subscription.user_id).where(Subscription.status == "active").distinct()
                query = query.where(User.id.in_(subquery))
                count_query = count_query.where(User.id.in_(subquery))
            else:
                # Users without any active subscription
                subquery = select(Subscription.user_id).where(Subscription.status == "active").distinct()
                query = query.where(~User.id.in_(subquery))
                count_query = count_query.where(~User.id.in_(subquery))

        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply ordering and pagination
        query = query.order_by(User.created_at.desc())
        query = query.offset(filters.skip).limit(filters.limit)

        # Execute query
        result = await self.db.execute(query)
        users = result.scalars().all()

        # Build response items with aggregated data
        user_items = []
        for user in users:
            # Check for active subscription
            active_sub_query = select(Subscription).where(
                Subscription.user_id == user.id, Subscription.status == "active"
            )
            active_sub_result = await self.db.execute(active_sub_query)
            has_active_sub = active_sub_result.scalar_one_or_none() is not None

            # Get total quota used
            quota_query = select(func.sum(Subscription.quota_used)).where(
                Subscription.user_id == user.id, Subscription.status == "active"
            )
            quota_result = await self.db.execute(quota_query)
            total_quota_used = quota_result.scalar() or 0

            user_items.append(
                UserListItem(
                    id=str(user.id),
                    email=user.email,
                    phone_number=user.phone_number,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    created_via=user.created_via,
                    created_at=user.created_at,
                    has_active_subscription=has_active_sub,
                    total_quota_used=total_quota_used,
                )
            )

        return UserListResponse(
            users=user_items,
            total=total,
            skip=filters.skip,
            limit=filters.limit,
        )

    async def get_user_detail(self, user_id: str) -> UserDetailResponse | None:
        """
        Get detailed user information including subscriptions, transactions, and quota.
        """
        # Fetch user with eager loading of subscriptions and their plans
        query = (
            select(User).where(User.id == user_id).options(joinedload(User.subscriptions).joinedload(Subscription.plan))
        )
        result = await self.db.execute(query)
        user = result.unique().scalar_one_or_none()

        if not user:
            return None

        # Get transaction count
        transaction_count_query = select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)
        transaction_count_result = await self.db.execute(transaction_count_query)
        transaction_count = transaction_count_result.scalar() or 0

        # Calculate quota summary
        active_subs = [sub for sub in user.subscriptions if sub.status == "active"]
        total_limit = sum(sub.image_generation_limit for sub in active_subs)
        total_used = sum(sub.quota_used for sub in active_subs)
        remaining = max(0, total_limit - total_used)

        quota_summary = QuotaSummary(
            total_limit=total_limit,
            total_used=total_used,
            remaining=remaining,
            subscriptions_count=len(active_subs),
        )

        # Convert subscriptions to response DTOs
        subscription_responses = [
            SubscriptionResponse(
                id=str(sub.id),
                plan=PlanResponse(
                    id=str(sub.plan.id),
                    name=sub.plan.name,
                    price_usd=sub.plan.price_usd,
                    image_quota=sub.plan.image_quota,
                    stripe_price_id=sub.plan.stripe_price_id,
                    razorpay_plan_id=sub.plan.razorpay_plan_id,
                    razorpay_payment_page_id=sub.plan.razorpay_payment_page_id,
                    billing_interval=sub.plan.billing_interval,
                    validity_days=sub.plan.validity_days,
                    is_popular=sub.plan.is_popular,
                    is_active=sub.plan.is_active,
                    created_at=sub.plan.created_at,
                ),
                status=sub.status,
                quota_used=sub.quota_used,
                image_generation_limit=sub.image_generation_limit,
                period_start=sub.period_start,
                period_end=sub.period_end,
                created_at=sub.created_at,
            )
            for sub in user.subscriptions
        ]

        return UserDetailResponse(
            id=str(user.id),
            email=user.email,
            phone_number=user.phone_number,
            full_name=user.full_name,
            gender=user.gender,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            created_via=user.created_via,
            created_at=user.created_at,
            updated_at=user.updated_at,
            subscriptions=subscription_responses,
            transaction_count=transaction_count,
            quota_summary=quota_summary,
            google_id=user.google_id,
            clerk_id=user.clerk_id,
            line_id=user.line_id,
        )

    async def update_user_status(self, user_id: str, is_active: bool, admin_id: str, reason: str | None = None) -> bool:
        """
        Update user active status (block/unblock).
        Logs the action to ActivityLog.
        """
        user = await self.db.get(User, user_id)
        if not user:
            return False

        old_status = user.is_active
        user.is_active = is_active

        # Log the status change
        action_description = f"User {'activated' if is_active else 'deactivated'}"
        changes = {"is_active": {"old": old_status, "new": is_active}}
        if reason:
            action_description += f" - Reason: {reason}"
            changes["reason"] = reason

        activity_log = ActivityLog(
            entity_type="user",
            entity_id=user_id,
            action=ActivityAction.UPDATE,
            performed_by_type=PerformedByType.ADMIN,
            performed_by_id=admin_id,
            changes=changes,
        )
        self.db.add(activity_log)

        await self.db.commit()

        logger.info(
            f"User {user_id} status changed from {old_status} to {is_active} by admin {admin_id}. Reason: {reason}"
        )
        return True

    async def get_user_activity(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> UserActivityResponse | None:
        """
        Get paginated user activity logs (ImageLog entries).
        """
        # Check if user exists
        user = await self.db.get(User, user_id)
        if not user:
            return None

        # Get total count
        count_query = select(func.count()).select_from(ImageLog).where(ImageLog.user_id == user_id)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get activity logs
        query = (
            select(ImageLog)
            .where(ImageLog.user_id == user_id)
            .order_by(ImageLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        logs = result.scalars().all()

        activity_items = [
            UserActivityLogItem(
                id=str(log.id),
                action=log.action or "Image Generation",
                gemini_tokens_used=log.gemini_tokens_used,
                cost_inr=log.cost_inr,
                timestamp=log.timestamp,
            )
            for log in logs
        ]

        return UserActivityResponse(
            activity_logs=activity_items,
            total=total,
            skip=skip,
            limit=limit,
        )

    async def get_user_transactions(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> dict | None:
        """
        Get paginated user transaction history.
        """
        # Check if user exists
        user = await self.db.get(User, user_id)
        if not user:
            return None

        # Get total count
        count_query = select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get transactions
        query = (
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        transaction_items = [
            TransactionResponse(
                id=str(txn.id),
                user_id=str(txn.user_id),
                plan_id=str(txn.plan_id),
                subscription_id=str(txn.subscription_id) if txn.subscription_id else None,
                amount=float(txn.amount),
                currency=txn.currency,
                payment_provider=txn.payment_provider,
                payment_provider_id=txn.payment_provider_id,
                payment_method=txn.payment_method,
                payment_status=txn.payment_status,
                reconciliation_status=txn.reconciliation_status,
                payment_metadata=txn.payment_metadata,
                created_at=txn.created_at,
                updated_at=txn.updated_at,
            )
            for txn in transactions
        ]

        return {
            "transactions": transaction_items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def assign_plan_to_user(
        self,
        user_id: str,
        plan_id: str,
        admin_id: str,
    ) -> Subscription | None:
        """
        Manually assign a plan to a user (admin action - no payment required).

        Args:
            user_id: Target user ID
            plan_id: Plan to assign
            admin_id: Admin performing the action

        Returns:
            Created Subscription or None if user/plan not found
        """
        # Verify user exists
        user = await self.db.get(User, user_id)
        if not user:
            logger.warning(f"Admin {admin_id} tried to assign plan to non-existent user {user_id}")
            return None

        # Verify plan exists and is active
        plan = await self.db.get(Plan, plan_id)
        if not plan or not plan.is_active:
            logger.warning(f"Admin {admin_id} tried to assign inactive/non-existent plan {plan_id} to user {user_id}")
            return None

        # Cancel any existing active subscriptions for this user
        cancel_query = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
        )
        cancel_result = await self.db.execute(cancel_query)
        existing_subs = cancel_result.scalars().all()
        for sub in existing_subs:
            sub.status = "canceled"
            logger.info(f"Canceled subscription {sub.id} for user {user_id} due to new plan assignment")

        # Create new subscription
        now = datetime.now(timezone.utc)
        period_end = now + timedelta(days=plan.validity_days)

        new_subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            payment_provider="admin_manual",
            status="active",
            quota_used=0,
            period_start=now,
            period_end=period_end,
            image_generation_limit=plan.image_quota,
        )

        self.db.add(new_subscription)

        # Log activity
        activity_log = ActivityLog(
            entity_type="subscription",
            entity_id=str(new_subscription.id),
            action=ActivityAction.CREATE,
            performed_by_type=PerformedByType.ADMIN,
            performed_by_id=admin_id,
            changes={
                "user_id": user_id,
                "plan_id": plan_id,
                "plan_name": plan.name,
                "image_quota": plan.image_quota,
                "validity_days": plan.validity_days,
                "method": "admin_manual",
            },
        )
        self.db.add(activity_log)

        await self.db.commit()
        await self.db.refresh(new_subscription)

        logger.info(
            f"Admin {admin_id} assigned plan {plan.name} ({plan_id}) to user {user_id} (subscription {new_subscription.id})"
        )
        return new_subscription
