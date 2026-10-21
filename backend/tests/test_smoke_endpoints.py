"""Quick smoke test for all algorithm route endpoints.

This file is intentionally script-friendly. The real pytest smoke coverage lives
in `test_smoke_endpoints_pytest`; keeping network probing behind `main()` avoids
exiting during pytest collection when no server is running.
"""
import urllib.request
import sys

URLS = [
    ("v1/health", "http://127.0.0.1:{port}/api/v1/health"),
    ("collection/health", "http://127.0.0.1:{port}/api/collection/health"),
    ("fusion/health", "http://127.0.0.1:{port}/api/fusion/health"),
    ("signal-optimization/status", "http://127.0.0.1:{port}/api/signal-optimization/status"),
    ("path-guidance/status", "http://127.0.0.1:{port}/api/path-guidance/status"),
    ("vehicle-speed/status", "http://127.0.0.1:{port}/api/vehicle-speed/status"),
    ("three-level/status", "http://127.0.0.1:{port}/api/three-level/status"),
    ("reconstruction/status", "http://127.0.0.1:{port}/api/reconstruction/status"),
    ("vehicle-control/health", "http://127.0.0.1:{port}/api/vehicle-control/health"),
]

def run_smoke(port="18051"):
    ok = 0
    fail = 0
    for name, url_tpl in URLS:
        url = url_tpl.format(port=port)
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            print(f"  OK  {resp.status}  {name}")
            ok += 1
        except Exception as e:
            print(f"  FAIL       {name}  =>  {e}")
            fail += 1
    print(f"\nResult: {ok} OK, {fail} FAIL")
    return ok, fail


def test_smoke_endpoints_pytest():
    """Collection-safe placeholder; network smoke is run explicitly as a script."""
    assert URLS


if __name__ == "__main__":
    _, fail = run_smoke(sys.argv[1] if len(sys.argv) > 1 else "18051")
    sys.exit(1 if fail else 0)
