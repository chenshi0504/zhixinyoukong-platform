"""
公开接口（无需认证）：供注册页面获取机构和班级列表。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.organization import Organization
from ..models.classroom import Class

router = APIRouter(prefix="/api/cloud/public", tags=["公开接口"])


@router.get("/orgs")
def list_orgs_public(db: Session = Depends(get_db)):
    """获取所有机构（用于注册选择）"""
    orgs = db.query(Organization).order_by(Organization.id).all()
    return [{"id": o.id, "name": o.name} for o in orgs]


@router.get("/classes")
def list_classes_public(
    org_id: int = Query(..., description="机构ID"),
    db: Session = Depends(get_db),
):
    """获取指定机构下的班级列表（用于注册选择）"""
    classes = (
        db.query(Class)
        .filter(Class.org_id == org_id)
        .order_by(Class.id)
        .all()
    )
    return [{"id": c.id, "name": c.name} for c in classes]
