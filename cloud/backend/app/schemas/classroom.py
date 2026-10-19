"""
班级管理 schemas
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ClassCreate(BaseModel):
    name: str
    description: str | None = None
    org_id: int | None = None


class ClassUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class StudentBrief(BaseModel):
    id: int
    username: str
    real_name: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ClassRead(BaseModel):
    id: int
    name: str
    org_id: int | None
    teacher_id: int | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClassDetail(ClassRead):
    """包含学生列表的班级详情"""
    students: list[StudentBrief] = []


class ClassStudentOp(BaseModel):
    """添加/移除学生"""
    student_ids: list[int]
