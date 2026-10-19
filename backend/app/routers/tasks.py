"""
Task management API routes.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import TaskCreate, TaskUpdate, TaskResponse, ErrorResponse
from ..services import task as task_service
from ..services.cloud_learning_proxy import (
    create_cloud_task,
    get_cloud_access_token,
    get_cloud_task,
    list_cloud_tasks,
    publish_cloud_task,
)
from ..dependencies import get_current_teacher
from .auth import get_current_user

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _default_cloud_task_payload(task_data: TaskCreate) -> dict:
    payload = task_data.model_dump()
    payload["module_id"] = payload.get("module_id") or payload.pop("module", None)
    if payload.get("deadline") is not None:
        payload["deadline"] = payload["deadline"].isoformat()
    payload.pop("scoring_criteria", None)
    return payload


@router.get("", response_model=List[dict] | List[TaskResponse])
async def get_tasks(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    获取任务列表。
    
    - 教师/管理员: 可以看到所有任务
    - 学生: 只能看到已发布的任务
    """
    cloud_token = get_cloud_access_token(token)
    if cloud_token:
        return list_cloud_tasks(cloud_token)
    if current_user.role == UserRole.STUDENT.value:
        return []
    tasks = task_service.get_tasks_by_user_role(db, current_user)
    return tasks


@router.post("", response_model=dict | TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_teacher),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    创建新任务。
    
    仅教师和管理员可以创建任务。新创建的任务默认为草稿状态。
    """
    cloud_token = get_cloud_access_token(token)
    if cloud_token:
        return create_cloud_task(cloud_token, _default_cloud_task_payload(task_data))
    task = task_service.create_task(db, task_data, current_user.id)
    return task


@router.get("/{task_id}", response_model=dict | TaskResponse, responses={
    404: {"model": ErrorResponse, "description": "任务不存在"}
})
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    获取单个任务详情。
    
    学生只能查看已发布的任务。
    """
    cloud_token = get_cloud_access_token(token)
    if cloud_token:
        task = get_cloud_task(cloud_token, task_id) if cloud_token else None
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "RES_002",
                    "message": "任务不存在或不属于当前班级",
                    "suggestion": "请确认教师已向您的班级发布任务"
                }
            )
        return task

    task = task_service.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_002",
                "message": "任务不存在",
                "suggestion": "请检查任务ID是否正确"
            }
        )
    
    # Students can only see published tasks
    if current_user.role == UserRole.STUDENT.value and task.status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "BIZ_003",
                "message": "任务尚未发布",
                "suggestion": "请等待教师发布任务"
            }
        )
    
    return task


@router.put("/{task_id}", response_model=TaskResponse, responses={
    404: {"model": ErrorResponse, "description": "任务不存在"},
    403: {"model": ErrorResponse, "description": "无权限"}
})
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    更新任务信息。
    
    仅任务创建者或管理员可以更新任务。
    """
    task = task_service.update_task(db, task_id, task_data, current_user)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, responses={
    404: {"model": ErrorResponse, "description": "任务不存在"},
    403: {"model": ErrorResponse, "description": "无权限"}
})
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    删除任务。
    
    仅任务创建者或管理员可以删除任务。
    """
    task_service.delete_task(db, task_id, current_user)
    return None


@router.post("/{task_id}/publish", response_model=dict | TaskResponse, responses={
    404: {"model": ErrorResponse, "description": "任务不存在"},
    403: {"model": ErrorResponse, "description": "无权限"},
    400: {"model": ErrorResponse, "description": "操作失败"}
})
async def publish_task(
    task_id: int,
    current_user: User = Depends(get_current_teacher),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    发布任务。
    
    将任务状态从草稿改为已发布，使学生可以看到该任务。
    """
    cloud_token = get_cloud_access_token(token)
    if cloud_token:
        return publish_cloud_task(cloud_token, task_id)
    task = task_service.publish_task(db, task_id, current_user)
    return task


@router.post("/{task_id}/close", response_model=TaskResponse, responses={
    404: {"model": ErrorResponse, "description": "任务不存在"},
    403: {"model": ErrorResponse, "description": "无权限"}
})
async def close_task(
    task_id: int,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    关闭任务。
    
    关闭任务后，学生将无法再提交报告。
    """
    task = task_service.close_task(db, task_id, current_user)
    return task
