"""Data Transfer Objects for User Management endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.schema import CreatedVia, UserGender
from app.dto.subscription_dto import SubscriptionResponse


class UserListFilters(BaseModel):
    """Filters for user list endpoint."""

    search: str | None = Field(None, description="Search by email, phone, or name")
    is_active: bool | None = Field(None, description="Filter by active status")
    created_via: CreatedVia | None = Field(None, description="Filter by registration source")
    has_active_subscription: bool | None = Field(None, description="Filter by subscription status")
    skip: int = Field(default=0, ge=0, description="Number of records to skip")
    limit: int = Field(default=50, ge=1, le=100, description="Maximum records to return")


class UserListItem(BaseModel):
    """Condensed user info for list view."""

    id: str = Field(..., description="User ID")
    email: str | None = Field(None, description="User email")
    phone_number: str | None = Field(None, description="User phone number")
    full_name: str = Field(..., description="Full name")
    is_active: bool = Field(..., description="Active status")
    created_via: CreatedVia = Field(..., description="Registration source")
    created_at: datetime = Field(..., description="Registration date")
    has_active_subscription: bool = Field(..., description="Has any active subscription")
    total_quota_used: int = Field(default=0, description="Total quota used across all subscriptions")

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """Response schema for paginated user list."""

    users: list[UserListItem] = Field(..., description="List of users")
    total: int = Field(..., description="Total count matching filters")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum records returned")


class QuotaSummary(BaseModel):
    """User's quota usage summary."""

    total_limit: int = Field(..., description="Total quota across all active subscriptions")
    total_used: int = Field(..., description="Total quota used")
    remaining: int = Field(..., description="Remaining quota")
    subscriptions_count: int = Field(..., description="Number of active subscriptions")


class UserDetailResponse(BaseModel):
    """Detailed user information."""

    id: str = Field(..., description="User ID")
    email: str | None = Field(None, description="User email")
    phone_number: str | None = Field(None, description="User phone number")
    full_name: str = Field(..., description="Full name")
    gender: UserGender | None = Field(None, description="Gender")
    avatar_url: str | None = Field(None, description="Avatar URL")
    is_active: bool = Field(..., description="Active status")
    created_via: CreatedVia = Field(..., description="Registration source")
    created_at: datetime = Field(..., description="Registration date")
    updated_at: datetime = Field(..., description="Last update date")

    # Additional details
    subscriptions: list[SubscriptionResponse] = Field(..., description="User's subscriptions")
    transaction_count: int = Field(..., description="Total transaction count")
    quota_summary: QuotaSummary = Field(..., description="Quota usage summary")

    # OAuth/Integration IDs
    google_id: str | None = Field(None, description="Google OAuth ID")
    clerk_id: str | None = Field(None, description="Clerk ID")
    line_id: str | None = Field(None, description="LINE ID")

    model_config = ConfigDict(from_attributes=True)


class UserStatusUpdateRequest(BaseModel):
    """Request to update user status."""

    is_active: bool = Field(..., description="New active status")
    reason: str | None = Field(None, description="Reason for status change")


class UserActivityLogItem(BaseModel):
    """Single activity log entry."""

    id: str = Field(..., description="Log ID")
    action: str = Field(..., description="Action performed")
    gemini_tokens_used: int | None = Field(None, description="Tokens used")
    cost_inr: float | None = Field(None, description="Cost in INR")
    timestamp: datetime = Field(..., description="When the action occurred")

    model_config = ConfigDict(from_attributes=True)


class UserActivityResponse(BaseModel):
    """Response schema for user activity logs."""

    activity_logs: list[UserActivityLogItem] = Field(..., description="Activity log entries")
    total: int = Field(..., description="Total activity count")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum records returned")
