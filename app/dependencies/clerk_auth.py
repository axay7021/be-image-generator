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
        # Method 1: Using Clerk's verify_token API (recommended)
        try:
            # Verify token using Clerk's backend API
            verified_token = clerk_client.tokens.verify(token)
            
            # Extract user_id from the verified token
            # The sub claim contains the Clerk user ID
            if hasattr(verified_token, 'sub'):
                user_id = verified_token.sub
            elif hasattr(verified_token, 'user_id'):
                user_id = verified_token.user_id
            else:
                # Fallback: decode to get claims
                decoded = jwt.decode(token, options={"verify_signature": False})
                user_id = decoded.get("sub")
            
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user identifier",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                
            return user_id
            
        except Exception as clerk_error:
            # Fallback to manual JWT verification if Clerk API fails
            # This requires the JWKS URL to be configured (optional)
            if settings.CLERK_JWKS_URL and settings.CLERK_JWKS_URL.startswith("https://"):
                try:
                    import requests
                    from jwt import PyJWKClient
                    
                    # Get signing key from JWKS
                    jwks_client = PyJWKClient(settings.CLERK_JWKS_URL)
                    signing_key = jwks_client.get_signing_key_from_jwt(token)
                    
                    # Verify and decode token
                    decoded = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=["RS256"],
                        options={"verify_exp": True, "verify_aud": False},
                    )
                    
                    user_id = decoded.get("sub")
                    if not user_id:
                        raise ValueError("Missing 'sub' claim in token")
                        
                    return user_id
                    
                except Exception as jwks_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Token verification failed: {str(jwks_error)}",
                        headers={"WWW-Authenticate": "Bearer"},
                    ) from jwks_error
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token verification failed: {str(clerk_error)}",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from clerk_error

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
