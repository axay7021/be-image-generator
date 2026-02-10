from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlanBase(BaseModel):
    name: str = Field(..., description="Name of the plan (e.g., Basic, Pro)")
    price_usd: float = Field(..., description="Price in USD")
    image_quota: int = Field(..., description="Number of images allowed")
    stripe_price_id: str = Field(..., description="Stripe Price ID")
    razorpay_plan_id: str | None = Field(default=None, description="Razorpay Plan ID (optional)")
    razorpay_payment_page_id: str | None = Field(default=None, description="Razorpay Payment Page ID (optional)")
    billing_interval: str | None = Field(default=None, description="Billing interval (month/year) or None for one-time")
    validity_days: int = Field(default=30, description="Plan validity in days (e.g., 30, 180)")
    is_popular: bool = Field(default=False, description="Whether this is a popular plan")


class PlanCreateRequest(PlanBase):
    pass


class PlanResponse(PlanBase):
    id: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionResponse(BaseModel):
    id: str
    plan: PlanResponse
    status: str
    image_generation_limit: int
    quota_used: int
    period_start: datetime
    period_end: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckoutData(BaseModel):
    url: str | None = None
    direct_access: bool = False
    subscription_id: str | None = None


class CheckoutResponse(BaseModel):
    success: bool
    message: str
    data: CheckoutData
