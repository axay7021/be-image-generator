"""Analytics router for admin dashboard."""

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import CurrentActiveAdmin
from app.dto.analytics_dto import (
    Period,
)
from app.services.analytics_service import AnalyticsService
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/overview", response_model=dict)
@limiter.limit("20/minute")
async def get_dashboard_overview(
    request: Request, admin: CurrentActiveAdmin, db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get quick overview stats for admin dashboard."""
    overview = await AnalyticsService.get_dashboard_overview(db)
    return success_response(data=overview.model_dump(), message="Dashboard overview retrieved successfully")


@router.get("/sales", response_model=dict)
@limiter.limit("20/minute")
async def get_sales_analytics(  # noqa: PLR0913
    request: Request,
    start_date: Annotated[date, Query(description="Start date (YYYY-MM-DD)")],
    end_date: Annotated[date, Query(description="End date (YYYY-MM-DD)")],
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[Period, Query(description="Aggregation period: daily, weekly, or monthly")] = "daily",
):
    """
    Get sales analytics with revenue breakdown.

    Returns time-series data showing revenue, transaction counts,
    and payment provider breakdown for the specified period.
    """
    analytics = await AnalyticsService.get_sales_analytics(period, start_date, end_date, db)
    return success_response(data=analytics.model_dump(), message="Sales analytics retrieved successfully")


@router.get("/traffic", response_model=dict)
@limiter.limit("20/minute")
async def get_traffic_analytics(  # noqa: PLR0913
    request: Request,
    start_date: Annotated[date, Query(description="Start date (YYYY-MM-DD)")],
    end_date: Annotated[date, Query(description="End date (YYYY-MM-DD)")],
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[Period, Query(description="Aggregation period: daily, weekly, or monthly")] = "daily",
):
    """
    Get user traffic and registration analytics.

    Returns time-series data showing new user registrations,
    active users, and registration source breakdown.
    """
    analytics = await AnalyticsService.get_traffic_analytics(period, start_date, end_date, db)
    return success_response(data=analytics.model_dump(), message="Traffic analytics retrieved successfully")


@router.get("/plans", response_model=dict)
@limiter.limit("20/minute")
async def get_plan_analytics(
    request: Request,
    start_date: Annotated[date, Query(description="Start date (YYYY-MM-DD)")],
    end_date: Annotated[date, Query(description="End date (YYYY-MM-DD)")],
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get analytics per subscription plan.

    Returns subscription counts, revenue, active users,
    and churn rates for each plan.
    """
    analytics = await AnalyticsService.get_plan_analytics(start_date, end_date, db)
    return success_response(data=analytics.model_dump(), message="Plan analytics retrieved successfully")
