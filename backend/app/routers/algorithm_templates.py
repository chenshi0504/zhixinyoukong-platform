"""
算法模板API路由。
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import (
    AlgorithmTemplateCreate, AlgorithmTemplateUpdate,
    AlgorithmTemplateResponse, ErrorResponse,
)
from ..services import algorithm_template as tpl_service
from ..dependencies import get_current_teacher
from .auth import get_current_user

router = APIRouter()


@router.post("", response_model=AlgorithmTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: AlgorithmTemplateCreate,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """创建算法模板（仅教师/管理员）。"""
    return tpl_service.create_template(
        db,
        module_id=data.module_id,
        name=data.name,
        code=data.code,
        teacher_id=current_user.id,
        description=data.description,
    )


@router.get("", response_model=List[AlgorithmTemplateResponse])
async def list_templates(
    module_id: Optional[str] = Query(None, description="按模块ID筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取算法模板列表，可按模块筛选。"""
    if module_id:
        return tpl_service.get_templates_by_module(db, module_id)
    return tpl_service.get_all_templates(db)


@router.get("/{template_id}", response_model=AlgorithmTemplateResponse, responses={
    404: {"model": ErrorResponse}
})
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单个算法模板详情。"""
    tpl = tpl_service.get_template_by_id(db, template_id)
    if not tpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RES_010", "message": "算法模板不存在"},
        )
    return tpl


@router.put("/{template_id}", response_model=AlgorithmTemplateResponse, responses={
    404: {"model": ErrorResponse}
})
async def update_template(
    template_id: int,
    data: AlgorithmTemplateUpdate,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """更新算法模板（仅教师/管理员）。"""
    return tpl_service.update_template(
        db, template_id,
        name=data.name,
        description=data.description,
        code=data.code,
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """删除算法模板（仅教师/管理员）。"""
    tpl_service.delete_template(db, template_id)
