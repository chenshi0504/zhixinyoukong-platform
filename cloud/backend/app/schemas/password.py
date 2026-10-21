from datetime import datetime
from pydantic import BaseModel


class PasswordRequestReview(BaseModel):
    admin_note: str | None = None


class PasswordRequestRead(BaseModel):
    id: int
    user_id: int
    username: str
    real_name: str | None
    role: str
    org_id: int | None
    organization_name: str | None = None
    status: str
    reason: str | None
    admin_note: str | None
    requested_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_id: int | None


class PasswordAuditRead(BaseModel):
    user_id: int
    username: str
    real_name: str | None
    role: str
    org_id: int | None
    organization_name: str | None = None
    is_active: bool
    password_history_count: int
    last_password_changed_at: datetime | None
    pending_request_count: int
    password_storage: str = "bcrypt哈希，不保存明文密码"
