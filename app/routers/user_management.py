"""User Management Router for admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies.auth import CurrentActiveAdmin
from app.dto.user_management_dto import (
    UserListFilters,
    UserStatusUpdateRequest,
)
from app.services.user_management_service import UserManagementService
from app.utils.response import success_response

router = APIRouter(prefix="/admin/users", tags=["Admin - User Management"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def list_users(  # noqa: PLR0913
    request: Request,
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(None, description="Search by email, phone, or name"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    created_via: str | None = Query(None, description="Filter by registration source"),
    has_active_subscription: bool | None = Query(None, description="Filter by subscription status"),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum records to return"),
):
    """
    Get paginated list of users with optional filters.

    Requires Clerk admin authentication.
    """
    filters = UserListFilters(
        search=search,
        is_active=is_active,
        created_via=created_via,
        has_active_subscription=has_active_subscription,
        skip=skip,
        limit=limit,
    )

    service = UserManagementService(db)
    result = await service.get_users(filters)

    return success_response(data=result.model_dump(), message="Users retrieved successfully")


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def get_user_detail(
    request: Request,
    user_id: str,
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get detailed information about a specific user.

    Includes subscriptions, transaction count, and quota summary.
    """
    service = UserManagementService(db)
    user_detail = await service.get_user_detail(user_id)

    if not user_detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return success_response(data=user_detail.model_dump(), message="User details retrieved")


@router.patch("/{user_id}/status", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def update_user_status(
    request: Request,
    user_id: str,
    body: UserStatusUpdateRequest,
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update user status (block/unblock).

    Logs the action to ActivityLog with optional reason.
    """
    service = UserManagementService(db)
    success = await service.update_user_status(
        user_id=user_id, is_active=body.is_active, admin_id=admin.id, reason=body.reason
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    action = "activated" if body.is_active else "deactivated"
    return success_response(
        data={"user_id": user_id, "is_active": body.is_active}, message=f"User {action} successfully"
    )


@router.get("/{user_id}/activity", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def get_user_activity(  # noqa: PLR0913
    request: Request,
    user_id: str,
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum records to return"),
):
    """
    Get paginated activity logs for a specific user.

    Returns ImageLog entries (image generation history).
    """
    service = UserManagementService(db)
    activity = await service.get_user_activity(user_id, skip=skip, limit=limit)

    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return success_response(data=activity.model_dump(), message="User activity retrieved")


@router.get("/{user_id}/transactions", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def get_user_transactions(  # noqa: PLR0913
    request: Request,
    user_id: str,
    admin: CurrentActiveAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum records to return"),
):
    """
    Get paginated transaction history for a specific user.

    Returns all transactions with payment and reconciliation status.
    """
    service = UserManagementService(db)
    transactions_data = await service.get_user_transactions(user_id, skip=skip, limit=limit)

    if not transactions_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Serialize transaction items
    transactions_data["transactions"] = [txn.model_dump() for txn in transactions_data["transactions"]]

    return success_response(data=transactions_data, message="User transactions retrieved")
