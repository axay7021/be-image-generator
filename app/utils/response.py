"""Common response wrapper utilities for standardized API responses"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# Generic type for data payload
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    Standardized API response wrapper

    All API endpoints should return responses in this format for consistency.

    Example:
        {
            "statusCode": 200,
            "success": true,
            "message": "Operation successful",
            "data": {...}
        }
    """

    statusCode: int = Field(..., description="HTTP status code")
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Human-readable message about the operation")
    data: T | None = Field(None, description="Response payload (object or array)")

    model_config = {"from_attributes": True}


class PaginatedData(BaseModel, Generic[T]):
    """
    Wrapper for paginated data with metadata
    """

    items: list[T] = Field(..., description="List of items for current page")
    totalCount: int = Field(..., description="Total number of items across all pages")
    totalPages: int = Field(..., description="Total number of pages")
    currentPage: int = Field(..., description="Current page number (1-indexed)")
    hasNextPage: bool = Field(..., description="Whether there is a next page")

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standardized paginated API response

    Example:
        {
            "statusCode": 200,
            "success": true,
            "message": "Items retrieved successfully",
            "data": [...],
            "totalCount": 100,
            "totalPages": 10,
            "currentPage": 1,
            "hasNextPage": true
        }
    """

    statusCode: int = Field(..., description="HTTP status code")
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Human-readable message about the operation")
    data: list[T] = Field(..., description="List of items for current page")
    totalCount: int = Field(..., description="Total number of items across all pages")
    totalPages: int = Field(..., description="Total number of pages")
    currentPage: int = Field(..., description="Current page number (1-indexed)")
    hasNextPage: bool = Field(..., description="Whether there is a next page")

    model_config = {"from_attributes": True}


# Helper functions for creating responses
def success_response(data: Any = None, message: str = "Operation successful", status_code: int = 200) -> dict[str, Any]:
    """
    Create a successful API response

    Args:
        data: Response payload
        message: Success message
        status_code: HTTP status code

    Returns:
        Standardized response dictionary
    """
    return {"statusCode": status_code, "success": True, "message": message, "data": data}


def error_response(message: str = "Operation failed", status_code: int = 400, data: Any = None) -> dict[str, Any]:
    """
    Create an error API response

    Args:
        message: Error message
        status_code: HTTP status code
        data: Additional error data (optional)

    Returns:
        Standardized error response dictionary
    """
    return {"statusCode": status_code, "success": False, "message": message, "data": data}


def paginated_response(
    items: list[Any],
    total_count: int,
    page: int = 1,
    page_size: int = 10,
    message: str = "Items retrieved successfully",
    status_code: int = 200,
) -> dict[str, Any]:
    """
    Create a paginated API response

    Args:
        items: List of items for current page
        total_count: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page
        message: Success message
        status_code: HTTP status code

    Returns:
        Standardized paginated response dictionary
    """
    import math

    total_pages = math.ceil(total_count / page_size) if page_size > 0 else 0
    has_next_page = page < total_pages

    return {
        "statusCode": status_code,
        "success": True,
        "message": message,
        "data": items,
        "totalCount": total_count,
        "totalPages": total_pages,
        "currentPage": page,
        "hasNextPage": has_next_page,
    }
