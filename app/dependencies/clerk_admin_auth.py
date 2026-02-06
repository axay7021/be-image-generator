"""Clerk authentication for admin users."""

import logging
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, get_settings
from app.db import get_db
from app.db.schema import Admin

logger = logging.getLogger(__name__)


def _get_jwks_url(settings: Settings) -> str:
    """Get the JWKS URL for Clerk token verification."""
    if settings.CLERK_JWKS_URL:
        return settings.CLERK_JWKS_URL

    # Derive JWKS URL from Clerk secret key
    # Clerk secret keys format: sk_test_xxx or sk_live_xxx
    if not settings.CLERK_SECRET_KEY:
        raise ValueError("CLERK_SECRET_KEY is not configured")

    if settings.CLERK_SECRET_KEY.startswith("sk_test_"):
        # Test environment
        issuer_base = "clerk.accounts.dev"
    elif settings.CLERK_SECRET_KEY.startswith("sk_live_"):
        # Production environment
        issuer_base = "clerk.com"
    else:
        raise ValueError("Invalid CLERK_SECRET_KEY format")

    return f"https://{issuer_base}/.well-known/jwks.json"


async def verify_clerk_admin_jwt(
    authorization: Annotated[str | None, Header()] = None, settings: Settings = Depends(get_settings)
) -> str:
    """
    Verify Clerk JWT token and extract admin Clerk ID.

    Args:
        authorization: Authorization header with Bearer token
        settings: Application settings

    Returns:
        Clerk user ID (sub claim from JWT)

    Raises:
        HTTPException: If token is invalid or missing
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header is required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header format")

    token = authorization.replace("Bearer ", "")

    try:
        # Get JWKS URL for token verification
        jwks_url = _get_jwks_url(settings)
        jwks_client = PyJWKClient(jwks_url)

        # Get the signing key from the token
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Verify and decode the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_exp": True, "verify_aud": False},  # Clerk doesn't use aud claim
        )

        # Extract Clerk user ID from 'sub' claim
        clerk_id = payload.get("sub")
        if not clerk_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing subject claim")

        return clerk_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"Error verifying Clerk admin token: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {str(e)}")


async def get_clerk_admin(
    clerk_id: Annotated[str, Depends(verify_clerk_admin_jwt)],
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Admin:
    """
    Get admin user from database by Clerk ID with email whitelist validation.

    Args:
        clerk_id: Clerk user ID from JWT verification
        db: Database session
        settings: Application settings

    Returns:
        Admin object

    Raises:
        HTTPException: If admin not found, inactive, or email not whitelisted
    """
    # Query admin by clerk_id
    result = await db.execute(select(Admin).where(Admin.clerk_id == clerk_id))
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your email is not authorized as an admin. Please contact the system administrator.",
        )

    # Check if admin is active
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your admin account has been deactivated. Please contact the system administrator.",
        )

    # Validate email against whitelist
    if settings.ADMIN_EMAILS:
        admin_emails = [email.strip() for email in settings.ADMIN_EMAILS.split(",")]
        if admin.email not in admin_emails:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Your email is not on the authorized admin list.",
            )

    return admin


# Optional dependency for endpoints that allow both authenticated and anonymous access
async def get_clerk_admin_optional(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Admin | None:
    """
    Optional admin authentication - returns None if no token provided.

    Args:
        authorization: Optional authorization header
        db: Database session
        settings: Application settings

    Returns:
        Admin object or None if no token provided
    """
    if not authorization:
        return None

    try:
        clerk_id = await verify_clerk_admin_jwt(authorization, settings)
        return await get_clerk_admin(clerk_id, db, settings)
    except HTTPException:
        return None
