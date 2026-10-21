"""交通流预测会话运行路由。

算法目录保持只读；每个浏览器会话在 runtime 下使用独立副本运行，避免并发任务覆盖状态、
自定义代码、图表和结果文件。
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from ..client_session import client_session_id
from ..paths import ALGORITHMS_DIR
from ..runtime_exec import build_script_command


router = APIRouter(prefix="/api/prediction", tags=["交通流预测"])

_SOURCE_DIR = Path(ALGORITHMS_DIR) / "traffic_prediction"
_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "traffic_prediction_sessions"
_MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("ZXK_PREDICTION_MAX_CONCURRENT_JOBS", "4")))
_SESSION_TTL_SECONDS = max(3600, int(os.environ.get("ZXK_PREDICTION_SESSION_TTL", str(24 * 3600))))
_LOCK = threading.RLock()
_TASKS: dict[str, dict] = {}
_PROCESSES: dict[str, subprocess.Popen] = {}
_LAST_SEEN: dict[str, float] = {}

_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _new_status() -> dict:
    return {"running": False, "task": None, "success": None, "message": "未运行"}


def _session_status(session_id: str) -> dict:
    with _LOCK:
        _LAST_SEEN[session_id] = time.time()
        return _TASKS.setdefault(session_id, _new_status())


def _set_session_status(session_id: str, **values) -> None:
    with _LOCK:
        _session_status(session_id).update(values)


def _process_options(log_handle, cwd: Path) -> dict:
    options = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        options["startupinfo"] = startupinfo
    return options


_WORKSPACE_LOCKS: dict[str, threading.Lock] = {}
_WORKSPACE_LOCKS_GUARD = threading.Lock()


def _workspace_lock(session_id: str) -> threading.Lock:
    with _WORKSPACE_LOCKS_GUARD:
        if len(_WORKSPACE_LOCKS) > 4096:
            _WORKSPACE_LOCKS.clear()
        return _WORKSPACE_LOCKS.setdefault(session_id, threading.Lock())


def _publish_workspace(temporary: Path, workspace: Path) -> None:
    """把准备好的临时目录挂到正式路径。

    Windows 上 os.replace 对目录并非原子操作：目标已存在，或临时目录里还有被杀毒
    /索引进程占用的句柄时会抛 WinError 5。并发首次访问时这会让请求直接 500，
    所以这里重试若干次，仍然失败才向上抛。
    """
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            temporary.replace(workspace)
            return
        except OSError as exc:
            last_error = exc
            if workspace.is_dir():
                return
            time.sleep(0.2 * (attempt + 1))
    if not workspace.is_dir() and last_error is not None:
        raise last_error


def _prepare_workspace(session_id: str) -> Path:
    workspace = _RUNTIME_ROOT / session_id
    if workspace.is_dir():
        (workspace / "charts").mkdir(parents=True, exist_ok=True)
        return workspace

    with _workspace_lock(session_id):
        if workspace.is_dir():
            (workspace / "charts").mkdir(parents=True, exist_ok=True)
            return workspace

        temporary = _RUNTIME_ROOT / f".{session_id}.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copytree(
                _SOURCE_DIR,
                temporary,
                ignore=shutil.ignore_patterns("charts", "__pycache__", "tests", "student_pack"),
            )
            (temporary / "charts").mkdir(parents=True, exist_ok=True)
            try:
                _publish_workspace(temporary, workspace)
            except OSError:
                if not workspace.is_dir():
                    raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
    return workspace


def _cleanup_stale_sessions() -> None:
    cutoff = time.time() - _SESSION_TTL_SECONDS
    with _LOCK:
        stale = [
            session_id
            for session_id, touched in _LAST_SEEN.items()
            if touched < cutoff and not (_PROCESSES.get(session_id) and _PROCESSES[session_id].poll() is None)
        ]
        for session_id in stale:
            _TASKS.pop(session_id, None)
            _LAST_SEEN.pop(session_id, None)
            _PROCESSES.pop(session_id, None)
    for session_id in stale:
        shutil.rmtree(_RUNTIME_ROOT / session_id, ignore_errors=True)


def _run_task(
    session_id: str,
    task: str,
    script_path: Path,
    script_args: list[str],
    cleanup_path: Path | None = None,
) -> None:
    workspace = script_path.parent
    if task != "custom":
        workspace = script_path.parent
    charts_dir = workspace / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    log_path = charts_dir / f"prediction_{task}.log"
    process = None
    started = time.time()
    try:
        command, env = build_script_command(str(script_path), cwd=str(workspace), script_args=script_args)
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write(f'\n[{datetime.now().isoformat()}] RUN {" ".join(command)}\n')
            log.flush()
            process = subprocess.Popen(command, env=env, **_process_options(log, workspace))
            with _LOCK:
                _PROCESSES[session_id] = process
                _session_status(session_id).update(pid=process.pid, message="运行中")
            returncode = process.wait()
        if returncode != 0:
            raise RuntimeError(f"后台进程退出码 {returncode}，请查看 {log_path.name}")
        elapsed = time.time() - started
        _set_session_status(
            session_id,
            running=False,
            success=True,
            message=f"任务完成（耗时{elapsed:.0f}秒）",
            pid=None,
        )
    except Exception as exc:
        _set_session_status(session_id, running=False, success=False, message=str(exc), pid=None)
    finally:
        with _LOCK:
            if _PROCESSES.get(session_id) is process:
                _PROCESSES.pop(session_id, None)
        if cleanup_path is not None:
            cleanup_path.unlink(missing_ok=True)


def _submit_task(
    session_id: str,
    task: str,
    script_path: Path,
    script_args: list[str] | None = None,
    cleanup_path: Path | None = None,
) -> dict | JSONResponse:
    if not script_path.is_file():
        return {"success": False, "message": f"{script_path.name}不存在"}

    _cleanup_stale_sessions()
    with _LOCK:
        status = _session_status(session_id)
        if status["running"]:
            return {"success": False, "message": "当前会话已有任务在运行，请等待完成"}
        active_count = sum(1 for value in _TASKS.values() if value.get("running"))
        if active_count >= _MAX_CONCURRENT_JOBS:
            # 与数据采集、多源数据融合保持一致：并发上限统一返回 429。
            return JSONResponse(
                {
                    "success": False,
                    "code": "PREDICTION_CAPACITY",
                    "message": "交通流预测已达到并发上限，请稍后重试",
                },
                status_code=429,
            )
        status.update(running=True, task=task, success=None, message="正在启动服务器后台任务", pid=None)

    threading.Thread(
        target=_run_task,
        args=(session_id, task, script_path, list(script_args or []), cleanup_path),
        daemon=True,
        name=f"traffic-prediction-{session_id[:8]}",
    ).start()
    return {
        "success": True,
        "message": "已提交到服务器后台运行",
        "async": True,
        "session_id": session_id,
    }


def _workspace_for_request(request: Request) -> tuple[str, Path]:
    session_id = client_session_id(request)
    workspace = _prepare_workspace(session_id)
    with _LOCK:
        _LAST_SEEN[session_id] = time.time()
    return session_id, workspace


def _read_key_value_file(path: Path) -> dict:
    result = {}
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                result[key] = value
    return result


@router.post("/train-model")
async def train_model(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _submit_task(session_id, "train", workspace / "predictor.py", ["--model", str(body.get("model", "all"))])


@router.post("/run-prediction")
async def run_prediction(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    return _submit_task(session_id, "predict", workspace / "predictor.py", ["--model", str(body.get("model", "all"))])


@router.post("/run-custom-algorithm")
async def run_custom_algorithm(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    try:
        body = await request.json()
        code = body.get("code", "")
    except Exception:
        return {"success": False, "message": "请求格式错误"}
    if not isinstance(code, str) or not code.strip():
        return {"success": False, "message": "代码不能为空"}

    script_path = workspace / f"custom_algorithm_{uuid.uuid4().hex}.py"
    try:
        script_path.write_text(code, encoding="utf-8")
    except OSError as exc:
        return {"success": False, "message": f"写入临时脚本失败: {exc}"}
    result = _submit_task(session_id, "custom", script_path, cleanup_path=script_path)
    # 达到并发上限时 _submit_task 返回的是 JSONResponse(429) 而不是 dict。
    if isinstance(result, dict) and not result.get("success"):
        script_path.unlink(missing_ok=True)
    return result


@router.post("/reset")
async def reset_prediction(request: Request):
    session_id = client_session_id(request)
    with _LOCK:
        process = _PROCESSES.get(session_id)
        if process and process.poll() is None:
            process.terminate()
        _TASKS[session_id] = _new_status()
        _TASKS[session_id]["message"] = "已重置"
        _LAST_SEEN[session_id] = time.time()
    return {"success": True, "message": "当前会话状态已重置", "session_id": session_id}


@router.get("/status")
async def prediction_status(request: Request):
    session_id = client_session_id(request)
    with _LOCK:
        return {**dict(_session_status(session_id)), "session_id": session_id}


@router.get("/get-results")
async def get_prediction_results(request: Request):
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    path = workspace / "charts" / "results.txt"
    if not path.is_file():
        return {"success": False, "message": "当前会话没有预测结果，请先运行预测"}
    try:
        return {"success": True, "data": _read_key_value_file(path)}
    except OSError as exc:
        return {"success": False, "message": str(exc)}


@router.get("/get-custom-results")
async def get_custom_results(request: Request):
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    path = workspace / "charts" / "custom_results.txt"
    if not path.is_file():
        return {"success": False, "message": "当前会话没有自定义算法结果，请先运行"}
    try:
        return {"success": True, "data": _read_key_value_file(path)}
    except OSError as exc:
        return {"success": False, "message": str(exc)}


@router.get("/download-report")
async def download_report(request: Request):
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    path = workspace / "charts" / "实验报告.txt"
    if path.is_file():
        return FileResponse(path, filename="交通流预测实验报告.txt")
    return JSONResponse({"error": "当前会话没有实验报告，请先运行预测"}, status_code=404)


@router.get("/download-data")
async def download_data():
    path = _SOURCE_DIR / "Traffic flow data.csv"
    if path.is_file():
        return FileResponse(path, filename="Traffic_flow_data.csv")
    return JSONResponse({"error": "数据文件不存在"}, status_code=404)


@router.get("/charts/{filename}")
async def get_chart(request: Request, filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        return JSONResponse({"error": "图表名称无效"}, status_code=400)
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    candidates = (workspace / "charts" / safe_name, workspace / safe_name)
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        return JSONResponse({"error": f"当前会话图表不存在: {safe_name}"}, status_code=404)
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type)


def reset_prediction_runtime_state() -> None:
    with _LOCK:
        processes = list(_PROCESSES.values())
        _PROCESSES.clear()
        _TASKS.clear()
        _LAST_SEEN.clear()
    for process in processes:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
