"""
版本更新管理路由。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from packaging.version import Version
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models.update import SoftwareUpdate
from ..schemas.update import UpdateCreate, UpdateRead, UpdateCheckResponse
from ..schemas.common import PagedResponse

router = APIRouter(prefix="/api/cloud/updates", tags=["版本更新"])


@router.get("", response_model=PagedResponse[UpdateRead])
def list_updates(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    q = db.query(SoftwareUpdate)
    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(SoftwareUpdate.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("", response_model=UpdateRead, status_code=status.HTTP_201_CREATED)
def create_update(
    body: UpdateCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    upd = SoftwareUpdate(**body.model_dump())
    db.add(upd)
    db.commit()
    db.refresh(upd)
    return upd


@router.get("/check", response_model=UpdateCheckResponse)
def check_update(
    version: str = Query(...),
    db: Session = Depends(get_db),
):
    latest = db.query(SoftwareUpdate).order_by(SoftwareUpdate.id.desc()).first()
    if latest is None:
        return UpdateCheckResponse(up_to_date=True)
    try:
        if Version(latest.version) > Version(version):
            return UpdateCheckResponse(up_to_date=False, latest=UpdateRead.model_validate(latest))
    except Exception:
        pass
    return UpdateCheckResponse(up_to_date=True)
