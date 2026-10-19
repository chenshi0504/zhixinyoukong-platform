"""学生端开放模块的并发能力与相互隔离测试。

覆盖范围（均为局域网学生可用的功能）：

1. 多源数据采集：多会话并发、同会话重复提交拦截、全局并发上限、越权下载拦截、工作目录隔离。
2. 多源数据融合：多会话并发、同会话重复提交拦截、全局并发上限。
3. 交通流预测：多会话并发、同会话重复提交拦截、全局并发上限。
4. 跨模块互不冲突：同一会话同时跑融合与预测；两个会话同时跑三个模块。
5. 容量是"每模块独立计数"：融合打满不影响预测。
6. reset 只影响自己的会话，不干扰其他学生。

测试使用 ASGITransport 并以局域网地址作为客户端，因此走的是真实中间件链路。
"""

import asyncio
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.routers import data_collection_session as collection_module
from app.routers import data_fusion_runtime as fusion_module
from app.routers import traffic_prediction as prediction_module


LAN_CLIENT = ("192.168.1.30", 42000)


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

class FakeProcess:
    """用于替代真实子进程，避免测试真的启动 YOLO / 算法进程。"""

    _next_pid = 30000

    def __init__(self, *args, **kwargs):
        self.pid = FakeProcess._next_pid
        FakeProcess._next_pid += 1
        self._returncode = None

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = 0

    def kill(self):
        self._returncode = -9

    def wait(self, timeout=None):
        if self._returncode is None:
            self._returncode = 0
        return self._returncode


def run_all(*coroutines):
    """在同一事件循环中并发执行多个请求工厂，模拟真实并发。"""

    async def _main():
        transport = httpx.ASGITransport(app=app, client=LAN_CLIENT)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await asyncio.gather(*(factory(client) for factory in coroutines))

    return asyncio.run(_main())


