"""多源数据采集会话传输层。

算法脚本和模型保持原样。本模块为每个浏览器会话建立独立工作目录和检测
进程，使局域网学生可以并发使用数据采集功能而不会共享固定帧文件或输出目录。
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse


router = APIRouter(prefix="/api/collection", tags=["数据采集会话"])

_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv"}
_ALGO_DIR = Path(__file__).resolve().parents[2] / "algorithms" / "data_collection"
_DETECTOR_DIR = _ALGO_DIR / "detector"
_DETECTOR_SCRIPT = _DETECTOR_DIR / "yolo11_tracker.py"
_SESSION_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "data_collection_sessions"
_DEFAULT_VIDEO = _DETECTOR_DIR / "data" / "video" / "test1.mp4"
_MAX_UPLOAD_BYTES = max(1, int(os.environ.get("ZXK_COLLECTION_MAX_UPLOAD_MB", "512"))) * 1024 * 1024
_MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("ZXK_COLLECTION_MAX_CONCURRENT_JOBS", "4")))
_SESSION_TTL_SECONDS = max(3600, int(os.environ.get("ZXK_COLLECTION_SESSION_TTL", str(24 * 3600))))
_LOCK = threading.RLock()
_SESSIONS: dict[str, float] = {}
_SESSION_TOKENS: dict[str, str] = {}
_JOBS: dict[str, dict] = {}

_SESSION_ROOT.mkdir(parents=True, exist_ok=True)


def normalize_session_id(value: object) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value if _SESSION_PATTERN.fullmatch(value) else None


def request_session_id(request: Request) -> Optional[str]:
    return normalize_session_id(request.headers.get("X-Client-Session"))


def request_session_token(request: Request) -> str:
    return str(request.headers.get("X-Client-Session-Token") or request.query_params.get("token") or "")


def register_session(session_id: str) -> None:
    with _LOCK:
        _SESSIONS[session_id] = time.time()
        if len(_SESSIONS) > 2048:
            for old_id, _ in sorted(_SESSIONS.items(), key=lambda item: item[1])[:512]:
                _SESSIONS.pop(old_id, None)


def _cleanup_stale_sessions() -> None:
    cutoff = time.time() - _SESSION_TTL_SECONDS
    with _LOCK:
        stale = [sid for sid, touched in _SESSIONS.items() if touched < cutoff and not (_JOBS.get(sid, {}).get("process") and _JOBS[sid]["process"].poll() is None)]
        for sid in stale:
            _SESSIONS.pop(sid, None)
            _SESSION_TOKENS.pop(sid, None)
            _JOBS.pop(sid, None)
    for sid in stale:
        shutil.rmtree(_SESSION_ROOT / sid, ignore_errors=True)


def _stop_process(process) -> None:
    """停止检测子进程，给它短暂收尾时间后再强制结束。"""
    if not process or process.poll() is not None:
        return
    try:
        process.terminate()
        if hasattr(process, "wait"):
            process.wait(timeout=5)
    except Exception:
        try:
            if hasattr(process, "kill") and process.poll() is None:
                process.kill()
                if hasattr(process, "wait"):
                    process.wait(timeout=2)
        except Exception:
            pass


def collection_guard(request: Request):
    """为旧接口记录会话，新接口的资源隔离由本模块的工作目录实现。"""

    session_id = request_session_id(request)
    token = request_session_token(request)
    expected_token = _SESSION_TOKENS.get(session_id or "")
    if session_id and expected_token and token and secrets.compare_digest(token, expected_token):
        register_session(session_id)
    return None


def finish_collection_request(request: Request, response) -> None:
    # 旧版全局数据采集路由保持兼容；会话路由不依赖请求结束钩子。
    return None


def _session_from_request(request: Request, session_id: str, allow_path_only: bool = False) -> str:
    session_id = normalize_session_id(session_id)
    header_id = request_session_id(request)
    token = request_session_token(request)
    expected_token = _SESSION_TOKENS.get(session_id or "")
    if not expected_token or not token or not secrets.compare_digest(token, expected_token):
        raise HTTPException(status_code=403, detail="invalid data collection session token")
    if not session_id or (header_id != session_id and not (allow_path_only and request.method == "GET" and not header_id)):
        raise HTTPException(status_code=403, detail="数据采集会话标识无效")
    register_session(session_id)
    return session_id


def _workspace(session_id: str) -> Path:
    workspace = _SESSION_ROOT / session_id
    (workspace / "detector").mkdir(parents=True, exist_ok=True)
    (workspace / "uploads").mkdir(parents=True, exist_ok=True)
    (workspace / "outputs").mkdir(parents=True, exist_ok=True)
    return workspace


def _job(session_id: str) -> dict:
    with _LOCK:
        return _JOBS.setdefault(session_id, {"status": "idle", "progress": 0})


def _refresh_job(session_id: str) -> dict:
    with _LOCK:
        job = _job(session_id)
        process = job.get("process")
        shared_file = Path(job["workspace"]) / "detector" / "shared_detection_data.json" if job.get("workspace") else None
        if shared_file and shared_file.is_file():
            try:
                shared = json.loads(shared_file.read_text(encoding="utf-8"))
                job.update({key: shared[key] for key in (
                    "status", "progress", "frameNum", "totalFrames", "fps", "objectCount",
                    "carCount", "busCount", "truckCount", "totalCount"
                ) if key in shared})
            except (OSError, ValueError, TypeError):
                pass
        if process is not None:
            returncode = process.poll()
            if returncode is not None and job.get("status") == "running":
                job["status"] = "completed" if returncode == 0 else "error"
                job["progress"] = 100 if returncode == 0 else job.get("progress", 0)
                job["message"] = "检测完成" if returncode == 0 else f"检测进程退出，代码 {returncode}"
        return dict(job)


def _resolve_video(session_id: str, name: object) -> Optional[Path]:
    value = str(name or "test1.mp4")
    candidate = Path(value)
    if candidate.is_absolute():
        allowed = [(_ALGO_DIR / candidate.name).resolve(), (_DETECTOR_DIR / "data" / "video" / candidate.name).resolve()]
        if candidate.resolve() in allowed and candidate.is_file():
            return candidate.resolve()
        return None
    safe_name = Path(value).name
    candidates = [
        _workspace(session_id) / "uploads" / safe_name,
        _ALGO_DIR / safe_name,
        _DETECTOR_DIR / "data" / "video" / safe_name,
        _DETECTOR_DIR / safe_name,
    ]
    for item in candidates:
        if item.is_file() and item.suffix.lower() in _ALLOWED_VIDEO_SUFFIXES:
            return item.resolve()
    return None


def _safe_model(model: object) -> Path:
    name = Path(str(model or "yolo11n.pt")).name
    if Path(name).suffix.lower() != ".pt":
        name = "yolo11n.pt"
    path = (_DETECTOR_DIR / name).resolve()
    if not path.is_file() or path.parent != _DETECTOR_DIR.resolve():
        path = (_DETECTOR_DIR / "yolo11n.pt").resolve()
    return path


def _python_executable() -> str:
    configured = os.environ.get("ZXK_ALGO_PYTHON_EXE", "").strip().strip('"')
    candidates = [configured, r"D:\chenshi\Research\torch_env\python.exe", sys.executable]
    return next((item for item in candidates if item and os.path.isfile(item)), sys.executable)


def _require_session(request: Request, session_id: str) -> str:
    return _session_from_request(request, session_id)


@router.post("/session")
async def create_collection_session(request: Request):
    session_id = request_session_id(request)
    session_token = request_session_token(request)
    if not session_id:
        try:
            body = await request.json()
        except Exception:
            body = {}
        session_id = normalize_session_id(body.get("session_id"))
        session_token = str(body.get("session_token") or session_token)
    existing_token = _SESSION_TOKENS.get(session_id or "")
    if not session_id or not existing_token or not session_token or not secrets.compare_digest(session_token, existing_token):
        session_id = uuid.uuid4().hex
        session_token = secrets.token_urlsafe(32)
        with _LOCK:
            _SESSION_TOKENS[session_id] = session_token
    _cleanup_stale_sessions()
    register_session(session_id)
    _workspace(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "session_token": session_token,
        "busy": False,
        "message": "data collection session established",
    }


@router.get("/session")
async def collection_session_status(request: Request):
    session_id = request_session_id(request)
    if not session_id:
        return JSONResponse({"success": False, "message": "缺少 X-Client-Session 请求头"}, status_code=400)
    _session_from_request(request, session_id)
    job = _refresh_job(session_id)
    return {"success": True, "session_id": session_id, "owns_detection": job.get("status") == "running", "busy": False, "status": job.get("status", "idle")}


@router.get("/session/{session_id}/health")
async def collection_health(request: Request, session_id: str):
    _require_session(request, session_id)
    return {"status": "ok", "service": "vehicle-detection", "session_id": session_id}


@router.get("/session/{session_id}/default-video")
async def default_video_info(request: Request, session_id: str):
    _require_session(request, session_id)
    if _DEFAULT_VIDEO.is_file():
        size = _DEFAULT_VIDEO.stat().st_size
        return {"success": True, "filename": _DEFAULT_VIDEO.name, "size": size, "sizeMB": f"{size / 1024 / 1024:.2f} MB"}
    return {"success": False, "message": "默认视频文件不存在"}


@router.post("/session/{session_id}/use-default-video")
async def use_default_video(request: Request, session_id: str):
    _require_session(request, session_id)
    if not _DEFAULT_VIDEO.is_file():
        return {"success": False, "message": "默认视频文件不存在"}
    return {"success": True, "message": "默认视频已准备就绪", "filename": _DEFAULT_VIDEO.name, "path": str(_DEFAULT_VIDEO), "size": _DEFAULT_VIDEO.stat().st_size}


def _catalog() -> list[dict]:
    path = _ALGO_DIR / "scenario_catalog.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    result = []
    for item in data.get("scenarios", []):
        filename = Path(str(item.get("filename", ""))).name
        video = _ALGO_DIR / filename
        if filename and video.is_file() and video.suffix.lower() in _ALLOWED_VIDEO_SUFFIXES:
            entry = dict(item)
            entry["filename"] = filename
            entry["sizeBytes"] = video.stat().st_size
            entry["sizeMB"] = f"{video.stat().st_size / 1024 / 1024:.2f} MB"
            result.append(entry)
    return result


@router.get("/session/{session_id}/scenarios")
async def list_scenarios(request: Request, session_id: str):
    _require_session(request, session_id)
    scenarios = _catalog()
    return {"success": True, "scenarios": scenarios, "count": len(scenarios)}


@router.post("/session/{session_id}/upload-video")
async def upload_video(request: Request, session_id: str, video: UploadFile = File(...)):
    _require_session(request, session_id)
    filename = Path(os.path.basename(video.filename or "upload.mp4"))
    if filename.suffix.lower() not in _ALLOWED_VIDEO_SUFFIXES:
        return JSONResponse({"success": False, "message": "仅支持 MP4、AVI、MOV、MKV 视频"}, status_code=400)
    destination = _workspace(session_id) / "uploads" / filename.name
    temporary = destination.with_suffix(destination.suffix + ".part")
    size = 0
    try:
        with temporary.open("wb") as output:
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    temporary.unlink(missing_ok=True)
                    return JSONResponse({"success": False, "message": f"视频不能超过 {_MAX_UPLOAD_BYTES // 1024 // 1024} MB"}, status_code=413)
                output.write(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"success": True, "message": "视频上传成功", "filename": filename.name, "path": str(destination), "size": size}


@router.post("/session/{session_id}/detection/start")
async def start_detection(request: Request, session_id: str):
    _require_session(request, session_id)
    try:
        body = await request.json()
    except Exception:
        body = {}
    video_path = _resolve_video(session_id, body.get("video", "test1.mp4"))
    if not video_path:
        return {"success": False, "message": f"视频文件不存在: {body.get('video', 'test1.mp4')}"}

    with _LOCK:
        current = _JOBS.get(session_id)
        if current and current.get("process") and current["process"].poll() is None:
            return JSONResponse({"success": False, "message": "当前会话已有检测任务在运行中"}, status_code=409)
        active_jobs = sum(1 for item in _JOBS.values() if item.get("process") and item["process"].poll() is None)
        if active_jobs >= _MAX_CONCURRENT_JOBS:
            return JSONResponse({"success": False, "code": "DATA_COLLECTION_CAPACITY", "message": "当前数据采集服务已达到并发上限，请稍后再试"}, status_code=429)

        workspace = _workspace(session_id)
        detector_dir = workspace / "detector"
        shutil.copy2(_DETECTOR_SCRIPT, detector_dir / "yolo11_tracker.py")
        output_name = Path(str(body.get("output") or f"{video_path.stem}_output.mp4")).name
        if Path(output_name).suffix.lower() not in _ALLOWED_VIDEO_SUFFIXES:
            output_name = f"{video_path.stem}_output.mp4"
        output_path = workspace / "outputs" / output_name
        log_path = workspace / "detector.log"
        model_path = _safe_model(body.get("model"))
        args = [
            _python_executable(), "-u", str(detector_dir / "yolo11_tracker.py"),
            "--video", str(video_path), "--model", str(model_path),
            "--conf", str(body.get("score", 0.50)), "--iou", str(body.get("iou", 0.45)),
            "--output", str(output_path), "--no-show",
        ]
        log_file = log_path.open("ab")
        try:
            kwargs = {"cwd": str(detector_dir), "stdout": log_file, "stderr": subprocess.STDOUT}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(args, **kwargs)
        finally:
            log_file.close()
        _JOBS[session_id] = {
            "status": "running", "progress": 10, "message": "正在启动检测...",
            "videoName": video_path.name, "outputFile": output_name,
            "startTime": time.strftime("%Y-%m-%d %H:%M:%S"), "workspace": str(workspace),
            "process": process, "taskId": f"{session_id[:8]}-{uuid.uuid4().hex[:12]}",
        }
    return {"success": True, "message": "检测任务已启动", "taskId": _JOBS[session_id]["taskId"], "videoFile": video_path.name, "outputFile": output_name}


@router.post("/session/{session_id}/detection/stop")
async def stop_detection(request: Request, session_id: str):
    _require_session(request, session_id)
    with _LOCK:
        job = _JOBS.get(session_id)
        process = job.get("process") if job else None
    # 终止子进程是阻塞操作（terminate → wait(5) → kill → wait(2)，最长约 7 秒）。
    # 必须在锁外执行：否则既冻结事件循环，又让其它会话的采集请求全部排队。
    if process is not None and process.poll() is None:
        _stop_process(process)
    if job is not None:
        with _LOCK:
            job["status"] = "stopped"
            job["message"] = "已手动停止"
    return {"success": True, "message": "检测任务已停止"}


@router.post("/session/{session_id}/detection/reset")
async def reset_detection(request: Request, session_id: str):
    _require_session(request, session_id)
    with _LOCK:
        job = _JOBS.pop(session_id, None)
        process = job.get("process") if job else None
    # 同上：阻塞的终止操作放在锁外。
    if process is not None and process.poll() is None:
        _stop_process(process)
    # 停止期间学生可能已重新提交检测任务，此时不能再删刚建好的工作目录。
    with _LOCK:
        session_is_idle = session_id not in _JOBS
    if session_is_idle:
        workspace = _SESSION_ROOT / session_id
        if workspace.is_dir():
            shutil.rmtree(workspace, ignore_errors=True)
    return {"success": True, "message": "检测状态已重置"}


@router.get("/session/{session_id}/detection/status")
async def detection_status(request: Request, session_id: str):
    _require_session(request, session_id)
    job = _refresh_job(session_id)
    return {"success": True, "status": job.get("status", "idle"), "progress": job.get("progress", 0), "message": job.get("message", "无正在进行的检测任务"), "videoName": job.get("videoName", ""), "startTime": job.get("startTime", ""), "taskId": job.get("taskId")}


@router.get("/session/{session_id}/detection/frame")
async def detection_frame(request: Request, session_id: str):
    _require_session(request, session_id)
    job = _refresh_job(session_id)
    detector_dir = Path(job["workspace"]) / "detector" if job.get("workspace") else None
    frame = None
    data = {}
    if detector_dir:
        frame_path = detector_dir / "shared_frame.jpg"
        data_path = detector_dir / "shared_detection_data.json"
        if frame_path.is_file() and time.time() - frame_path.stat().st_mtime < 5:
            frame = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        if data_path.is_file():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
    return {"success": True, "frame": frame, **{key: data.get(key, job.get(key, 0)) for key in ("frameNum", "totalFrames", "fps", "objectCount", "carCount", "busCount", "truckCount", "totalCount", "progress")}, "status": data.get("status", job.get("status", "idle"))}


def _session_files(session_id: str):
    workspace = _SESSION_ROOT / session_id
    output_dir = workspace / "outputs"
    if output_dir.is_dir():
        for item in output_dir.iterdir():
            if item.is_file() and item.suffix.lower() in {".mp4", ".avi"}:
                yield item
    detector_dir = workspace / "detector"
    if detector_dir.is_dir():
        for item in detector_dir.iterdir():
            if item.is_file() and item.suffix.lower() == ".txt":
                yield item


@router.get("/session/{session_id}/get-results")
async def get_results(request: Request, session_id: str):
    _require_session(request, session_id)
    results = []
    for item in _session_files(session_id):
        if item.suffix.lower() in {".mp4", ".avi"}:
            results.append({"type": "video", "name": item.name, "path": f"outputs/{item.name}", "size": f"{item.stat().st_size / 1024 / 1024:.2f} MB"})
        else:
            results.append({"type": "statistics", "name": item.name, "path": item.name, "content": item.read_text(encoding="utf-8", errors="replace")})
    return {"success": True, "results": results, "count": len(results)}


@router.get("/session/{session_id}/output-video")
async def output_video_info(request: Request, session_id: str):
    _require_session(request, session_id)
    videos = [item for item in _session_files(session_id) if item.suffix.lower() in {".mp4", ".avi"}]
    videos.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    if not videos:
        return {"success": False, "message": "暂无输出视频", "videoUrl": None}
    item = videos[0]
    token = _SESSION_TOKENS[session_id]
    return {"success": True, "videoUrl": f"/api/collection/session/{session_id}/outputs/{item.name}?token={token}", "videoName": item.name, "videoSize": f"{item.stat().st_size / 1024 / 1024:.2f} MB", "videoTime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.stat().st_mtime)), "allVideos": [{"name": v.name, "size": f"{v.stat().st_size / 1024 / 1024:.2f} MB", "mtime": v.stat().st_mtime} for v in videos]}


@router.get("/session/{session_id}/statistics")
async def statistics(request: Request, session_id: str):
    _require_session(request, session_id)
    job = _refresh_job(session_id)
    counts = {key: int(job.get(key, 0) or 0) for key in ("carCount", "busCount", "truckCount", "totalCount")}
    time_slots = []
    detector_dir = _SESSION_ROOT / session_id / "detector"
    stat_files = sorted(detector_dir.glob("*_yolo11.txt"), key=lambda item: item.stat().st_mtime, reverse=True) if detector_dir.is_dir() else []
    if stat_files:
        try:
            for line in stat_files[0].read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.strip().split()
                if len(parts) >= 6 and parts[0] != "总计":
                    time_slots.append({
                        "period": parts[0], "interval": parts[1],
                        "car": int(parts[2]), "bus": int(parts[3]),
                        "truck": int(parts[4]), "total": int(parts[5]),
                    })
        except (OSError, ValueError):
            time_slots = []
    return {"success": True, **counts, "timeSlots": time_slots}


def _safe_session_file(session_id: str, filename: str, output_only: bool = False) -> Optional[Path]:
    safe = Path(os.path.basename(filename))
    roots = [(_SESSION_ROOT / session_id / "outputs")] if output_only else [
        _SESSION_ROOT / session_id / "outputs",
        _SESSION_ROOT / session_id / "detector",
    ]
    for root in roots:
        path = (root / safe).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file():
            return path
    return None


@router.get("/session/{session_id}/download/{filename}")
async def download_file(request: Request, session_id: str, filename: str):
    _session_from_request(request, session_id, allow_path_only=True)
    path = _safe_session_file(session_id, filename)
    if not path:
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    return FileResponse(path, filename=path.name)


@router.get("/session/{session_id}/outputs/{filename}")
async def serve_output(request: Request, session_id: str, filename: str):
    _session_from_request(request, session_id, allow_path_only=True)
    path = _safe_session_file(session_id, filename, output_only=True)
    if not path:
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    media_type = "video/mp4" if path.suffix.lower() == ".mp4" else "video/x-msvideo" if path.suffix.lower() == ".avi" else "application/octet-stream"
    return FileResponse(path, media_type=media_type)


def reset_collection_session_state() -> None:
    with _LOCK:
        for job in _JOBS.values():
            process = job.get("process")
            if process and process.poll() is None:
                _stop_process(process)
        _JOBS.clear()
        _SESSIONS.clear()
        _SESSION_TOKENS.clear()
