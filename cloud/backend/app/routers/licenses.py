"""
License 管理路由：生成、吊销、列表、激活、验证。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models.license import License
from ..schemas.license import (
    LicenseCreate, LicenseRead,
    LicenseActivateRequest, LicenseActivateResponse,
    LicenseVerifyRequest, LicenseVerifyResponse,
)
from ..schemas.common import PagedResponse
from ..services.license import generate_license_key, calculate_expiry, activate_license, verify_activation_token

router = APIRouter(prefix="/api/cloud/licenses", tags=["License 管理"])


@router.get("", response_model=PagedResponse[LicenseRead])
def list_licenses(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    org_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    q = db.query(License)
    if org_id is not None:
        q = q.filter(License.org_id == org_id)
    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(License.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("/generate", response_model=LicenseRead, status_code=status.HTTP_201_CREATED)
def generate_license(
    body: LicenseCreate,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    key = generate_license_key()
    lic = License(
        license_key=key,
        org_id=body.org_id,
        license_type=body.license_type,
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return lic


@router.put("/{license_id}/revoke", response_model=LicenseRead)
def revoke_license(
    license_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_role("super_admin")),
):
    lic = db.query(License).filter(License.id == license_id).first()
    if lic is None:
        raise HTTPException(status_code=404, detail="License 不存在")
    lic.is_active = False
    db.commit()
    db.refresh(lic)
    return lic


# --- Sync API（Local_Client 调用，无需管理员 JWT）---

@router.post("/activate", response_model=LicenseActivateResponse)
def activate(body: LicenseActivateRequest, db: Session = Depends(get_db)):
    result = activate_license(db, body.license_key, body.machine_id)
    if result is None:
        raise HTTPException(status_code=400, detail="激活失败")
    if "error" in result:
        error_map = {
            "LICENSE_NOT_FOUND": (404, "License 不存在"),
            "LICENSE_REVOKED": (400, "License 已被吊销"),
            "LICENSE_ALREADY_BOUND": (409, "License 已绑定其他机器"),
        }
        code, msg = error_map.get(result["error"], (400, result["error"]))
        raise HTTPException(status_code=code, detail=msg)
    return LicenseActivateResponse(**result)


@router.post("/verify", response_model=LicenseVerifyResponse)
def verify(body: LicenseVerifyRequest, db: Session = Depends(get_db)):
    result = verify_activation_token(db, body.activation_token)
    return LicenseVerifyResponse(**result)
