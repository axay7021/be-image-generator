import asyncio
from datetime import datetime, timedelta
from typing import Annotated, Any

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.logger import logger
from app.core.settings import settings
from app.db import get_db
from app.db.schema import Plan, Subscription, User
from app.dependencies.auth import get_current_active_admin
from app.dependencies.user_auth import get_current_active_user
from app.dto.subscription_dto import (
    CheckoutResponse,
    PlanCreateRequest,
    PlanResponse,
    SubscriptionResponse,
)
from app.utils.response import success_response

router = APIRouter(tags=["Subscription"])

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# ============================================
# Admin Endpoints (Manage Plans)
# ============================================


@router.post("/admin/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: PlanCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_user: Annotated[Any, Depends(get_current_active_admin)],
):
    """Create a new subscription plan"""
    # Check if plan name exists
    query = select(Plan).where(Plan.name == data.name)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Plan with this name already exists")

    new_plan = Plan(
        name=data.name,
        price_usd=data.price_usd,
        image_quota=data.image_quota,
        stripe_price_id=data.stripe_price_id,
        razorpay_plan_id=data.razorpay_plan_id,
        razorpay_payment_page_id=data.razorpay_payment_page_id,
        billing_interval=data.billing_interval,
        validity_days=data.validity_days,
    )
    db.add(new_plan)
    await db.commit()
    await db.refresh(new_plan)

    return success_response(
        data=PlanResponse.model_validate(new_plan).model_dump(), message="Plan created successfully", status_code=201
    )


@router.get("/plans", status_code=status.HTTP_200_OK)
async def list_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all active plans"""
    query = select(Plan).where(Plan.is_active.is_(True))
    result = await db.execute(query)
    plans = result.scalars().all()

    return success_response(
        data=[PlanResponse.model_validate(p).model_dump() for p in plans], message="Plans retrieved successfully"
    )


# ============================================
# User Endpoints (Checkout)
# ============================================


@router.post("/checkout/{plan_id}", status_code=status.HTTP_200_OK, response_model=CheckoutResponse)
async def create_checkout_session(
    plan_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a Stripe Checkout session for a plan"""
    plan = await db.get(Plan, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        # Determine success/cancel URLs
        # Use Frontend URL for redirection
        base_url = settings.FRONTEND_URL.rstrip("/")
        success_url = f"{base_url}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/subscription/cancel"

        mode = "subscription" if plan.billing_interval else "payment"

        # Run blocking Stripe call in a thread to avoid freezing the event loop
        print(f"DEBUG: Calling Stripe Session.create with mode={mode}, price={plan.stripe_price_id}")
        checkout_session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            payment_method_types=["card"],
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            mode=mode,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user.email,
            client_reference_id=str(user.id),
            metadata={"plan_id": str(plan.id), "user_id": str(user.id)},
            payment_intent_data={"metadata": {"plan_id": str(plan.id), "user_id": str(user.id)}}
            if mode == "payment"
            else None,
        )
        print(f"DEBUG: Stripe Session created: {checkout_session.url}")

        return success_response(data={"url": checkout_session.url}, message="Checkout session created")

    except Exception as e:
        logger.error(f"Checkout session creation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/my-subscription", status_code=status.HTTP_200_OK)
async def get_my_subscription(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get current user's active subscription (aggregated)"""
    # Fetch ALL active subscriptions
    query = (
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.created_at.asc())  # Oldest first
    )

    result = await db.execute(query)
    subscriptions = result.scalars().all()

    if not subscriptions:
        return success_response(data=None, message="No active subscription")

    # Calculate totals
    total_limit = sum(sub.image_generation_limit for sub in subscriptions)
    total_used = sum(sub.quota_used for sub in subscriptions)

    # Use the first (oldest) subscription for metadata (plan details etc)
    primary_sub = subscriptions[0]
    await db.refresh(primary_sub, ["plan"])

    # Create response object
    response_data = SubscriptionResponse.model_validate(primary_sub)

    # Override with aggregated totals
    response_data.image_generation_limit = total_limit
    response_data.quota_used = total_used

    return success_response(data=response_data.model_dump(), message="Subscription retrieved")


