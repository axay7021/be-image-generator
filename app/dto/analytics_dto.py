"""Data Transfer Objects for Analytics endpoints."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["daily", "weekly", "monthly"]


class SalesDataPoint(BaseModel):
    """Single data point for sales analytics."""

    date: str = Field(..., description="Date or period label")
    revenue: Decimal = Field(..., description="Total revenue for the period")
    transaction_count: int = Field(..., description="Number of transactions")
    successful_count: int = Field(..., description="Successful transactions")
    failed_count: int = Field(..., description="Failed transactions")


class PaymentProviderBreakdown(BaseModel):
    """Revenue breakdown by payment provider."""

    razorpay_revenue: Decimal = Field(..., description="Revenue from Razorpay")
    stripe_revenue: Decimal = Field(..., description="Revenue from Stripe")
    razorpay_count: int = Field(..., description="Number of Razorpay transactions")
    stripe_count: int = Field(..., description="Number of Stripe transactions")


class SalesAnalyticsResponse(BaseModel):
    """Response schema for sales analytics."""

    period: Period = Field(..., description="Aggregation period")
    start_date: date = Field(..., description="Start date of the range")
    end_date: date = Field(..., description="End date of the range")
    data_points: list[SalesDataPoint] = Field(..., description="Time series data")
    provider_breakdown: PaymentProviderBreakdown = Field(..., description="Payment provider breakdown")
    total_revenue: Decimal = Field(..., description="Total revenue in the period")
    total_transactions: int = Field(..., description="Total transaction count")


class TrafficDataPoint(BaseModel):
    """Single data point for traffic analytics."""

    date: str = Field(..., description="Date or period label")
    new_users: int = Field(..., description="New user registrations")
    active_users: int = Field(..., description="Users with active subscriptions")
    total_users: int = Field(..., description="Cumulative total users")


class CreatedViaBreakdown(BaseModel):
    """User registration source breakdown."""

    web: int = Field(default=0, description="Users created via web")
    google: int = Field(default=0, description="Users created via Google OAuth")
    clerk: int = Field(default=0, description="Users created via Clerk")
    line: int = Field(default=0, description="Users created via LINE")
    ai_call: int = Field(default=0, description="Users created via AI call")


class TrafficAnalyticsResponse(BaseModel):
    """Response schema for traffic analytics."""

    period: Period = Field(..., description="Aggregation period")
    start_date: date = Field(..., description="Start date of the range")
    end_date: date = Field(..., description="End date of the range")
    data_points: list[TrafficDataPoint] = Field(..., description="Time series data")
    source_breakdown: CreatedViaBreakdown = Field(..., description="Registration source breakdown")
    total_new_users: int = Field(..., description="Total new users in the period")
    current_active_users: int = Field(..., description="Currently active users")
    retention_rate: float = Field(..., description="Retention rate percentage")


class PlanAnalyticsItem(BaseModel):
    """Analytics for a single plan."""

    plan_id: str = Field(..., description="Plan ID")
    plan_name: str = Field(..., description="Plan name")
    subscription_count: int = Field(..., description="Total subscriptions (all time)")
    active_subscriptions: int = Field(..., description="Currently active subscriptions")
    total_revenue: Decimal = Field(..., description="Total revenue from this plan")
    active_users: int = Field(..., description="Number of users with active subscriptions")
    churn_count: int = Field(..., description="Number of canceled subscriptions")
    churn_rate: float = Field(..., description="Churn rate percentage")


class PlanAnalyticsResponse(BaseModel):
    """Response schema for plan analytics."""

    start_date: date = Field(..., description="Start date of the range")
    end_date: date = Field(..., description="End date of the range")
    plans: list[PlanAnalyticsItem] = Field(..., description="Analytics per plan")
    total_subscriptions: int = Field(..., description="Total subscriptions across all plans")
    total_revenue: Decimal = Field(..., description="Total revenue across all plans")


class DashboardOverviewResponse(BaseModel):
    """Quick overview stats for admin dashboard."""

    total_users: int = Field(..., description="Total registered users")
    active_subscriptions: int = Field(..., description="Currently active subscriptions")
    total_revenue_today: Decimal = Field(..., description="Revenue today")
    total_revenue_month: Decimal = Field(..., description="Revenue this month")
    new_users_today: int = Field(..., description="New users today")
    new_users_month: int = Field(..., description="New users this month")
    pending_transactions: int = Field(..., description="Transactions awaiting payment")
    unmatched_transactions: int = Field(..., description="Transactions needing reconciliation")
