"""
认证服务：JWT 生成/验证、bcrypt 密码哈希、Refresh Token 管理。
"""
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.user import User, RefreshToken


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user: User) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "org_id": user.org_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def create_refresh_token(db: Session, user: User) -> str:
    """生成 refresh token，哈希后存入数据库，返回明文 token。"""
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    rt = RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    db.add(rt)
    db.commit()
    return raw_token


def validate_refresh_token(db: Session, raw_token: str) -> Optional[User]:
    """验证 refresh token，返回对应用户或 None。"""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    rt = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.expires_at > datetime.now(timezone.utc),
    ).first()
    if rt is None:
        return None
    return rt.user


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """删除指定 refresh token。"""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).delete()
    db.commit()


def revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    """删除用户所有 refresh token（密码重置时调用）。"""
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.commit()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """验证用户名密码，返回用户或 None。"""
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user
