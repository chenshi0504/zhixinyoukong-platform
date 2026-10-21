"""
Report Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReportBase(BaseModel):
    """Base report schema."""
    task_id: int


class ReportCreate(ReportBase):
    """Schema for creating a report (file upload handled separately)."""
    pass


class ReportGrade(BaseModel):
    """Schema for grading a report."""
    score: float = Field(..., ge=0, le=100)
    feedback: Optional[str] = None


class ReportResponse(BaseModel):
    """Schema for report response."""
    id: int
    task_id: int
    student_id: int
    file_name: str
    file_path: str
    score: Optional[float]
    feedback: Optional[str]
    status: str
    is_late: bool
    submitted_at: datetime
    graded_at: Optional[datetime]
    graded_by: Optional[int]
    
    class Config:
        from_attributes = True


class ReportListResponse(BaseModel):
    """Schema for report list with additional info."""
    id: int
    task_id: int
    task_title: Optional[str] = None
    student_id: int
    student_name: Optional[str] = None
    student_number: Optional[str] = None
    file_name: str
    score: Optional[float]
    status: str
    is_late: bool
    submitted_at: datetime
    graded_at: Optional[datetime]
    
    class Config:
        from_attributes = True
