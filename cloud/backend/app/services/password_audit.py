from sqlalchemy.orm import Session

from ..models.password import PasswordHistory
from ..models.user import User


def record_password_hash(
    db: Session,
    user: User,
    password_hash: str,
    *,
    source: str,
    changed_by_id: int | None = None,
    request_id: int | None = None,
) -> PasswordHistory:
    item = PasswordHistory(
        user_id=user.id,
        password_hash=password_hash,
        source=source,
        changed_by_id=changed_by_id,
        request_id=request_id,
    )
    db.add(item)
    return item


def ensure_current_password_snapshot(db: Session, user: User, *, source: str = "snapshot") -> None:
    exists = (
        db.query(PasswordHistory.id)
        .filter(
            PasswordHistory.user_id == user.id,
            PasswordHistory.password_hash == user.password_hash,
        )
        .first()
    )
    if not exists:
        record_password_hash(db, user, user.password_hash, source=source)
