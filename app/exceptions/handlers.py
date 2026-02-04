"""Global exception handlers for the application"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import logger


def error_response(status_code: int, message: str, data: Any = None) -> JSONResponse:
    """
    Create a standardized error response

    Args:
        status_code: HTTP status code
        message: Error message
        data: Additional error data (optional)

    Returns:
        JSONResponse with standardized error format
    """
    return JSONResponse(
        status_code=status_code,
        content={"statusCode": status_code, "success": False, "message": message, "data": data},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions with standardized format

    This catches all HTTPException instances raised in the application
    and formats them with the standardized response structure.
    """
    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail} | Path: {request.url.path} | Method: {request.method}"
    )

    return error_response(status_code=exc.status_code, message=str(exc.detail))


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle Pydantic validation errors with standardized format

    Returns detailed validation errors in a user-friendly format.
    """
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")

    # Format validation errors
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field or "body", "message": error["msg"], "type": error["type"]})

    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Validation error",
        data={"errors": errors},
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """
    Handle database integrity errors with standardized format

    This catches constraint violations, unique key errors, etc.
    """
    logger.error(f"Database integrity error on {request.url.path}: {str(exc)}", exc_info=True)

    # Extract meaningful error message
    error_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)

    # Check for common integrity errors
    if "unique constraint" in error_msg.lower() or "duplicate" in error_msg.lower():
        message = "A record with this value already exists"
    elif "foreign key" in error_msg.lower():
        message = "Related record not found"
    elif "not null" in error_msg.lower():
        message = "Required field is missing"
    else:
        message = "Database constraint violation"

    return error_response(status_code=status.HTTP_400_BAD_REQUEST, message=message)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all other unhandled exceptions with standardized format

    This is the catch-all handler for unexpected errors.
    """
    logger.error(f"Unhandled exception on {request.url.path}: {str(exc)}", exc_info=True)

    # In production, don't expose internal error details
    return error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred. Please try again later.",
    )


def add_exception_handlers(app: FastAPI):
    """Add global exception handlers to the FastAPI application"""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
