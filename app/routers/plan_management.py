"""Plan Management Router for admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.schema import Admin
from app.dependencies.clerk_admin_auth import get_clerk_admin
from app.dto.plan_management_dto import (
    PlanCreateRequest,
    PlanListResponse,
    PlanResponse,
    PlanStatsResponse,
    PlanUpdateRequest,
)
from app.services.plan_management_service import PlanManagementService
from app.utils.response import success_response

router = APIRouter(prefix="/admin/plans", tags=["Admin - Plan Management"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/create", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_plan(
    request: Request,
    body: PlanCreateRequest,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new subscription plan.

    If billing_interval is provided ('monthly' or 'yearly'), creates a Razorpay recurring plan.
    Otherwise, creates a one-time payment plan.

    Requires Clerk admin authentication.
    """
    service = PlanManagementService(db)

    try:
        plan = await service.create_plan(
            name=body.name,
            price_usd=body.price_usd,
            image_quota=body.image_quota,
            validity_days=body.validity_days,
            billing_interval=body.billing_interval,
            is_popular=body.is_popular,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    plan_response = PlanResponse(
        id=str(plan.id),
        name=plan.name,
        price_usd=plan.price_usd,
        image_quota=plan.image_quota,
        validity_days=plan.validity_days,
        billing_interval=plan.billing_interval,
        razorpay_plan_id=plan.razorpay_plan_id,
        is_active=plan.is_active,
        is_popular=plan.is_popular,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )

    return success_response(data=plan_response.model_dump(), message="Plan created successfully")


@router.get("", status_code=status.HTTP_200_OK)
# @router.get("/", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def list_plans(
    request: Request,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: bool = Query(default=False, description="Include inactive plans"),
):
    """
    Get list of all plans.

    By default, only returns active plans. Set include_inactive=true to see all.
    Requires Clerk admin authentication.
    """
    service = PlanManagementService(db)
    plans = await service.get_all_plans(include_inactive=include_inactive)

    plan_responses = [
        PlanResponse(
            id=str(plan.id),
            name=plan.name,
            price_usd=plan.price_usd,
            image_quota=plan.image_quota,
            validity_days=plan.validity_days,
            billing_interval=plan.billing_interval,
            razorpay_plan_id=plan.razorpay_plan_id,
            is_active=plan.is_active,
            is_popular=plan.is_popular,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
        for plan in plans
    ]

    return success_response(
        data=PlanListResponse(plans=plan_responses, total=len(plan_responses)).model_dump(),
        message="Plans retrieved successfully",
    )


@router.get("/{plan_id}", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def get_plan(
    request: Request,
    plan_id: str,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get detailed information about a specific plan.

    Requires Clerk admin authentication.
    """
    service = PlanManagementService(db)
    plan = await service.get_plan(plan_id)

    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    plan_response = PlanResponse(
        id=str(plan.id),
        name=plan.name,
        price_usd=plan.price_usd,
        image_quota=plan.image_quota,
        validity_days=plan.validity_days,
        billing_interval=plan.billing_interval,
        razorpay_plan_id=plan.razorpay_plan_id,
        is_active=plan.is_active,
        is_popular=plan.is_popular,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )

    return success_response(data=plan_response.model_dump(), message="Plan details retrieved")


@router.patch("/{plan_id}", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def update_plan(
    request: Request,
    plan_id: str,
    body: PlanUpdateRequest,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update plan details.

    Note: Cannot modify billing_interval or Razorpay plan after creation.
    Updating price_usd won't update the Razorpay plan price.

    Requires Clerk admin authentication.
    """
    service = PlanManagementService(db)
    plan = await service.update_plan(
        plan_id=plan_id,
        name=body.name,
        price_usd=body.price_usd,
        image_quota=body.image_quota,
        validity_days=body.validity_days,
        is_active=body.is_active,
        is_popular=body.is_popular,
    )

    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    plan_response = PlanResponse(
        id=str(plan.id),
        name=plan.name,
        price_usd=plan.price_usd,
        image_quota=plan.image_quota,
        validity_days=plan.validity_days,
        billing_interval=plan.billing_interval,
        razorpay_plan_id=plan.razorpay_plan_id,
        is_active=plan.is_active,
        is_popular=plan.is_popular,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )

    return success_response(data=plan_response.model_dump(), message="Plan updated successfully")


@router.delete("/{plan_id}", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def delete_plan(
    request: Request,
    plan_id: str,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Soft delete a plan (sets is_active to False).

    Cannot delete plans with active subscriptions.
    Requires Clerk admin authentication.
    """
    service = PlanManagementService(db)

    try:
        success = await service.delete_plan(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    return success_response(data={"plan_id": plan_id}, message="Plan deleted successfully")


@router.get("/{plan_id}/stats", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def get_plan_stats(
    request: Request,
    plan_id: str,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get statistics for a specific plan.

    Returns subscription counts by status and other metrics.
    Requires Clerk admin authentication.
    """
    service = PlanManagementService(db)
    stats = await service.get_plan_stats(plan_id)

    if not stats:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    stats_response = PlanStatsResponse(**stats)

    return success_response(data=stats_response.model_dump(), message="Plan statistics retrieved")
