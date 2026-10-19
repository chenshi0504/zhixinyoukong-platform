"""
Algorithm template and script Pydantic schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ---- 算法模板 ----

class AlgorithmTemplateCreate(BaseModel):
    """创建算法模板请求。"""
    module_id: str = Field(..., max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    code: str = Field(..., min_length=1)


class AlgorithmTemplateUpdate(BaseModel):
    """更新算法模板请求。"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    code: Optional[str] = Field(None, min_length=1)


class AlgorithmTemplateResponse(BaseModel):
    """算法模板响应。"""
    id: int
    module_id: str
    name: str
    description: Optional[str]
    code: str
    teacher_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- 学生算法脚本 ----

class AlgorithmScriptSubmit(BaseModel):
    """学生提交算法脚本请求。"""
    task_id: int
    module_id: str = Field(..., max_length=50)
    code: str = Field(..., min_length=1)


class AlgorithmScriptResponse(BaseModel):
    """算法脚本响应。"""
    id: int
    student_id: int
    task_id: int
    module_id: str
    code: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    execution_duration: Optional[float] = None
    execution_status: str
    submitted_at: datetime
    executed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExecutionRequest(BaseModel):
    """执行脚本请求。"""
    timeout: int = Field(default=60, ge=1, le=120)
