"""Data Transfer Objects for Plan Management endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanCreateRequest(BaseModel):
    """Request to create a new plan."""

    name: str = Field(..., min_length=1, max_length=100, description="Plan name")
    price_usd: float = Field(..., gt=0, description="Price in USD")
    image_quota: int = Field(..., gt=0, description="Number of images allowed")
    validity_days: int = Field(..., gt=0, description="Plan validity in days")
    billing_interval: str | None = Field(None, description="For recurring: 'monthly' or 'yearly'")
    is_popular: bool = Field(default=False, description="Mark as popular plan")


class PlanUpdateRequest(BaseModel):
    """Request to update an existing plan."""

    name: str | None = Field(None, min_length=1, max_length=100, description="Plan name")
    price_usd: float | None = Field(None, gt=0, description="Price in USD")
    image_quota: int | None = Field(None, gt=0, description="Number of images allowed")
    validity_days: int | None = Field(None, gt=0, description="Plan validity in days")
    is_active: bool | None = Field(None, description="Active status")
    is_popular: bool | None = Field(None, description="Popular status")


class PlanResponse(BaseModel):
    """Response schema for plan details."""

    id: str = Field(..., description="Plan ID")
    name: str = Field(..., description="Plan name")
    price_usd: float = Field(..., description="Price in USD")
    image_quota: int = Field(..., description="Number of images allowed")
    validity_days: int = Field(..., description="Plan validity in days")
    billing_interval: str | None = Field(None, description="Billing interval if recurring")
    razorpay_plan_id: str | None = Field(None, description="Razorpay plan ID")
    is_active: bool = Field(..., description="Active status")
    is_popular: bool = Field(..., description="Popular status")
    created_at: datetime = Field(..., description="Creation date")
    updated_at: datetime = Field(..., description="Last update date")

    model_config = ConfigDict(from_attributes=True)


class PlanStatsResponse(BaseModel):
    """Response schema for plan statistics."""

    plan_id: str = Field(..., description="Plan ID")
    plan_name: str = Field(..., description="Plan name")
    total_subscriptions: int = Field(..., description="Total subscriptions count")
    active_subscriptions: int = Field(..., description="Active subscriptions count")
    canceled_subscriptions: int = Field(..., description="Canceled subscriptions count")
    expired_subscriptions: int = Field(..., description="Expired subscriptions count")
    quota_exhausted_subscriptions: int = Field(..., description="Quota exhausted subscriptions count")
    is_active: bool = Field(..., description="Plan active status")
    razorpay_plan_id: str | None = Field(None, description="Razorpay plan ID")


class PlanListResponse(BaseModel):
    """Response schema for list of plans."""

    plans: list[PlanResponse] = Field(..., description="List of plans")
    total: int = Field(..., description="Total count")
