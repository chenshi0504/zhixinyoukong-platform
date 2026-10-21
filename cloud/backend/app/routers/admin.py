"""
管理后台 Dashboard 路由。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models.organization import Organization
from ..models.license import License
from ..models.password import PasswordChangeRequest
from ..models.report import Report
from ..models.user import User

router = APIRouter(prefix="/api/cloud/admin", tags=["管理后台"])


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    total_orgs = db.query(sa_func.count(Organization.id)).scalar() or 0
    total_licenses = db.query(sa_func.count(License.id)).scalar() or 0
    active_licenses = db.query(sa_func.count(License.id)).filter(License.is_active == True).scalar() or 0
    total_users = db.query(sa_func.count(User.id)).scalar() or 0
    pending_reports = db.query(sa_func.count(Report.id)).filter(Report.status == "submitted").scalar() or 0
    pending_password_q = (
        db.query(sa_func.count(PasswordChangeRequest.id))
        .join(User, PasswordChangeRequest.user_id == User.id)
        .filter(PasswordChangeRequest.status == "pending")
    )
    if current_user.role == "org_admin":
        pending_password_q = pending_password_q.filter(User.org_id == current_user.org_id)
    pending_password_requests = pending_password_q.scalar() or 0

    return {
        "total_organizations": total_orgs,
        "total_licenses": total_licenses,
        "active_licenses": active_licenses,
        "total_users": total_users,
        "pending_reports": pending_reports,
        "pending_password_requests": pending_password_requests,
    }
