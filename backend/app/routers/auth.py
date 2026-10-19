from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import requests
import time

from ..cloud_client import create_cloud_session
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User, UserRole
from ..schemas.auth import LoginRequest, TokenResponse
from ..schemas.user import UserResponse
from ..services.auth import authenticate_user, create_access_token, get_password_hash
from ..services.cloud_learning_proxy import get_cloud_access_token, submit_cloud_password_change_request

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class RegisterRequest(BaseModel):
    org_id: int
    class_id: int
    real_name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)
    reason: str | None = Field(None, max_length=500)


def _error(message: str, code: str):
    return {"code": code, "message": message}


def _issue_token(user: User) -> TokenResponse:
    return _issue_token_with_cloud(user, None)


def _issue_token_with_cloud(user: User, cloud_access_token: str | None) -> TokenResponse:
    payload = {"sub": user.username, "user_id": user.id, "role": user.role}
    if cloud_access_token:
        payload["cloud_access_token"] = cloud_access_token
    return TokenResponse(
        access_token=create_access_token(payload)
    )


def _to_user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


async def _login_user(db: Session, username: str, password: str) -> TokenResponse:
    user = authenticate_user(db, username, password)
    # 云端探测是同步网络请求（timeout=5），且每次登录必然发起一次。
    # 登录端点保持 async，这里把网络调用放进线程池：否则云端不可达时每次登录都会
    # 冻结整个事件循环，全班几十人的登录请求会被完全串行排队。
    cloud_user, cloud_token = await run_in_threadpool(_try_cloud_login, username, password)
    if not user:
        if cloud_user:
            user = _sync_local_user_from_cloud(db, cloud_user, password)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_error("用户名或密码错误", "AUTH_002"),
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif cloud_user:
        user = _sync_local_user_from_cloud(db, cloud_user, password)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error("用户已被禁用", "AUTH_004"),
        )
    return _issue_token_with_cloud(user, cloud_token)


def _cloud_base_url() -> str:
    return (settings.CLOUD_API_URL or "").rstrip("/")


def _parse_list_response(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "orgs", "classes"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _proxy_cloud_get(path: str, params: dict | None = None):
    cloud_url = _cloud_base_url()
    if not cloud_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("云端服务未配置，无法获取机构和班级", "AUTH_005"),
        )
    try:
        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.get(f"{cloud_url}{path}", params=params, timeout=5)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=_error(_extract_error_message(resp, "云端接口返回异常"), "AUTH_005"),
            )
        return _parse_list_response(resp.json())
    except requests.RequestException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("无法连接云端服务，请确认云端平台已启动", "AUTH_005"),
        )


def _extract_error_message(resp: requests.Response, fallback: str) -> str:
    try:
        data = resp.json()
    except Exception:
        return fallback
    if isinstance(data, dict):
        detail = data.get("detail", fallback)
        if isinstance(detail, dict):
            return detail.get("message") or detail.get("detail") or fallback
        if isinstance(detail, str):
            return detail
    return fallback


def _map_cloud_role(role: str | None) -> str:
    if role in {"super_admin", "org_admin"}:
        return UserRole.ADMIN.value
    if role == UserRole.TEACHER.value:
        return UserRole.TEACHER.value
    return UserRole.STUDENT.value


# 云端不可达时，短时间内不再重复等超时。
# CLOUD_API_URL 指向一个没有服务监听的地址时，每次登录都要白等满 5 秒
# （timeout=5），全班几十人同时登录会被彻底拖死。探测失败后进入退避窗口，
# 窗口内本机账号照常登录（云端账号本来也连不上，结果不变）。
_CLOUD_PROBE_BACKOFF_SECONDS = 30.0
_cloud_probe_blocked_until = 0.0


def _try_cloud_login(username: str, password: str) -> tuple[dict | None, str | None]:
    global _cloud_probe_blocked_until
    cloud_url = _cloud_base_url()
    if not cloud_url:
        return None, None
    if time.monotonic() < _cloud_probe_blocked_until:
        return None, None
    try:
        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.post(
                f"{cloud_url}/api/cloud/auth/login",
                json={"username": username, "password": password},
                timeout=5,
            )
    except requests.RequestException:
        _cloud_probe_blocked_until = time.monotonic() + _CLOUD_PROBE_BACKOFF_SECONDS
        return None, None
    _cloud_probe_blocked_until = 0.0
    if resp.status_code != 200:
        return None, None
    data = resp.json() if resp.content else {}
    if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
        return None, None
    return data["user"], data.get("access_token")


