"""局域网学生任务的会话隔离和并发提交测试。"""

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.routers import data_fusion_runtime as fusion_module
from app.routers import traffic_prediction as prediction_module


SESSION_A = "student-session-aaaaaaaa"
SESSION_B = "student-session-bbbbbbbb"


async def _concurrent_requests(method: str, path: str, sessions: tuple[str, ...], **kwargs):
    transport = httpx.ASGITransport(app=app, client=("192.168.1.30", 42000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await asyncio.gather(*(
            client.request(method, path, headers={"X-Client-Session": session_id}, **kwargs)
            for session_id in sessions
        ))


def _wait_until(predicate, timeout=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("后台测试任务未按期结束")


def test_prediction_accepts_two_sessions_and_keeps_status_separate(monkeypatch, tmp_path):
    prediction_module.reset_prediction_runtime_state()
    release = threading.Event()

    def prepare(session_id):
        workspace = tmp_path / session_id
        (workspace / "charts").mkdir(parents=True, exist_ok=True)
        (workspace / "predictor.py").write_text("# test", encoding="utf-8")
        return workspace

    def fake_run(session_id, task, script_path, script_args, cleanup_path=None):
        release.wait(timeout=2)
        prediction_module._set_session_status(
            session_id,
            running=False,
            success=True,
            message=f"{session_id}完成",
            pid=None,
        )

    monkeypatch.setattr(prediction_module, "_prepare_workspace", prepare)
    monkeypatch.setattr(prediction_module, "_run_task", fake_run)
    responses = asyncio.run(_concurrent_requests("POST", "/api/prediction/run-prediction", (SESSION_A, SESSION_B), json={"model": "all"}))
    assert all(response.status_code == 200 and response.json()["success"] for response in responses)
    assert prediction_module._TASKS[SESSION_A]["running"] is True
    assert prediction_module._TASKS[SESSION_B]["running"] is True

    duplicate = asyncio.run(_concurrent_requests("POST", "/api/prediction/run-prediction", (SESSION_A,), json={"model": "all"}))[0]
    assert duplicate.json()["success"] is False
    release.set()
    _wait_until(lambda: not prediction_module._TASKS[SESSION_A]["running"] and not prediction_module._TASKS[SESSION_B]["running"])


def test_fusion_accepts_two_sessions_and_keeps_status_separate(monkeypatch, tmp_path):
    fusion_module.reset_fusion_runtime_state()
    release = threading.Event()

    def prepare(session_id):
        workspace = tmp_path / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "贝叶斯融合_新版.py").write_text("# test", encoding="utf-8")
        return workspace

    def fake_run(session_id, task_key, workspace, script_path, cleanup_path=None):
        release.wait(timeout=2)
        fusion_module._set_status(session_id, task_key, running=False, success=True, message="完成", pid=None)

    monkeypatch.setattr(fusion_module, "_prepare_workspace", prepare)
    monkeypatch.setattr(fusion_module, "_run_task", fake_run)
    responses = asyncio.run(_concurrent_requests("POST", "/api/fusion/start", (SESSION_A, SESSION_B)))
    assert all(response.status_code == 200 and response.json()["success"] for response in responses)
    assert fusion_module._TASKS[SESSION_A]["fusion"]["running"] is True
    assert fusion_module._TASKS[SESSION_B]["fusion"]["running"] is True

    duplicate = asyncio.run(_concurrent_requests("POST", "/api/fusion/start", (SESSION_A,)))[0]
    assert duplicate.json()["success"] is False
    release.set()
    _wait_until(lambda: not fusion_module._TASKS[SESSION_A]["fusion"]["running"] and not fusion_module._TASKS[SESSION_B]["fusion"]["running"])


def test_prediction_and_fusion_results_are_isolated_by_session(monkeypatch, tmp_path):
    prediction_root = tmp_path / "prediction"
    fusion_root = tmp_path / "fusion"

    for session_id, marker in ((SESSION_A, "A"), (SESSION_B, "B")):
        prediction_workspace = prediction_root / session_id
        (prediction_workspace / "charts").mkdir(parents=True)
        (prediction_workspace / "charts" / "results.txt").write_text(f"owner={marker}\n", encoding="utf-8")

        fusion_workspace = fusion_root / session_id
        result_dir = fusion_workspace / "output" / "fusion" / "val"
        result_dir.mkdir(parents=True)
        (result_dir / "sample.json").write_text(json.dumps({"owner": marker}), encoding="utf-8")

    monkeypatch.setattr(prediction_module, "_RUNTIME_ROOT", prediction_root)
    monkeypatch.setattr(fusion_module, "_RUNTIME_ROOT", fusion_root)

    prediction_results = asyncio.run(_concurrent_requests("GET", "/api/prediction/get-results", (SESSION_A, SESSION_B)))
    assert [response.json()["data"]["owner"] for response in prediction_results] == ["A", "B"]

    fusion_results = asyncio.run(_concurrent_requests("GET", "/api/fusion/get-fusion-data", (SESSION_A, SESSION_B)))
    assert [response.json()["sample"]["owner"] for response in fusion_results] == ["A", "B"]
