"""User service for authentication and profile management"""

import random
import string
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_user_access_token,
    create_user_refresh_token,
    get_password_hash,
    parse_user_agent,
    verify_password,
    verify_user_refresh_token,
)
from app.core.settings import settings
from app.db.schema import (
    CreatedVia,
    DeviceType,
    EmailOTP,
    LoginStatus,
    OTPPurpose,
    User,
    UserGender,
    UserLoginHistory,
    UserSession,
)
from app.i18n import msg

# ============================================
# User Queries
# ============================================


async def get_user_by_phone(phone: str, db: AsyncSession) -> User | None:
    """Get user by phone number"""
    query = select(User).where(User.phone_number == phone)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_email(email: str, db: AsyncSession) -> User | None:
    """Get user by email address"""
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()


# ============================================
# Web User Creation
# ============================================


async def create_user_from_web(
    email: str,
    password: str,
    full_name: str | None = None,
    phone_number: str | None = None,
    gender: UserGender | None = None,
    db: AsyncSession = None,
) -> User:
    """Create a new user from web registration (email/password)"""
    # Check if user exists by email
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg("EMAIL_ALREADY_EXISTS"),
        )

    # Check if phone number exists (if provided)
    if phone_number:
        query = select(User).where(User.phone_number == phone_number)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=msg("PHONE_ALREADY_EXISTS"),
            )

    # Default full_name if not provided
    if not full_name:
        full_name = email.split("@")[0]

    # Hash password
    password_hash = get_password_hash(password)

    user = User(
        email=email,
        phone_number=phone_number,
        password_hash=password_hash,
        full_name=full_name,
        gender=gender,
        created_via=CreatedVia.WEB.value,
        is_active=True,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


async def authenticate_web_user(
    email: str,
    password: str,
    request: Request,
    db: AsyncSession,
) -> tuple[User, str, str]:
    """Authenticate user with email and password"""
    # Check if user exists
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Avoid leaking user existence
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg("INVALID_CREDENTIALS"),
        )

    # Verify password (only if user has one)
    if not user.password_hash or not verify_password(password, user.password_hash):
        log_login_attempt(
            user_id=user.id,
            email=email,
            request=request,
            status=LoginStatus.FAILED,
            failure_reason="Invalid credentials",
            db=db,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg("INVALID_CREDENTIALS"),
        )

    if not user.is_active:
        log_login_attempt(
            user_id=user.id,
            email=email,
            request=request,
            status=LoginStatus.BLOCKED,
            failure_reason="Account inactive",
            db=db,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=msg("ACCOUNT_INACTIVE"),
        )

    # Generate tokens
    access_token, refresh_token = await create_user_session(
        user=user,
        request=request,
        db=db,
    )

    # Log success
    log_login_attempt(
        user_id=user.id,
        email=email,
        request=request,
        status=LoginStatus.SUCCESS,
        db=db,
    )
    await db.commit()

    return user, access_token, refresh_token


async def get_or_create_google_user(
    google_user_data: dict,
    request: Request,
    db: AsyncSession,
) -> tuple[User, str, str]:
    """Get existing google user or create new one"""
    google_id = google_user_data["sub"]
    email = google_user_data["email"]
    full_name = google_user_data.get("name", "")
    picture = google_user_data.get("picture")

    # 1. Try to find by Google ID
    query = select(User).where(User.google_id == google_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        # Update details if changed
        if user.email != email:
            user.email = email
        if picture and user.avatar_url != picture:
            user.avatar_url = picture

        await db.commit()
    else:
        # 2. Try to find by Email (Link account)
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if user:
            # Link existing account
            user.google_id = google_id
            if picture and not user.avatar_url:
                user.avatar_url = picture
            await db.commit()
        else:
            # 3. Create new user
            user = User(
                google_id=google_id,
                email=email,
                full_name=full_name,
                avatar_url=picture,
                created_via=CreatedVia.GOOGLE.value,
                is_active=True,
                password_hash=None,  # No password for Google users
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

    # Generate tokens
    access_token, refresh_token = await create_user_session(
        user=user,
        request=request,
        db=db,
    )

    # Log success
    log_login_attempt(
        user_id=user.id,
        email=email,
        request=request,
        status=LoginStatus.SUCCESS,
        db=db,
    )

    await db.commit()
    return user, access_token, refresh_token


async def change_user_password(user_id: str, old_password: str, new_password: str, db: AsyncSession) -> None:
    """
    Change user's password
    """
    # Get user
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg("USER_NOT_FOUND"))

    # Check if user has a password (web users only)
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg("NO_PASSWORD_ACCOUNT"),
        )

    # Verify old password
    # Verify old password
    if not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg("INCORRECT_PASSWORD"))

    # Hash new password
    user.password_hash = get_password_hash(new_password)

    await db.commit()


