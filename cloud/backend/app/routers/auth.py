"""
认证路由：登录、登出、刷新 Token、教师注册、修改密码。
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models.user import User
from ..models.password import PasswordChangeRequest as PasswordChangeRequestModel
from ..models.organization import Organization
from ..schemas.user import (
    LoginRequest, LoginResponse, UserRead,
    TokenRefreshRequest, TokenRefreshResponse,
    TeacherRegisterRequest, TeacherRegisterResponse,
    StudentRegisterRequest, StudentRegisterResponse,
    PasswordChangeRequest as PasswordChangePayload,
)
from ..services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
    hash_password,
    verify_password,
    revoke_all_refresh_tokens,
)
from ..services.password_audit import ensure_current_password_snapshot, record_password_hash

router = APIRouter(prefix="/api/cloud/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(db, user)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/register", response_model=TeacherRegisterResponse)
def register_teacher(body: TeacherRegisterRequest, db: Session = Depends(get_db)):
    """教师自助注册：选择已有机构，系统自动分配账号。"""
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于6位")
    if not body.real_name.strip():
        raise HTTPException(status_code=400, detail="姓名不能为空")

    org = db.query(Organization).filter(Organization.id == body.org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在，请先由管理员创建机构")

    user = User(
        username=f"teacher_pending_{uuid.uuid4().hex}",
        password_hash=hash_password(body.password),
        role="teacher",
        real_name=body.real_name.strip(),
        org_id=org.id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    user.username = f"teacher{user.id}"
    record_password_hash(db, user, user.password_hash, source="teacher_register")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="账号生成冲突，请重新提交注册")

    return TeacherRegisterResponse(
        username=user.username,
        real_name=body.real_name.strip(),
        org_name=org.name,
    )


@router.post("/register/user", response_model=StudentRegisterResponse)
def register_student(body: StudentRegisterRequest, db: Session = Depends(get_db)):
    """学生注册：提交机构ID、班级ID、姓名、密码，系统自动分配学号账号。"""
    from ..models.classroom import Class, student_classes

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于6位")
    if not body.real_name.strip():
        raise HTTPException(status_code=400, detail="姓名不能为空")

    # 验证机构存在
    org = db.query(Organization).filter(Organization.id == body.org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="机构不存在")

    # 验证班级存在且属于该机构
    class_obj = db.query(Class).filter(
        Class.id == body.class_id,
        Class.org_id == body.org_id
    ).first()
    if class_obj is None:
        raise HTTPException(status_code=404, detail="班级不存在或不属于该机构")

    # 创建学生用户
    user = User(
        username=f"student_pending_{uuid.uuid4().hex}",
        password_hash=hash_password(body.password),
        role="student",
        real_name=body.real_name.strip(),
        org_id=body.org_id,
        is_active=True,
    )
    db.add(user)
    db.flush()  # 获取 user.id
    username = f"student{body.org_id}{user.id:04d}"
    student_id = f"{body.org_id}{user.id:04d}"
    user.username = username
    record_password_hash(db, user, user.password_hash, source="student_register")

    # 将学生加入班级
    stmt = student_classes.insert().values(student_id=user.id, class_id=body.class_id)
    db.execute(stmt)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="账号生成冲突，请重新提交注册")

    return StudentRegisterResponse(
        username=username,
        real_name=body.real_name.strip(),
        role="student",
        class_name=class_obj.name,
        student_id=student_id,
    )


@router.post("/change-password", status_code=200)
def change_password(
    body: PasswordChangePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改当前用户密码。"""
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")

    new_hash = hash_password(body.new_password)
    if current_user.role in ("teacher", "student"):
        pending = db.query(PasswordChangeRequestModel).filter(
            PasswordChangeRequestModel.user_id == current_user.id,
            PasswordChangeRequestModel.status == "pending",
        ).first()
        if pending is None:
            pending = PasswordChangeRequestModel(
                user_id=current_user.id,
                requested_password_hash=new_hash,
                reason=body.reason,
            )
            db.add(pending)
        else:
            pending.requested_password_hash = new_hash
            pending.reason = body.reason
        db.commit()
        db.refresh(pending)
        return {
            "message": "密码修改申请已提交，管理员审批通过后生效",
            "status": "pending",
            "request_id": pending.id,
        }

    ensure_current_password_snapshot(db, current_user, source="snapshot_before_admin_self_change")
    current_user.password_hash = new_hash
    record_password_hash(
        db,
        current_user,
        new_hash,
        source="admin_self_change",
        changed_by_id=current_user.id,
    )
    db.commit()
    # 吊销所有 refresh token，强制重新登录
    revoke_all_refresh_tokens(db, current_user.id)
    return {"message": "密码修改成功，请重新登录", "status": "changed"}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(body: TokenRefreshRequest, db: Session = Depends(get_db)):
    user = validate_refresh_token(db, body.refresh_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 无效或已过期",
        )
    access_token = create_access_token(user)
    return TokenRefreshResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    body: TokenRefreshRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    revoke_refresh_token(db, body.refresh_token)
