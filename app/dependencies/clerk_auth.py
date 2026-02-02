"""Clerk authentication dependency for Next.js frontend integration"""

from typing import Annotated

import jwt
from clerk_backend_api import Clerk
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.settings import settings

# Initialize Clerk client
clerk_client = Clerk(bearer_auth=settings.CLERK_SECRET_KEY)

# HTTP Bearer token scheme
security = HTTPBearer()


async def get_clerk_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> str:
    """
    Validate Clerk JWT token and return user_id.

    This dependency:
    1. Extracts the Bearer token from Authorization header
    2. Verifies the JWT signature using Clerk's JWKS
    3. Validates token expiration and claims
    4. Returns the user_id (from 'sub' claim)

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        str: Clerk user_id from the token's 'sub' claim

    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Method 1: Decode JWT and verify manually using JWKS
        # Clerk tokens are standard JWTs that can be verified using the issuer's JWKS
        try:
            # First, decode without verification to get the issuer
            decoded_unverified = jwt.decode(token, options={"verify_signature": False})

            # Get the issuer from the token (e.g., https://clerk.your-domain.com)
            issuer = decoded_unverified.get("iss")
            if not issuer:
                raise ValueError("Token missing issuer (iss) claim")

            # Construct JWKS URL from issuer
            jwks_url = f"{issuer}/.well-known/jwks.json"

            # Import PyJWKClient for JWKS verification
            from jwt import PyJWKClient

            # Get signing key from JWKS
            jwks_client = PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Verify and decode token with full validation
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_exp": True, "verify_aud": False},
            )

            # Extract user_id from the 'sub' claim
            user_id = decoded.get("sub")
            if not user_id:
                raise ValueError("Token missing 'sub' claim (user ID)")

            return user_id

        except Exception as jwt_error:
            # Log the error for debugging
            from app.core.logger import logger

            logger.error(f"Clerk token verification failed: {str(jwt_error)}")

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {str(jwt_error)}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from jwt_error

    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# Type alias for dependency injection
ClerkUserId = Annotated[str, Depends(get_clerk_user)]
