"""
本地 License 验证模块
负责激活、保存和离线校验 Activation Token。
支持30天试用期（未激活时自动进入试用模式）。
"""
import json
import os
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from .machine_id import generate_machine_id

_logger = logging.getLogger(__name__)

# RSA public key path (shipped with local client, matches cloud private key)
_PUBLIC_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license_public.pem")

# Token 存储路径（用户数据目录）
_TOKEN_DIR = os.path.join(os.path.expanduser("~"), ".zhixinyoukong")
_TOKEN_FILE = os.path.join(_TOKEN_DIR, "activation.json")
_TRIAL_FILE = os.path.join(_TOKEN_DIR, "trial.json")

# 试用期天数
TRIAL_DAYS = 30

# 云端 API 地址（可通过环境变量覆盖）
CLOUD_API_BASE = os.environ.get("CLOUD_API_URL", "https://cloud.zhixinyoukong.com")


class LicenseStatus:
    """License 状态。"""
    def __init__(self, activated: bool, license_type: str = "",
                 expires_at: str = "", error: str = "", machine_id: str = "",
                 trial: bool = False, trial_remaining_days: int = -1):
        self.activated = activated
        self.license_type = license_type
        self.expires_at = expires_at
        self.error = error
        self.machine_id = machine_id
        self.trial = trial
        self.trial_remaining_days = trial_remaining_days

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False  # permanent
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return False

    @property
    def display_type(self) -> str:
        types = {"trial": "试用版", "education": "教育版", "permanent": "永久版"}
        return types.get(self.license_type, self.license_type)


