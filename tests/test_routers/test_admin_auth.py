import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.schema import Admin, AdminRole

# Mock data
ADMIN_EMAIL = "test_admin@example.com"
ADMIN_PASSWORD = "test_password_123"
ADMIN_NAME = "Test Admin"


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create a test admin user"""
    # Check if exists first (though transaction should be clean)
    from sqlalchemy import select

    result = await db_session.execute(select(Admin).where(Admin.email == ADMIN_EMAIL))
    if result.scalar_one_or_none():
        return

    admin = Admin(
        email=ADMIN_EMAIL,
        password_hash=get_password_hash(ADMIN_PASSWORD),
        full_name=ADMIN_NAME,
        role=AdminRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_admin_login_success(client: AsyncClient, admin_user):
    """Test successful admin login"""
    response = await client.post("/admin/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]
    # Verify token_type is bearer
    assert data["data"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_admin_login_failure(client: AsyncClient, admin_user):
    """Test admin login with incorrect password"""
    response = await client.post("/admin/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong_password"})
    assert response.status_code == 401
    # Message format depends on handler, just checking 401 is sufficient


@pytest.mark.asyncio
async def test_admin_login_non_existent(client: AsyncClient):
    """Test admin login for non-existent user"""
    response = await client.post("/admin/auth/login", json={"email": "nonexistent@example.com", "password": "password"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_refresh_token(client: AsyncClient, admin_user):
    """Test token refresh flow"""
    # 1. Login to get tokens
    login_response = await client.post("/admin/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    tokens = login_response.json()["data"]
    refresh_token = tokens["refresh_token"]

    # 2. Refresh token
    response = await client.post("/admin/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]
    assert data["data"]["access_token"] != tokens["access_token"]


@pytest.mark.asyncio
async def test_admin_logout(client: AsyncClient, admin_user):
    """Test logout flow"""
    # 1. Login
    login_response = await client.post("/admin/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    data = login_response.json()["data"]
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    # 2. Logout
    response = await client.post(
        "/admin/auth/logout", headers={"Authorization": f"Bearer {access_token}"}, json={"refresh_token": refresh_token}
    )

    assert response.status_code == 200
    # assert response.json()["message"] == "Logged out successfully" # I18n dependent

    # 3. Verify token is invalid (protected endpoint)
    # We can try to access me or logout again
    response = await client.post(
        "/admin/auth/logout", headers={"Authorization": f"Bearer {access_token}"}, json={"refresh_token": refresh_token}
    )
    # This should fail because the session is deleted/revoked or token invalid
    assert response.status_code == 401
