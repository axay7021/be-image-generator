"""Admin service for authentication and management"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    get_password_hash,
    hash_otp,
    parse_user_agent,
    verify_access_token,
    verify_otp,
    verify_password,
    verify_refresh_token,
)
from app.core.settings import settings
from app.db.schema import (
    ActiveToken,
    Admin,
    DeviceType,
    EmailOTP,
    LoginHistory,
    LoginStatus,
    OTPPurpose,
    RefreshToken,
    Session,
)
from app.i18n import msg
from app.services.email_service import email_service


async def authenticate_admin(email: str, password: str, request: Request, db: AsyncSession) -> tuple[str, str]:
    """
    Authenticate admin and return tokens
    """
    # Get request metadata
    user_agent = request.headers.get("user-agent", "Unknown")
    ip_address = request.client.host if request.client else "Unknown"

    # Find admin by email
    query = select(Admin).where(Admin.email == email)
    result = await db.execute(query)
    admin = result.scalar_one_or_none()

    # Log failed attempt if admin not found
    if not admin:
        login_log = LoginHistory(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            status=LoginStatus.FAILED,
            failure_reason="Invalid email",
        )
        db.add(login_log)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Verify password
    if not verify_password(password, admin.password_hash):
        login_log = LoginHistory(
            admin_id=admin.id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            status=LoginStatus.FAILED,
            failure_reason="Invalid password",
        )
        db.add(login_log)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if admin is active
    if not admin.is_active:
        login_log = LoginHistory(
            admin_id=admin.id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            status=LoginStatus.BLOCKED,
            failure_reason="Account inactive",
        )
        db.add(login_log)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Parse device info
    device_info = parse_user_agent(user_agent)

    # -----------------------------------------------------
    # Enforce Single Session: Invalidate all previous sessions
    # -----------------------------------------------------
    # Revoke all refresh tokens
    await db.execute(update(RefreshToken).where(RefreshToken.admin_id == admin.id).values(is_revoked=True))

    # Deactivate all sessions
    await db.execute(update(Session).where(Session.admin_id == admin.id).values(is_active=False))

    # Delete all active access tokens
    await db.execute(delete(ActiveToken).where(ActiveToken.admin_id == admin.id))

    await db.flush()

    # Generate tokens
    access_token, access_jti = create_access_token(data={"sub": str(admin.id), "role": admin.role.value})
    refresh_token_str = create_refresh_token(admin_id=str(admin.id))

    # Decode refresh token to get expiration
    refresh_payload = verify_refresh_token(refresh_token_str)
    if not refresh_payload:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate refresh token",
        )
    refresh_expires = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)

    # Create refresh token record
    refresh_token = RefreshToken(
        admin_id=admin.id,
        token=refresh_token_str,
        device_info=user_agent,
        ip_address=ip_address,
        expires_at=refresh_expires,
    )
    db.add(refresh_token)
    await db.flush()  # Get refresh token ID

    # Create session
    session = Session(
        admin_id=admin.id,
        refresh_token_id=refresh_token.id,
        device_name=device_info["name"],
        device_type=DeviceType(device_info["type"]),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)

    # Add access token to whitelist
    access_payload = verify_access_token(access_token)
    if not access_payload:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate access token",
        )
    access_expires = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)

    active_token = ActiveToken(jti=access_jti, admin_id=admin.id, expires_at=access_expires)
    db.add(active_token)

    # Log successful login
    login_log = LoginHistory(
        admin_id=admin.id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        status=LoginStatus.SUCCESS,
    )
    db.add(login_log)

    await db.commit()

    return access_token, refresh_token_str


async def refresh_admin_token(refresh_token_str: str, authorization: str, db: AsyncSession) -> tuple[str, str]:
    """Refresh admin access token"""
    # Decode refresh token
    payload = verify_refresh_token(refresh_token_str)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    admin_id = payload.get("sub")

    # Find refresh token in database
    query = select(RefreshToken).where(RefreshToken.token == refresh_token_str, RefreshToken.admin_id == admin_id)
    result = await db.execute(query)
    stored_token = result.scalar_one_or_none()

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )

    # Check if token is revoked
    if stored_token.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    # Check if token is expired
    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    # Get admin
    query = select(Admin).where(Admin.id == admin_id)
    result = await db.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin not found or inactive",
        )

    # Delete old access token from whitelist (if provided)
    if authorization and authorization.startswith("Bearer "):
        old_access_token = authorization.replace("Bearer ", "")
        old_payload = verify_access_token(old_access_token)
        if old_payload and old_payload.get("jti"):
            await db.execute(delete(ActiveToken).where(ActiveToken.jti == old_payload["jti"]))

    # Create new access token with jti
    access_token, new_access_jti = create_access_token(data={"sub": str(admin.id), "role": admin.role.value})

    # Add new access token to whitelist
    access_payload = verify_access_token(access_token)
    if not access_payload:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate access token",
        )
    access_expires = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)

    new_active_token = ActiveToken(jti=new_access_jti, admin_id=admin.id, expires_at=access_expires)
    db.add(new_active_token)

    # Create new refresh token (rotation)
    new_refresh_token_str = create_refresh_token(admin_id=str(admin.id))

    # Revoke old refresh token
    stored_token.is_revoked = True

    # Create new refresh token record
    new_refresh_payload = verify_refresh_token(new_refresh_token_str)
    if not new_refresh_payload:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate refresh token",
        )
    new_refresh_expires = datetime.fromtimestamp(new_refresh_payload["exp"], tz=timezone.utc)

    new_refresh_token = RefreshToken(
        admin_id=admin.id,
        token=new_refresh_token_str,
        device_info=stored_token.device_info,
        ip_address=stored_token.ip_address,
        expires_at=new_refresh_expires,
    )
    db.add(new_refresh_token)

    await db.commit()

    return access_token, new_refresh_token_str


async def logout_admin(refresh_token_str: str, authorization: str, admin_id: str, db: AsyncSession) -> None:
    """Logout admin"""
    # Extract and delete current access token from whitelist
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        payload = verify_access_token(token)

        if payload and payload.get("jti"):
            # Delete access token from whitelist
            await db.execute(delete(ActiveToken).where(ActiveToken.jti == payload["jti"]))

    # Revoke refresh token
    query = select(RefreshToken).where(
        RefreshToken.token == refresh_token_str,
        RefreshToken.admin_id == admin_id,
        RefreshToken.is_revoked.is_(False),
    )
    result = await db.execute(query)
    refresh_token = result.scalar_one_or_none()

    if refresh_token:
        refresh_token.is_revoked = True

        # Deactivate associated sessions
        sessions_query = select(Session).where(
            Session.refresh_token_id == refresh_token.id,
            Session.is_active.is_(True),
        )
        sessions_result = await db.execute(sessions_query)
        sessions = sessions_result.scalars().all()

        for session in sessions:
            session.is_active = False

        await db.commit()


async def request_password_reset(email: str, db: AsyncSession) -> str | None:
    """Request password reset"""
    # Find admin (don't reveal if exists)
    query = select(Admin).where(Admin.email == email)
    result = await db.execute(query)
    admin = result.scalar_one_or_none()

    otp_code = None
    if admin:
        # Generate OTP
        otp = generate_otp()

        # Store hashed OTP
        email_otp = EmailOTP(
            email=email,
            otp_code=hash_otp(otp),
            purpose=OTPPurpose.PASSWORD_RESET,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        )
        db.add(email_otp)
        await db.commit()

        # Send OTP email
        email_service.send_otp_email(email, otp, "password reset")

        # Return OTP in development mode for testing
        if settings.DEBUG:
            otp_code = otp

    return otp_code


async def verify_password_reset_otp(email: str, otp: str, db: AsyncSession) -> tuple[bool, str]:
    """Verify OTP"""
    # Find most recent OTP
    query = (
        select(EmailOTP)
        .where(
            EmailOTP.email == email,
            EmailOTP.purpose == OTPPurpose.PASSWORD_RESET,
            EmailOTP.is_used.is_(False),
        )
        .order_by(desc(EmailOTP.created_at))
        .limit(1)  # Get only the most recent OTP
    )
    result = await db.execute(query)
    otp_record = result.scalar_one_or_none()

    if not otp_record:
        return False, msg("OTP_INVALID")

    # Check expiry
    if otp_record.expires_at < datetime.now(timezone.utc):
        return False, msg("OTP_EXPIRED")

    # Check attempts
    if otp_record.attempts >= settings.MAX_OTP_ATTEMPTS:
        return False, msg("OTP_TOO_MANY_ATTEMPTS")

    # Increment attempts
    otp_record.attempts += 1

    # Verify OTP
    if not verify_otp(otp, otp_record.otp_code):
        await db.commit()
        return False, msg("OTP_INVALID")

    await db.commit()
    return True, msg("OTP_VERIFIED")


async def reset_password(email: str, otp: str, new_password: str, db: AsyncSession) -> None:
    """Reset password"""
    # Find and verify most recent OTP
    query = (
        select(EmailOTP)
        .where(
            EmailOTP.email == email,
            EmailOTP.purpose == OTPPurpose.PASSWORD_RESET,
            EmailOTP.is_used.is_(False),
        )
        .order_by(desc(EmailOTP.created_at))
        .limit(1)
    )
    result = await db.execute(query)
    otp_record = result.scalar_one_or_none()

    if not otp_record or otp_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )

    if not verify_otp(otp, otp_record.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP",
        )

    # Mark OTP as used
    otp_record.is_used = True

    # Find admin
    query = select(Admin).where(Admin.email == email)
    result = await db.execute(query)
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin not found",
        )

    # Update password
    admin.password_hash = get_password_hash(new_password)

    # Revoke all refresh tokens
    await db.execute(update(RefreshToken).where(RefreshToken.admin_id == admin.id).values(is_revoked=True))

    # Mark sessions as inactive
    await db.execute(update(Session).where(Session.admin_id == admin.id).values(is_active=False))

    await db.commit()

    # Send notification email
    email_service.send_password_changed_email(email, admin.full_name)


async def get_admin_sessions(admin_id: str, current_ip: str, db: AsyncSession) -> list[Session]:
    """Get active sessions for admin"""
    query = (
        select(Session)
        .where(Session.admin_id == admin_id, Session.is_active.is_(True))
        .order_by(desc(Session.last_activity))
    )
    result = await db.execute(query)
    return result.scalars().all()


async def revoke_session(session_id: str, admin_id: str, db: AsyncSession) -> None:
    """Revoke a specific session"""
    query = select(Session).where(
        Session.id == session_id,
        Session.admin_id == admin_id,
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    session.is_active = False

    if session.refresh_token_id:
        await db.execute(
            update(RefreshToken).where(RefreshToken.id == session.refresh_token_id).values(is_revoked=True)
        )

    await db.commit()


async def revoke_all_sessions(admin_id: str, current_ip: str, db: AsyncSession) -> int:
    """Revoke all other sessions"""
    query = select(Session).where(
        Session.admin_id == admin_id,
        Session.ip_address != current_ip,
        Session.is_active.is_(True),
    )
    result = await db.execute(query)
    sessions = result.scalars().all()

    for session in sessions:
        session.is_active = False
        if session.refresh_token_id:
            await db.execute(
                update(RefreshToken).where(RefreshToken.id == session.refresh_token_id).values(is_revoked=True)
            )

    await db.commit()
    return len(sessions)


async def sync_clerk_admin(
    clerk_id: str,
    email: str,
    full_name: str,
    db: AsyncSession,
    avatar_url: str | None = None,
    performed_by_type: str = "ai_agent",
    performed_by_id: str | None = None,
) -> Admin:
    """
    Create or update admin from Clerk webhook payload.

    Args:
        clerk_id: Clerk user ID
        email: Admin email
        full_name: Admin full name
        db: Database session
        avatar_url: Optional avatar URL from Clerk
        performed_by_type: Type of entity performing the sync
        performed_by_id: ID of entity performing the sync

    Returns:
        Admin object (created or updated)
    """
    from uuid import uuid4

    from app.db.schema import ActivityAction, ActivityLog, AdminRole, PerformedByType

    # Check if admin already exists by clerk_id
    result = await db.execute(select(Admin).where(Admin.clerk_id == clerk_id))
    admin = result.scalar_one_or_none()

    if admin:
        # Update existing admin
        changes = {}
        if admin.email != email:
            changes["email"] = {"old": admin.email, "new": email}
            admin.email = email
        if admin.full_name != full_name:
            changes["full_name"] = {"old": admin.full_name, "new": full_name}
            admin.full_name = full_name

        if changes:
            # Log update activity
            activity_log = ActivityLog(
                id=str(uuid4()),
                entity_type="admin",
                entity_id=admin.id,
                action=ActivityAction.UPDATE,
                performed_by_type=PerformedByType(performed_by_type),
                performed_by_id=performed_by_id,
                changes=changes,
            )
            db.add(activity_log)

            await db.commit()
            await db.refresh(admin)
    else:
        # Create new admin
        admin = Admin(
            id=str(uuid4()),
            clerk_id=clerk_id,
            email=email,
            full_name=full_name,
            password_hash=None,  # Clerk admins don't have passwords
            role=AdminRole.ADMIN,  # Default role
            is_active=True,
        )
        db.add(admin)

        # Log creation activity
        activity_log = ActivityLog(
            id=str(uuid4()),
            entity_type="admin",
            entity_id=admin.id,
            action=ActivityAction.CREATE,
            performed_by_type=PerformedByType(performed_by_type),
            performed_by_id=performed_by_id,
            changes={"clerk_id": clerk_id, "email": email, "full_name": full_name, "role": AdminRole.ADMIN.value},
        )
        db.add(activity_log)

        await db.commit()
        await db.refresh(admin)

    return admin
