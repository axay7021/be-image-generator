from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ============================================
# Request DTOs
# ============================================


class LoginRequest(BaseModel):
    """Login request with email and password"""

    email: EmailStr
    password: str = Field(..., min_length=6)


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""

    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Request to reset password - send OTP"""

    email: EmailStr


class VerifyOTPRequest(BaseModel):
    """Verify OTP code"""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    """Reset password with OTP"""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)


# ============================================
# Response DTOs
# ============================================


class TokenResponse(BaseModel):
    """JWT token response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AdminResponse(BaseModel):
    """Admin user response"""

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    """Active session response"""

    id: str
    device_name: str
    device_type: str
    ip_address: str
    location: str | None = None
    last_activity: datetime
    is_current: bool
    created_at: datetime


class LoginHistoryResponse(BaseModel):
    """Login attempt history response"""

    id: str
    email: str
    ip_address: str
    location: str | None = None
    status: str
    user_agent: str
    created_at: datetime


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str


class OTPVerificationResponse(BaseModel):
    """OTP verification result"""

    message: str
    valid: bool
