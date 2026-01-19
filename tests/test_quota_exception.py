from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from app.db.schema import DailyUsage, Plan, Subscription
from app.dependencies.quota import check_quota
from app.exceptions.quota_exception import QuotaLimitExceeded


@pytest.mark.asyncio
async def test_quota_limit_exceeded_anonymous():
    """Test that check_quota raises QuotaLimitExceeded for anonymous user exceeding limit"""
    mock_request = MagicMock(spec=Request)
    mock_request.client.host = "127.0.0.1"

    mock_db = AsyncMock()
    mock_user = None

    # Simulate DB returning daily usage >= limit (1)
    mock_result = MagicMock()
    mock_daily_usage = DailyUsage(usage_count=1)
    mock_result.scalar_one_or_none.return_value = mock_daily_usage
    mock_db.execute.return_value = mock_result

    # Mock settings.ENVIRONMENT to not be 'development' to enforce quota
    with pytest.raises(QuotaLimitExceeded) as exc_info:
        # We need to ensure settings.ENVIRONMENT is not 'development'
        # Since we can't easily patch settings here without more context,
        # we'll assume the environment allows quota grouping or we patch it if needed.
        # Ideally we patch 'app.dependencies.quota.settings'
        from app.dependencies import quota

        original_env = quota.settings.ENVIRONMENT
        quota.settings.ENVIRONMENT = "production"

        try:
            await check_quota(mock_request, mock_db, mock_user)
        finally:
            quota.settings.ENVIRONMENT = original_env

    assert exc_info.value.detail == "Daily free limit reached. Please login or subscribe for more."


@pytest.mark.asyncio
async def test_quota_limit_exceeded_subscription():
    """Test that check_quota raises QuotaLimitExceeded for subscriber exceeding limit"""
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock()

    mock_user = MagicMock()
    mock_user.id = 123

    # Simulate active subscription with usage >= limit
    mock_sub = MagicMock(spec=Subscription)
    mock_sub.quota_used = 100
    mock_sub.plan = MagicMock(spec=Plan)
    mock_sub.plan.image_quota = 100

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sub
    mock_db.execute.return_value = mock_result

    with pytest.raises(QuotaLimitExceeded) as exc_info:
        from app.dependencies import quota

        original_env = quota.settings.ENVIRONMENT
        quota.settings.ENVIRONMENT = "production"

        try:
            await check_quota(mock_request, mock_db, mock_user)
        finally:
            quota.settings.ENVIRONMENT = original_env

    assert exc_info.value.detail == "Subscription plan quota exceeded."
