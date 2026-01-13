from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Build a simple JSON response that includes the details of the rate limit
    that was hit. If no limit is hit, the countdown is added to headers.
    """
    return JSONResponse(
        content={
            "success": False,
            "error": {
                "code": 429,
                "message": f"Rate limit exceeded: {exc.detail}",
                "path": str(request.url.path),
            },
        },
        status_code=429,
    )
