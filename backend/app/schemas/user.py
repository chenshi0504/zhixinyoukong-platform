"""
User Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema with common fields."""
    username: str = Field(..., min_length=2, max_length=50)
    real_name: Optional[str] = Field(None, max_length=50)
    student_id: Optional[str] = Field(None, max_length=20)
    class_name: Optional[str] = Field(None, max_length=50)


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=6, max_length=100)
    role: Literal["admin", "teacher", "student"] = "student"


class UserUpdate(BaseModel):
    """Schema for updating user information."""
    real_name: Optional[str] = Field(None, max_length=50)
    student_id: Optional[str] = Field(None, max_length=20)
    class_name: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    role: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserInDB(UserResponse):
    """Schema for user in database (includes password hash)."""
    password_hash: str


class PasswordReset(BaseModel):
    """Schema for password reset."""
    new_password: str = Field(..., min_length=6, max_length=100)


class StudentImport(BaseModel):
    """Schema for student import from Excel."""
    username: str
    real_name: str
    student_id: str
    class_name: Optional[str] = None
