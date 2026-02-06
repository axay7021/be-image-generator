"""Data Transfer Objects for Transaction management."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.schema import PaymentProvider, PaymentStatus, ReconciliationStatus


class TransactionBase(BaseModel):
    """Base transaction schema."""

    amount: Decimal = Field(..., description="Transaction amount")
    currency: str = Field(default="INR", description="Currency code")
    payment_provider: PaymentProvider = Field(..., description="Payment provider")
    payment_method: str | None = Field(None, description="Payment method (card, upi, etc.)")
    payment_metadata: dict | None = Field(None, description="Additional payment metadata")


class TransactionCreateRequest(TransactionBase):
    """Request schema for creating a transaction."""

    user_id: str = Field(..., description="User ID")
    plan_id: str = Field(..., description="Plan ID")
    subscription_id: str | None = Field(None, description="Associated subscription ID")
    payment_provider_id: str = Field(..., description="External payment ID from provider")
    payment_status: PaymentStatus = Field(default=PaymentStatus.PENDING, description="Payment status")
    reconciliation_status: ReconciliationStatus = Field(
        default=ReconciliationStatus.MATCHED, description="Reconciliation status"
    )


class TransactionResponse(TransactionBase):
    """Response schema for transaction details."""

    id: str = Field(..., description="Transaction ID")
    user_id: str = Field(..., description="User ID")
    plan_id: str = Field(..., description="Plan ID")
    subscription_id: str | None = Field(None, description="Associated subscription ID")
    payment_provider_id: str = Field(..., description="External payment ID")
    payment_status: PaymentStatus = Field(..., description="Payment status")
    reconciliation_status: ReconciliationStatus = Field(..., description="Reconciliation status")
    created_at: datetime = Field(..., description="Transaction creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    """Response schema for paginated transaction list."""

    transactions: list[TransactionResponse] = Field(..., description="List of transactions")
    total: int = Field(..., description="Total count of transactions")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum records returned")


class TransactionUpdateRequest(BaseModel):
    """Request schema for updating transaction status."""

    payment_status: PaymentStatus | None = Field(None, description="New payment status")
    reconciliation_status: ReconciliationStatus | None = Field(None, description="New reconciliation status")
    payment_metadata: dict | None = Field(None, description="Updated metadata")


class TransactionSummary(BaseModel):
    """Summary statistics for transactions."""

    total_amount: Decimal = Field(..., description="Total transaction amount")
    transaction_count: int = Field(..., description="Number of transactions")
    successful_transactions: int = Field(..., description="Number of successful transactions")
    failed_transactions: int = Field(..., description="Number of failed transactions")
    pending_transactions: int = Field(..., description="Number of pending transactions")
    refunded_transactions: int = Field(..., description="Number of refunded transactions")
