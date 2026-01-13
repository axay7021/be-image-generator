"""User authentication endpoints"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_user_access_token,
    create_user_refresh_token,
    verify_user_refresh_token,
)
from app.core.settings import settings
from app.db import get_db
from app.db.schema import User, UserGender, UserSession
from app.dependencies.clerk_auth import ClerkUserId
from app.dependencies.user_auth import CurrentActiveUser
from app.dto.user_dto import (
    OTPVerificationResponse,
    UserChangePasswordRequest,
    UserForgotPasswordRequest,
    UserLoginRequest,
    UserRefreshTokenRequest,
    UserRegisterRequest,
    UserResetPasswordRequest,
    UserResponse,
    UserTokenResponse,
    UserVerifyOTPRequest,
)
from app.i18n import msg
from app.services import user_service
from app.services.oauth_service import oauth_service
from app.utils.response import success_response

router = APIRouter(prefix="/user/auth", tags=["User Authentication"])


# ============================================
# Web Authentication Endpoints
# ============================================


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    data: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Register a new user with email and password
    """
    # Create user
    user = await user_service.create_user_from_web(
        email=data.email,
        password=data.password,
        full_name=data.full_name,
        db=db,
    )

    # Authenticate user (generate tokens and create session)
    user, access_token, refresh_token = await user_service.authenticate_web_user(
        email=data.email,
        password=data.password,
        request=request,
        db=db,
    )

    token_data = UserTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    user_data = UserResponse.model_validate(user)

    return success_response(
        data={
            "tokens": token_data.model_dump(),
            "user": user_data.model_dump(),
        },
        message=msg("REGISTRATION_SUCCESS"),
        status_code=status.HTTP_201_CREATED,
    )


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    data: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Login with email and password
    """
    # Authenticate user
    user, access_token, refresh_token = await user_service.authenticate_web_user(
        email=data.email,
        password=data.password,
        request=request,
        db=db,
    )

    token_data = UserTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    user_data = UserResponse.model_validate(user)

    return success_response(
        data={
            "tokens": token_data.model_dump(),
            "user": user_data.model_dump(),
        },
        message=msg("LOGIN_SUCCESS"),
        status_code=status.HTTP_200_OK,
    )


# ============================================
# Clerk Authentication (Next.js)
# ============================================


@router.get("/clerk/auth-check", status_code=status.HTTP_200_OK)
async def clerk_auth_check(
    clerk_user_id: ClerkUserId,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Verify Clerk authentication and return access/refresh tokens.

    This endpoint:
    1. Validates the Clerk JWT token from Next.js
    2. Gets or creates the user in the local database
    3. Issues access and refresh tokens for your system
    4. Returns tokens and user data

    Usage:
        Authorization: Bearer <clerk_jwt_token>
    """
    # Get or create user in database and generate tokens
    user, access_token, refresh_token = await user_service.get_or_create_clerk_user(
        clerk_user_id=clerk_user_id,
        request=request,
        db=db,
    )

    token_data = UserTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    user_data = UserResponse.model_validate(user)

    return success_response(
        data={
            "tokens": token_data.model_dump(),
            "user": user_data.model_dump(),
        },
        message=msg("LOGIN_SUCCESS"),
        status_code=status.HTTP_200_OK,
    )


# ============================================
# Google OAuth
# ============================================


@router.get("/google/login", status_code=status.HTTP_200_OK)
async def google_login() -> Any:
    """
    Get Google OAuth login URL
    """
    auth_url = oauth_service.get_google_auth_url()
    return success_response(
        data={"auth_url": auth_url},
        message="Google Auth URL generated",
    )