def _sync_local_user_from_cloud(db: Session, cloud_user: dict, password: str) -> User:
    username = cloud_user.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error("云端返回的用户信息不完整", "AUTH_005"),
        )
    local_user = db.query(User).filter(User.username == username).first()
    role = _map_cloud_role(cloud_user.get("role"))
    real_name = cloud_user.get("real_name")
    class_name = cloud_user.get("class_name")
    student_id = str(cloud_user.get("id")) if cloud_user.get("id") is not None else None
    if local_user is None:
        local_user = User(
            username=username,
            password_hash=get_password_hash(password),
            role=role,
            real_name=real_name,
            student_id=student_id,
            class_name=class_name,
            is_active=bool(cloud_user.get("is_active", True)),
        )
        db.add(local_user)
    else:
        local_user.password_hash = get_password_hash(password)
        local_user.role = role
        local_user.real_name = real_name or local_user.real_name
        local_user.student_id = student_id or local_user.student_id
        local_user.class_name = class_name or local_user.class_name
        local_user.is_active = bool(cloud_user.get("is_active", True))
    db.commit()
    db.refresh(local_user)
    return local_user


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    return await _login_user(db, form_data.username, form_data.password)


@router.post("/login/json", response_model=TokenResponse)
async def login_json(payload: LoginRequest, db: Session = Depends(get_db)):
    return await _login_user(db, payload.username, payload.password)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    cloud_token = get_cloud_access_token(token)
    if not cloud_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error("请使用云端班级账号重新登录后提交密码修改申请", "AUTH_006"),
        )
    return submit_cloud_password_change_request(
        cloud_token,
        old_password=payload.old_password,
        new_password=payload.new_password,
        reason=payload.reason,
    )


@router.get("/public/orgs")
async def public_orgs():
    # 同为同步网络代理，登录页加载时调用，同样不能占用事件循环。
    return await run_in_threadpool(_proxy_cloud_get, "/api/cloud/public/orgs")


@router.get("/public/classes")
async def public_classes(org_id: int = Query(..., ge=1)):
    return await run_in_threadpool(_proxy_cloud_get, "/api/cloud/public/classes", {"org_id": org_id})


@router.post("/register")
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    cloud_url = _cloud_base_url()
    if not cloud_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("云端服务未配置，无法注册", "AUTH_005"),
        )

    try:
        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.post(
                f"{cloud_url}/api/cloud/auth/register/user",
                json=payload.model_dump(),
                timeout=8,
            )
    except requests.RequestException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("无法连接云端服务，请稍后重试", "AUTH_005"),
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=_error(_extract_error_message(resp, "注册失败"), "AUTH_005"),
        )

    data = resp.json() if resp.content else {}
    cloud_user = data.get("user") if isinstance(data, dict) else None
    user_data = cloud_user if isinstance(cloud_user, dict) else (data if isinstance(data, dict) else {})
    username = user_data.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error("云端返回的注册信息不完整", "AUTH_005"),
        )

    local_user = db.query(User).filter(User.username == username).first()
    role = user_data.get("role") or UserRole.STUDENT.value
    real_name = user_data.get("real_name") or payload.real_name
    class_name = user_data.get("class_name")
    student_id = user_data.get("student_id")

    if local_user is None:
        local_user = User(
            username=username,
            password_hash=get_password_hash(payload.password),
            role=role,
            real_name=real_name,
            class_name=class_name,
            student_id=student_id,
            is_active=True,
        )
        db.add(local_user)
    else:
        local_user.password_hash = get_password_hash(payload.password)
        local_user.role = role
        local_user.real_name = real_name
        local_user.class_name = class_name
        local_user.student_id = student_id
        local_user.is_active = True

    db.commit()
    db.refresh(local_user)

    cloud_user, cloud_access_token = _try_cloud_login(username, payload.password)
    if cloud_user:
        local_user = _sync_local_user_from_cloud(db, cloud_user, payload.password)

    token = _issue_token_with_cloud(local_user, cloud_access_token)
    return {
        "access_token": token.access_token,
        "token_type": token.token_type,
        "user": _to_user_response(local_user),
    }
