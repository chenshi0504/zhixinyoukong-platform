# -*- coding: utf-8 -*-
"""LAN concurrency report for the platform. Manual load test, not a pytest case.

Point it at the LAN address so the backend really evaluates the callers as LAN
clients (students). Scenarios:

  S1  login burst        N concurrent logins
  S2  full student flow  N concurrent students walking every LAN-available module
  S3  read-only storm    N concurrent read-only clients
  S4  mixed task start   collection / fusion / prediction / read-only fired at the
                         very same instant through a barrier; launched jobs are
                         stopped again afterwards and quota release is verified

Usage:
    python backend/tests/lan_concurrency_report.py http://10.8.129.232:8000 12
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

BASE = ""
RECORDS = []
PROBLEMS = []
NOTES = []
LOCK = threading.Lock()

COLLECTION_QUOTA = 4
FUSION_QUOTA = 4
PREDICTION_QUOTA = 4


def note(text):
    with LOCK:
        NOTES.append(text)


def record(scenario, tag, status, ms, err):
    with LOCK:
        RECORDS.append((scenario, tag, status, ms, err))


def problem(text):
    with LOCK:
        PROBLEMS.append(text)


def request(method, path, body=None, token=None, headers=None, timeout=120,
            scenario=None, tag=None):
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
    if scenario:
        record(scenario, tag, status, ms, err)
    return status, raw, err


def as_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def percentile(values, ratio):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * ratio), len(ordered) - 1)]


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


# --------------------------------------------------------------------------
# S1  login burst
# --------------------------------------------------------------------------
def scenario_login_burst(count):
    def worker(_):
        request("POST", "/api/v1/auth/login/json",
                {"username": "student", "password": "123456"},
                scenario="S1", tag="login")

    with ThreadPoolExecutor(max_workers=count) as pool:
        list(pool.map(worker, range(count)))


# --------------------------------------------------------------------------
# S2  full student flow
# --------------------------------------------------------------------------
def student_flow(_):
    status, raw, _ = request("GET", "/api/v1/access-context",
                             scenario="S2", tag="access-context")
    if as_json(raw).get("access_mode") != "lan":
        problem("S2: access-context did not report lan")

    status, raw, _ = request("POST", "/api/v1/auth/login/json",
                             {"username": "student", "password": "123456"},
                             scenario="S2", tag="login")
    token = as_json(raw).get("access_token")
    if status != 200 or not token:
        problem("S2: login failed HTTP %d" % status)

    request("GET", "/api/v1/auth/me", token=token, scenario="S2", tag="auth/me")
    request("GET", "/api/v1/health", scenario="S2", tag="health")
    request("GET", "/api/v1/experiment-backends/status",
            scenario="S2", tag="backends-status")
    request("GET", "/api/v1/simulators/status", scenario="S2", tag="simulators-status")
    request("GET", "/api/v1/self-algorithms/packs", token=token,
            scenario="S2", tag="self-algo-packs")
    for asset in STATIC_ASSETS:
        request("GET", asset, scenario="S2", tag="static-asset")

    status, raw, _ = request("POST", "/api/collection/session",
                             scenario="S2", tag="collection-session")
    data = as_json(raw)
    sid, token2 = data.get("session_id"), data.get("session_token")
    if not sid or not token2:
        problem("S2: collection session not created")
    else:
        hdr = {"X-Client-Session": sid, "X-Client-Session-Token": token2}
        request("GET", "/api/collection/session/%s/health" % sid, headers=hdr,
                scenario="S2", tag="collection-health")
        request("GET", "/api/collection/session/%s/detection/status" % sid, headers=hdr,
                scenario="S2", tag="collection-status")
        other = "lanprobe" + uuid.uuid4().hex[:12]
        stolen, _, _ = request("GET", "/api/collection/session/%s/health" % sid,
                               headers={"X-Client-Session": other,
                                        "X-Client-Session-Token": token2},
                               scenario="S2", tag="cross-session-deny")
        if stolen != 403:
            problem("S2: cross-session read not denied (HTTP %d)" % stolen)

    fsid = "lanload" + uuid.uuid4().hex[:16]
    request("GET", "/api/fusion/status", headers={"X-Client-Session": fsid},
            scenario="S2", tag="fusion-status")
    request("GET", "/api/fusion/health", headers={"X-Client-Session": fsid},
            scenario="S2", tag="fusion-health")
    request("GET", "/api/prediction/status", headers={"X-Client-Session": fsid},
            scenario="S2", tag="prediction-status")
    request("GET", "/api/prediction/get-results", headers={"X-Client-Session": fsid},
            scenario="S2", tag="prediction-results")


def scenario_full_flow(count):
    with ThreadPoolExecutor(max_workers=count) as pool:
        list(pool.map(student_flow, range(count)))


# --------------------------------------------------------------------------
# S3  read-only storm
# --------------------------------------------------------------------------
def scenario_read_only(count):
    def worker(_):
        request("GET", "/api/v1/health", scenario="S3", tag="health")
        request("GET", "/api/v1/access-context", scenario="S3", tag="access-context")
        request("GET", "/api/v1/experiment-backends/status",
                scenario="S3", tag="backends-status")
        request("GET", "/api/v1/simulators/status", scenario="S3", tag="simulators-status")
        request("GET", "/api/prediction/status",
                headers={"X-Client-Session": "lanro" + uuid.uuid4().hex[:12]},
                scenario="S3", tag="prediction-status")

    with ThreadPoolExecutor(max_workers=count) as pool:
        list(pool.map(worker, range(count)))


# --------------------------------------------------------------------------
# S4  mixed task start (all fired at the same instant)
# --------------------------------------------------------------------------
def prepare_clients(collection_n, fusion_n, prediction_n, readonly_n):
    cases = []
    for _ in range(collection_n):
        _, raw, _ = request("POST", "/api/collection/session")
        data = as_json(raw)
        cases.append(("collection", {"sid": data.get("session_id"),
                                     "token": data.get("session_token")}))
    for _ in range(fusion_n):
        cases.append(("fusion", {"sid": "lanmixf" + uuid.uuid4().hex[:12]}))
    for _ in range(prediction_n):
        cases.append(("prediction", {"sid": "lanmixp" + uuid.uuid4().hex[:12]}))
    for _ in range(readonly_n):
        _, raw, _ = request("POST", "/api/collection/session")
        data = as_json(raw)
        cases.append(("readonly", {"sid": data.get("session_id"),
                                   "token": data.get("session_token")}))
    return cases


def mixed_worker(barrier, case, out):
    kind, payload = case
    sid = payload["sid"]
    barrier.wait()          # every client leaves the gate at the same moment
    if kind == "collection":
        hdr = {"X-Client-Session": sid, "X-Client-Session-Token": payload["token"]}
        status, raw, _ = request("POST", "/api/collection/session/%s/detection/start" % sid,
                                 body={}, headers=hdr, scenario="S4", tag="collection-start")
        out.append(("collection", sid, payload["token"], status, as_json(raw)))
    elif kind == "fusion":
        status, raw, _ = request("POST", "/api/fusion/start",
                                 headers={"X-Client-Session": sid},
                                 scenario="S4", tag="fusion-start")
        out.append(("fusion", sid, None, status, as_json(raw)))
    elif kind == "prediction":
        status, raw, _ = request("POST", "/api/prediction/run-prediction",
                                 body={"model": "all"},
                                 headers={"X-Client-Session": sid},
                                 scenario="S4", tag="prediction-start")
        out.append(("prediction", sid, None, status, as_json(raw)))
    else:
        request("GET", "/api/v1/experiment-backends/status",
                scenario="S4", tag="readonly")
        request("GET", "/api/prediction/status",
                headers={"X-Client-Session": sid}, scenario="S4", tag="readonly")


def scenario_mixed(collection_n, fusion_n, prediction_n, readonly_n):
    cases = prepare_clients(collection_n, fusion_n, prediction_n, readonly_n)
    barrier = threading.Barrier(len(cases))
    out = []
    with ThreadPoolExecutor(max_workers=len(cases)) as pool:
        list(pool.map(lambda case: mixed_worker(barrier, case, out), cases))

    grouped = defaultdict(list)
    for kind, sid, token, status, body in out:
        grouped[kind].append((sid, token, status, body))

    for kind, quota in (("collection", COLLECTION_QUOTA),
                        ("fusion", FUSION_QUOTA),
                        ("prediction", PREDICTION_QUOTA)):
        rows = grouped.get(kind, [])
        accepted = [row for row in rows if row[2] == 200 and row[3].get("success")]
        rejected = [row for row in rows if row[2] == 429]
        if len(accepted) != quota:
            problem("S4/%s: expected %d accepted, got %d" % (kind, quota, len(accepted)))
        if len(rejected) != len(rows) - quota:
            problem("S4/%s: expected %d rejected, got %d"
                    % (kind, len(rows) - quota, len(rejected)))
        for row in rejected:
            code = row[3].get("code")
            if not code or not code.endswith("CAPACITY"):
                problem("S4/%s: rejection without *_CAPACITY code (%r)" % (kind, code))
        note("S4 %-11s 提交 %d -> 接收 %d / 429 拒绝 %d"
             % (kind, len(rows), len(accepted), len(rejected)))
    return grouped


def cleanup(grouped):
    for kind, rows in grouped.items():
        for sid, token, status, body in rows:
            if kind == "collection":
                hdr = {"X-Client-Session": sid, "X-Client-Session-Token": token}
                request("POST", "/api/collection/session/%s/detection/stop" % sid,
                        headers=hdr)
                request("POST", "/api/collection/session/%s/detection/reset" % sid,
                        headers=hdr)
            elif kind == "fusion" and status == 200 and body.get("success"):
                request("POST", "/api/fusion/reset", headers={"X-Client-Session": sid})
            elif kind == "prediction" and status == 200 and body.get("success"):
                request("POST", "/api/prediction/reset", headers={"X-Client-Session": sid})


def verify_quota_released():
    _, raw, _ = request("POST", "/api/collection/session")
    data = as_json(raw)
    sid, token = data.get("session_id"), data.get("session_token")
    hdr = {"X-Client-Session": sid, "X-Client-Session-Token": token}
    status, raw, _ = request("POST", "/api/collection/session/%s/detection/start" % sid,
                             body={}, headers=hdr)
    body = as_json(raw)
    if status == 200 and body.get("success"):
        note("清理后配额已释放：新会话可再次启动检测（通过）")
    else:
        problem("清理后仍无法启动检测：HTTP %d %r" % (status, body.get("message")))
    request("POST", "/api/collection/session/%s/detection/stop" % sid, headers=hdr)
    request("POST", "/api/collection/session/%s/detection/reset" % sid, headers=hdr)


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
SCENARIO_NAMES = {
    "S1": "登录风暴",
    "S2": "学生全流程",
    "S3": "只读查询风暴",
    "S4": "不同任务同时启动",
}


def print_report(elapsed_by_scenario, concurrency):
    print("=" * 92)
    print("局域网并发测试报告")
    print("目标: %s    并发客户端: %d    时间: %s"
          % (BASE, concurrency, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 92)

    for scenario in ("S1", "S2", "S3", "S4"):
        rows = [row for row in RECORDS if row[0] == scenario]
        if not rows:
            continue
        print()
        print("[%s] %s   （%d 个并发客户端，%d 个请求，耗时 %.2f s）"
              % (scenario, SCENARIO_NAMES[scenario], concurrency, len(rows),
                 elapsed_by_scenario.get(scenario, 0.0)))
        print("-" * 92)
        print("%-24s %5s %9s %9s %9s  %s"
              % ("步骤", "次数", "p50ms", "p95ms", "maxms", "状态码"))
        by_tag = defaultdict(list)
        for _, tag, status, ms, err in rows:
            by_tag[tag].append((status, ms, err))
        for tag in sorted(by_tag):
            items = by_tag[tag]
            latencies = [item[1] for item in items]
            codes = defaultdict(int)
            for status, _, _ in items:
                codes[status] += 1
            print("%-24s %5d %9.1f %9.1f %9.1f  %s"
                  % (tag, len(items), percentile(latencies, 0.5),
                     percentile(latencies, 0.95), max(latencies),
                     ",".join("%s:%d" % (k, v) for k, v in sorted(codes.items()))))

    if NOTES:
        print()
        print("混合任务明细")
        print("-" * 92)
        for text in NOTES:
            print("  " + text)

    total = len(RECORDS)
    server_errors = [row for row in RECORDS if row[2] >= 500 or row[2] == 0]
    print()
    print("=" * 92)
    print("总请求 %d    5xx/连接错误 %d    HTTP 429(配额拒绝) %d"
          % (total, len(server_errors),
             sum(1 for row in RECORDS if row[2] == 429)))
    if PROBLEMS:
        print("断言失败 %d 项:" % len(PROBLEMS))
        for text in PROBLEMS:
            print("  - " + text)
    else:
        print("断言：全部通过")
    print("=" * 92)
    return 1 if (PROBLEMS or server_errors) else 0


def main():
    global BASE
    BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://10.8.129.232:8000").rstrip("/")
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    only = set((sys.argv[3] if len(sys.argv) > 3 else "S1,S2,S3,S4").split(","))

    elapsed = {}
    if "S1" in only:
        start = time.perf_counter()
        scenario_login_burst(count)
        elapsed["S1"] = time.perf_counter() - start
    if "S2" in only:
        start = time.perf_counter()
        scenario_full_flow(count)
        elapsed["S2"] = time.perf_counter() - start
    if "S3" in only:
        start = time.perf_counter()
        scenario_read_only(count)
        elapsed["S3"] = time.perf_counter() - start
    if "S4" in only:
        start = time.perf_counter()
        grouped = scenario_mixed(COLLECTION_QUOTA + 1, FUSION_QUOTA + 1,
                                 PREDICTION_QUOTA + 1, 3)
        elapsed["S4"] = time.perf_counter() - start
        cleanup(grouped)
        verify_quota_released()

    return print_report(elapsed, count)


if __name__ == "__main__":
    sys.exit(main())
