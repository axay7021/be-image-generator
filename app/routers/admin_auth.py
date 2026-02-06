import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.settings import settings
from app.db import get_db
from app.db.schema import Admin, LoginHistory
from app.dependencies.auth import CurrentActiveAdmin
from app.dependencies.clerk_admin_auth import get_clerk_admin
from app.dto.auth_dto import (
    AdminResponse,
    LoginHistoryResponse,
    LoginRequest,
    OTPVerificationResponse,
    PasswordResetRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SessionResponse,
    TokenResponse,
    VerifyOTPRequest,
)
from app.i18n import msg
from app.services import admin_service
from app.utils.response import success_response

router = APIRouter(prefix="/admin/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Authenticate admin and return JWT tokens

    - **email**: Admin email address
    - **password**: Admin password
    """
    access_token, refresh_token = await admin_service.authenticate_admin(
        email=data.email,
        password=data.password,
        request=request,
        db=db,
    )

    token_data = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return success_response(
        data=token_data.model_dump(),
        message=msg("LOGIN_SUCCESS"),
        status_code=status.HTTP_200_OK,
    )


@router.post("/refresh", status_code=201)
async def refresh_token(
    request: Request,
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Refresh access token using refresh token

    - **refresh_token**: Valid refresh token
    """
    authorization = request.headers.get("authorization", "")

    access_token, new_refresh_token = await admin_service.refresh_admin_token(
        refresh_token_str=data.refresh_token,
        authorization=authorization,
        db=db,
    )

    token_data = TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return success_response(data=token_data.model_dump(), message=msg("TOKEN_REFRESHED"))


@router.post("/logout")
async def logout(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_admin: CurrentActiveAdmin,
    authorization: str = Header(),
):
    """
    Logout admin and revoke tokens
    """
    await admin_service.logout_admin(
        refresh_token_str=data.refresh_token,
        authorization=authorization,
        admin_id=current_admin.id,
        db=db,
    )

    return success_response(data=None, message=msg("LOGOUT_SUCCESS"))


@router.get("/me")
async def get_current_admin_info(current_admin: CurrentActiveAdmin):
    """
    Get current admin information
    """
    admin_data = AdminResponse.model_validate(current_admin)

    return success_response(data=admin_data.model_dump(), message=msg("ADMIN_PROFILE_RETRIEVED"))


# ============================================
# Password Reset Endpoints
# ============================================


@router.post("/password-reset/request")
async def request_password_reset(
    data: PasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Request password reset - sends OTP to email
    """
    otp_code = await admin_service.request_password_reset(email=data.email, db=db)

    # Always return same message (security)
    response_data = {"message": "If email exists, OTP has been sent"}
    if otp_code:
        response_data["otp"] = otp_code  # Only in development

    return success_response(data=response_data if otp_code else None, message=msg("OTP_SENT"))


@router.post("/password-reset/verify")
async def verify_password_reset_otp(
    data: VerifyOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Verify OTP code
    """
    is_valid, message = await admin_service.verify_password_reset_otp(email=data.email, otp=data.otp, db=db)

    otp_response = OTPVerificationResponse(message=message, valid=is_valid)
    return success_response(data=otp_response.model_dump(), message=message)


@router.post("/password-reset/reset")
async def reset_password(
    data: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Reset password with OTP
    """
    await admin_service.reset_password(email=data.email, otp=data.otp, new_password=data.new_password, db=db)

    return success_response(data=None, message=msg("PASSWORD_RESET_SUCCESS"))


# ============================================
# Session Management Endpoints
# ============================================


@router.get("/sessions")
async def get_sessions(
    request: Request,
    current_admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all active sessions for current admin
    """
    current_ip = request.client.host if request.client else "Unknown"

    sessions = await admin_service.get_admin_sessions(admin_id=current_admin.id, current_ip=current_ip, db=db)

    sessions_data = [
        SessionResponse(
            id=session.id,
            device_name=session.device_name,
            device_type=session.device_type.value,
            ip_address=session.ip_address,
            location=session.location,
            last_activity=session.last_activity,
            is_current=session.ip_address == current_ip,
            created_at=session.created_at,
        ).model_dump()
        for session in sessions
    ]

    return success_response(data=sessions_data, message=msg("SESSIONS_RETRIEVED"))


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Revoke a specific session
    """
    await admin_service.revoke_session(session_id=session_id, admin_id=current_admin.id, db=db)

    return success_response(data=None, message=msg("SESSION_REVOKED_SUCCESS"))


@router.delete("/sessions/all")
async def revoke_all_sessions(
    request: Request,
    current_admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Revoke all sessions except current one
    """
    current_ip = request.client.host if request.client else "Unknown"

    count = await admin_service.revoke_all_sessions(admin_id=current_admin.id, current_ip=current_ip, db=db)

    return success_response(data=None, message=msg("SESSIONS_REVOKED", count=count))


# ============================================
# Login History Endpoint
# ============================================


@router.get("/login-history")
async def get_login_history(
    current_admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
):
    """
    Get login history for current admin
    """
    # Note: Keeping simple queries in router is sometimes okay,
    # but for consistency we could move this to service too.
    # For now, I'll leverage the existing service structure or direct DB if simple.
    # To fully separate, let's keep it here but arguably this is "read" logic.
    # To follow strict separation requested, I should move this too?
    # The previous auth.py had logic mixed. I'll invoke direct DB here as it's a simple query
    # or add a service method if strictest separation is desired.
    # Given the previous context, let's keep simple read queries here or use a service method.
    # I'll create a quick helper in the service for this to be clean.
    # Wait, I didn't add get_login_history to service in previous step.
    # I will add it now or query directly. Querying directly is fine for read-only.

    query = (
        select(LoginHistory)
        .where(LoginHistory.admin_id == current_admin.id)
        .order_by(desc(LoginHistory.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    history = result.scalars().all()

    history_data = [
        LoginHistoryResponse(
            id=record.id,
            email=record.email,
            ip_address=record.ip_address,
            location=record.location,
            status=record.status.value,
            user_agent=record.user_agent,
            created_at=record.created_at,
        ).model_dump()
        for record in history
    ]

    return success_response(data=history_data, message=msg("LOGIN_HISTORY_RETRIEVED"))


# ============================================
# Clerk Admin Authentication
# ============================================


@router.get("/clerk/me")
async def get_clerk_admin_profile(
    current_admin: Annotated[Admin, Depends(get_clerk_admin)],
):
    """
    Get current admin profile (Clerk-authenticated).

    This endpoint is for admins who authenticate via Clerk.
    Returns admin profile information.
    """
    admin_data = AdminResponse(
        id=current_admin.id,
        email=current_admin.email,
        full_name=current_admin.full_name,
        role=current_admin.role.value,
        is_active=current_admin.is_active,
        created_at=current_admin.created_at,
        updated_at=current_admin.updated_at,
    ).model_dump()

    return success_response(data=admin_data, message="Admin profile retrieved successfully")


@router.post("/clerk/webhook")
async def clerk_admin_webhook(
    request: Request,
    svix_id: Annotated[str | None, Header(alias="svix-id")] = None,
    svix_timestamp: Annotated[str | None, Header(alias="svix-timestamp")] = None,
    svix_signature: Annotated[str | None, Header(alias="svix-signature")] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook endpoint for Clerk admin user sync.

    Handles events:
    - user.created: Create admin record when new admin signs up via Clerk
    - user.updated: Update admin info when changed in Clerk
    - user.deleted: Deactivate admin when deleted in Clerk
    """
    if not settings.ADMIN_CLERK_WEBHOOK_SECRET:
        return success_response(message="Admin Clerk webhook not configured", data={"processed": False})

    # Verify webhook signature
    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Svix headers")

    # Get the raw body
    body = await request.body()

    try:
        wh = Webhook(settings.ADMIN_CLERK_WEBHOOK_SECRET)
        payload = wh.verify(
            body, {"svix-id": svix_id, "svix-timestamp": svix_timestamp, "svix-signature": svix_signature}
        )
    except WebhookVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Webhook verification failed: {str(e)}")

    event_type = payload.get("type")
    data = payload.get("data", {})

    clerk_id = data.get("id")
    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (
            email["email_address"]
            for email in email_addresses
            if email.get("id") == data.get("primary_email_address_id")
        ),
        None,
    )

    if event_type in ["user.created", "user.updated"]:
        # Validate email against whitelist
        if settings.ADMIN_EMAILS:
            admin_emails = [e.strip() for e in settings.ADMIN_EMAILS.split(",")]
            if primary_email not in admin_emails:
                logger.warning(
                    f"Clerk webhook: Email {primary_email} not in admin whitelist, not creating admin record"
                )
                return success_response(
                    message=f"Email {primary_email} is not authorized as an admin",
                    data={"processed": False, "reason": "email_not_whitelisted"},
                    status_code=200,
                )

        # Extract name
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip() or primary_email.split("@")[0]

        # Sync admin
        await admin_service.sync_clerk_admin(
            clerk_id=clerk_id, email=primary_email, full_name=full_name, db=db, performed_by_type="ai_agent"
        )

        return success_response(
            message=f"Admin {event_type} processed successfully", data={"clerk_id": clerk_id, "email": primary_email}
        )

    elif event_type == "user.deleted":
        if not clerk_id:
            return success_response(message="Missing clerk_id in deletion event", data={"processed": False})

        # Deactivate admin
        result = await db.execute(select(Admin).where(Admin.clerk_id == clerk_id))
        admin = result.scalar_one_or_none()

        if admin:
            admin.is_active = False
            await db.commit()
            return success_response(message="Admin deactivated successfully", data={"clerk_id": clerk_id})

    return success_response(message=f"Event {event_type} received but not processed", data={"event_type": event_type})
