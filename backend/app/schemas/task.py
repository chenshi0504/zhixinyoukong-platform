"""
Task Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class TaskBase(BaseModel):
    """Base task schema with common fields."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    module_id: Optional[str] = Field(None, max_length=50)
    deadline: Optional[datetime] = None
    scoring_criteria: Optional[str] = None


class TaskCreate(TaskBase):
    """Schema for creating a new task."""
    pass


class TaskUpdate(BaseModel):
    """Schema for updating task information."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    module_id: Optional[str] = Field(None, max_length=50)
    deadline: Optional[datetime] = None
    scoring_criteria: Optional[str] = None


class TaskResponse(TaskBase):
    """Schema for task response."""
    id: int
    teacher_id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Schema for task list response with teacher info."""
    id: int
    title: str
    description: Optional[str]
    module_id: Optional[str]
    status: str
    deadline: Optional[datetime]
    created_at: datetime
    teacher_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class TaskStatusUpdate(BaseModel):
    """Schema for updating task status."""
    status: Literal["draft", "published", "closed"]
