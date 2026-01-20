import pytest
from unittest.mock import MagicMock, AsyncMock
from app.dependencies.quota import check_quota
from app.db.schema import Subscription, Plan, User


@pytest.mark.asyncio
async def test_quota_check_uses_subscription_limit():
    # Mock mocks
    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"

    mock_db = AsyncMock()

    # Mock User
    mock_user = User(id="user_123", email="test@example.com")

    # Mock Subscription
    # Status active, limit 50, quota_used 49
    mock_sub = Subscription(
        id="sub_123",
        user_id="user_123",
        plan_id="plan_123",
        status="active",
        image_generation_limit=50,
        quota_used=49,
        period_end=datetime.now() + timedelta(days=30),
    )
    # Ensure checking plan doesn't affect it (though code shouldn't access it)
    mock_sub.plan = MagicMock()
    mock_sub.plan.image_quota = 100  # Different from subscription limit

    # Setup DB response
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sub
    mock_db.execute.return_value = mock_result

    # Act
    remaining = await check_quota(mock_request, mock_db, mock_user)

    # Assert
    assert remaining == 1
    # Verify we didn't use the plan's quota (100 - 49 = 51)


@pytest.mark.asyncio
async def test_quota_exhausted_uses_subscription_limit():
    # Mock mocks
    mock_request = MagicMock()

    mock_db = AsyncMock()
    mock_user = User(id="user_123", email="test@example.com")

    # Mock Subscription with limit 50, used 50
    mock_sub = Subscription(
        id="sub_123",
        user_id="user_123",
        plan_id="plan_123",
        status="active",
        image_generation_limit=50,
        quota_used=50,
        period_end=datetime.now() + timedelta(days=30),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sub
    mock_db.execute.return_value = mock_result

    # Act & Assert
    from app.exceptions.quota_exception import QuotaLimitExceeded

    with pytest.raises(QuotaLimitExceeded) as exc:
        await check_quota(mock_request, mock_db, mock_user)

    assert "Subscription quota exceeded" in str(exc.value.detail)


from datetime import datetime, timedelta
