from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.logger import logger, request_logger
from app.core.settings import settings
from app.exceptions import (
    HTTPException,
    QuotaLimitExceeded,
    RequestValidationError,
    global_exception_handler,
    http_exception_handler,
    quota_limit_exceeded_handler,
    rate_limit_exceeded_handler,
    validation_exception_handler,
)
from app.routers import router
from app.tasks.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting up the application...")

    # Start background scheduler for cleanup tasks

    # Start background scheduler for cleanup tasks
    start_scheduler()

    yield

    # Shutdown
    stop_scheduler()
    logger.info("Application shutdown complete")


app: FastAPI = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)


limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])
app.state.limiter = limiter


# Register Middleware
# Trust proxy headers (X-Forwarded-For, etc.) - Critical for running behind Caddy/Nginx
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def register_request_logger(request: Request, call_next):
    if request.url.path.startswith('/api/v1/modify-image') and not settings.GEMINI_API_KEY:
        return JSONResponse(status_code=503, content={"code": "AI_NOT_CONFIGURED", "message": "Image generation is not configured yet. The owner must add the Gemini key."})
    if request.url.path.startswith('/api/') and not settings.DATABASE_URL:
        return JSONResponse(status_code=503, content={"code": "DATABASE_NOT_CONFIGURED", "message": "Database is not configured yet."})
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    origin = request.headers.get("origin", "unknown")
    referer = request.headers.get("referer", "unknown")

    request_logger.info(
        f"Incoming request: {request.method} {request.url.path} | "
        f"IP: {client_ip} | User-Agent: {user_agent} | "
        f"Origin: {origin} | Referer: {referer}"
    )

    response = await call_next(request)

    request_logger.info(
        f"Completed request: {request.method} {request.url.path} | Status: {response.status_code} | IP: {client_ip}"
    )
    return response


app.include_router(router)
app.add_middleware(SlowAPIMiddleware)


# Register Exception Handlers (order matters: most specific first)
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore
app.add_exception_handler(Exception, global_exception_handler)  # type: ignore
app.add_exception_handler(QuotaLimitExceeded, quota_limit_exceeded_handler)  # type: ignore
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "configured": {"database": bool(settings.DATABASE_URL), "ai": bool(settings.GEMINI_API_KEY), "clerk": bool(settings.CLERK_SECRET_KEY and settings.CLERK_JWKS_URL)}}
