from fastapi import Request
from fastapi.responses import JSONResponse


class QuotaLimitExceeded(Exception):
    def __init__(self, detail: str = "Quota limit exceeded"):
        self.detail = detail


async def quota_limit_exceeded_handler(request: Request, exc: QuotaLimitExceeded) -> JSONResponse:
    """
    Handle QuotaLimitExceeded with standardized format
    """
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": {
                "code": 429,
                "message": exc.detail,
                "path": str(request.url.path),
            },
        },
    )
