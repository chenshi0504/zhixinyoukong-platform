"""
License 服务：License key 生成、RSA 签名/验证 Activation_Token。
"""
import json
import base64
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.license import License


def generate_license_key() -> str:
    """生成 XXXX-XXXX-XXXX-XXXX 格式的 license key。"""
    raw = secrets.token_hex(16).upper()  # 32 hex chars
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def calculate_expiry(license_type: str, from_dt: Optional[datetime] = None) -> Optional[datetime]:
    """根据 license 类型计算过期时间。"""
    base = from_dt or datetime.now(timezone.utc)
    if license_type == "trial":
        return base + timedelta(days=30)
    elif license_type == "education":
        return base + timedelta(days=180)
    return None  # permanent


def _sign_payload(payload: dict) -> str:
    """
    签名 Activation_Token。
    简化实现：使用 HMAC-SHA256（与 SECRET_KEY 对称签名）。
    生产环境可替换为 RSA 非对称签名。
    格式：base64(json_payload).base64(signature)
    """
    from ..config import get_settings
    settings = get_settings()

    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()

    sig_input = f"{payload_b64}.{settings.secret_key}".encode()
    signature = hashlib.sha256(sig_input).hexdigest()
    sig_b64 = base64.urlsafe_b64encode(signature.encode()).decode()

    return f"{payload_b64}.{sig_b64}"


def _verify_signature(token: str) -> Optional[dict]:
    """验证 Activation_Token 签名，返回 payload 或 None。"""
    from ..config import get_settings
    settings = get_settings()

    parts = token.split(".", 1)
    if len(parts) != 2:
        return None

    payload_b64, sig_b64 = parts

    # 重新计算签名
    sig_input = f"{payload_b64}.{settings.secret_key}".encode()
    expected_sig = hashlib.sha256(sig_input).hexdigest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig.encode()).decode()

    if sig_b64 != expected_b64:
        return None

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return None


def activate_license(db: Session, license_key: str, machine_id: str) -> Optional[dict]:
    """
    激活 License：绑定 machine_id，返回签名的 Activation_Token 信息。
    返回 None 表示失败，返回 dict 包含 error 字段表示具体错误。
    """
    lic = db.query(License).filter(License.license_key == license_key).first()
    if lic is None:
        return {"error": "LICENSE_NOT_FOUND"}

    if not lic.is_active:
        return {"error": "LICENSE_REVOKED"}

    if lic.machine_id and lic.machine_id != machine_id:
        return {"error": "LICENSE_ALREADY_BOUND"}

    now = datetime.now(timezone.utc)

    if lic.machine_id is None:
        lic.machine_id = machine_id
        lic.activated_at = now
        if lic.expires_at is None:
            lic.expires_at = calculate_expiry(lic.license_type, now)
        db.commit()
        db.refresh(lic)

    payload = {
        "license_id": lic.id,
        "license_key": lic.license_key,
        "machine_id": lic.machine_id,
        "license_type": lic.license_type,
        "org_id": lic.org_id,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        "activated_at": lic.activated_at.isoformat() if lic.activated_at else None,
    }

    token = _sign_payload(payload)
    return {
        "activation_token": token,
        "expires_at": lic.expires_at,
        "license_type": lic.license_type,
    }


def verify_activation_token(db: Session, token: str) -> dict:
    """验证 Activation_Token，返回 license 状态。"""
    payload = _verify_signature(token)
    if payload is None:
        return {"is_active": False, "error": "INVALID_TOKEN"}

    # 检查过期
    expires_str = payload.get("expires_at")
    if expires_str:
        expires_at = datetime.fromisoformat(expires_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return {"is_active": False, "error": "LICENSE_EXPIRED"}

    # 检查数据库中 license 是否仍然 active
    license_id = payload.get("license_id")
    if license_id:
        lic = db.query(License).filter(License.id == license_id).first()
        if lic is None or not lic.is_active:
            return {"is_active": False, "error": "LICENSE_REVOKED"}

    return {
        "is_active": True,
        "license_type": payload.get("license_type"),
        "expires_at": payload.get("expires_at"),
        "machine_id": payload.get("machine_id"),
    }
