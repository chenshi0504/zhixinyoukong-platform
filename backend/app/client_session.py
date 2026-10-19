"""局域网学生功能的轻量客户端会话标识。

会话 ID 决定运行时工作目录（多源数据融合、交通流预测都按会话隔离），
因此这里要保证两件事：
1. 同一个浏览器能稳定拿到同一个值；
2. 不同客户端不会因为「没有携带会话标识」而落进同一个共享目录。
"""

from __future__ import annotations

import hashlib
import re

from fastapi import Request


_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
# 历史版本在取不到会话标识时统一返回这个常量，结果所有「不带会话头/参数/Cookie」
# 的调用方共用同一个工作目录，互相覆盖结果、互相抢占运行权，且客户端还能主动
# 传入该值加入公共桶。现在把它列为保留值：既不返回，也不接受。
_RESERVED_SESSION_IDS = {"legacy-client-session"}


def _derived_session_id(request: Request) -> str:
    """为未携带会话标识的客户端派生一个稳定且互不相同的会话 ID。

    只使用服务端可见的连接地址与请求头，不读取可伪造的 ``X-Forwarded-For``。
    派生结果满足 ``_SESSION_PATTERN``，可直接用作目录名。
    """

    client = request.client
    host = str(client.host) if client and client.host else "unknown"
    fingerprint = "|".join(
        (
            host,
            request.headers.get("user-agent", ""),
            request.headers.get("accept-language", ""),
        )
    )
    digest = hashlib.sha1(fingerprint.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"anon-{digest}"


def client_session_id(request: Request) -> str:
    """从请求头、查询参数或 Cookie 取得稳定且可用于目录名的会话标识。"""

    candidates = (
        request.headers.get("X-Client-Session"),
        request.query_params.get("session"),
        request.cookies.get("zxk_client_session_id"),
    )
    for value in candidates:
        normalized = str(value or "").strip()
        if _SESSION_PATTERN.fullmatch(normalized) and normalized not in _RESERVED_SESSION_IDS:
            return normalized
    return _derived_session_id(request)
