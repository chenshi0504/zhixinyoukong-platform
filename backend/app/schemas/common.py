"""
Common Pydantic schemas for error responses and pagination.
"""
from pydantic import BaseModel
from typing import Optional, List, Generic, TypeVar
from datetime import datetime

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    code: str
    message: str
    detail: Optional[str] = None
    suggestion: Optional[str] = None


class SuccessResponse(BaseModel):
    """Standard success response schema."""
    message: str
    data: Optional[dict] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response schema."""
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str
    service: str
    version: str
    timestamp: datetime