def _save_token(data: dict) -> None:
    """保存激活信息到本地文件。"""
    os.makedirs(_TOKEN_DIR, exist_ok=True)
    with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_token() -> Optional[dict]:
    """从本地文件加载激活信息。"""
    if not os.path.isfile(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _decode_token_payload(token: str) -> Optional[dict]:
    """解码 Activation Token 的 payload 部分（不验证签名）。"""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    try:
        payload_b64 = parts[0]
        pad = 4 - len(payload_b64) % 4
        if pad != 4:
            payload_b64 += "=" * pad
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return None


def _verify_token_rsa(token: str) -> Optional[dict]:
    """
    使用 RSA 公钥验证 Activation Token 签名。
    返回 payload dict 或 None（签名无效/无公钥）。
    """
    if not os.path.isfile(_PUBLIC_KEY_FILE):
        _logger.debug("RSA public key not found, skipping RSA verification")
        return None
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig_b64 = parts
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        with open(_PUBLIC_KEY_FILE, "rb") as f:
            pub_key = load_pem_public_key(f.read())
        sig_bytes = base64.urlsafe_b64decode(sig_b64)
        pub_key.verify(sig_bytes, payload_b64.encode(), asym_padding.PKCS1v15(), hashes.SHA256())
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except ImportError:
        _logger.warning("cryptography not installed, cannot verify RSA signature")
        return None
    except Exception:
        _logger.warning("RSA signature verification failed")
        return None


def _get_trial_info() -> Optional[dict]:
    """获取试用期信息。首次调用时自动创建试用记录。"""
    if os.path.isfile(_TRIAL_FILE):
        try:
            with open(_TRIAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _init_trial() -> dict:
    """初始化试用期（首次运行时调用）。"""
    machine_id = generate_machine_id()
    trial_data = {
        "machine_id": machine_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)).isoformat(),
        "trial_days": TRIAL_DAYS,
    }
    os.makedirs(_TOKEN_DIR, exist_ok=True)
    with open(_TRIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(trial_data, f, ensure_ascii=False, indent=2)
    return trial_data


def check_trial() -> LicenseStatus:
    """
    检查试用期状态。
    - 如果从未试用过，自动初始化30天试用期
    - 如果试用期内，返回 activated=True, trial=True
    - 如果试用期已过，返回 activated=False
    """
    trial = _get_trial_info()
    if trial is None:
        trial = _init_trial()

    # 检查机器码
    current_mid = generate_machine_id()
    if trial.get("machine_id") and trial["machine_id"] != current_mid:
        return LicenseStatus(False, error="试用期机器码不匹配")

    # 检查是否过期
    try:
        exp = datetime.fromisoformat(trial["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remaining = (exp - now).days
        if remaining < 0:
            return LicenseStatus(
                False,
                license_type="trial",
                error=f"试用期已过期（{TRIAL_DAYS}天），请激活正式License",
                trial=True,
                trial_remaining_days=0,
            )
        return LicenseStatus(
            activated=True,
            license_type="trial",
            expires_at=trial["expires_at"],
            machine_id=current_mid,
            trial=True,
            trial_remaining_days=remaining,
        )
    except Exception:
        return LicenseStatus(False, error="试用期数据损坏，请联系管理员")


def activate(license_key: str) -> LicenseStatus:
    """
    在线激活 License。
    调用云端 API，成功后保存 Activation Token 到本地。
    """
    machine_id = generate_machine_id()

    try:
        resp = requests.post(
            f"{CLOUD_API_BASE}/api/cloud/licenses/activate",
            json={"license_key": license_key, "machine_id": machine_id},
            timeout=15,
        )
    except requests.ConnectionError:
        return LicenseStatus(False, error="无法连接到授权服务器，请检查网络")
    except requests.Timeout:
        return LicenseStatus(False, error="连接授权服务器超时")

    if resp.status_code == 200:
        data = resp.json()
        # 保存到本地
        _save_token({
            "activation_token": data["activation_token"],
            "license_type": data.get("license_type", ""),
            "expires_at": data.get("expires_at", ""),
            "machine_id": machine_id,
            "activated_at": datetime.now(timezone.utc).isoformat(),
        })
        return LicenseStatus(
            activated=True,
            license_type=data.get("license_type", ""),
            expires_at=data.get("expires_at", ""),
            machine_id=machine_id,
        )
    else:
        detail = resp.json().get("detail", "激活失败") if resp.headers.get("content-type", "").startswith("application/json") else "激活失败"
        return LicenseStatus(False, error=str(detail))


def verify_online() -> LicenseStatus:
    """在线验证当前 Activation Token。"""
    saved = _load_token()
    if not saved or "activation_token" not in saved:
        return LicenseStatus(False, error="未激活")

    try:
        resp = requests.post(
            f"{CLOUD_API_BASE}/api/cloud/licenses/verify",
            json={"activation_token": saved["activation_token"]},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("is_active"):
                return LicenseStatus(
                    activated=True,
                    license_type=data.get("license_type", saved.get("license_type", "")),
                    expires_at=data.get("expires_at", saved.get("expires_at", "")),
                    machine_id=data.get("machine_id", saved.get("machine_id", "")),
                )
            return LicenseStatus(False, error=data.get("error", "License 已失效"))
    except Exception:
        pass

    # 网络失败时回退到离线验证
    return verify_offline()


def verify_offline() -> LicenseStatus:
    """
    离线验证 Activation Token。
    优先使用 RSA 公钥验证签名，若公钥不可用则回退到基本 payload 检查。
    """
    saved = _load_token()
    if not saved or "activation_token" not in saved:
        return LicenseStatus(False, error="未激活，请联网激活软件")

    # 检查机器码
    current_mid = generate_machine_id()
    saved_mid = saved.get("machine_id", "")
    if saved_mid and saved_mid != current_mid:
        return LicenseStatus(False, error="机器码不匹配，请重新激活")

    token = saved["activation_token"]

    # 尝试 RSA 签名验证
    payload = _verify_token_rsa(token)
    if payload is None:
        # 回退：仅解码 payload（无公钥或旧版 HMAC token）
        payload = _decode_token_payload(token)
    if payload is None:
        return LicenseStatus(False, error="激活令牌损坏")

    result = LicenseStatus(
        activated=True,
        license_type=payload.get("license_type", saved.get("license_type", "")),
        expires_at=payload.get("expires_at", saved.get("expires_at", "")),
        machine_id=current_mid,
    )

    if result.is_expired:
        return LicenseStatus(False, error="License 已过期，请续期")

    return result


def check_license() -> LicenseStatus:
    """
    综合检查 License 状态。
    优先级：正式激活 > 试用期。
    1. 如果已激活（有activation.json），验证正式License
    2. 如果未激活，检查试用期（自动初始化30天试用）
    """
    saved = _load_token()
    if saved and "activation_token" in saved:
        # 有正式激活记录，走正式验证流程
        offline = verify_offline()
        if not offline.activated:
            return offline
        try:
            return verify_online()
        except Exception:
            return offline

    # 未激活 — 检查试用期
    return check_trial()


def deactivate() -> None:
    """清除本地激活信息。"""
    if os.path.isfile(_TOKEN_FILE):
        os.remove(_TOKEN_FILE)
