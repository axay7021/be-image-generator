"""Reconciliation Router for payment sync and audit."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.schema import Admin
from app.dependencies.clerk_admin_auth import get_clerk_admin
from app.dto.reconciliation_dto import (
    DiscrepanciesResponse,
    DiscrepancyItem,
    ReconciliationSyncRequest,
)
from app.services.reconciliation_service import ReconciliationService
from app.utils.response import success_response

router = APIRouter(prefix="/admin/reconciliation", tags=["Admin - Reconciliation"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/sync", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def sync_payments(
    http_request: Request,
    request: ReconciliationSyncRequest,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Sync transactions with payment provider API.

    Fetches payments from the provider for the specified date range and:
    - Matches existing transactions
    - Flags amount discrepancies
    - Creates missing transactions (if captured)

    Rate limited to 5 requests per minute due to external API calls.
    Requires Clerk admin authentication.
    """
    service = ReconciliationService(db)

    try:
        if request.provider.value == "razorpay":
            report = await service.sync_razorpay(
                from_date=request.from_date,
                to_date=request.to_date,
                performed_by_id=str(admin.id),
            )
        else:
            # Stripe reconciliation can be added here
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Stripe reconciliation not yet implemented"
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return success_response(
        data=report.model_dump(),
        message=f"Reconciliation completed: {report.matched_count} matched, "
        f"{report.unmatched_count} unmatched, {report.created_count} created",
    )


@router.get("/discrepancies", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_discrepancies(
    request: Request,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get list of all transactions with reconciliation discrepancies.

    Returns transactions where reconciliation_status is 'unmatched'.
    These require manual review and resolution.

    Requires Clerk admin authentication.
    """
    service = ReconciliationService(db)
    discrepancies_data = await service.get_discrepancies()

    discrepancies = [DiscrepancyItem(**item) for item in discrepancies_data]

    total_amount = sum(item.amount for item in discrepancies)

    response = DiscrepanciesResponse(
        discrepancies=discrepancies,
        total=len(discrepancies),
        unmatched_amount=total_amount,
    )

    return success_response(
        data=response.model_dump(), message=f"Found {len(discrepancies)} transactions needing reconciliation"
    )


@router.patch("/{transaction_id}/manual-reconcile", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def manual_reconcile_transaction(
    request: Request,
    transaction_id: str,
    admin: Annotated[Admin, Depends(get_clerk_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: str = None,
):
    """
    Manually mark a transaction as reconciled.

    Use this for transactions that cannot be auto-reconciled but have been
    verified manually. Sets reconciliation_status to 'manual'.

    Requires Clerk admin authentication.
    """
    service = ReconciliationService(db)
    success = await service.mark_as_manually_reconciled(
        transaction_id=transaction_id,
        performed_by_id=str(admin.id),
        notes=notes,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return success_response(data={"transaction_id": transaction_id}, message="Transaction manually reconciled")
