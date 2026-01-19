from fastapi import APIRouter

from app.routers import (
    admin,
    admin_auth,
    example,
    image,
    subscription,
    user_auth,
    webhook,
)

router = APIRouter(prefix="/api/v1")

router.include_router(webhook.router)

router.include_router(admin_auth.router)
router.include_router(user_auth.router)
router.include_router(subscription.router)
router.include_router(image.router)
router.include_router(admin.router)
router.include_router(example.router)
