"""
用户管理路由：CRUD、CSV 批量导入、密码重置。
"""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models.user import User
from ..models.classroom import Class, student_classes
from ..schemas.user import UserCreate, UserRead, UserUpdate, PasswordResetRequest
from ..schemas.common import PagedResponse
from ..services.auth import hash_password, revoke_all_refresh_tokens
from ..services.password_audit import ensure_current_password_snapshot, record_password_hash

router = APIRouter(prefix="/api/cloud/users", tags=["用户管理"])


def _ensure_global_username_available(db: Session, username: str) -> None:
    exists = db.query(User.id).filter(User.username == username).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="登录账号已存在，请更换账号")


@router.get("", response_model=PagedResponse[UserRead])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    org_id: int | None = Query(None),
    role: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Org_Admin/Teacher 只能看本机构用户
    q = db.query(User)
    if current_user.role in ("org_admin", "teacher"):
        q = q.filter(User.org_id == current_user.org_id)
    elif org_id is not None:
        q = q.filter(User.org_id == org_id)
    if role:
        q = q.filter(User.role == role)
    if current_user.role == "teacher" and role == "student":
        managed_class_ids = [
            c.id for c in db.query(Class.id).filter(Class.teacher_id == current_user.id).all()
        ]
        if not managed_class_ids:
            return PagedResponse(items=[], total=0, page=page, page_size=page_size, pages=1)
        student_ids = [
            row.student_id
            for row in db.execute(
                student_classes.select().where(student_classes.c.class_id.in_(managed_class_ids))
            ).fetchall()
        ]
        if not student_ids:
            return PagedResponse(items=[], total=0, page=page, page_size=page_size, pages=1)
        q = q.filter(User.id.in_(student_ids))
    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    if body.role == "student":
        raise HTTPException(status_code=400, detail="云端管理平台不再创建学生账号")
    if current_user.role == "org_admin":
        body.org_id = current_user.org_id
    _ensure_global_username_available(db, body.username)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        real_name=body.real_name,
        org_id=body.org_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="登录账号已存在，请更换账号")
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if current_user.role == "org_admin" and user.org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="权限不足")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int,
    body: PasswordResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if current_user.role == "org_admin" and user.org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="权限不足")
    ensure_current_password_snapshot(db, user, source="snapshot_before_admin_reset")
    user.password_hash = hash_password(body.new_password)
    record_password_hash(
        db,
        user,
        user.password_hash,
        source="admin_reset",
        changed_by_id=current_user.id,
    )
    revoke_all_refresh_tokens(db, user.id)
    db.commit()


@router.post("/import")
def import_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin")),
):
    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    created = 0
    errors = []
    for i, row in enumerate(reader, start=2):
        try:
            org_id = current_user.org_id if current_user.role == "org_admin" else int(row.get("org_id", 0))
            username = row["username"]
            if db.query(User.id).filter(User.username == username).first() is not None:
                raise ValueError("登录账号已存在")
            user = User(
                username=username,
                password_hash=hash_password(row.get("password", "123456")),
                role=row.get("role", "teacher"),
                real_name=row.get("real_name"),
                org_id=org_id,
            )
            if user.role == "student":
                raise ValueError("云端管理平台不再导入学生账号")
            db.add(user)
            db.flush()
            created += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        errors.append({"row": "commit", "error": "存在重复登录账号或数据约束冲突"})
    return {"created": created, "errors": errors}
