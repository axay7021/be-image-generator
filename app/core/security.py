import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.settings import settings

password_hash: PasswordHash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return password_hash.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> tuple[str, str]:
    """
    Create a JWT access token with unique identifier

    Args:
        data: Data to encode in the token (should include 'sub' for user ID)
        expires_delta: Optional custom expiration time

    Returns:
        tuple: (encoded_jwt, jti) - Token string and its unique JWT ID
    """
    import uuid

    to_encode = data.copy()
    jti = str(uuid.uuid4())  # Unique token identifier

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access", "jti": jti})
    encoded_jwt = jwt.encode(to_encode, settings.ADMIN_JWT_SECRET, algorithm="HS256")
    return encoded_jwt, jti


def create_refresh_token(admin_id: str, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT refresh token

    Args:
        admin_id: Admin user ID
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded refresh token
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {"sub": admin_id, "exp": expire, "type": "refresh", "jti": str(uuid.uuid4())}
    encoded_jwt = jwt.encode(to_encode, settings.ADMIN_JWT_SECRET_REF, algorithm="HS256")
    return encoded_jwt


def verify_access_token(token: str) -> dict | None:
    """
    Decode and validate an access token

    Args:
        token: JWT access token

    Returns:
        dict: Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.ADMIN_JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_refresh_token(token: str) -> dict | None:
    """
    Decode and validate a refresh token

    Args:
        token: JWT refresh token

    Returns:
        dict: Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.ADMIN_JWT_SECRET_REF, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============================================
# User JWT Functions
# ============================================


def create_user_access_token(data: dict, expires_delta: timedelta | None = None) -> tuple[str, str]:
    """
    Create a JWT access token for user with unique identifier

    Args:
        data: Data to encode in the token (should include 'sub' for user ID)
        expires_delta: Optional custom expiration time

    Returns:
        tuple: (encoded_jwt, jti) - Token string and its unique JWT ID
    """

    to_encode = data.copy()
    jti = str(uuid.uuid4())  # Unique token identifier

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.USER_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "user_access", "jti": jti})
    encoded_jwt = jwt.encode(to_encode, settings.USER_JWT_SECRET, algorithm="HS256")
    return encoded_jwt, jti


def create_user_refresh_token(user_id: str, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT refresh token for user

    Args:
        user_id: User ID
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded refresh token
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.USER_REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {"sub": user_id, "exp": expire, "type": "user_refresh", "jti": str(uuid.uuid4())}
    encoded_jwt = jwt.encode(to_encode, settings.USER_JWT_SECRET_REF, algorithm="HS256")
    return encoded_jwt


def verify_user_access_token(token: str) -> dict | None:
    """
    Decode and validate a user access token

    Args:
        token: JWT access token

    Returns:
        dict: Decoded token payload or None if invalid
    """
    try:
        print("Token:", token)
        print("Secret:", settings.USER_JWT_SECRET)
        payload = jwt.decode(token, settings.USER_JWT_SECRET, algorithms=["HS256"])
        print("Payload:", payload)
        if payload.get("type") != "user_access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_user_refresh_token(token: str) -> dict | None:
    """
    Decode and validate a user refresh token

    Args:
        token: JWT refresh token

    Returns:
        dict: Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.USER_JWT_SECRET_REF, algorithms=["HS256"])
        if payload.get("type") != "user_refresh":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============================================
# OTP Functions
# ============================================


def generate_otp(length: int = 6) -> str:
    """
    Generate a random numeric OTP code

    Args:
        length: Length of OTP (default 6)

    Returns:
        str: Random numeric OTP
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(otp: str) -> str:
    """
    Hash an OTP code for database storage

    Args:
        otp: Plain OTP code

    Returns:
        str: Hashed OTP
    """
    return password_hash.hash(otp)


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """
    Verify an OTP code against its hash

    Args:
        plain_otp: Plain OTP code from user
        hashed_otp: Hashed OTP from database

    Returns:
        bool: True if OTP matches
    """
    return password_hash.verify(plain_otp, hashed_otp)


def parse_user_agent(user_agent: str) -> dict:
    """
    Parse user agent string to extract device information

    Args:
        user_agent: User agent string from request

    Returns:
        dict: Parsed device info with 'name' and 'type'
    """
    user_agent = user_agent.lower()

    # Determine device type
    if "mobile" in user_agent or "android" in user_agent or "iphone" in user_agent:
        device_type = "mobile"
    elif "tablet" in user_agent or "ipad" in user_agent:
        device_type = "tablet"
    else:
        device_type = "desktop"

    # Extract browser name
    browser = "Unknown"
    if "edg" in user_agent:
        browser = "Edge"
    elif "chrome" in user_agent:
        browser = "Chrome"
    elif "safari" in user_agent and "chrome" not in user_agent:
        browser = "Safari"
    elif "firefox" in user_agent:
        browser = "Firefox"
    elif "opera" in user_agent or "opr" in user_agent:
        browser = "Opera"

    # Extract OS
    os_name = "Unknown"
    if "windows" in user_agent:
        os_name = "Windows"
    elif "mac" in user_agent:
        os_name = "macOS"
    elif "linux" in user_agent:
        os_name = "Linux"
    elif "android" in user_agent:
        os_name = "Android"
    elif "ios" in user_agent or "iphone" in user_agent or "ipad" in user_agent:
        os_name = "iOS"

    device_name = f"{browser} on {os_name}"

    return {"name": device_name, "type": device_type}
