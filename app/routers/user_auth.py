"""User authentication endpoints"""

from fastapi import APIRouter, status

from app.dependencies.user_auth import CurrentActiveUser
from app.dto.user_dto import UserResponse
from app.i18n import msg
from app.utils.response import success_response

router = APIRouter(prefix="/user/auth", tags=["User Authentication"])


# ============================================
# Profile Endpoints
# ============================================


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user_info(current_user: CurrentActiveUser):
    """
    Get current user information.
    Authentication: Bearer <Clerk Token>
    """
    user_data = UserResponse.model_validate(current_user)

    return success_response(
        data=user_data.model_dump(),
        message=msg("PROFILE_RETRIEVED"),
    )
