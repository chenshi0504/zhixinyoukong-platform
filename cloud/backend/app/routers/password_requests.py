from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models.organization import Organization
from ..models.password import PasswordChangeRequest, PasswordHistory
from ..models.user import User
from ..schemas.password import PasswordAuditRead, PasswordRequestRead, PasswordRequestReview
from ..services.auth import revoke_all_refresh_tokens
from ..services.password_audit import ensure_current_password_snapshot, record_password_hash

router = APIRouter(prefix="/api/cloud/password-requests", tags=["密码申请"])


def _scope_user_query(q, current_user: User):
    if current_user.role == "org_admin":
        q = q.filter(User.org_id == current_user.org_id)
    return q


def _get_scoped_request(db: Session, request_id: int, current_user: User) -> PasswordChangeRequest:
    q = db.query(PasswordChangeRequest).join(User, PasswordChangeRequest.user_id == User.id)
    q = _scope_user_query(q, current_user)
    item = q.filter(PasswordChangeRequest.id == request_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="密码修改申请不存在")
    return item


def _request_to_read(item: PasswordChangeRequest) -> PasswordRequestRead:
    user = item.user
    org = user.organization if user else None
    return PasswordRequestRead(
        id=item.id,
        user_id=item.user_id,
        username=user.username if user else "",
        real_name=user.real_name if user else None,
        role=user.role if user else "",
        org_id=user.org_id if user else None,
        organization_name=org.name if org else None,
        status=item.status,
        reason=item.reason,
        admin_note=item.admin_note,
        requested_at=item.requested_at,
        reviewed_at=item.reviewed_at,
        reviewed_by_id=item.reviewed_by_id,
    )


@router.get("")
def list_password_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query("pending", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    q = db.query(PasswordChangeRequest).join(User, PasswordChangeRequest.user_id == User.id)
    q = _scope_user_query(q, current_user)
    if status_filter and status_filter != "all":
        q = q.filter(PasswordChangeRequest.status == status_filter)
    total = q.count()
    pages = (total + page_size - 1) // page_size if total else 1
    items = (
        q.order_by(PasswordChangeRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_request_to_read(item).model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@router.post("/{request_id}/approve", response_model=PasswordRequestRead)
def approve_password_request(
    request_id: int,
    body: PasswordRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    item = _get_scoped_request(db, request_id, current_user)
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理，不能重复审批")
    target = item.user
    if target is None:
        raise HTTPException(status_code=404, detail="申请对应的用户不存在")

    ensure_current_password_snapshot(db, target, source="snapshot_before_request_approval")
    target.password_hash = item.requested_password_hash
    record_password_hash(
        db,
        target,
        target.password_hash,
        source="request_approved",
        changed_by_id=current_user.id,
        request_id=item.id,
    )
    item.status = "approved"
    item.admin_note = body.admin_note
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    revoke_all_refresh_tokens(db, target.id)
    return _request_to_read(item)


@router.post("/{request_id}/reject", response_model=PasswordRequestRead)
def reject_password_request(
    request_id: int,
    body: PasswordRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    item = _get_scoped_request(db, request_id, current_user)
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理，不能重复审批")
    item.status = "rejected"
    item.admin_note = body.admin_note
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _request_to_read(item)


@router.get("/account-audit")
def account_password_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    q = db.query(User)
    q = _scope_user_query(q, current_user)
    if role:
        q = q.filter(User.role == role)
    total = q.count()
    pages = (total + page_size - 1) // page_size if total else 1
    users = q.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result: list[PasswordAuditRead] = []
    for user in users:
        history_count = db.query(func.count(PasswordHistory.id)).filter(PasswordHistory.user_id == user.id).scalar() or 0
        last_history = (
            db.query(PasswordHistory)
            .filter(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.id.desc())
            .first()
        )
        pending_count = (
            db.query(func.count(PasswordChangeRequest.id))
            .filter(
                PasswordChangeRequest.user_id == user.id,
                PasswordChangeRequest.status == "pending",
            )
            .scalar()
            or 0
        )
        result.append(
            PasswordAuditRead(
                user_id=user.id,
                username=user.username,
                real_name=user.real_name,
                role=user.role,
                org_id=user.org_id,
                organization_name=user.organization.name if user.organization else None,
                is_active=user.is_active,
                password_history_count=history_count,
                last_password_changed_at=last_history.created_at if last_history else None,
                pending_request_count=pending_count,
            )
        )

    return {
        "items": [item.model_dump() for item in result],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "note": "密码只保存 bcrypt 哈希，不保存或展示明文密码；管理员可通过重置密码发放临时密码。",
    }
