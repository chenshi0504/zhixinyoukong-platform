"""
云端混合认证服务
实现本地登录时尝试云端验证 + 本地缓存的混合认证模式：
- 联网时：先调用云端 /api/cloud/auth/login 验证账号密码，成功后同步用户到本地
- 云端拒绝(401)：若用户有 cloud_id（来自云端）则拒绝登录；否则回退本地认证
- 网络异常/离线：回退到本地缓存认证
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
from sqlalchemy.orm import Session

from ..cloud_client import create_cloud_session
from ..config import settings
from ..models import User, UserRole

logger = logging.getLogger(__name__)

# 云端角色 → 本地角色映射
_CLOUD_ROLE_MAP = {
    "super_admin": "admin",
    "org_admin": "admin",
    "teacher": "teacher",
    "student": "student",
}


def _cloud_login(username: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    调用云端登录接口验证账号密码。

    Returns:
        (cloud_user_dict, error_msg)
        - 成功: (user_dict, None)
        - 认证失败: (None, "auth_failed")
        - 网络/其他错误: (None, "network_error")
    """
    cloud_url = settings.CLOUD_API_URL
    if not cloud_url:
        return None, "network_error"

    try:
        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.post(
                f"{cloud_url}/api/cloud/auth/login",
                json={"username": username, "password": password},
                timeout=5,
            )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("user"), None
        elif resp.status_code == 401:
            return None, "auth_failed"
        else:
            logger.warning("云端登录返回非预期状态码: %s", resp.status_code)
            return None, "network_error"
    except requests.RequestException as e:
        logger.info("云端不可达，将使用本地认证: %s", e)
        return None, "network_error"


def _map_cloud_role(cloud_role: str) -> str:
    """将云端角色映射为本地角色"""
    return _CLOUD_ROLE_MAP.get(cloud_role, cloud_role)


def sync_cloud_user_to_local(
    db: Session,
    cloud_user: dict,
    password: str,
) -> User:
    """
    将云端验证通过的用户同步到本地数据库（创建或更新）。

    Args:
        db: 数据库会话
        cloud_user: 云端返回的用户信息 dict
        password: 用户本次输入的明文密码（用于本地缓存哈希）

    Returns:
        本地 User 对象
    """
    from .auth import get_password_hash

    cloud_id = str(cloud_user["id"])
    username = cloud_user["username"]
    role = _map_cloud_role(cloud_user.get("role", "student"))
    real_name = cloud_user.get("real_name")
    org_id = str(cloud_user["org_id"]) if cloud_user.get("org_id") else None
    now = datetime.now(timezone.utc)

    # 优先通过 cloud_id 查找
    local_user = db.query(User).filter(User.cloud_id == cloud_id).first()
    if not local_user:
        # 再通过 username 查找（可能是首次同步，本地有同名 seed 用户）
        local_user = db.query(User).filter(User.username == username).first()

    if local_user:
        # 更新现有用户
        local_user.cloud_id = cloud_id
        local_user.password_hash = get_password_hash(password)
        local_user.role = role
        local_user.real_name = real_name or local_user.real_name
        local_user.org_id = org_id
        local_user.is_active = cloud_user.get("is_active", True)
        local_user.cloud_synced_at = now
    else:
        # 创建新本地用户
        local_user = User(
            username=username,
            password_hash=get_password_hash(password),
            role=role,
            real_name=real_name,
            cloud_id=cloud_id,
            org_id=org_id,
            is_active=cloud_user.get("is_active", True),
            cloud_synced_at=now,
        )
        db.add(local_user)

    db.commit()
    db.refresh(local_user)
    logger.info("已同步云端用户到本地: %s (cloud_id=%s)", username, cloud_id)
    return local_user


def cloud_register(
    db: Session,
    org_id: int,
    class_id: int,
    real_name: str,
    password: str,
) -> Tuple[Optional[User], Optional[str]]:
    """
    在云端注册学生，成功后同步到本地。
    云端会自动分配用户名并将学生加入班级。

    Returns:
        (local_user, error_detail)
        - 成功: (User, None)
        - 失败: (None, error_message)
    """
    cloud_url = settings.CLOUD_API_URL
    if not cloud_url:
        return None, "云端服务未配置，无法注册"

    try:
        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.post(
                f"{cloud_url}/api/cloud/auth/register/user",
                json={
                    "org_id": org_id,
                    "class_id": class_id,
                    "real_name": real_name,
                    "password": password,
                },
                timeout=5,
            )
        if resp.status_code == 200:
            data = resp.json()
            cloud_user = data.get("user")
            if cloud_user:
                local_user = sync_cloud_user_to_local(db, cloud_user, password)
                return local_user, None
            return None, "云端返回数据异常"
        else:
            detail = "注册失败"
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                pass
            return None, detail
    except requests.RequestException as e:
        logger.warning("云端不可达，无法注册: %s", e)
        return None, "无法连接云端服务，请检查网络后重试"


def hybrid_authenticate(
    db: Session, username: str, password: str
) -> Tuple[Optional[User], Optional[str]]:
    """
    混合认证：联网时优先云端验证，离线时回退本地缓存。

    Returns:
        (user, error_detail)
        - 成功: (User, None)
        - 失败: (None, error_message)
    """
    from .auth import verify_password

    cloud_user, cloud_err = _cloud_login(username, password)

    # ---- 云端验证成功 ----
    if cloud_user is not None:
        local_user = sync_cloud_user_to_local(db, cloud_user, password)
        if not local_user.is_active:
            return None, "用户已被禁用"
        return local_user, None

    # ---- 云端明确拒绝（密码错误 / 用户不存在）----
    if cloud_err == "auth_failed":
        # 如果本地用户来源于云端（有 cloud_id），以云端为准，拒绝登录
        local_user = db.query(User).filter(User.username == username).first()
        if local_user and local_user.cloud_id:
            return None, "用户名或密码错误（云端验证失败）"
        # 纯本地用户，仍可用本地认证
        if local_user and local_user.is_active and verify_password(password, local_user.password_hash):
            return local_user, None
        return None, "用户名或密码错误"

    # ---- 网络异常 / 云端不可达 → 回退本地缓存 ----
    local_user = db.query(User).filter(User.username == username).first()
    if not local_user:
        return None, "用户名或密码错误"
    if not local_user.is_active:
        return None, "用户已被禁用"
    if not verify_password(password, local_user.password_hash):
        return None, "用户名或密码错误"
    return local_user, None