@router.get("/google/callback", status_code=status.HTTP_200_OK)
async def google_callback(
    code: str,
    req: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """
    Handle Google OAuth callback
    """
    try:
        # Get Google user info
        google_user = await oauth_service.get_google_user(code)

        # Get or create user
        user, access_token, refresh_token = await user_service.get_or_create_google_user(
            google_user_data=google_user,
            request=req,
            db=db,
        )

        token_data = UserTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

        user_data = UserResponse.model_validate(user)

        return success_response(
            data={
                "tokens": token_data.model_dump(),
                "user": user_data.model_dump(),
            },
            message=msg("LOGIN_SUCCESS"),
            status_code=status.HTTP_200_OK,
        )
    except Exception as e:
        # Log error in production
        print(f"Google login error: {e}")
        raise HTTPException(  # noqa: B904
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg("GOOGLE_LOGIN_FAILED"),
        )


# ============================================
# Token Management Endpoints
# ============================================


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_token(
    request: Request,
    data: UserRefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token using refresh token
    """
    # Decode refresh token
    payload = verify_user_refresh_token(data.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")

    # Find session with this refresh token
    query = select(UserSession).where(
        UserSession.refresh_token == data.refresh_token,
        UserSession.user_id == user_id,
        UserSession.is_active.is_(True),
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or expired",
        )

    # Check if refresh token is expired
    if session.refresh_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    # Get user
    user_query = select(User).where(User.id == user_id)
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found or inactive",
        )

    # Generate new tokens
    new_access_token, new_access_jti = create_user_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_user_refresh_token(user_id=str(user.id))

    # Decode new tokens to get expiration
    new_access_payload = verify_user_refresh_token(new_access_token)
    new_refresh_payload = verify_user_refresh_token(new_refresh_token)

    new_access_expires = (
        datetime.fromtimestamp(new_access_payload["exp"], tz=timezone.utc)
        if new_access_payload
        else datetime.now(timezone.utc) + timedelta(minutes=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    new_refresh_expires = (
        datetime.fromtimestamp(new_refresh_payload["exp"], tz=timezone.utc)
        if new_refresh_payload
        else datetime.now(timezone.utc) + timedelta(days=settings.USER_REFRESH_TOKEN_EXPIRE_DAYS)
    )

    # Update session with new tokens
    session.access_token = new_access_token
    session.refresh_token = new_refresh_token
    session.access_token_jti = new_access_jti
    session.access_expires_at = new_access_expires
    session.refresh_expires_at = new_refresh_expires
    session.last_activity = datetime.now(timezone.utc)

    await db.commit()

    token_data = UserTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return success_response(
        data=token_data.model_dump(),
        message=msg("TOKEN_REFRESHED"),
        status_code=status.HTTP_200_OK,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    current_user: CurrentActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Logout user and revoke current session
    """
    # Get access token from header
    authorization = request.headers.get("Authorization")
    if not authorization:
        return success_response(data=None, message=msg("LOGOUT_SUCCESS"))

    scheme, _, token = authorization.partition(" ")

    # Delete current session
    if token:
        await db.execute(delete(UserSession).where(UserSession.access_token == token))
        await db.commit()

    return success_response(data=None, message=msg("LOGOUT_SUCCESS"))


# ============================================
# Profile Endpoints
# ============================================


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user_info(current_user: CurrentActiveUser):
    """
    Get current user information
    """
    user_data = UserResponse.model_validate(current_user)

    return success_response(
        data=user_data.model_dump(),
        message=msg("PROFILE_RETRIEVED"),
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    current_user: CurrentActiveUser,
    data: UserChangePasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Change user's password
    """
    # Change password
    await user_service.change_user_password(
        user_id=current_user.id,
        old_password=data.old_password,
        new_password=data.new_password,
        db=db,
    )

    return success_response(
        data=None,
        message=msg("PASSWORD_CHANGED"),
    )


# ============================================
# Password Reset Endpoints
# ============================================


@router.post("/password-reset/request")
async def request_password_reset(
    data: UserForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Request password reset - sends OTP to email
    """
    otp_code = await user_service.request_password_reset(email=data.email, db=db)

    # Always return same message (security)
    response_data = {"message": "If email exists, OTP has been sent"}
    if otp_code:
        response_data["otp"] = otp_code  # Only in development

    return success_response(data=response_data if otp_code else None, message=msg("OTP_SENT"))


@router.post("/password-reset/verify")
async def verify_password_reset_otp(
    data: UserVerifyOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Verify OTP code
    """
    is_valid, message = await user_service.verify_password_reset_otp(email=data.email, otp=data.otp, db=db)

    otp_response = OTPVerificationResponse(message=message, valid=is_valid)
    return success_response(data=otp_response.model_dump(), message=message)


@router.post("/password-reset/reset")
async def reset_password(
    data: UserResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Reset password with OTP
    """
    await user_service.reset_password_with_otp(email=data.email, otp=data.otp, new_password=data.new_password, db=db)

    return success_response(data=None, message=msg("PASSWORD_RESET_SUCCESS"))
