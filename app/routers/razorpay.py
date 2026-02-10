from datetime import datetime, timedelta, timezone
from typing import Annotated

import razorpay
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.core.settings import settings
from app.db import get_db
from app.db.schema import Plan, Subscription, User
from app.dependencies.user_auth import get_current_active_user
from app.services.subscription_bypass_service import (
    get_purchase_gate_state,
    grant_free_bypass,
    is_free_bypass_plan,
    purchase_block_reason,
)
from app.services.transaction_service import TransactionService
from app.utils.response import success_response

router = APIRouter(prefix="/razorpay", tags=["Razorpay"])

# Initialize Razorpay Client
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@router.post("/checkout/{plan_id}", status_code=status.HTTP_200_OK)
async def create_order(
    plan_id: str,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a Razorpay Order for a plan"""
    plan = await db.get(Plan, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    gate_state = await get_purchase_gate_state(db, str(user.id))
    now = datetime.now(timezone.utc)
    block_reason = purchase_block_reason(gate_state, now)
    if block_reason:
        raise HTTPException(status_code=400, detail=block_reason)

    if is_free_bypass_plan(str(plan.id)):
        subscription = await grant_free_bypass(db, user, plan)
        return success_response(
            data={
                "direct_access": True,
                "subscription_id": str(subscription.id),
            },
            message="Free access granted",
        )

    try:
        if plan.razorpay_plan_id and plan.billing_interval:
            # Create Subscription (Recurring) ONLY if billing_interval is set
            # We assume the Plan created on Dashboard matches the interval/amount users expect.

            sub_data = {
                "plan_id": plan.razorpay_plan_id,
                "total_count": 120,  # Max cycles (approx 10 years monthly), or 1 if just using it as a vehicle?
                # Usually total_count is required.
                "quantity": 1,
                "customer_notify": 1,
                "notes": {"user_id": str(user.id), "plan_id": str(plan.id)},
            }

            subscription = client.subscription.create(data=sub_data)

            return success_response(
                data={
                    "subscription_id": subscription["id"],  # Frontend should use this key
                    "key_id": settings.RAZORPAY_KEY_ID,
                    "name": settings.APP_NAME,
                    "description": f"Subscription to {plan.name}",
                    "prefill": {"name": user.full_name, "email": user.email, "contact": user.phone_number},
                },
                message="Razorpay subscription created",
            )

        else:
            # Create Payment Link (One-Time)
            # This replaces both static Payment Page and Standard Order.
            # Using Payment Links API as requested to guarantee "notes" are passed to webhook.

            amount_in_smallest_unit = int(plan.price_usd * 100)

            payment_link_data = {
                "amount": amount_in_smallest_unit,
                "currency": "INR",  # Using USD as per DB schema
                "accept_partial": False,
                "description": f"Payment for {plan.name}",
                "customer": {"name": user.full_name, "email": user.email, "contact": user.phone_number},
                "notes": {"user_id": str(user.id), "plan_id": str(plan.id)},
                # Redirect user back to frontend after payment
                "callback_url": f"{settings.FRONTEND_URL}/subscription/success",
                "callback_method": "get",
            }

            response = client.payment_link.create(payment_link_data)

            return success_response(
                data={"payment_page_url": response["short_url"], "message": "Payment Link generated"},
                message="Payment Link created",
            )

    except Exception as e:
        logger.error(f"Razorpay creation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/webhook", include_in_schema=False)
async def razorpay_webhook(  # noqa: PLR0912, PLR0915
    request: Request,
    x_razorpay_signature: Annotated[str, Header()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    # Verify Signature
    try:
        client.utility.verify_webhook_signature(body_str, x_razorpay_signature, settings.RAZORPAY_WEBHOOK_SECRET)
    except Exception as e:
        logger.error(f"Razorpay custom signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    event = await request.json()
    event_type = event.get("event")

    logger.info(f"Received Razorpay webhook: {event_type}")

    if event_type == "payment.captured":
        # Handle one-time payment success
        payment = event["payload"]["payment"]["entity"]
        notes = payment.get("notes", {})

        if isinstance(notes, list):
            notes = {}

        # DEBUG LOGGING
        logger.info(f"Payment Captured Notes: {notes}")

        user_id = notes.get("user_id")
        plan_id = notes.get("plan_id")

        # Fallback: Try to find user by email/phone if user_id is missing
        if not user_id:
            logger.info("user_id not found in notes. Trying fallback via email/contact.")
            email = payment.get("email") or notes.get("email")

            if email:
                # Find user by email
                stmt = select(User).where(User.email == email)
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if user:
                    user_id = str(user.id)
                    logger.info(f"Found user {user_id} via email {email}")

        if user_id:
            if not plan_id:
                # Heuristic: Match plan by price
                amount_paid = payment.get("amount")  # in paise
                if amount_paid:
                    amount_usd = amount_paid / 100.0
                    stmt = select(Plan).where(Plan.price_usd == amount_usd)
                    result = await db.execute(stmt)
                    matched_plan = result.scalar_one_or_none()
                    if matched_plan:
                        plan_id = str(matched_plan.id)
                        logger.info(f"Matched plan {plan_id} via amount {amount_paid}")

        if user_id and plan_id:
            # Create Transaction record for analytics and reconciliation
            transaction_service = TransactionService(db)
            amount_in_cents = payment.get("amount", 0)  # Razorpay amount is in paise
            amount_usd = amount_in_cents / 100.0

            await transaction_service.create_transaction(
                user_id=user_id,
                plan_id=plan_id,
                amount=amount_usd,
                currency=payment.get("currency", "INR"),
                payment_provider="razorpay",
                payment_provider_id=payment["id"],
                payment_status="captured",
                payment_metadata={
                    "razorpay_payment_id": payment["id"],
                    "razorpay_order_id": payment.get("order_id"),
                    "method": payment.get("method"),
                    "email": payment.get("email"),
                    "contact": payment.get("contact"),
                    "notes": notes,
                },
            )
            logger.info(f"Created transaction record for Razorpay payment {payment['id']}")

            # Use Payment ID as key
            await handle_payment_success(user_id, plan_id, payment["id"], db)
        else:
            logger.error(f"Missing user_id ({user_id}) or plan_id ({plan_id}) in payment. data: {payment}")

    elif event_type == "subscription.charged":
        # Handle subscription success
        subscription = event["payload"]["subscription"]["entity"]
        payment = event["payload"]["payment"]["entity"]

        notes = subscription.get("notes", {})
        user_id = notes.get("user_id")
        plan_id = notes.get("plan_id")

        # Razorpay Subscription ID (starts with sub_)
        sub_id = subscription["id"]

        if user_id and plan_id:
            await handle_payment_success(user_id, plan_id, sub_id, db)

    return {"status": "ok"}


async def handle_payment_success(user_id: str, plan_id: str, payment_id: str, db: AsyncSession):
    # Check duplicate
    stmt = select(Subscription).where(Subscription.razorpay_subscription_id == payment_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        return

    plan = await db.get(Plan, plan_id)
    if not plan:
        return

    now = datetime.now()
    expiration_date = now + timedelta(days=plan.validity_days)

    new_sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        razorpay_subscription_id=payment_id,  # Storing Payment ID as sub ID for one-time
        payment_provider="razorpay",
        status="active",
        quota_used=0,
        period_start=now,
        period_end=expiration_date,
        image_generation_limit=plan.image_quota,
    )
    db.add(new_sub)
    await db.commit()
    logger.info(f"Activated Razorpay subscription {payment_id} for user {user_id}")