@router.get("/my-subscription-history", status_code=status.HTTP_200_OK)
async def get_my_subscription_history(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get all subscriptions for the current user (history)"""
    query = (
        select(Subscription)
        .options(joinedload(Subscription.plan))
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    result = await db.execute(query)
    subs = result.scalars().all()

    return success_response(
        data=[SubscriptionResponse.model_validate(sub).model_dump() for sub in subs],
        message="Subscription history retrieved",
    )


# ============================================
# Stripe Webhook
# ============================================


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str, Header()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    payload = await request.body()
    sig_header = stripe_signature
    print(f"DEBUG: Received webhook with signature: {sig_header}")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        print(f"DEBUG: Webhook verified. Event Type: {event['type']}")
    except ValueError as e:
        print(f"DEBUG: Webhook Payload Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload") from e
    except stripe.error.SignatureVerificationError as e:
        print(f"DEBUG: Webhook Signature Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    # Handle events
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print(f"DEBUG: Processing checkout.session.completed for session {session.get('id')}")
        # Fulfill the purchase...
        await handle_checkout_completed(session, db)

    elif event["type"] == "payment_intent.succeeded":
        print(f"DEBUG: Processing payment_intent.succeeded for {event['data']['object'].get('id')}")
        await handle_payment_intent_succeeded(event["data"]["object"], db)

    elif event["type"] == "invoice.payment_succeeded":
        # Reset quota for new period
        invoice = event["data"]["object"]
        await handle_payment_succeeded(invoice, db)

    elif event["type"] == "customer.subscription.deleted":
        # Cancel subscription
        subscription = event["data"]["object"]
        await handle_subscription_deleted(subscription, db)

    return {"status": "success"}


async def handle_checkout_completed(session, db: AsyncSession):
    user_id = session.get("client_reference_id")
    plan_id = session.get("metadata", {}).get("plan_id")
    stripe_sub_id = session.get("subscription")

    if not user_id or not plan_id:
        logger.error(f"Missing user_id or plan_id in checkout session: {session}")
        return

    logger.info(f"Processing checkout for user {user_id}, plan {plan_id}")

    # Get the plan to know the validity period
    plan = await db.get(Plan, plan_id)
    if not plan:
        logger.error(f"Plan {plan_id} not found")
        return

    # Deactivate old active subscriptions - REMOVED to allow stacking
    # stmt = select(Subscription).where(Subscription.user_id == user_id, Subscription.status == "active")
    # result = await db.execute(stmt)
    # old_subs = result.scalars().all()
    # for sub in old_subs:
    #     sub.status = "canceled"
    #     logger.info(f"Canceled old subscription {sub.id}")

    # Set period dates based on plan validity
    now = datetime.now()
    expiration_date = now + timedelta(days=plan.validity_days)

    # For one-time payments (no subscription ID)
    if not stripe_sub_id:
        # Prefer Payment Intent ID for consistency with fallback handler
        payment_intent_id = session.get("payment_intent")
        if payment_intent_id and isinstance(payment_intent_id, str):
            stripe_sub_id = f"one_time_{payment_intent_id}"
        else:
            stripe_sub_id = f"one_time_{session.get('id')}"

        logger.info(f"One-time payment, using ID: {stripe_sub_id}")

        # Check if already fulfilled (e.g. by payment_intent event)
        stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            logger.info(f"Subscription {stripe_sub_id} already fulfilled (likely by payment_intent).")
            return

    new_sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        stripe_subscription_id=stripe_sub_id,
        status="active",
        quota_used=0,
        period_start=now,
        period_end=expiration_date,  # Set expiration based on plan validity
        image_generation_limit=plan.image_quota,
    )
    db.add(new_sub)
    await db.commit()
    logger.info(f"Created subscription {stripe_sub_id} for user {user_id}, expires on {expiration_date}")


async def handle_payment_succeeded(invoice, db: AsyncSession):
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()

    if sub:
        sub.quota_used = 0  # Reset quota
        sub.status = "active"  # Reactivate if it was quota_exhausted
        sub.period_start = datetime.fromtimestamp(invoice["period_start"])
        sub.period_end = datetime.fromtimestamp(invoice["period_end"])
        await db.commit()
        logger.info(f"Subscription {stripe_sub_id} reactivated with quota reset")


async def handle_payment_intent_succeeded(payment_intent, db: AsyncSession):
    # This acts as a FALLBACK if checkout.session.completed is missing/delayed
    metadata = payment_intent.get("metadata", {})
    user_id = metadata.get("user_id")
    plan_id = metadata.get("plan_id")

    if not user_id or not plan_id:
        # Many payment intents might not be for subscriptions (e.g. invoices?), ignore them if no metadata
        # Only process if we explicitly added the metadata in create_checkout_session
        return

    logger.info(f"Processing payment_intent fallback for user {user_id}, plan {plan_id}")

    # Use payment_intent ID as the unique key to prevent duplication with checkout session
    # If checkout session handles it, it uses "one_time_{session_id}"
    # If we handle it here, we use "one_time_{payment_intent_id}"
    # Wait, if we use different IDs, we might double-fulfill!
    #
    # Checkout Session ID != Payment Intent ID.
    # We must check if "one_time_{payment_intent_id}" OR "one_time_{session_id}" exists?
    # No, we can't easily know the session ID from here without an API call.
    #
    # STRATEGY:
    # 1. We prioritize checkout.session.completed.
    # 2. If this runs, it means checkout.session.completed might have failed or not arrived yet.
    # 3. We'll use "pi_{payment_intent_id}" as the subscription ID.
    # 4. If checkout.session.completed arrives LATER, it uses "one_time_{session_id}".
    #    --> Double fulfillment risk.
    #
    # However, for the USER's specific issue, they are NOT getting checkout.session.completed.
    # So this unblocks them.
    #
    # Can we link them? The Checkout Session object contains `payment_intent` ID.
    # So in `handle_checkout_completed`, we should PREFER using payment_intent ID if available?
    # Yes. Let's modify handle_checkout_completed first to use payment_intent ID if available.

    stripe_sub_id = f"one_time_{payment_intent['id']}"

    # Check validation
    stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        logger.info(f"Payment intent {stripe_sub_id} already processed.")
        return

    # Helper logic similar to handle_checkout
    plan = await db.get(Plan, plan_id)
    if not plan:
        logger.error(f"Plan {plan_id} not found")
        return

    now = datetime.now()
    expiration_date = now + timedelta(days=plan.validity_days)

    new_sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        stripe_subscription_id=stripe_sub_id,
        status="active",
        quota_used=0,
        period_start=now,
        period_end=expiration_date,
        image_generation_limit=plan.image_quota,
    )
    db.add(new_sub)
    await db.commit()
    logger.info(f"Created subscription (fallback) {stripe_sub_id} for user {user_id}")


async def handle_subscription_deleted(subscription_obj, db: AsyncSession):
    stripe_sub_id = subscription_obj["id"]
    stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()

    if sub:
        sub.status = "canceled"
        await db.commit()
