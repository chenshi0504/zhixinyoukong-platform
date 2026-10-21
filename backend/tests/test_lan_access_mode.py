"""局域网访问控制和数据采集会话链路测试。"""

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as main_module
from app.main import app
from app.access_mode import requires_local_control
from app.routers import data_collection_session as collection_module
from starlette.requests import Request


def request(client_address, method, path, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app, client=client_address)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


def access_request(path, method="POST"):
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("192.168.1.20", 41000),
            "server": ("test", 80),
        }
    )


def test_access_context_distinguishes_local_and_lan():
    remote = request(("192.168.1.20", 41000), "GET", "/api/v1/access-context")
    assert remote.status_code == 200
    assert remote.json()["access_mode"] == "lan"
    assert remote.json()["can_control_local_services"] is False
    assert remote.json()["can_start_experiment_backends"] is True

    local = request(("127.0.0.1", 41000), "GET", "/api/v1/access-context")
    assert local.status_code == 200
    assert local.json()["access_mode"] == "local"
    assert local.json()["can_control_local_services"] is True
    assert local.json()["can_start_experiment_backends"] is True
    assert local.json()["default_account"] == {"username": "student", "password": "123456"}

    for path in (
        "/api/v1/simulators/sumo/launch",
        "/api/v1/simulators/carla/launch",
        "/api/v1/simulators/shared-simulator/launch",
        "/api/carla-sim/start",
        "/api/vehicle-control/cars/1/commands",
        "/api/vehicle-control/send-command",
        "/api/vehicle-control/road-topology/goal-node",
        "/api/vehicle-control/reset",
        "/api/cars/1/commands",
        "/api/road-topology/goal-node",
    ):
        response = request(("192.168.1.20", 41000), "POST", path, json={})
        assert response.status_code == 403, path


def test_lan_allows_student_experiment_operations():
    for path in (
        "/api/prediction/train-model",
        "/api/prediction/run-prediction",
        "/api/prediction/run-custom-algorithm",
        "/api/prediction/reset",
        "/api/fusion/start",
        "/api/fusion/run-custom-fusion",
    ):
        assert requires_local_control(access_request(path)) is False, path

    # 只读状态查询对局域网保持开放（车规级 HIL 车辆状态可查看）。
    for path in (
        "/api/vehicle-control/vehicle-state",
        "/api/vehicle-control/cars",
        "/api/cars",
        "/api/vehicle-control/road-topology/status",
    ):
        assert requires_local_control(access_request(path, method="GET")) is False, path

    # 启动平台后端 CMD 是共享的幂等预热入口，允许局域网触发；
    # 交通流重构（DTALite/NEXTA）与三层级模块的运行接口同样允许局域网触发：
    # 后端会在运行平台的本机弹出 CMD 窗口执行，结果通过轮询接口反馈。
    assert requires_local_control(access_request("/api/v1/experiment-backends/start")) is False
    for path in (
        "/api/reconstruction/run-dtalite",
        "/api/reconstruction/launch-nexta",
        "/api/reconstruction/save-params",
        "/api/reconstruction/generate-report",
        "/api/reconstruction/export-network-doc",
        "/api/signal-optimization/run",
        "/api/signal-optimization/run-custom",
        "/api/signal-optimization/reset",
        "/api/signal-optimization/stop",
        "/api/path-guidance/run",
        "/api/path-guidance/reset",
        "/api/vehicle-speed/run",
        "/api/vehicle-speed/run-custom",
        "/api/vehicle-speed/reset",
        "/api/vehicle-speed/stop",
        "/api/three-level/run",
        "/api/three-level/reset",
    ):
        assert requires_local_control(access_request(path)) is False, path


def test_lan_backend_launcher_opens_cmd_without_starting_native_simulation(monkeypatch):
    native_start_called = False

    def fail_if_native_stack_starts():
        nonlocal native_start_called
        native_start_called = True
        raise AssertionError("局域网请求不得启动 CARLA/VIC-Sim")

    monkeypatch.setattr(main_module, "_EXPERIMENT_BACKEND_SPECS", [])
    monkeypatch.setattr(main_module, "_ensure_experiment_native_stack", fail_if_native_stack_starts)
    monkeypatch.setattr(
        main_module,
        "_launch_experiment_warmup_console",
        lambda: {
            "success": True,
            "ready": True,
            "message": "测试预热完成",
            "checks": [],
            "console_pid": 23456,
        },
    )

    response = request(("192.168.1.20", 41000), "POST", "/api/v1/experiment-backends/start", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_mode"] == "lan"
    assert payload["ready"] is True
    assert payload["console_pid"] == 23456
    assert payload["native"]["skipped"] is True
    assert native_start_called is False


def test_lan_uses_session_collection_transport(monkeypatch, tmp_path):
    class FakeProcess:
        _next_pid = 20000

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.pid = FakeProcess._next_pid
            FakeProcess._next_pid += 1
            self._returncode = None

        def poll(self):
            return self._returncode

        def terminate(self):
            self._returncode = 0

    monkeypatch.setattr(collection_module.subprocess, "Popen", FakeProcess)
    session_root = tmp_path / "data_collection_sessions"
    session_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(collection_module, "_SESSION_ROOT", session_root)
    sids = []
    tokens = {}
    for _ in range(2):
        created = request(("192.168.1.20", 41000), "POST", "/api/collection/session", json={})
        assert created.status_code == 200
        sid = created.json()["session_id"]
        sids.append(sid)
        tokens[sid] = created.json()["session_token"]
        headers = {"X-Client-Session": sid, "X-Client-Session-Token": tokens[sid]}
        started = request(
            ("192.168.1.20", 41000),
            "POST",
            f"/api/collection/session/{sid}/detection/start",
            headers=headers,
            json={"video": "test1.mp4", "model": "yolo11n.pt"},
        )
        assert started.status_code == 200
        assert started.json()["success"] is True

    workspaces = [Path(collection_module._JOBS[sid]["workspace"]) for sid in sids]
    assert workspaces[0] != workspaces[1]
    assert all(path.parent == collection_module._SESSION_ROOT for path in workspaces)

    for sid in sids:
        headers = {"X-Client-Session": sid, "X-Client-Session-Token": tokens[sid]}
        status = request(("192.168.1.20", 41000), "GET", f"/api/collection/session/{sid}/detection/status", headers=headers)
        assert status.status_code == 200
        output = workspaces[sids.index(sid)] / "outputs" / "result.mp4"
        output.write_bytes(b"session-output")
        media = request(("192.168.1.20", 41000), "GET", f"/api/collection/session/{sid}/outputs/result.mp4?token={tokens[sid]}")
        assert media.status_code == 200
        unauthorized = request(("192.168.1.20", 41000), "GET", f"/api/collection/session/{sid}/outputs/result.mp4")
        assert unauthorized.status_code == 403
        stopped = request(("192.168.1.20", 41000), "POST", f"/api/collection/session/{sid}/detection/stop", headers=headers)
        assert stopped.status_code == 200

    legacy = request(("192.168.1.20", 41000), "GET", "/api/collection/get-results")
    assert legacy.status_code == 409
    assert legacy.json()["code"] == "DATA_COLLECTION_SESSION_REQUIRED"

    collection_module.reset_collection_session_state()
