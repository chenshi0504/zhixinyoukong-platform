# -*- coding: utf-8 -*-
"""LAN concurrency test for the platform.

Simulates N students hitting the platform through its LAN address and walking
the full student flow (login, page loads, read-only APIs, per-session
collection/fusion/prediction endpoints), then reports status codes, latency
distribution and correctness assertions.

Usage:  python _lan_concurrency_test.py [base_url] [concurrent_students]
"""

import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# 注意：参数在 main() 里解析，不在导入期解析。文件名以 _test.py 结尾会被 pytest
# 收集，模块级解析 sys.argv[2] 会让整个测试套件在收集阶段直接报错。
BASE = "http://10.8.129.232:8000"
STUDENTS = 12

_records = []
_problems = []
_lock = threading.Lock()


def record(tag, status, ms, err):
    with _lock:
        _records.append((tag, status, ms, err))


def fail(message):
    with _lock:
        _problems.append(message)


def call(tag, method, path, body=None, token=None, headers=None, timeout=60):
    url = BASE + urllib.parse.quote(path, safe="/?=&%")
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    start = time.perf_counter()
    status, raw, err = 0, b"", ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except Exception as exc:
        err = "%s: %s" % (type(exc).__name__, exc)
    ms = (time.perf_counter() - start) * 1000
    record(tag, status, ms, err)
    return status, raw, err


def as_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


# Every page/asset a student browser pulls when opening the platform.
STATIC_ASSETS = [
    "/student.html",
    "/src/pages/多源数据采集功能/data_collection.html",
    "/src/pages/多源数据采集功能/data_collection.js",
    "/src/pages/多源数据融合功能/data_fusion_new.html",
    "/src/pages/多源数据融合功能/data_fusion_new.js",
    "/src/pages/交通流重构功能/traffic_reconstruction.html",
    "/src/pages/交通流重构功能/traffic_reconstruction.js",
    "/src/pages/交通流预测功能/traffic_flow_prediction.html",
    "/src/pages/交通流预测功能/traffic_flow_prediction.js",
    "/src/components/local-only-guard.js",
    "/src/components/lan-guard.js",
    "/src/components/status-bar.js",
]


def student(index):
    """One virtual student walking the LAN-available feature set."""

    # 1. Access context must report LAN (this is the address students use).
    status, raw, _ = call("01 access-context", "GET", "/api/v1/access-context")
    ctx = as_json(raw)
    if ctx.get("access_mode") != "lan":
        fail("client %d: expected access_mode=lan, got %r" % (index, ctx.get("access_mode")))
    if ctx.get("can_control_local_services") is not False:
        fail("client %d: can_control_local_services should be False on LAN" % index)

    # 2. Login (bcrypt + token issue) - the classroom hot path.
    status, raw, _ = call("02 login", "POST", "/api/v1/auth/login/json",
                          {"username": "student", "password": "123456"})
    if status != 200:
        fail("client %d: login failed HTTP %d" % (index, status))
    token = as_json(raw).get("access_token")
    if not token:
        fail("client %d: login returned no access_token" % index)

    call("03 auth/me", "GET", "/api/v1/auth/me", token=token)
    call("04 health", "GET", "/api/v1/health")
    call("05 backends-status", "GET", "/api/v1/experiment-backends/status")
    call("06 simulators-status", "GET", "/api/v1/simulators/status")
    call("07 self-algo packs", "GET", "/api/v1/self-algorithms/packs", token=token)

    for asset in STATIC_ASSETS:
        call("08 static asset", "GET", asset)

    # 3. Data collection session lifecycle (per-browser isolation).
    status, raw, _ = call("09 collection-session", "POST", "/api/collection/session")
    session = as_json(raw)
    csid = session.get("session_id")
    ctoken = session.get("session_token")
    if not csid or not ctoken:
        fail("client %d: collection session not created (HTTP %d)" % (index, status))
    else:
        hdr = {"X-Client-Session": csid, "X-Client-Session-Token": ctoken}
        call("10 collection-health", "GET", "/api/collection/session/%s/health" % csid, headers=hdr)
        call("11 collection-status", "GET", "/api/collection/session/%s/detection/status" % csid, headers=hdr)
        call("12 collection-scenarios", "GET", "/api/collection/session/%s/scenarios" % csid, headers=hdr)

        # Another student must not be able to read this session.
        other = "lanprobe" + uuid.uuid4().hex[:12]
        stolen, _, _ = call("13 cross-session-deny", "GET",
                            "/api/collection/session/%s/health" % csid,
                            headers={"X-Client-Session": other, "X-Client-Session-Token": ctoken})
        if stolen != 403:
            fail("client %d: cross-session read not denied, HTTP %d" % (index, stolen))

    # 4. Fusion / prediction session-scoped read paths.
    sid = "lanload" + uuid.uuid4().hex[:16]
    call("14 fusion-status", "GET", "/api/fusion/status", headers={"X-Client-Session": sid})
    call("15 fusion-health", "GET", "/api/fusion/health", headers={"X-Client-Session": sid})
    call("16 prediction-status", "GET", "/api/prediction/status", headers={"X-Client-Session": sid})
    call("17 prediction-results", "GET", "/api/prediction/get-results", headers={"X-Client-Session": sid})


def percentile(values, ratio):
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(int(len(ordered) * ratio), len(ordered) - 1)
    return ordered[position]


def main():
    global BASE, STUDENTS
    if len(sys.argv) > 1:
        BASE = sys.argv[1].rstrip("/")
    if len(sys.argv) > 2:
        STUDENTS = int(sys.argv[2])
    print("target      : %s" % BASE)
    print("concurrency : %d students" % STUDENTS)
    print("-" * 82)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=STUDENTS) as pool:
        list(pool.map(student, range(1, STUDENTS + 1)))
    elapsed = time.perf_counter() - started

    tags = defaultdict(list)
    for tag, status, ms, err in _records:
        tags[tag].append((status, ms, err))

    print("%-22s %5s %8s %8s %8s %8s %8s" % ("step", "n", "p50ms", "p95ms", "maxms", "codes", "err"))
    for tag in sorted(tags):
        rows = tags[tag]
        latencies = [row[1] for row in rows]
        codes = defaultdict(int)
        for status, _, _ in rows:
            codes[status] += 1
        code_text = ",".join("%s:%d" % (code, count) for code, count in sorted(codes.items()))
        errors = sum(1 for row in rows if row[2])
        print("%-22s %5d %8.1f %8.1f %8.1f %8s %8d" % (
            tag, len(rows), percentile(latencies, 0.50), percentile(latencies, 0.95),
            max(latencies), code_text, errors))

    total = len(_records)
    server_errors = [row for row in _records if row[1] >= 500 or row[1] == 0]
    print("-" * 82)
    print("total requests      : %d" % total)
    print("wall time           : %.2f s" % elapsed)
    print("throughput          : %.1f req/s" % (total / elapsed if elapsed else 0))
    print("all latencies p95   : %.1f ms" % percentile([row[2] for row in _records], 0.95))
    print("5xx / connection err: %d" % len(server_errors))

    logins = tags.get("02 login", [])
    if logins:
        print("login burst (%d)     : max %.0f ms, p50 %.0f ms" % (
            len(logins), max(row[1] for row in logins), percentile([row[1] for row in logins], 0.5)))

    print("-" * 82)
    if _problems:
        print("ASSERTIONS FAILED (%d):" % len(_problems))
        for item in _problems[:20]:
            print("  - " + item)
    else:
        print("ASSERTIONS: all passed")

    return 1 if (_problems or server_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
