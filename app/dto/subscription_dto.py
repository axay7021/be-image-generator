from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class PlanBase(BaseModel):
    name: str = Field(..., description="Name of the plan (e.g., Basic, Pro)")
    price_usd: float = Field(..., description="Price in USD")
    image_quota: int = Field(..., description="Number of images allowed")
    stripe_price_id: str = Field(..., description="Stripe Price ID")
    validity_days: int = Field(default=30, description="Plan validity in days (e.g., 30, 180)")


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
    period_end: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckoutData(BaseModel):
    url: str


class CheckoutResponse(BaseModel):
    success: bool
    message: str
    data: CheckoutData