# ============================================
# User Profile Management
# ============================================


async def update_user_profile(
    user_id: str,
    full_name: str | None,
    phone_number: str | None,
    gender: UserGender | None,
    email: str | None,
    db: AsyncSession,
) -> User:
    """
    Update user profile
    """
    # Get user
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg("USER_NOT_FOUND"))

    # Update fields
    if full_name is not None:
        if not full_name.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg("NAME_EMPTY"))
        user.full_name = full_name.strip()

    if phone_number is not None:
        # Check if phone already exists (for other users)
        phone_query = select(User).where(User.phone_number == phone_number, User.id != user_id)
        phone_result = await db.execute(phone_query)
        if phone_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg("PHONE_IN_USE"))
        user.phone_number = phone_number

    if gender is not None:
        user.gender = gender

    if email is not None:
        user.email = email

    await db.commit()
    await db.refresh(user)

    return user


# ============================================
# Authentication
# ============================================


async def get_user_by_line_id(line_id: str, db: AsyncSession) -> User | None:
    """Get user by LINE ID"""
    query = select(User).where(User.line_id == line_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_user_from_line(
    line_id: str,
    line_name: str,
    picture_url: str | None,
    db: AsyncSession,
) -> User:
    """Create a new user from LINE login"""
    user = User(
        line_id=line_id,
        line_name=line_name,
        line_picture_url=picture_url,
        full_name=line_name,  # Use LINE name as full name
        created_via=CreatedVia.LINE.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_line_user(
    line_id: str, line_name: str, picture_url: str | None, request: Request, db: AsyncSession
) -> tuple[User, str, str]:
    """
    Authenticate LINE user (login or register)
    """
    # Get request metadata
    user_agent = request.headers.get("user-agent", "Unknown")
    ip_address = request.client.host if request.client else "Unknown"

    # Get or create user
    user = await get_user_by_line_id(line_id, db)

    if not user:
        # Create new user
        user = await create_user_from_line(line_id, line_name, picture_url, db)
        login_status = LoginStatus.SUCCESS
        failure_reason = None
    else:
        # Existing user - update LINE info if changed
        if user.line_name != line_name or user.line_picture_url != picture_url:
            user.line_name = line_name
            user.line_picture_url = picture_url
            await db.commit()

        # Check if user is active
        if not user.is_active:
            log_login_attempt(
                user_id=user.id,
                line_id=line_id,
                request=request,
                status=LoginStatus.BLOCKED,
                failure_reason="Account inactive",
                db=db,
            )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg("ACCOUNT_INACTIVE"))

        login_status = LoginStatus.SUCCESS
        failure_reason = None

    # Generate tokens
    access_token, refresh_token = await create_user_session(
        user=user,
        request=request,
        db=db,
    )

    # Log successful login
    log_login_attempt(
        user_id=user.id,
        line_id=line_id,
        request=request,
        status=login_status,
        failure_reason=failure_reason,
        db=db,
    )

    await db.commit()

    return user, access_token, refresh_token


async def get_or_create_clerk_user(
    clerk_user_id: str,
    request: Request,
    db: AsyncSession,
) -> tuple[User, str, str]:
    """Get existing Clerk user or create new one"""
    from app.core.logger import logger
    from app.dependencies.clerk_auth import clerk_client

    # 1. Try to find by Clerk ID stored in our system
    # Using google_id field temporarily for Clerk ID (consider adding clerk_id column)
    query = select(User).where(User.google_id == clerk_user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        # User exists, just proceed with token generation
        logger.info(f"Existing Clerk user found: {user.id}")
    else:
        # Fetch user details from Clerk API
        try:
            logger.info(f"Fetching user details from Clerk for user_id: {clerk_user_id}")
            clerk_user = clerk_client.users.get(user_id=clerk_user_id)

            email = None
            full_name = "Clerk User"
            avatar_url = None

            # Extract email from Clerk user
            if hasattr(clerk_user, "email_addresses") and clerk_user.email_addresses:
                email = clerk_user.email_addresses[0].email_address
                logger.info(f"Extracted email from Clerk: {email}")

            # Extract name
            if hasattr(clerk_user, "first_name") and hasattr(clerk_user, "last_name"):
                first = clerk_user.first_name or ""
                last = clerk_user.last_name or ""
                full_name = f"{first} {last}".strip()
                if not full_name:
                    full_name = "Clerk User"

            # Extract avatar
            if hasattr(clerk_user, "image_url"):
                avatar_url = clerk_user.image_url

            logger.info(f"Clerk user info - Email: {email}, Name: {full_name}")

            # Check if user exists by email
            if email:
                query = select(User).where(User.email == email)
                result = await db.execute(query)
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    # Link existing account with Clerk ID
                    logger.info(f"Linking existing user {existing_user.id} with Clerk ID")
                    existing_user.google_id = clerk_user_id
                    if avatar_url and not existing_user.avatar_url:
                        existing_user.avatar_url = avatar_url
                    await db.commit()
                    await db.refresh(existing_user)
                    user = existing_user
                else:
                    # Create new user
                    logger.info(f"Creating new user with email: {email}")
                    user = User(
                        google_id=clerk_user_id,
                        email=email,
                        full_name=full_name,
                        avatar_url=avatar_url,
                        created_via=CreatedVia.GOOGLE.value,
                        is_active=True,
                        password_hash=None,
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    logger.info(f"User created successfully with ID: {user.id}")
            else:
                # No email, create user with just Clerk ID
                logger.warning("No email found in Clerk user, creating user without email")
                user = User(
                    google_id=clerk_user_id,
                    full_name=full_name,
                    avatar_url=avatar_url,
                    created_via=CreatedVia.GOOGLE.value,
                    is_active=True,
                    password_hash=None,
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                logger.info(f"User created without email, ID: {user.id}")

        except Exception as e:
            # Log the actual error for debugging
            logger.error(f"Failed to fetch user from Clerk API: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to authenticate with Clerk: {str(e)}",
            ) from e

    # Generate tokens
    access_token, refresh_token = await create_user_session(
        user=user,
        request=request,
        db=db,
    )

    # Log success
    log_login_attempt(
        user_id=user.id,
        email=user.email,
        request=request,
        status=LoginStatus.SUCCESS,
        db=db,
    )
    await db.commit()

    return user, access_token, refresh_token


async def create_user_session(user: User, request: Request, db: AsyncSession) -> tuple[str, str]:
    """Create new user session and tokens"""
    # Get request metadata
    user_agent = request.headers.get("user-agent", "Unknown")
    ip_address = request.client.host if request.client else "Unknown"
    device_info = parse_user_agent(user_agent)

    # Revoke existing session (single session enforcement per unique constraint)
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))

    # Generate tokens
    access_token, access_jti = create_user_access_token(data={"sub": str(user.id)})
    refresh_token = create_user_refresh_token(user_id=str(user.id))

    # Decode tokens to get expiration
    access_payload = verify_user_refresh_token(access_token)
    refresh_payload = verify_user_refresh_token(refresh_token)

    access_expires = (
        datetime.fromtimestamp(access_payload["exp"], tz=UTC)
        if access_payload
        else datetime.now(UTC) + timedelta(minutes=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_expires = (
        datetime.fromtimestamp(refresh_payload["exp"], tz=UTC)
        if refresh_payload
        else datetime.now(UTC) + timedelta(days=settings.USER_REFRESH_TOKEN_EXPIRE_DAYS)
    )

    # Create new session
    session = UserSession(
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_jti=access_jti,
        device_name=device_info["name"],
        device_type=DeviceType(device_info["type"]),
        ip_address=ip_address,
        user_agent=user_agent,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires,
    )
    db.add(session)

    return access_token, refresh_token


def log_login_attempt(
    user_id: str | None,
    request: Request,
    status: LoginStatus,
    db: AsyncSession,
    email: str | None = None,
    phone_number: str | None = None,
    line_id: str | None = None,
    failure_reason: str | None = None,
) -> None:
    """Log login attempt"""
    # Get client info
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    login_log = UserLoginHistory(
        user_id=user_id,
        phone_number=phone_number,
        line_id=line_id,
        ip_address=client_ip,
        user_agent=user_agent,
        status=status,
        failure_reason=failure_reason,
    )
    db.add(login_log)


async def request_password_reset(email: str, db: AsyncSession) -> str | None:
    """
    Request password reset OTP
    """
    # Check if user exists
    user = await get_user_by_email(email, db)
    if not user:
        # Don't reveal user existence
        return None

    # Check if user has password
    if not user.password_hash:
        return None  # Social login users can't reset password

    # Generate OTP
    otp = "".join(random.choices(string.digits, k=6))

    # Save OTP
    expiration = datetime.now(UTC) + timedelta(minutes=10)
    email_otp = EmailOTP(
        email=email,
        otp_code=otp,
        purpose=OTPPurpose.PASSWORD_RESET,
        expires_at=expiration,
    )
    db.add(email_otp)
    await db.commit()

    # In a real app, send email here
    print("=================================")
    print(f" PASSWORD RESET OTP for {email}: {otp}")
    print("=================================")

    return otp


async def verify_password_reset_otp(email: str, otp: str, db: AsyncSession) -> tuple[bool, str]:
    """
    Verify password reset OTP
    """

    query = (
        select(EmailOTP)
        .where(
            EmailOTP.email == email,
            EmailOTP.otp_code == otp,
            EmailOTP.purpose == OTPPurpose.PASSWORD_RESET,
            EmailOTP.is_used.is_(False),
            EmailOTP.expires_at > datetime.now(UTC),
        )
        .order_by(desc(EmailOTP.created_at))
        .limit(1)
    )

    result = await db.execute(query)
    otp_record = result.scalar_one_or_none()

    if not otp_record:
        return False, msg("OTP_INVALID")

    return True, msg("OTP_VALID")


async def reset_password_with_otp(email: str, otp: str, new_password: str, db: AsyncSession) -> None:
    """
    Reset password using verified OTP
    """
    # Verify OTP again to be safe (and mark used)

    query = (
        select(EmailOTP)
        .where(
            EmailOTP.email == email,
            EmailOTP.otp_code == otp,
            EmailOTP.purpose == OTPPurpose.PASSWORD_RESET,
            EmailOTP.is_used.is_(False),
            EmailOTP.expires_at > datetime.now(UTC),
        )
        .order_by(desc(EmailOTP.created_at))
        .limit(1)
    )
    result = await db.execute(query)
    otp_record = result.scalar_one_or_none()

    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg("OTP_INVALID"))

    # Get User
    user = await get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg("USER_NOT_FOUND"))

    # Update Password

    user.password_hash = get_password_hash(new_password)

    # Mark OTP as used
    otp_record.is_used = True

    await db.commit()
