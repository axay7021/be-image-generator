"""Authentication dependencies for FastAPI"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_access_token
from app.db import get_db
from app.db.schema import ActiveToken, Admin, AdminRole
from app.i18n import msg

security = HTTPBearer()


async def get_current_admin(
    token: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Admin:
    """
    Get current authenticated admin from access token.

    Validates:
    1. Token format and signature
    2. Token expiration
    3. Admin exists in database
    4. Admin has at least one active session (effective logout)

    This ensures that revoking refresh tokens/sessions immediately
    invalidates access tokens as well.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=msg("TOKEN_INVALID"),
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode token
    payload = verify_access_token(token.credentials)
    if payload is None:
        raise credentials_exception

    admin_id: str = payload.get("sub")  # type: ignore
    jti: str = payload.get("jti")  # type: ignore

    if admin_id is None or jti is None:
        raise credentials_exception

    # WHITELIST CHECK: Verify token is in active tokens table

    whitelist_query = select(ActiveToken).where(ActiveToken.jti == jti).limit(1)
    result = await db.execute(whitelist_query)
    active_token = result.scalar_one_or_none()

    if not active_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg("TOKEN_REVOKED"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get admin from database
    query = select(Admin).where(Admin.id == admin_id)
    result = await db.execute(query)
    admin = result.scalar_one_or_none()

    if admin is None:
        raise credentials_exception

    return admin


async def get_current_active_admin(
    current_admin: Annotated[Admin, Depends(get_current_admin)],
) -> Admin:
    """
    Get current admin and verify they are active

    Args:
        current_admin: Current admin from token

    Returns:
        Admin: Active admin user

    Raises:
        HTTPException: If admin is inactive
    """
    if not current_admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg("INACTIVE_ADMIN"))
    return current_admin


def require_role(*allowed_roles: AdminRole):
    """
    Dependency factory to require specific admin roles

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role(AdminRole.ADMIN))])

    Args:
        *allowed_roles: Allowed admin roles

    Returns:
        Dependency function
    """

    async def role_checker(
        current_admin: Annotated[Admin, Depends(get_current_active_admin)],
    ) -> Admin:
        if current_admin.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=msg("INSUFFICIENT_PERMISSIONS"),
            )
        return current_admin

    return role_checker


# Convenient dependencies for common use cases
CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]
CurrentActiveAdmin = Annotated[Admin, Depends(get_current_active_admin)]
