from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base

# ============================================
# Enums
# ============================================


class UserGender(str, PyEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class CreatedVia(str, PyEnum):
    WEB = "WEB"
    LINE = "LINE"
    AI_CALL = "AI_CALL"
    GOOGLE = "GOOGLE"
    CLERK = "CLERK"


class AdminRole(str, PyEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    STAFF = "staff"


class ActivityAction(str, PyEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CANCEL = "cancel"


class PerformedByType(str, PyEnum):
    ADMIN = "admin"
    USER = "user"
    AI_AGENT = "ai_agent"


class DeviceType(str, PyEnum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"
    UNKNOWN = "unknown"


class LoginStatus(str, PyEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class OTPPurpose(str, PyEnum):
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


# ============================================
# Models
# ============================================


class Admin(Base):
    """Admin users who manage the system"""

    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), nullable=False, default=AdminRole.STAFF)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="admin")
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="admin")
    login_history: Mapped[list["LoginHistory"]] = relationship("LoginHistory", back_populates="admin")


class User(Base):
    """Customer accounts who book appointments"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Contact Information (at least one required: phone OR line_id OR email)
    phone_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)

    # Password for web authentication (nullable - LINE/AI/Google users don't have passwords)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Google Integration
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Clerk Integration
    clerk_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)

    # LINE Integration (optional - for LINE mini app users)
    line_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    line_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # line_picture_url can be reused or removed if avatar_url is generic, keeping both for safety or migrating.
    # User requested avatar_url, let's keep line_picture_url for specific line usage if needed, or map avatar_url to it.
    # The prompt implies a new field. Let's keep line_picture_url for backward compatibility/clarity
    line_picture_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # User Details
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[UserGender | None] = mapped_column(Enum(UserGender), nullable=True)

    # Status & Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_via: Mapped[CreatedVia] = mapped_column(Enum(CreatedVia), nullable=False, default=CreatedVia.WEB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user_session: Mapped[list["UserSession"]] = relationship("UserSession", back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user")


class ActivityLog(Base):
    """Audit trail for all system activities"""

    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[ActivityAction] = mapped_column(Enum(ActivityAction), nullable=False)
    performed_by_type: Mapped[PerformedByType] = mapped_column(Enum(PerformedByType), nullable=False, index=True)
    performed_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class RefreshToken(Base):
    """Refresh tokens for admin authentication"""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("admins.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    admin: Mapped["Admin"] = relationship("Admin", back_populates="refresh_tokens")
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="refresh_token")


class Session(Base):
    """Active sessions for admin users with device tracking"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("admins.id"), nullable=False, index=True)
    refresh_token_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("refresh_tokens.id"), nullable=True)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType), nullable=False, default=DeviceType.UNKNOWN)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    admin: Mapped["Admin"] = relationship("Admin", back_populates="sessions")
    refresh_token: Mapped[Optional["RefreshToken"]] = relationship("RefreshToken", back_populates="sessions")


class ActiveToken(Base):
    """Whitelist of currently valid access tokens"""

    __tablename__ = "active_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    jti: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )  # JWT ID - unique identifier for this token
    admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("admins.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # When this token will expire naturally

    # Relationships
    admin: Mapped["Admin"] = relationship("Admin")


class LoginHistory(Base):
    """Login attempt history for security auditing"""

    __tablename__ = "login_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admins.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[LoginStatus] = mapped_column(Enum(LoginStatus), nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    admin: Mapped[Optional["Admin"]] = relationship("Admin", back_populates="login_history")


class EmailOTP(Base):
    """Email OTP codes for password reset and verification"""

    __tablename__ = "email_otps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    otp_code: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[OTPPurpose] = mapped_column(Enum(OTPPurpose), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserSession(Base):
    """Active session for user (only one session per user allowed)"""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Tokens stored directly in session (simplified for single session)
    access_token: Mapped[str] = mapped_column(String(500), nullable=False)
    refresh_token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    access_token_jti: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )  # JWT ID for access token

    # Session metadata
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(Enum(DeviceType), nullable=False, default=DeviceType.UNKNOWN)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Expiration
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Activity tracking
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_session")


class UserLoginHistory(Base):
    """Login attempt history for users"""

    __tablename__ = "user_login_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    # Login identifier (phone or line_id)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    line_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Request metadata
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Result
    status: Mapped[LoginStatus] = mapped_column(Enum(LoginStatus), nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")


# ============================================
# Subscription & Quota System Models
# ============================================


class Plan(Base):
    """Subscription plans managed by admin"""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    image_quota: Mapped[int] = mapped_column(Integer, nullable=False)
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_interval: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # e.g., "month", "year", None for one-time
    validity_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )  # Plan validity period (e.g., 30, 180 days)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    """User subscriptions to plans"""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="active", index=True
    )  # active, quota_exhausted, expired, canceled
    image_generation_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # Expiration date
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship("Plan", back_populates="subscriptions")


class DailyUsage(Base):
    """Track daily usage for free tier enforcement"""

    __tablename__ = "daily_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # user_id or ip_address
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Ensure unique record per identifier per day
    __table_args__ = (UniqueConstraint("identifier", "date", name="uq_daily_usage_identifier_date"),)


class ImageLog(Base):
    """Audit log for image generation usage and costs"""

    __tablename__ = "image_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # modify-image, upscale
    gemini_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_inr: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="image_logs")


# Update User model to include relationships
User.subscriptions = relationship("Subscription", back_populates="user")
User.user_session = relationship("UserSession", back_populates="user")
User.image_logs = relationship("ImageLog", back_populates="user")
