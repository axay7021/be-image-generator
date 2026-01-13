"""Data Transfer Objects (DTOs) for user-related requests and responses"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================
# Request DTOs
# ============================================


class LineTokenVerifyRequest(BaseModel):
    """Request to verify LINE access token"""

    access_token: str = Field(..., description="LINE access token from client")


class LineLoginRequest(BaseModel):
    """Request to login/register with LINE credentials"""

    line_id: str = Field(..., description="LINE user ID")
    line_name: str = Field(..., description="LINE display name")
    picture_url: str | None = Field(None, description="LINE profile picture URL")


class UserUpdateProfileRequest(BaseModel):
    """Request to update user profile"""

    full_name: str | None = Field(None, min_length=1, max_length=255)
    phone_number: str | None = Field(None, max_length=20)
    gender: str | None = Field(None, pattern="^(male|female|other)$")
    email: str | None = Field(None, max_length=255)


class UserRefreshTokenRequest(BaseModel):
    """Request to refresh access token"""

    refresh_token: str


class UserRegisterRequest(BaseModel):
    """Request to register new user with email and password"""

    email: str = Field(
        ...,
        description="Email address",
        pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    )
    password: str = Field(..., min_length=8, max_length=100, description="Password (min 8 characters)")
    full_name: str | None = Field(None, min_length=1, max_length=255, description="User's full name")
    phone_number: str | None = Field(None, min_length=10, max_length=13, description="Optional Phone number")
    gender: str | None = Field(None, pattern="^(male|female|other)$", description="Optional gender")

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str | None) -> str | None:
        """Validate phone number format if provided"""
        if not v:
            return None

        # Remove any spaces, dashes, or plus signs
        cleaned = re.sub(r"[\s\-+]", "", v)

        # Indian phone numbers: 10 digits, starting with 6-9
        indian_pattern = r"^(?:\+91)?[6-9]\d{9}$"

        # Japanese phone numbers:
        japanese_pattern = r"^(?:\+81|0)(?:70|80|90)\d{8}$"

        if re.match(indian_pattern, cleaned):
            return cleaned.replace("+91", "") if cleaned.startswith("+91") else cleaned
        elif re.match(japanese_pattern, cleaned):
            if cleaned.startswith("+81"):
                return "0" + cleaned[3:]
            return cleaned
        else:
            raise ValueError("Invalid phone number format.")


class UserLoginRequest(BaseModel):
    """Request to login with email and password"""

    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class UserChangePasswordRequest(BaseModel):
    """Request to change password (authenticated user)"""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password (min 8 characters)")


class UserForgotPasswordRequest(BaseModel):
    """Request to initiate password reset"""

    email: str = Field(..., description="Registered email address")


class UserVerifyOTPRequest(BaseModel):
    """Request to verify OTP for password reset"""

    email: str = Field(..., description="Registered email address")
    otp: str = Field(..., description="OTP code received via email")


class UserResetPasswordRequest(BaseModel):
    """Request to reset password with OTP"""

    email: str = Field(..., description="Registered email address")
    otp: str = Field(..., description="OTP code")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password")


# ============================================
# Response DTOs
# ============================================


class LineUserDataResponse(BaseModel):
    """LINE user data from token verification"""

    line_id: str
    display_name: str
    picture_url: str | None = None


class UserTokenResponse(BaseModel):
    """JWT token response for user"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """User profile response"""

    id: str
    email: str | None = None
    full_name: str
    is_active: bool
    created_via: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSessionResponse(BaseModel):
    """Active session response"""

    id: str
    device_name: str
    device_type: str
    ip_address: str
    location: str | None = None
    last_activity: datetime
    created_at: datetime


class UserLoginHistoryResponse(BaseModel):
    """Login attempt history response"""

    id: str
    phone_number: str | None = None
    line_id: str | None = None
    ip_address: str
    location: str | None = None
    status: str
    user_agent: str
    created_at: datetime


class OTPVerificationResponse(BaseModel):
    """Response for OTP verification"""

    message: str
    valid: bool
