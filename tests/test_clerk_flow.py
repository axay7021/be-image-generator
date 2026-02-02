from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.schema import User


# Mock Svix
@pytest.fixture
def mock_svix():
    with patch("app.routers.webhook.Webhook") as mock:
        yield mock


@pytest.mark.asyncio
async def test_clerk_webhook_creates_user(client: AsyncClient, db_session: AsyncSession, mock_svix):
    instance = mock_svix.return_value
    instance.verify.return_value = {
        "type": "user.created",
        "data": {
            "id": "user_clerk_123",
            "first_name": "Test",
            "last_name": "Clerk",
            "email_addresses": [{"id": "email_1", "email_address": "clerk@test.com"}],
            "primary_email_address_id": "email_1",
            "image_url": "http://img.com/avatar.png",
        },
    }
    headers = {"svix-id": "msg_123", "svix-timestamp": "1234567890", "svix-signature": "v1,signature"}
    settings.CLERK_WEBHOOK_SECRET = "whsec_test"
    response = await client.post("/webhooks/clerk", json={}, headers=headers)
    assert response.status_code == 200

    result = await db_session.execute(select(User).where(User.clerk_id == "user_clerk_123"))
    user = result.scalar_one_or_none()
    assert user is not None


@pytest.mark.asyncio
async def test_clerk_auth_login(client: AsyncClient, db_session: AsyncSession):
    user = User(clerk_id="user_clerk_auth_test", email="auth@test.com", full_name="Auth Test", is_active=True)
    db_session.add(user)
    await db_session.commit()

    with patch("app.dependencies.user_auth.get_clerk_user", return_value="user_clerk_auth_test"):
        response = await client.get("/user/auth/me", headers={"Authorization": "Bearer valid_clerk_token"})
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "auth@test.com"


@pytest.mark.asyncio
async def test_clerk_auth_lazy_sync(client: AsyncClient, db_session: AsyncSession):
    # Mock where used in user_auth.py logic chain
    with patch("app.dependencies.user_auth.get_clerk_user", return_value="user_lazy_sync"):
        # Helper inner class for mocking response
        class MockUser:
            pass

        m = MockUser()
        m.email_addresses = [MagicMock(email_address="lazy@test.com")]
        m.first_name = "Lazy"
        m.last_name = "Sync"
        m.image_url = None

        # Patch the SOURCE in clerk_auth because user_auth imports it at runtime
        with patch("app.dependencies.clerk_auth.clerk_client.users.get", return_value=m):
            response = await client.get("/user/auth/me", headers={"Authorization": "Bearer valid_token_new_user"})

            assert response.status_code == 200
            assert response.json()["data"]["email"] == "lazy@test.com"
