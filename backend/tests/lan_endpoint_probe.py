# -*- coding: utf-8 -*-
"""Isolate which LAN-available endpoint stalls under concurrency.

Usage: python _lan_probe.py <base_url> <concurrency>
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# 参数在 main() 里解析，避免导入期依赖 sys.argv。
BASE = "http://10.8.129.232:8000"
N = 12

PROBES = [
    ("GET  /api/v1/health", "GET", "/api/v1/health", None),
    ("GET  /api/v1/access-context", "GET", "/api/v1/access-context", None),
    ("GET  /api/v1/experiment-backends/status", "GET", "/api/v1/experiment-backends/status", None),
    ("GET  /api/v1/simulators/status", "GET", "/api/v1/simulators/status", None),
    ("GET  /api/v1/self-algorithms/packs", "GET", "/api/v1/self-algorithms/packs", None),
    ("POST /api/v1/auth/login/json", "POST", "/api/v1/auth/login/json",
     {"username": "student", "password": "123456"}),
    ("GET  /api/prediction/get-results", "GET", "/api/prediction/get-results", None),
]


def one(method, path, body, timeout=90):
    url = BASE + urllib.parse.quote(path, safe="/?=&%")
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    start = time.perf_counter()
    status = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read()
    except Exception:
        status = 0
    return status, (time.perf_counter() - start) * 1000


def main():
    global BASE, N
    if len(sys.argv) > 1:
        BASE = sys.argv[1].rstrip("/")
    if len(sys.argv) > 2:
        N = int(sys.argv[2])
    print("target: %s   concurrency: %d" % (BASE, N))
    print("%-42s %5s %9s %9s %9s %9s" % ("endpoint", "n", "p50ms", "maxms", "wallms", "codes"))
    for label, method, path, body in PROBES:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=N) as pool:
            results = list(pool.map(lambda _: one(method, path, body), range(N)))
        wall = (time.perf_counter() - started) * 1000
        latencies = sorted(ms for _, ms in results)
        codes = {}
        for status, _ in results:
            codes[status] = codes.get(status, 0) + 1
        print("%-42s %5d %9.1f %9.1f %9.1f %9s" % (
            label, N, latencies[len(latencies) // 2], latencies[-1], wall,
            ",".join("%s:%d" % (k, v) for k, v in sorted(codes.items()))))


if __name__ == "__main__":
    main()