def wait_until(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_session_factory(path, session_id):
    """构造"固定会话标识"的请求工厂。"""
    return lambda client: client.post(
        path,
        headers={"X-Client-Session": session_id},
        json={},
    )


# ---------------------------------------------------------------------------
# 1. 多源数据采集
# ---------------------------------------------------------------------------

def _prepare_collection(monkeypatch, tmp_path, max_jobs):
    collection_module.reset_collection_session_state()
    session_root = tmp_path / "collection_sessions"
    session_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(collection_module, "_SESSION_ROOT", session_root)
    monkeypatch.setattr(collection_module, "_MAX_CONCURRENT_JOBS", max_jobs)
    monkeypatch.setattr(collection_module.subprocess, "Popen", FakeProcess)
    fake_video = tmp_path / "test1.mp4"
    fake_video.write_bytes(b"fake-video")
    monkeypatch.setattr(collection_module, "_resolve_video", lambda sid, name: fake_video)
    return session_root


def _create_collection_sessions(count):
    factories = [lambda client: client.post("/api/collection/session", json={}) for _ in range(count)]
    responses = run_all(*factories)
    sessions = []
    for response in responses:
        payload = response.json()
        sessions.append((payload["session_id"], payload["session_token"]))
    return sessions


def _start_detection_factory(session_id, token):
    return lambda client: client.post(
        f"/api/collection/session/{session_id}/detection/start",
        headers={"X-Client-Session": session_id, "X-Client-Session-Token": token},
        json={"video": "test1.mp4", "model": "yolo11n.pt"},
    )


def test_collection_concurrent_sessions_are_isolated(monkeypatch, tmp_path):
    session_root = _prepare_collection(monkeypatch, tmp_path, max_jobs=4)
    sessions = _create_collection_sessions(2)
    assert len({sid for sid, _ in sessions}) == 2, "每个浏览器会话必须拿到不同标识"

    responses = run_all(*(_start_detection_factory(sid, token) for sid, token in sessions))
    assert all(r.status_code == 200 and r.json()["success"] for r in responses)

    workspaces = [Path(collection_module._JOBS[sid]["workspace"]) for sid, _ in sessions]
    assert workspaces[0] != workspaces[1], "两个会话必须使用不同工作目录"
    assert all(path.parent == session_root for path in workspaces)

    # 状态互不串台
    statuses = run_all(*(
        (lambda c, sid=sid, token=token: c.get(
            f"/api/collection/session/{sid}/detection/status",
            headers={"X-Client-Session": sid, "X-Client-Session-Token": token},
        ))
        for sid, token in sessions
    ))
    assert all(r.status_code == 200 for r in statuses)
    # 每个会话的检测任务号都嵌入自己的会话前缀，说明状态没有串台
    assert all(r.json()["taskId"].startswith(sid[:8]) for r, (sid, _) in zip(statuses, sessions))

    collection_module.reset_collection_session_state()


def test_collection_rejects_duplicate_and_enforces_capacity(monkeypatch, tmp_path):
    _prepare_collection(monkeypatch, tmp_path, max_jobs=2)
    sessions = _create_collection_sessions(3)

    first_two = sessions[:2]
    accepted = run_all(*(_start_detection_factory(sid, token) for sid, token in first_two))
    assert all(r.status_code == 200 for r in accepted)

    # 同一会话重复提交 → 409
    duplicate = run_all(_start_detection_factory(*first_two[0]))[0]
    assert duplicate.status_code == 409
    assert "已有检测任务" in duplicate.json()["message"]

    # 已达全局并发上限，第三个会话被拒 → 429
    overflow = run_all(_start_detection_factory(*sessions[2]))[0]
    assert overflow.status_code == 429
    assert overflow.json()["code"] == "DATA_COLLECTION_CAPACITY"

    collection_module.reset_collection_session_state()


def test_collection_blocks_cross_session_download(monkeypatch, tmp_path):
    _prepare_collection(monkeypatch, tmp_path, max_jobs=4)
    sessions = _create_collection_sessions(2)
    run_all(*(_start_detection_factory(sid, token) for sid, token in sessions))

    (sid_a, token_a), (sid_b, token_b) = sessions
    output_dir = Path(collection_module._JOBS[sid_a]["workspace"]) / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.mp4").write_bytes(b"session-a-output")

    stolen = run_all(lambda client: client.get(
        f"/api/collection/session/{sid_a}/outputs/result.mp4?token={token_b}"
    ))[0]
    assert stolen.status_code == 403, "拿别人的 token 不能下载结果"

    owned = run_all(lambda client: client.get(
        f"/api/collection/session/{sid_a}/outputs/result.mp4?token={token_a}"
    ))[0]
    assert owned.status_code == 200

    collection_module.reset_collection_session_state()


def test_collection_stop_and_reset_do_not_hold_lock(monkeypatch, tmp_path):
    """停止/重置检测必须能正常终止子进程并清理工作目录。

    回归点：终止子进程会阻塞（terminate → wait → kill），必须在锁外执行，
    否则会冻结事件循环并让其它会话的采集请求排队。
    """
    session_root = _prepare_collection(monkeypatch, tmp_path, max_jobs=4)
    session_id, token = _create_collection_sessions(1)[0]
    run_all(_start_detection_factory(session_id, token))
    assert session_id in collection_module._JOBS

    stopped = run_all(lambda client: client.post(
        f"/api/collection/session/{session_id}/detection/stop",
        headers={"X-Client-Session": session_id, "X-Client-Session-Token": token},
    ))[0]
    assert stopped.status_code == 200 and stopped.json()["success"] is True
    assert collection_module._JOBS[session_id]["status"] == "stopped"

    workspace = session_root / session_id
    assert workspace.is_dir()

    reset = run_all(lambda client: client.post(
        f"/api/collection/session/{session_id}/detection/reset",
        headers={"X-Client-Session": session_id, "X-Client-Session-Token": token},
    ))[0]
    assert reset.status_code == 200 and reset.json()["success"] is True
    assert session_id not in collection_module._JOBS
    assert not workspace.is_dir()

    collection_module.reset_collection_session_state()


# ---------------------------------------------------------------------------
# 2 + 3. 融合与预测：多会话并发
# ---------------------------------------------------------------------------

def _prepare_fusion(monkeypatch, tmp_path, release, max_jobs=None):
    fusion_module.reset_fusion_runtime_state()
    root = tmp_path / "fusion_sessions"

    def prepare(session_id):
        workspace = root / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "贝叶斯融合_新版.py").write_text("# test", encoding="utf-8")
        return workspace

    def run_task(session_id, task_key, workspace, script_path, cleanup_path=None):
        release.wait(timeout=3)
        fusion_module._set_status(session_id, task_key, running=False, success=True, message="完成", pid=None)

    monkeypatch.setattr(fusion_module, "_prepare_workspace", prepare)
    monkeypatch.setattr(fusion_module, "_run_task", run_task)
    if max_jobs is not None:
        monkeypatch.setattr(fusion_module, "_MAX_CONCURRENT_JOBS", max_jobs)
    return root


