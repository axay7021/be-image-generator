from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.db.schema import (
    CreatedVia,
    Plan,
    Subscription,
    User,
)

# ============================================
# User Queries
# ============================================


async def get_user_by_phone(phone: str, db: AsyncSession) -> User | None:
    """Get user by phone number"""
    query = select(User).where(User.phone_number == phone)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_email(email: str, db: AsyncSession) -> User | None:
    """Get user by email address"""
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_clerk_id(clerk_id: str, db: AsyncSession) -> User | None:
    """Get user by Clerk ID"""
    query = select(User).where(User.clerk_id == clerk_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


# ============================================
# Clerk Webhook Handling & Sync
# ============================================


async def create_or_update_from_clerk_payload(  # noqa: PLR0915
    payload: dict,
    email: str | None,
    db: AsyncSession,
) -> User:
    """
    Create or update user from Clerk user payload.
    Used by both Webhook (Create/Update) and Auth Dependency (Sync on login).
    """
    clerk_id = payload.get("id")
    if not clerk_id:
        raise ValueError("Missing 'id' in Clerk payload")

    # Extract user details
    first_name = payload.get("first_name", "") or ""
    last_name = payload.get("last_name", "") or ""
    full_name = f"{first_name} {last_name}".strip()
    if not full_name:
        full_name = "Clerk User"

    avatar_url = payload.get("image_url") or payload.get("profile_image_url")

    # 1. Try to find by Clerk ID
    existing_user = await get_user_by_clerk_id(clerk_id, db)

    if existing_user:
        # Update existing user
        updated = False
        if float(payload.get("updated_at", 0)) > 0:
            # Basic check to avoid overwriting with stale data, though payload usually fresh
            pass

        if existing_user.email != email:
            existing_user.email = email
            updated = True

        if existing_user.full_name != full_name:
            existing_user.full_name = full_name
            updated = True

        if avatar_url and existing_user.avatar_url != avatar_url:
            existing_user.avatar_url = avatar_url
            updated = True

        if updated:
            await db.commit()
            await db.refresh(existing_user)
            logger.info(f"User {existing_user.id} updated from Clerk payload")

        return existing_user

    else:
        # 2. Try to find by Email (Link account or Legacy migration)
        # Note: migrating old users who have google_id as their 'clerk_id' conceptually
        if email:
            user_by_email = await get_user_by_email(email, db)
            if user_by_email:
                logger.info(f"Linking existing user {user_by_email.id} (email match) to Clerk ID {clerk_id}")
                user_by_email.clerk_id = clerk_id

                # Update other fields
                user_by_email.full_name = full_name
                if avatar_url:
                    user_by_email.avatar_url = avatar_url

                await db.commit()
                await db.refresh(user_by_email)
                return user_by_email

        # 3. Create new user
        logger.info(f"Creating new user from Clerk ID {clerk_id}")
        new_user = User(
            clerk_id=clerk_id,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            created_via=CreatedVia.CLERK,
            is_active=True,
            password_hash=None,
        )
        db.add(new_user)
        try:
            await db.commit()
            await db.refresh(new_user)

            # Assign default 'Basic' subscription
            plan_query = select(Plan).where(Plan.name == "Basic")
            plan_result = await db.execute(plan_query)
            basic_plan = plan_result.scalar_one_or_none()

            if basic_plan:
                now = datetime.now(timezone.utc)
                period_end = now + timedelta(days=basic_plan.validity_days)
                new_subscription = Subscription(
                    user_id=new_user.id,
                    plan_id=basic_plan.id,
                    payment_provider="system_default",
                    status="active",
                    quota_used=0,
                    period_start=now,
                    period_end=period_end,
                    image_generation_limit=basic_plan.image_quota,
                )
                db.add(new_subscription)
                await db.commit()
                logger.info(f"Assigned default Basic plan to new user {new_user.id}")

            return new_user
        except IntegrityError:
            await db.rollback()
            # Race condition handling
            return await get_user_by_clerk_id(clerk_id, db)


async def handle_clerk_webhook_event(event_type: str, data: dict, db: AsyncSession):
    """
    Handle Clerk webhook events.

    Supported events:
    - user.created
    - user.updated
    - user.deleted
    """
    logger.info(f"Processing Clerk Webhook: {event_type}")

    if event_type in ["user.created", "user.updated"]:
        # Extract primary email
        email = None
        email_addresses = data.get("email_addresses", [])
        primary_email_id = data.get("primary_email_address_id")

        for email_obj in email_addresses:
            if email_obj.get("id") == primary_email_id:
                email = email_obj.get("email_address")
                break

        if not email and email_addresses:
            # Fallback to first email
            email = email_addresses[0].get("email_address")

        await create_or_update_from_clerk_payload(data, email, db)

    elif event_type == "user.deleted":
        clerk_id = data.get("id")
        if not clerk_id:
            logger.warning("Clerk user.deleted event missing ID")
            return

        user = await get_user_by_clerk_id(clerk_id, db)
        if user:
            logger.info(f"Marking user {user.id} (Clerk {clerk_id}) as inactive due to deletion")
            user.is_active = False  # Soft delete
            # Optional: user.clerk_id = None # to allow re-registration? Maybe not.
            await db.commit()
        else:
            logger.info(f"User {clerk_id} not found for deletion")

    else:
        logger.debug(f"Unhandled Clerk event type: {event_type}")
