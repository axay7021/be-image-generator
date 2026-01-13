"""User authentication dependencies for FastAPI"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_user_access_token
from app.db import get_db
from app.db.schema import User, UserSession
from app.i18n import msg

security = HTTPBearer()


async def get_current_user(
    token: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current authenticated user from access token.

    Validates:
    1. Token format and signature
    2. Token expiration
    3. User exists in database
    4. User has an active session with this token (single session enforcement)

    This ensures that only one active session exists per user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=msg("TOKEN_INVALID"),
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode token
    payload = verify_user_access_token(token.credentials)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")  # type: ignore
    jti: str = payload.get("jti")  # type: ignore

    if user_id is None or jti is None:
        raise credentials_exception

    # Verify token is in active session (single session check)
    session_query = (
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.access_token_jti == jti,
            UserSession.is_active.is_(True),
        )
        .limit(1)
    )
    result = await db.execute(session_query)
    active_session = result.scalar_one_or_none()

    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg("SESSION_REVOKED"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get current user and verify they are active

    Args:
        current_user: Current user from token

    Returns:
        User: Active user

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg("INACTIVE_USER"))
    return current_user


security_optional = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    token: Annotated[HTTPAuthorizationCredentials | None, Depends(security_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """
    Get current user if token is valid, otherwise return None.
    Does not raise HTTPException.
    """
    if not token:
        return None

    try:
        # Decode token
        payload = verify_user_access_token(token.credentials)
        if payload is None:
            return None

        user_id: str = payload.get("sub")
        jti: str = payload.get("jti")

        if user_id is None or jti is None:
            return None

        # Verify token is in active session
        session_query = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.access_token_jti == jti,
                UserSession.is_active.is_(True),
            )
            .limit(1)
        )
        result = await db.execute(session_query)
        active_session = result.scalar_one_or_none()

        if not active_session:
            return None

        # Get user
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        return user
    except Exception:
        return None


# Convenient dependencies for common use cases
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