def _prepare_prediction(monkeypatch, tmp_path, release, max_jobs=None):
    prediction_module.reset_prediction_runtime_state()
    root = tmp_path / "prediction_sessions"

    def prepare(session_id):
        workspace = root / session_id
        (workspace / "charts").mkdir(parents=True, exist_ok=True)
        (workspace / "predictor.py").write_text("# test", encoding="utf-8")
        return workspace

    def run_task(session_id, task, script_path, script_args, cleanup_path=None):
        release.wait(timeout=3)
        prediction_module._set_session_status(session_id, running=False, success=True, message="完成", pid=None)

    monkeypatch.setattr(prediction_module, "_prepare_workspace", prepare)
    monkeypatch.setattr(prediction_module, "_run_task", run_task)
    if max_jobs is not None:
        monkeypatch.setattr(prediction_module, "_MAX_CONCURRENT_JOBS", max_jobs)
    return root


def test_fusion_and_prediction_run_in_parallel_across_sessions(monkeypatch, tmp_path):
    release = threading.Event()
    _prepare_fusion(monkeypatch, tmp_path, release)
    _prepare_prediction(monkeypatch, tmp_path, release)

    session_a, session_b = "student-session-aaaaaaaa", "student-session-bbbbbbbb"
    responses = run_all(
        make_session_factory("/api/fusion/start", session_a),
        make_session_factory("/api/fusion/start", session_b),
        make_session_factory("/api/prediction/run-prediction", session_a),
        make_session_factory("/api/prediction/run-prediction", session_b),
    )
    assert all(r.status_code == 200 and r.json()["success"] for r in responses)

    assert fusion_module._TASKS[session_a]["fusion"]["running"] is True
    assert fusion_module._TASKS[session_b]["fusion"]["running"] is True
    assert prediction_module._TASKS[session_a]["running"] is True
    assert prediction_module._TASKS[session_b]["running"] is True

    # 各自的重复提交被拒，且不影响别人
    duplicate = run_all(make_session_factory("/api/fusion/start", session_a))[0]
    assert duplicate.json()["success"] is False
    assert prediction_module._TASKS[session_b]["running"] is True

    release.set()
    assert wait_until(lambda: not fusion_module._TASKS[session_a]["fusion"]["running"]
                      and not prediction_module._TASKS[session_a]["running"])


def test_fusion_and_prediction_enforce_own_capacity(monkeypatch, tmp_path):
    release = threading.Event()
    _prepare_fusion(monkeypatch, tmp_path, release, max_jobs=2)
    _prepare_prediction(monkeypatch, tmp_path, release, max_jobs=2)

    fusion_sessions = ["student-fusion-aaaaaaaa", "student-fusion-bbbbbbbb", "student-fusion-cccccccc"]
    accepted = run_all(*(make_session_factory("/api/fusion/start", sid) for sid in fusion_sessions[:2]))
    assert all(r.json()["success"] for r in accepted)

    overflow = run_all(make_session_factory("/api/fusion/start", fusion_sessions[2]))[0]
    # 与数据采集保持一致：并发上限统一返回 429 + code
    assert overflow.status_code == 429
    assert overflow.json()["code"] == "FUSION_CAPACITY"

    # 预测的额度与融合相互独立：融合打满不影响预测
    prediction_ok = run_all(make_session_factory("/api/prediction/run-prediction", "student-predict-aaaaaaaa"))[0]
    assert prediction_ok.status_code == 200 and prediction_ok.json()["success"] is True

    release.set()


# ---------------------------------------------------------------------------
# 4. 同一会话内跨模块并行
# ---------------------------------------------------------------------------

