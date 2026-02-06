"""Reconciliation Service for payment provider sync and audit."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import razorpay
import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.core.settings import settings
from app.db.schema import (
    ActivityLog,
    PaymentProvider,
    PaymentStatus,
    ReconciliationStatus,
    Transaction,
)
from app.dto.reconciliation_dto import ReconciliationReport


class ReconciliationService:
    """Service for reconciling transactions with payment providers."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        stripe.api_key = settings.STRIPE_SECRET_KEY

    async def sync_razorpay(
        self,
        from_date: date,
        to_date: date,
        performed_by_id: str = None,
    ) -> ReconciliationReport:
        """
        Fetch Razorpay payments and reconcile with database transactions.

        Args:
            from_date: Start date for fetching payments
            to_date: End date for fetching payments
            performed_by_id: Admin ID performing the sync

        Returns:
            ReconciliationReport with sync results
        """
        logger.info(f"Starting Razorpay reconciliation from {from_date} to {to_date}")

        # Convert dates to Unix timestamps
        from_timestamp = int(datetime.combine(from_date, datetime.min.time()).timestamp())
        to_timestamp = int(datetime.combine(to_date + timedelta(days=1), datetime.min.time()).timestamp())

        matched_count = 0
        unmatched_count = 0
        created_count = 0
        amount_discrepancies = []
        missing_in_db = []

        try:
            # Fetch payments from Razorpay
            payments = self.razorpay_client.payment.all(
                {
                    "from": from_timestamp,
                    "to": to_timestamp,
                    "count": 100,  # Adjust as needed, use pagination if necessary
                }
            )

            payment_list = payments.get("items", [])
            total_fetched = len(payment_list)

            logger.info(f"Fetched {total_fetched} payments from Razorpay")

            for payment in payment_list:
                payment_id = payment["id"]
                amount_paise = payment.get("amount", 0)
                amount = Decimal(amount_paise) / Decimal(100)  # Convert paise to rupees
                currency = payment.get("currency", "INR")
                status = payment.get("status", "")

                # Map Razorpay status to our enum
                payment_status_map = {
                    "captured": PaymentStatus.CAPTURED,
                    "authorized": PaymentStatus.PENDING,
                    "failed": PaymentStatus.FAILED,
                    "refunded": PaymentStatus.REFUNDED,
                }
                payment_status = payment_status_map.get(status, PaymentStatus.PENDING)

                # Check if transaction exists in DB
                query = select(Transaction).where(Transaction.payment_provider_id == payment_id)
                result = await self.db.execute(query)
                transaction = result.scalar_one_or_none()

                if transaction:
                    # Transaction exists, verify amounts
                    if abs(float(transaction.amount) - float(amount)) > 0.01:  # Allow 1 cent tolerance
                        # Amount mismatch
                        transaction.reconciliation_status = ReconciliationStatus.UNMATCHED
                        unmatched_count += 1
                        amount_discrepancies.append(
                            {
                                "payment_id": payment_id,
                                "db_amount": float(transaction.amount),
                                "provider_amount": float(amount),
                                "currency": currency,
                            }
                        )
                        logger.warning(f"Amount mismatch for {payment_id}: DB={transaction.amount}, Provider={amount}")
                    else:
                        # Amounts match
                        if transaction.reconciliation_status == ReconciliationStatus.UNMATCHED:
                            transaction.reconciliation_status = ReconciliationStatus.MATCHED
                        matched_count += 1
                # Transaction missing in DB
                elif status == "captured":
                    # Only create for captured payments
                    notes = payment.get("notes", {})
                    user_id = notes.get("user_id")
                    plan_id = notes.get("plan_id")

                    if user_id and plan_id:
                        new_transaction = Transaction(
                            user_id=user_id,
                            plan_id=plan_id,
                            amount=amount,
                            currency=currency,
                            payment_provider=PaymentProvider.RAZORPAY,
                            payment_provider_id=payment_id,
                            payment_status=payment_status,
                            reconciliation_status=ReconciliationStatus.UNMATCHED,
                            payment_metadata={
                                "razorpay_payment_id": payment_id,
                                "razorpay_order_id": payment.get("order_id"),
                                "method": payment.get("method"),
                                "email": payment.get("email"),
                                "contact": payment.get("contact"),
                                "reconciled_from_api": True,
                            },
                        )
                        self.db.add(new_transaction)
                        created_count += 1
                        logger.info(f"Created missing transaction for Razorpay payment {payment_id}")
                    else:
                        missing_in_db.append(
                            {
                                "payment_id": payment_id,
                                "amount": float(amount),
                                "currency": currency,
                                "reason": "Missing user_id or plan_id in notes",
                            }
                        )
                else:
                    missing_in_db.append(
                        {
                            "payment_id": payment_id,
                            "amount": float(amount),
                            "currency": currency,
                            "status": status,
                            "reason": f"Payment status is {status}, not captured",
                        }
                    )

            await self.db.commit()

            # Log reconciliation action
            if performed_by_id:
                activity_log = ActivityLog(
                    action=f"Reconciliation sync completed for Razorpay ({from_date} to {to_date})",
                    performed_by_id=performed_by_id,
                    performed_by_type="admin",
                    entity_type="reconciliation",
                )
                self.db.add(activity_log)
                await self.db.commit()

            return ReconciliationReport(
                provider="razorpay",
                total_fetched=total_fetched,
                matched_count=matched_count,
                unmatched_count=unmatched_count,
                created_count=created_count,
                amount_discrepancies=amount_discrepancies,
                missing_in_db=missing_in_db,
            )

        except Exception as e:
            logger.error(f"Razorpay reconciliation failed: {e}", exc_info=True)
            raise ValueError(f"Reconciliation sync failed: {str(e)}")

    async def get_discrepancies(self) -> list[dict[str, Any]]:
        """
        Get all transactions with unmatched reconciliation status.

        Returns:
            List of transactions needing manual review
        """
        query = (
            select(Transaction)
            .where(Transaction.reconciliation_status == ReconciliationStatus.UNMATCHED)
            .order_by(Transaction.created_at.desc())
        )

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        discrepancies = []
        for txn in transactions:
            discrepancies.append(
                {
                    "transaction_id": str(txn.id),
                    "user_id": str(txn.user_id) if txn.user_id else None,
                    "provider_payment_id": txn.payment_provider_id,
                    "payment_provider": txn.payment_provider,
                    "reconciliation_status": txn.reconciliation_status,
                    "amount": float(txn.amount),
                    "currency": txn.currency,
                    "payment_status": txn.payment_status,
                    "created_at": txn.created_at,
                    "issue_description": "Amount mismatch or missing webhook data",
                }
            )

        return discrepancies

    async def mark_as_manually_reconciled(
        self,
        transaction_id: str,
        performed_by_id: str,
        notes: str = None,
    ) -> bool:
        """
        Manually mark a transaction as reconciled.

        Args:
            transaction_id: Transaction ID to update
            performed_by_id: Admin performing the action
            notes: Optional notes about the manual reconciliation

        Returns:
            True if successful, False if transaction not found
        """
        transaction = await self.db.get(Transaction, transaction_id)
        if not transaction:
            return False

        old_status = transaction.reconciliation_status
        transaction.reconciliation_status = ReconciliationStatus.MANUAL

        # Log the manual reconciliation
        activity_log = ActivityLog(
            action=f"Manual reconciliation: {transaction.payment_provider_id}",
            performed_by_id=performed_by_id,
            performed_by_type="admin",
            entity_type="transaction",
            entity_id=str(transaction.id),
            changes={
                "reconciliation_status": {
                    "old": old_status.value,
                    "new": ReconciliationStatus.MANUAL.value,
                },
                "notes": notes,
            },
        )
        self.db.add(activity_log)

        await self.db.commit()
        logger.info(f"Transaction {transaction_id} manually reconciled by admin {performed_by_id}")
        return True
