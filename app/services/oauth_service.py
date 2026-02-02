import httpx
from fastapi import HTTPException, status

from app.core.settings import settings
from app.i18n import msg


class OAuthService:
    @staticmethod
    def get_google_auth_url() -> str:
        """Generate Google OAuth authorization URL"""
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            "?response_type=code"
            f"&client_id={settings.GOOGLE_CLIENT_ID}"
            f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
            "&scope=openid%20email%20profile"
            "&access_type=offline"
            "&prompt=consent"
        )

    @staticmethod
    async def get_google_user(code: str) -> dict:
        """Exchange code for token and get user info"""
        async with httpx.AsyncClient() as client:
            # Exchange code for token
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=msg("GOOGLE_LOGIN_FAILED"),
                )

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            # Get user info
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if user_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=msg("GOOGLE_LOGIN_FAILED"),
                )

            return user_response.json()


oauth_service = OAuthService()
