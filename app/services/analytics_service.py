"""Service for analytics and reporting."""

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import (
    DailyAnalytics,
    ImageLog,
    PaymentProvider,
    PaymentStatus,
    Plan,
    ReconciliationStatus,
    Subscription,
    Transaction,
    User,
)
from app.dto.analytics_dto import (
    CreatedViaBreakdown,
    DashboardOverviewResponse,
    PaymentProviderBreakdown,
    Period,
    PlanAnalyticsItem,
    PlanAnalyticsResponse,
    SalesAnalyticsResponse,
    SalesDataPoint,
    TrafficAnalyticsResponse,
    TrafficDataPoint,
)
from app.utils.date_helpers import (
    end_of_month,
    format_date_for_display,
    get_date_range,
    group_by_period,
    start_of_month,
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for computing and retrieving analytics data."""

    @staticmethod
    async def compute_daily_stats(target_date: date, db: AsyncSession) -> dict:
        """
        Compute analytics statistics for a specific date.

        Args:
            target_date: Date to compute stats for
            db: Database session

        Returns:
            Dictionary with daily statistics
        """
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())

        # Calculate revenue from captured transactions
        revenue_query = select(
            func.coalesce(func.sum(Transaction.amount), 0).label("total_revenue"),
            func.coalesce(
                func.sum(case((Transaction.payment_provider == PaymentProvider.RAZORPAY, Transaction.amount), else_=0)),
                0,
            ).label("razorpay_revenue"),
            func.coalesce(
                func.sum(case((Transaction.payment_provider == PaymentProvider.STRIPE, Transaction.amount), else_=0)), 0
            ).label("stripe_revenue"),
            func.count(case((Transaction.payment_status == PaymentStatus.FAILED, 1))).label("failed_transactions"),
        ).where(
            and_(
                Transaction.created_at >= start_dt,
                Transaction.created_at <= end_dt,
                Transaction.payment_status == PaymentStatus.CAPTURED,
            )
        )

        revenue_result = await db.execute(revenue_query)
        revenue_row = revenue_result.one()

        # Count new users
        new_users_query = select(func.count(User.id)).where(
            and_(User.created_at >= start_dt, User.created_at <= end_dt)
        )
        new_users_result = await db.execute(new_users_query)
        new_users = new_users_result.scalar() or 0

        # Count new subscriptions
        new_subs_query = select(func.count(Subscription.id)).where(
            and_(Subscription.created_at >= start_dt, Subscription.created_at <= end_dt)
        )
        new_subs_result = await db.execute(new_subs_query)
        new_subscriptions = new_subs_result.scalar() or 0

        # Count active subscriptions at end of day
        active_subs_query = select(func.count(Subscription.id)).where(
            and_(Subscription.status == "active", Subscription.period_end >= end_dt)
        )
        active_subs_result = await db.execute(active_subs_query)
        active_subscriptions = active_subs_result.scalar() or 0

        # Sum quota used from image logs
        quota_query = select(func.coalesce(func.count(ImageLog.id), 0)).where(
            and_(ImageLog.timestamp >= start_dt, ImageLog.timestamp <= end_dt)
        )
        quota_result = await db.execute(quota_query)
        total_quota_used = quota_result.scalar() or 0

        return {
            "date": target_date,
            "total_revenue": Decimal(str(revenue_row.total_revenue)),
            "razorpay_revenue": Decimal(str(revenue_row.razorpay_revenue)),
            "stripe_revenue": Decimal(str(revenue_row.stripe_revenue)),
            "failed_transactions": revenue_row.failed_transactions,
            "new_users": new_users,
            "new_subscriptions": new_subscriptions,
            "active_subscriptions": active_subscriptions,
            "total_quota_used": total_quota_used,
        }

    @staticmethod
    async def get_sales_analytics(
        period: Period, start_date: date, end_date: date, db: AsyncSession
    ) -> SalesAnalyticsResponse:
        """Get sales analytics for the specified period."""
        get_date_range(period, start_date, end_date)

        # Query aggregated data based on period
        if period == "daily":
            # Use pre-computed daily analytics where available
            daily_analytics_query = (
                select(DailyAnalytics)
                .where(and_(DailyAnalytics.date >= start_date, DailyAnalytics.date <= end_date))
                .order_by(DailyAnalytics.date)
            )

            result = await db.execute(daily_analytics_query)
            daily_data = result.scalars().all()

            data_points = [
                SalesDataPoint(
                    date=format_date_for_display(day.date, period),
                    revenue=day.total_revenue,
                    transaction_count=day.new_subscriptions,  # Approximate
                    successful_count=day.new_subscriptions,
                    failed_count=day.failed_transactions,
                )
                for day in daily_data
            ]

            # Calculate provider breakdown from daily analytics
            provider_breakdown = PaymentProviderBreakdown(
                razorpay_revenue=sum((d.razorpay_revenue for d in daily_data), Decimal(0)),
                stripe_revenue=sum((d.stripe_revenue for d in daily_data), Decimal(0)),
                razorpay_count=0,  # Not tracked in daily analytics
                stripe_count=0,
            )

            total_revenue = sum((d.total_revenue for d in daily_data), Decimal(0))
            total_transactions = sum((d.new_subscriptions for d in daily_data), 0)

        else:
            # For weekly/monthly, query transactions directly with date_trunc
            period_format = group_by_period(period)

            transactions_query = (
                select(
                    func.date_trunc(period_format, Transaction.created_at).label("period_start"),
                    func.sum(Transaction.amount).label("revenue"),
                    func.count(Transaction.id).label("transaction_count"),
                    func.count(case((Transaction.payment_status == PaymentStatus.CAPTURED, 1))).label(
                        "successful_count"
                    ),
                    func.count(case((Transaction.payment_status == PaymentStatus.FAILED, 1))).label("failed_count"),
                )
                .where(
                    and_(
                        Transaction.created_at >= datetime.combine(start_date, datetime.min.time()),
                        Transaction.created_at <= datetime.combine(end_date, datetime.max.time()),
                        Transaction.payment_status == PaymentStatus.CAPTURED,
                    )
                )
                .group_by("period_start")
                .order_by("period_start")
            )

            result = await db.execute(transactions_query)
            rows = result.all()

            data_points = [
                SalesDataPoint(
                    date=row.period_start.strftime("%Y-%m-%d"),
                    revenue=Decimal(str(row.revenue or 0)),
                    transaction_count=row.transaction_count or 0,
                    successful_count=row.successful_count or 0,
                    failed_count=row.failed_count or 0,
                )
                for row in rows
            ]

            # Get provider breakdown
            provider_query = select(
                func.sum(
                    case((Transaction.payment_provider == PaymentProvider.RAZORPAY, Transaction.amount), else_=0)
                ).label("razorpay_revenue"),
                func.sum(
                    case((Transaction.payment_provider == PaymentProvider.STRIPE, Transaction.amount), else_=0)
                ).label("stripe_revenue"),
                func.count(case((Transaction.payment_provider == PaymentProvider.RAZORPAY, 1))).label("razorpay_count"),
                func.count(case((Transaction.payment_provider == PaymentProvider.STRIPE, 1))).label("stripe_count"),
            ).where(
                and_(
                    Transaction.created_at >= datetime.combine(start_date, datetime.min.time()),
                    Transaction.created_at <= datetime.combine(end_date, datetime.max.time()),
                    Transaction.payment_status == PaymentStatus.CAPTURED,
                )
            )

            provider_result = await db.execute(provider_query)
            provider_row = provider_result.one()

            provider_breakdown = PaymentProviderBreakdown(
                razorpay_revenue=Decimal(str(provider_row.razorpay_revenue or 0)),
                stripe_revenue=Decimal(str(provider_row.stripe_revenue or 0)),
                razorpay_count=provider_row.razorpay_count or 0,
                stripe_count=provider_row.stripe_count or 0,
            )

            total_revenue = sum((dp.revenue for dp in data_points), Decimal(0))
            total_transactions = sum((dp.transaction_count for dp in data_points), 0)

        return SalesAnalyticsResponse(
            period=period,
            start_date=start_date,
            end_date=end_date,
            data_points=data_points,
            provider_breakdown=provider_breakdown,
            total_revenue=total_revenue,
            total_transactions=total_transactions,
        )

    @staticmethod
    async def get_traffic_analytics(
        period: Period, start_date: date, end_date: date, db: AsyncSession
    ) -> TrafficAnalyticsResponse:
        """Get traffic/user analytics for the specified period."""
        period_format = group_by_period(period)

        # Query users grouped by period
        users_query = (
            select(
                func.date_trunc(period_format, User.created_at).label("period_start"),
                func.count(User.id).label("new_users"),
            )
            .where(
                and_(
                    User.created_at >= datetime.combine(start_date, datetime.min.time()),
                    User.created_at <= datetime.combine(end_date, datetime.max.time()),
                )
            )
            .group_by("period_start")
            .order_by("period_start")
        )

        users_result = await db.execute(users_query)
        users_rows = users_result.all()

        # Get cumulative totals
        total_users_query = select(func.count(User.id)).where(
            User.created_at <= datetime.combine(end_date, datetime.max.time())
        )
        total_users_result = await db.execute(total_users_query)
        cumulative_total = total_users_result.scalar() or 0

        # Get current active users (with active subscriptions)
        active_users_query = select(func.count(distinct(Subscription.user_id))).where(
            and_(Subscription.status == "active", Subscription.period_end >= datetime.now())
        )
        active_users_result = await db.execute(active_users_query)
        current_active_users = active_users_result.scalar() or 0

        # Build data points
        data_points = []
        running_total = cumulative_total - sum((row.new_users for row in users_rows), 0)

        for row in users_rows:
            running_total += row.new_users or 0
            data_points.append(
                TrafficDataPoint(
                    date=row.period_start.strftime("%Y-%m-%d"),
                    new_users=row.new_users or 0,
                    active_users=current_active_users,  # Simplified - actual would need period-specific query
                    total_users=running_total,
                )
            )

        # Get registration source breakdown
        source_query = (
            select(User.created_via, func.count(User.id).label("count"))
            .where(
                and_(
                    User.created_at >= datetime.combine(start_date, datetime.min.time()),
                    User.created_at <= datetime.combine(end_date, datetime.max.time()),
                )
            )
            .group_by(User.created_via)
        )

        source_result = await db.execute(source_query)
        source_rows = source_result.all()

        source_breakdown = CreatedViaBreakdown()
        for row in source_rows:
            source_value = row.created_via.value.lower()
            if hasattr(source_breakdown, source_value):
                setattr(source_breakdown, source_value, row.count)

        # Calculate retention rate (simplified)
        retention_rate = (current_active_users / cumulative_total * 100) if cumulative_total > 0 else 0.0

        return TrafficAnalyticsResponse(
            period=period,
            start_date=start_date,
            end_date=end_date,
            data_points=data_points,
            source_breakdown=source_breakdown,
            total_new_users=sum((dp.new_users for dp in data_points), 0),
            current_active_users=current_active_users,
            retention_rate=round(retention_rate, 2),
        )

    @staticmethod
    async def get_plan_analytics(start_date: date, end_date: date, db: AsyncSession) -> PlanAnalyticsResponse:
        """Get analytics per plan."""
        # Query subscriptions and revenue per plan
        plan_query = (
            select(
                Plan.id.label("plan_id"),
                Plan.name.label("plan_name"),
                func.count(Subscription.id).label("subscription_count"),
                func.count(case((Subscription.status == "active", 1))).label("active_subscriptions"),
                func.count(distinct(Subscription.user_id)).label("active_users"),
                func.count(case((Subscription.status == "canceled", 1))).label("churn_count"),
            )
            .join(Subscription, Subscription.plan_id == Plan.id)
            .where(
                and_(
                    Subscription.created_at >= datetime.combine(start_date, datetime.min.time()),
                    Subscription.created_at <= datetime.combine(end_date, datetime.max.time()),
                )
            )
            .group_by(Plan.id, Plan.name)
        )

        plan_result = await db.execute(plan_query)
        plan_rows = plan_result.all()

        plans = []
        total_subscriptions = 0
        total_revenue = Decimal(0)

        for row in plan_rows:
            # Get revenue for this plan from transactions
            revenue_query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(
                    Transaction.plan_id == row.plan_id,
                    Transaction.payment_status == PaymentStatus.CAPTURED,
                    Transaction.created_at >= datetime.combine(start_date, datetime.min.time()),
                    Transaction.created_at <= datetime.combine(end_date, datetime.max.time()),
                )
            )
            revenue_result = await db.execute(revenue_query)
            plan_revenue = Decimal(str(revenue_result.scalar() or 0))

            churn_rate = (row.churn_count / row.subscription_count * 100) if row.subscription_count > 0 else 0.0

            plans.append(
                PlanAnalyticsItem(
                    plan_id=row.plan_id,
                    plan_name=row.plan_name,
                    subscription_count=row.subscription_count or 0,
                    active_subscriptions=row.active_subscriptions or 0,
                    total_revenue=plan_revenue,
                    active_users=row.active_users or 0,
                    churn_count=row.churn_count or 0,
                    churn_rate=round(churn_rate, 2),
                )
            )

            total_subscriptions += row.subscription_count or 0
            total_revenue += plan_revenue

        return PlanAnalyticsResponse(
            start_date=start_date,
            end_date=end_date,
            plans=plans,
            total_subscriptions=total_subscriptions,
            total_revenue=total_revenue,
        )

    @staticmethod
    async def get_dashboard_overview(db: AsyncSession) -> DashboardOverviewResponse:
        """Get quick overview stats for dashboard."""
        today = date.today()
        month_start = start_of_month(today)
        month_end = end_of_month(today)

        # Total users
        total_users_query = select(func.count(User.id))
        total_users = (await db.execute(total_users_query)).scalar() or 0

        # Active subscriptions
        active_subs_query = select(func.count(Subscription.id)).where(
            and_(Subscription.status == "active", Subscription.period_end >= datetime.now())
        )
        active_subscriptions = (await db.execute(active_subs_query)).scalar() or 0

        # Revenue today
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        revenue_today_query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(
                Transaction.created_at >= today_start,
                Transaction.created_at <= today_end,
                Transaction.payment_status == PaymentStatus.CAPTURED,
            )
        )
        total_revenue_today = Decimal(str((await db.execute(revenue_today_query)).scalar() or 0))

        # Revenue this month
        month_start_dt = datetime.combine(month_start, datetime.min.time())
        month_end_dt = datetime.combine(month_end, datetime.max.time())

        revenue_month_query = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(
                Transaction.created_at >= month_start_dt,
                Transaction.created_at <= month_end_dt,
                Transaction.payment_status == PaymentStatus.CAPTURED,
            )
        )
        total_revenue_month = Decimal(str((await db.execute(revenue_month_query)).scalar() or 0))

        # New users today
        new_users_today_query = select(func.count(User.id)).where(
            and_(User.created_at >= today_start, User.created_at <= today_end)
        )
        new_users_today = (await db.execute(new_users_today_query)).scalar() or 0

        # New users this month
        new_users_month_query = select(func.count(User.id)).where(
            and_(User.created_at >= month_start_dt, User.created_at <= month_end_dt)
        )
        new_users_month = (await db.execute(new_users_month_query)).scalar() or 0

        # Pending transactions
        pending_query = select(func.count(Transaction.id)).where(Transaction.payment_status == PaymentStatus.PENDING)
        pending_transactions = (await db.execute(pending_query)).scalar() or 0

        # Unmatched transactions
        unmatched_query = select(func.count(Transaction.id)).where(
            Transaction.reconciliation_status == ReconciliationStatus.UNMATCHED
        )
        unmatched_transactions = (await db.execute(unmatched_query)).scalar() or 0

        logger.info(
            f"Dashboard overview: {total_users} users, {active_subscriptions} active subs, "
            f"${total_revenue_today} revenue today, ${total_revenue_month} this month, "
            f"{new_users_today} new users today, {new_users_month} this month, "
            f"{pending_transactions} pending transactions, {unmatched_transactions} unmatched transactions"
        )
        return DashboardOverviewResponse(
            total_users=total_users,
            active_subscriptions=active_subscriptions,
            total_revenue_today=total_revenue_today,
            total_revenue_month=total_revenue_month,
            new_users_today=new_users_today,
            new_users_month=new_users_month,
            pending_transactions=pending_transactions,
            unmatched_transactions=unmatched_transactions,
        )
