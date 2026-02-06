"""Service for managing payment transactions."""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schema import (
    ActivityAction,
    ActivityLog,
    PaymentProvider,
    PaymentStatus,
    PerformedByType,
    ReconciliationStatus,
    Transaction,
)
from app.dto.transaction_dto import TransactionSummary

logger = logging.getLogger(__name__)


class TransactionService:
    """Service for managing payment transactions."""

    @staticmethod
    async def create_transaction(
        db: AsyncSession,
        user_id: str,
        plan_id: str,
        payment_provider_id: str,
        amount: Decimal,
        currency: str,
        payment_provider: PaymentProvider,
        payment_status: PaymentStatus = PaymentStatus.PENDING,
        reconciliation_status: ReconciliationStatus = ReconciliationStatus.MATCHED,
        subscription_id: str | None = None,
        payment_method: str | None = None,
        payment_metadata: dict | None = None,
        performed_by_id: str | None = None,
        performed_by_type: PerformedByType = PerformedByType.AI_AGENT,
    ) -> Transaction:
        """
        Create a new transaction record.

        Args:
            db: Database session
            user_id: User ID
            plan_id: Plan ID
            payment_provider_id: External payment ID from provider
            amount: Transaction amount
            currency: Currency code
            payment_provider: Payment provider (stripe/razorpay)
            payment_status: Payment status
            reconciliation_status: Reconciliation status
            subscription_id: Optional subscription ID
            payment_method: Payment method (card, upi, etc.)
            payment_metadata: Additional payment metadata
            performed_by_id: ID of the entity creating the transaction
            performed_by_type: Type of entity (admin/user/ai_agent)

        Returns:
            Created Transaction object
        """
        # Check if transaction with this payment_provider_id already exists
        existing = await db.execute(select(Transaction).where(Transaction.payment_provider_id == payment_provider_id))
        if existing.scalar_one_or_none():
            logger.warning(f"Transaction with payment_provider_id {payment_provider_id} already exists")
            return existing.scalar_one()

        # Create transaction
        transaction = Transaction(
            id=str(uuid4()),
            user_id=user_id,
            plan_id=plan_id,
            subscription_id=subscription_id,
            payment_provider_id=payment_provider_id,
            amount=amount,
            currency=currency,
            payment_provider=payment_provider,
            payment_method=payment_method,
            payment_status=payment_status,
            reconciliation_status=reconciliation_status,
            payment_metadata=payment_metadata or {},
        )

        db.add(transaction)

        # Log activity
        activity_log = ActivityLog(
            id=str(uuid4()),
            entity_type="transaction",
            entity_id=transaction.id,
            action=ActivityAction.CREATE,
            performed_by_type=performed_by_type,
            performed_by_id=performed_by_id,
            changes={
                "amount": float(amount),
                "currency": currency,
                "payment_provider": payment_provider.value,
                "payment_status": payment_status.value,
                "user_id": user_id,
                "plan_id": plan_id,
            },
        )
        db.add(activity_log)

        await db.commit()
        await db.refresh(transaction)

        logger.info(f"Created transaction {transaction.id} for user {user_id}, amount: {amount} {currency}")
        return transaction

    @staticmethod
    async def update_transaction_status(
        db: AsyncSession,
        transaction_id: str,
        payment_status: PaymentStatus | None = None,
        reconciliation_status: ReconciliationStatus | None = None,
        payment_metadata: dict | None = None,
        performed_by_id: str | None = None,
        performed_by_type: PerformedByType = PerformedByType.ADMIN,
    ) -> Transaction:
        """
        Update transaction status.

        Args:
            db: Database session
            transaction_id: Transaction ID
            payment_status: New payment status
            reconciliation_status: New reconciliation status
            payment_metadata: Updated metadata
            performed_by_id: ID of the entity updating the transaction
            performed_by_type: Type of entity (admin/user/ai_agent)

        Returns:
            Updated Transaction object
        """
        result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
        transaction = result.scalar_one_or_none()

        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")

        changes = {}

        if payment_status and transaction.payment_status != payment_status:
            changes["payment_status"] = {"old": transaction.payment_status.value, "new": payment_status.value}
            transaction.payment_status = payment_status

        if reconciliation_status and transaction.reconciliation_status != reconciliation_status:
            changes["reconciliation_status"] = {
                "old": transaction.reconciliation_status.value,
                "new": reconciliation_status.value,
            }
            transaction.reconciliation_status = reconciliation_status

        if payment_metadata:
            transaction.payment_metadata = {**(transaction.payment_metadata or {}), **payment_metadata}
            changes["metadata_updated"] = True

        if changes:
            # Log activity
            activity_log = ActivityLog(
                id=str(uuid4()),
                entity_type="transaction",
                entity_id=transaction.id,
                action=ActivityAction.UPDATE,
                performed_by_type=performed_by_type,
                performed_by_id=performed_by_id,
                changes=changes,
            )
            db.add(activity_log)

            await db.commit()
            await db.refresh(transaction)
            logger.info(f"Updated transaction {transaction_id}: {changes}")

        return transaction

    @staticmethod
    async def get_transaction_summary(
        db: AsyncSession,
        user_id: str | None = None,
        plan_id: str | None = None,
        payment_provider: PaymentProvider | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> TransactionSummary:
        """
        Get summary statistics for transactions.

        Args:
            db: Database session
            user_id: Filter by user ID
            plan_id: Filter by plan ID
            payment_provider: Filter by payment provider
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            TransactionSummary object with statistics
        """
        query = select(
            func.sum(Transaction.amount).label("total_amount"),
            func.count(Transaction.id).label("transaction_count"),
            func.sum(func.case((Transaction.payment_status == PaymentStatus.CAPTURED, 1), else_=0)).label(
                "successful_transactions"
            ),
            func.sum(func.case((Transaction.payment_status == PaymentStatus.FAILED, 1), else_=0)).label(
                "failed_transactions"
            ),
            func.sum(func.case((Transaction.payment_status == PaymentStatus.PENDING, 1), else_=0)).label(
                "pending_transactions"
            ),
            func.sum(func.case((Transaction.payment_status == PaymentStatus.REFUNDED, 1), else_=0)).label(
                "refunded_transactions"
            ),
        )

        # Apply filters
        if user_id:
            query = query.where(Transaction.user_id == user_id)
        if plan_id:
            query = query.where(Transaction.plan_id == plan_id)
        if payment_provider:
            query = query.where(Transaction.payment_provider == payment_provider)
        if start_date:
            query = query.where(Transaction.created_at >= start_date)
        if end_date:
            query = query.where(Transaction.created_at <= end_date)

        result = await db.execute(query)
        row = result.one()

        return TransactionSummary(
            total_amount=row.total_amount or Decimal(0),
            transaction_count=row.transaction_count or 0,
            successful_transactions=row.successful_transactions or 0,
            failed_transactions=row.failed_transactions or 0,
            pending_transactions=row.pending_transactions or 0,
            refunded_transactions=row.refunded_transactions or 0,
        )

    @staticmethod
    async def get_transaction_by_provider_id(db: AsyncSession, payment_provider_id: str) -> Transaction | None:
        """
        Get transaction by external payment provider ID.

        Args:
            db: Database session
            payment_provider_id: External payment ID

        Returns:
            Transaction object or None
        """
        result = await db.execute(select(Transaction).where(Transaction.payment_provider_id == payment_provider_id))
        return result.scalar_one_or_none()
