"""Webhook endpoints"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.logger import logger
from app.core.settings import settings
from app.db import get_db
from app.services import user_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/clerk", status_code=status.HTTP_200_OK)
async def clerk_webhook(
    request: Request,
    svix_id: Annotated[str, Header(alias="svix-id")],
    svix_timestamp: Annotated[str, Header(alias="svix-timestamp")],
    svix_signature: Annotated[str, Header(alias="svix-signature")],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Clerk webhooks for user synchronization.
    Verifies Svix signature.
    """
    webhook_secret = settings.CLERK_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("CLERK_WEBHOOK_SECRET is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook configuration error",
        )

    # Get body as bytes for verification
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    # Verify Signature
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }

    wh = Webhook(webhook_secret)
    try:
        payload = wh.verify(body_text, headers)
    except WebhookVerificationError as e:
        logger.warning(f"Webhook verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    # Process Event
    event_type = payload.get("type")
    data = payload.get("data")

    if not event_type or not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload format",
        )

    try:
        await user_service.handle_clerk_webhook_event(event_type, data, db)
    except Exception as e:
        logger.error(f"Error processing webhook event {event_type}: {e}", exc_info=True)
        # Return 200 to Clerk even if processing fails to prevent retries if it's a logic error?
        # Better to 500 so Clerk retries transients, but careful with poison messages.
        # For now, let it fail (500) so we see alerts.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing event",
        )

    return {"status": "received"}
