"""客户端会话标识的派生与保留值测试。

会话标识决定融合 / 预测的运行时工作目录，必须保证：
1. 带会话标识的请求原样采纳；
2. 历史保留值不再被接受（否则任何客户端都能加入共享公共桶）；
3. 未带标识的请求按客户端派生，不同客户端不会落进同一个目录。
"""

import re
import sys
from pathlib import Path

from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.client_session import client_session_id  # noqa: E402


SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def make_request(headers=None, client=("192.168.1.30", 40000)):
    raw_headers = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": raw_headers,
            "client": client,
            "server": ("test", 80),
        }
    )


def test_explicit_session_header_is_used():
    session = "student-session-aaaaaaaa"
    request = make_request({"x-client-session": session})
    assert client_session_id(request) == session


def test_cookie_is_used_when_header_missing():
    session = "cookie-session-bbbbbbbbbb"
    request = make_request({"cookie": f"zxk_client_session_id={session}"})
    assert client_session_id(request) == session


def test_reserved_legacy_session_is_rejected():
    """历史公共桶标识必须失效，避免所有无标识客户端共用同一目录。"""
    request = make_request({"x-client-session": "legacy-client-session"})
    derived = client_session_id(request)
    assert derived != "legacy-client-session"
    assert SESSION_PATTERN.fullmatch(derived), derived


def test_anonymous_clients_get_distinct_sessions():
    """不同客户端（IP / User-Agent 不同）必须派生出互不相同的会话。"""

    first = client_session_id(
        make_request({"user-agent": "Mozilla/5.0 A"}, client=("192.168.1.30", 40000))
    )
    second = client_session_id(
        make_request({"user-agent": "Mozilla/5.0 B"}, client=("192.168.1.31", 40000))
    )
    third = client_session_id(
        make_request({"user-agent": "Mozilla/5.0 A"}, client=("192.168.1.31", 40000))
    )

    assert len({first, second, third}) == 3
    assert all(SESSION_PATTERN.fullmatch(value) for value in (first, second, third))


def test_anonymous_session_is_stable_for_same_client():
    headers = {"user-agent": "Mozilla/5.0 A"}
    client = ("192.168.1.30", 40000)
    assert client_session_id(make_request(headers, client)) == client_session_id(
        make_request(headers, client)
    )


def test_invalid_session_value_falls_back_to_derived():
    """非法格式（过短/含非法字符）不得直接用作目录名。"""
    for bad_value in ("short", "has space here", "a/b/c/d/e/f/g/h/i/j/k"):
        derived = client_session_id(make_request({"x-client-session": bad_value}))
        assert derived != bad_value
        assert SESSION_PATTERN.fullmatch(derived), derived
