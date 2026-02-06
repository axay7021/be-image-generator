from fastapi import APIRouter

from app.routers import (
    admin_auth,
    analytics,
    example,
    image,
    plan_management,
    razorpay,
    reconciliation,
    subscription,
    user_auth,
    user_management,
    webhook,
)

router = APIRouter(prefix="/api/v1")

router.include_router(webhook.router)
router.include_router(razorpay.router)

router.include_router(admin_auth.router)
router.include_router(user_auth.router)
router.include_router(subscription.router)
router.include_router(image.router)
router.include_router(example.router)

# Admin panel routers
router.include_router(analytics.router)
router.include_router(user_management.router)
router.include_router(plan_management.router)
router.include_router(reconciliation.router)
