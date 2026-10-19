"""
Experiment record API routes.
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import (
    ExperimentStart, ExperimentLog, ExperimentResponse,
    ExperimentComplete, ErrorResponse
)
from ..services import experiment as experiment_service
from .auth import get_current_user

router = APIRouter()


@router.post("/start", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def start_experiment(
    data: ExperimentStart,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    开始一个新实验，创建实验记录。
    """
    record = experiment_service.start_experiment(
        db, current_user.id, data.module_id, data.task_id
    )
    return record


@router.post("/{record_id}/log", response_model=ExperimentResponse, responses={
    404: {"model": ErrorResponse, "description": "实验记录不存在"}
})
async def log_operation(
    record_id: int,
    data: ExperimentLog,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    记录实验操作。
    """
    record = experiment_service.log_operation(
        db, record_id, current_user.id, data.operation
    )
    return record


@router.post("/{record_id}/complete", response_model=ExperimentResponse, responses={
    404: {"model": ErrorResponse, "description": "实验记录不存在"}
})
async def complete_experiment(
    record_id: int,
    data: ExperimentComplete = ExperimentComplete(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    完成实验，保存最终结果。
    """
    record = experiment_service.complete_experiment(
        db, record_id, current_user.id, data.result_data
    )
    return record


@router.get("", response_model=List[ExperimentResponse])
async def get_experiments(
    task_id: Optional[int] = Query(None, description="按任务ID筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取实验记录列表。
    
    - 学生: 只能看到自己的实验记录
    - 教师/管理员: 可按任务筛选查看所有记录
    """
    if current_user.role == UserRole.STUDENT.value:
        return experiment_service.get_experiments_by_student(db, current_user.id)
    
    if task_id:
        return experiment_service.get_experiments_by_task(db, task_id)
    
    # For teachers/admins without filter, return empty (too broad)
    return []


@router.get("/{record_id}", response_model=ExperimentResponse, responses={
    404: {"model": ErrorResponse, "description": "实验记录不存在"}
})
async def get_experiment(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取实验记录详情。"""
    record = experiment_service.get_experiment_by_id(db, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_004",
                "message": "实验记录不存在",
                "suggestion": "请检查实验记录ID是否正确"
            }
        )
    
    # Students can only view their own records
    if current_user.role == UserRole.STUDENT.value and record.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权查看此实验记录",
                "suggestion": "您只能查看自己的实验记录"
            }
        )
    
    return record
