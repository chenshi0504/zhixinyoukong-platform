"""
机构管理路由：CRUD + 详情（含关联数据）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models.organization import Organization
from ..models.license import License
from ..models.user import User
from ..schemas.organization import OrgCreate, OrgRead, OrgUpdate, OrgDetail
from ..schemas.common import PagedResponse

router = APIRouter(prefix="/api/cloud/orgs", tags=["机构管理"])


@router.get("", response_model=PagedResponse[OrgRead])
def list_orgs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    search: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    q = db.query(Organization)
    if search:
        q = q.filter(Organization.name.contains(search))
    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(Organization.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("", response_model=OrgRead, status_code=status.HTTP_201_CREATED)
def create_org(
    body: OrgCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    org = Organization(**body.model_dump())
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get("/{org_id}", response_model=OrgDetail)
def get_org(
    org_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")

    license_count = db.query(sa_func.count(License.id)).filter(License.org_id == org_id).scalar() or 0
    active_license_count = db.query(sa_func.count(License.id)).filter(
        License.org_id == org_id, License.is_active == True
    ).scalar() or 0
    user_count = db.query(sa_func.count(User.id)).filter(User.org_id == org_id).scalar() or 0

    data = OrgRead.model_validate(org).model_dump()
    data.update(license_count=license_count, active_license_count=active_license_count, user_count=user_count)
    return OrgDetail(**data)


@router.put("/{org_id}", response_model=OrgRead)
def update_org(
    org_id: int,
    body: OrgUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(org, k, v)
    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_org(
    org_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")

    active_count = db.query(sa_func.count(License.id)).filter(
        License.org_id == org_id, License.is_active == True
    ).scalar() or 0
    if active_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该机构有活跃 License，请先吊销后再删除",
        )

    db.delete(org)
    db.commit()
