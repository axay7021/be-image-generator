from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    APP_NAME: str = "fastapi templalte"
    DEBUG: bool = True
    ENVIRONMENT: str = "production"  # development or production
    RATE_LIMIT_DEFAULT: str = "10/minute"
    MCP_SERVER_URL: str = "http://localhost:8001/tools/mcp"
    FRONTEND_URL: str = "http://localhost:3000"
    MAX_TEXT_INPUT_LENGTH: int = 500

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost/postgres"

    # JWT Configuration
    ADMIN_JWT_SECRET: str = "change_this_to_a_secure_secret_key"
    ADMIN_JWT_SECRET_REF: str = "change_this_to_a_secure_refresh_secret_key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # In minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # In days

    # User JWT Configuration
    USER_JWT_SECRET: str = "change_this_to_user_secret_key"
    USER_JWT_SECRET_REF: str = "change_this_to_user_refresh_secret_key"
    USER_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour
    USER_REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 days

    # OTP Configuration
    OTP_EXPIRE_MINUTES: int = 10
    MAX_OTP_ATTEMPTS: int = 3

    # LINE Integration
    LINE_CHANNEL_ID: str = ""
    LINE_CHANNEL_SECRET: str = ""
    LINE_API_VERIFY_URL: str = "https://api.line.me/oauth2/v2.1/verify"
    LINE_API_PROFILE_URL: str = "https://api.line.me/v2/profile"

    # SMTP Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@barbershop.com"
    SMTP_FROM_NAME: str = "Barber Shop"
    SMTP_USE_TLS: bool = True

    # Auth
    SECRET_KEY: str = "change_this_to_a_secure_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Admin JWT Credentials (from .env file)
    # Format: admin1@example.com:password1,admin2@example.com:password2
    ADMIN_CREDENTIALS: str = ""  # Comma-separated email:password pairs

    # Super Admin
    SUPER_ADMIN_EMAIL: str = "admin@example.com"
    SUPER_ADMIN_PASSWORD: str = "admin123"
    SUPER_ADMIN_NAME: str = "Super Admin"

    def get_admin_credentials(self) -> dict[str, str]:
        """
        Parse admin credentials from ADMIN_CREDENTIALS env variable.
        Format: email1:password1,email2:password2
        Returns: {email: password, ...}
        """
        admins = {}
        if self.ADMIN_CREDENTIALS:
            pairs = self.ADMIN_CREDENTIALS.split(",")
            for pair in pairs:
                if ":" in pair:
                    email, password = pair.strip().split(":", 1)
                    admins[email.strip()] = password.strip()
        return admins

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/user/auth/google/callback"

    # Clerk Authentication (Next.js Frontend)
    # Only CLERK_SECRET_KEY is required - get it from https://dashboard.clerk.com
    CLERK_SECRET_KEY: str = ""
    CLERK_WEBHOOK_SECRET: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""  # Optional, for frontend reference
    CLERK_JWKS_URL: str = ""  # Optional fallback, auto-derived from secret key

    # LiveKit Agent
    ASSEMBLYAI_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    ELEVEN_LABS_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_API_URL: str = ""
    OPENAI_API_KEY: str = ""
    # Internationalization
    MESSAGE_LANG: str = "en"  # "en" for English (development), "ja" for Japanese (production)

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
