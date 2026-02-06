"""Data Transfer Objects for Reconciliation endpoints."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.schema import PaymentProvider, PaymentStatus, ReconciliationStatus


class ReconciliationSyncRequest(BaseModel):
    """Request to sync transactions with payment provider."""

    provider: PaymentProvider = Field(..., description="Payment provider to sync")
    from_date: date = Field(..., description="Start date for reconciliation")
    to_date: date = Field(..., description="End date for reconciliation")


class ReconciliationReport(BaseModel):
    """Report of reconciliation sync results."""

    provider: str = Field(..., description="Payment provider")
    total_fetched: int = Field(..., description="Total payments fetched from provider")
    matched_count: int = Field(..., description="Transactions matched successfully")
    unmatched_count: int = Field(..., description="Transactions with discrepancies")
    created_count: int = Field(..., description="New transactions created")
    amount_discrepancies: list[dict] = Field(default_factory=list, description="Amount mismatches")
    missing_in_db: list[dict] = Field(default_factory=list, description="Payments not in database")
    synced_at: datetime = Field(default_factory=datetime.now, description="Sync timestamp")


class DiscrepancyItem(BaseModel):
    """Single transaction discrepancy."""

    transaction_id: str = Field(..., description="Transaction ID")
    user_id: str | None = Field(None, description="User ID")
    provider_payment_id: str = Field(..., description="Payment ID from provider")
    payment_provider: PaymentProvider = Field(..., description="Payment provider")
    reconciliation_status: ReconciliationStatus = Field(..., description="Current status")
    amount: float = Field(..., description="Transaction amount")
    currency: str = Field(..., description="Currency")
    payment_status: PaymentStatus = Field(..., description="Payment status")
    created_at: datetime = Field(..., description="Transaction date")
    issue_description: str | None = Field(None, description="Description of discrepancy")

    model_config = ConfigDict(from_attributes=True)


class DiscrepanciesResponse(BaseModel):
    """Response with list of discrepancies."""

    discrepancies: list[DiscrepancyItem] = Field(..., description="List of unmatched transactions")
    total: int = Field(..., description="Total discrepancy count")
    unmatched_amount: float = Field(..., description="Total amount in unmatched transactions")