def test_same_session_runs_fusion_and_prediction_simultaneously(monkeypatch, tmp_path):
    release = threading.Event()
    _prepare_fusion(monkeypatch, tmp_path, release)
    _prepare_prediction(monkeypatch, tmp_path, release)

    session = "student-session-shared0001"
    responses = run_all(
        make_session_factory("/api/fusion/start", session),
        make_session_factory("/api/prediction/run-prediction", session),
    )
    assert all(r.status_code == 200 and r.json()["success"] for r in responses), \
        "同一学生的不同模块必须可以并行，各自的运行状态互不阻塞"

    assert fusion_module._TASKS[session]["fusion"]["running"] is True
    assert prediction_module._TASKS[session]["running"] is True

    # 状态查询互不干扰
    fusion_status, prediction_status = run_all(
        lambda c: c.get("/api/fusion/status", headers={"X-Client-Session": session}),
        lambda c: c.get("/api/prediction/status", headers={"X-Client-Session": session}),
    )
    assert fusion_status.json()["tasks"]["fusion"]["running"] is True
    assert prediction_status.json()["running"] is True

    release.set()
    assert wait_until(lambda: not fusion_module._TASKS[session]["fusion"]["running"])


# ---------------------------------------------------------------------------
# 5. 三模块同时并发（学生真实课堂场景）
# ---------------------------------------------------------------------------

def test_three_modules_run_concurrently_for_two_students(monkeypatch, tmp_path):
    release = threading.Event()
    _prepare_collection(monkeypatch, tmp_path, max_jobs=4)
    _prepare_fusion(monkeypatch, tmp_path, release)
    _prepare_prediction(monkeypatch, tmp_path, release)

    # 采集走真实会话语义，先建立两个采集会话
    collection_sessions = _create_collection_sessions(2)

    factories = []
    for sid, token in collection_sessions:
        factories.append(_start_detection_factory(sid, token))
    for session in ("student-matrix-aaaaaaaa", "student-matrix-bbbbbbbb"):
        factories.append(make_session_factory("/api/fusion/start", session))
        factories.append(make_session_factory("/api/prediction/run-prediction", session))

    responses = run_all(*factories)
    assert all(r.status_code == 200 and r.json()["success"] for r in responses), \
        "两个学生同时使用三个模块，六个任务必须全部受理"

    # 各模块只登记自己的会话，互不污染
    assert set(fusion_module._TASKS) == {"student-matrix-aaaaaaaa", "student-matrix-bbbbbbbb"}
    assert set(prediction_module._TASKS) == {"student-matrix-aaaaaaaa", "student-matrix-bbbbbbbb"}
    assert set(collection_module._JOBS) == {sid for sid, _ in collection_sessions}

    # 采集结果目录与算法会话目录完全分离
    collection_root = collection_module._SESSION_ROOT
    fusion_root = fusion_module._RUNTIME_ROOT
    prediction_root = prediction_module._RUNTIME_ROOT
    assert collection_root != fusion_root != prediction_root
    assert all(Path(job["workspace"]).parent == collection_root for job in collection_module._JOBS.values())

    release.set()
    collection_module.reset_collection_session_state()


# ---------------------------------------------------------------------------
# 6. reset 只影响自己的会话
# ---------------------------------------------------------------------------

def test_reset_only_affects_own_session(monkeypatch, tmp_path):
    release = threading.Event()
    _prepare_fusion(monkeypatch, tmp_path, release)

    session_a, session_b = "student-reset-aaaaaaaaaa", "student-reset-bbbbbbbbbb"
    run_all(
        make_session_factory("/api/fusion/start", session_a),
        make_session_factory("/api/fusion/start", session_b),
    )
    assert fusion_module._TASKS[session_a]["fusion"]["running"] is True
    assert fusion_module._TASKS[session_b]["fusion"]["running"] is True

    reset = run_all(make_session_factory("/api/fusion/reset", session_a))[0]
    assert reset.json()["success"] is True
    assert fusion_module._TASKS[session_a]["fusion"]["running"] is False
    assert fusion_module._TASKS[session_b]["fusion"]["running"] is True, "重置不能影响其他学生"

    release.set()
