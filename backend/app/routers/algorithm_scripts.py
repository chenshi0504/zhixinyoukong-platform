"""
学生算法脚本API路由。
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import (
    AlgorithmScriptSubmit, AlgorithmScriptResponse,
    ExecutionRequest, ErrorResponse,
)
from ..services import algorithm_script as script_service
from .auth import get_current_user

router = APIRouter()


@router.post("", response_model=AlgorithmScriptResponse, status_code=status.HTTP_201_CREATED)
async def submit_script(
    data: AlgorithmScriptSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交算法脚本（学生提交自己的代码）。"""
    return script_service.submit_script(
        db,
        student_id=current_user.id,
        task_id=data.task_id,
        module_id=data.module_id,
        code=data.code,
    )


@router.get("", response_model=List[AlgorithmScriptResponse])
async def list_scripts(
    task_id: Optional[int] = Query(None, description="按任务ID筛选"),
    student_id: Optional[int] = Query(None, description="按学生ID筛选（仅教师）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取算法脚本列表。

    - 学生：只能看到自己的脚本
    - 教师/管理员：可按task_id和student_id筛选
    """
    if current_user.role == UserRole.STUDENT.value:
        return script_service.get_scripts_by_student(db, current_user.id, task_id)

    # 教师/管理员
    if task_id:
        return script_service.get_scripts_by_task(db, task_id, student_id)
    if student_id:
        return script_service.get_scripts_by_student(db, student_id, task_id)
    return []


@router.get("/{script_id}", response_model=AlgorithmScriptResponse, responses={
    404: {"model": ErrorResponse}
})
async def get_script(
    script_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取脚本详情。"""
    script = script_service.get_script_by_id(db, script_id)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RES_011", "message": "算法脚本不存在"},
        )
    # 学生只能看自己的
    if (
        current_user.role == UserRole.STUDENT.value
        and script.student_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERM_010", "message": "无权查看此脚本"},
        )
    return script


@router.post("/{script_id}/execute", response_model=AlgorithmScriptResponse, responses={
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
})
async def execute_script(
    script_id: int,
    data: ExecutionRequest = ExecutionRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """执行算法脚本。"""
    return script_service.execute_user_script(
        db, script_id, current_user.id, timeout=data.timeout
    )
