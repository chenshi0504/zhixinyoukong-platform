"""
Experiment record Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime


class ExperimentStart(BaseModel):
    """Schema for starting an experiment."""
    task_id: Optional[int] = None
    module_id: str = Field(..., max_length=50)


class ExperimentLog(BaseModel):
    """Schema for logging an experiment operation."""
    operation: Dict[str, Any]


class ExperimentResponse(BaseModel):
    """Schema for experiment record response."""
    id: int
    task_id: Optional[int]
    student_id: int
    module_id: str
    operation_log: Optional[str]
    result_data: Optional[str]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ExperimentComplete(BaseModel):
    """Schema for completing an experiment."""
    result_data: Optional[Dict[str, Any]] = None
