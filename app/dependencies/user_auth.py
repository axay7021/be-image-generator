"""User authentication dependencies for FastAPI"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.schema import User
from app.dependencies.clerk_auth import get_clerk_user

# Re-use Clerk auth dependency logic but wrapped for our User model
from app.dependencies.clerk_auth import security as clerk_security
from app.services import user_service


async def get_current_user(
    token: Annotated[HTTPAuthorizationCredentials, Depends(clerk_security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current authenticated user via Clerk Token.

    1. Verify Clerk Token (via get_clerk_user logic).
    2. Find user in local DB by `clerk_id`.
    3. If not found, try to sync/create (Lazy Mode) or return 401.
    """
    # 1. Verify Token and get Clerk ID
    # We call the logic from clerk_auth dependency directly or re-implement?
    # Better to reuse. But get_clerk_user is a dependency returning str.
    # We can call it manually if we extract the logic, but depends is cleaner.

    try:
        # We need to use the token to get the user ID.
        # Since this is a dependency function, we can just call get_clerk_user
        # if we could simpler, but here we are inside the dependency.
        # Let's use the helper we created in clerk_auth or just call it:
        clerk_user_id = await get_clerk_user(token)
    except HTTPException as e:
        # Log the authentication failure
        from app.core.logger import logger

        logger.warning(f"Authentication failed in get_current_user: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed. Please refresh your session and try again.",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed. Please refresh your session and try again.",
        ) from e

    # 2. Find User in DB
    user = await user_service.get_user_by_clerk_id(clerk_user_id, db)

    if not user:
        # Lazy Mode: User might not exist yet if webhook failed or hasn't arrived.
        # Ideally, we should fetch user details from Clerk and create them here.
        # But for now, let's just return 401 or try to "auto-register" if we had the full profile.
        # The token claims might have email/name?
        # Svix/Clerk tokens usually have `sub` (ID).
        # We can trigger a sync if we had the client.

        # PROACTIVE FIX: Try to fetch from Clerk API to ensure we have the user
        # This makes the system robust against webhook failures.
        try:
            from app.dependencies.clerk_auth import clerk_client

            clerk_user_obj = clerk_client.users.get(user_id=clerk_user_id)

            # Convert to payload format expected by service
            email = None
            if hasattr(clerk_user_obj, "email_addresses") and clerk_user_obj.email_addresses:
                email = clerk_user_obj.email_addresses[0].email_address

            first = getattr(clerk_user_obj, "first_name", "") or ""
            last = getattr(clerk_user_obj, "last_name", "") or ""

            payload = {
                "id": clerk_user_id,
                "first_name": first,
                "last_name": last,
                "image_url": getattr(clerk_user_obj, "image_url", None),
                # ... other fields
            }

            user = await user_service.create_or_update_from_clerk_payload(payload=payload, email=email, db=db)

        except Exception as e:
            # If we can't fetch from Clerk (rate limit etc), we have to fail
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found and sync failed",
            ) from e

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get current user and verify they are active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive User")
    return current_user


async def get_current_user_optional(
    token: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """
    Optional authentication. Returns None if no token or invalid.
    """
    if not token:
        return None

    try:
        user = await get_current_user(token, db)
        return user
    except HTTPException:
        return None


# Convenient dependencies
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
