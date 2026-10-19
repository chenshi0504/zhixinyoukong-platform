"""
仿真工具 API。

提供服务器侧 SUMO / NetEdit / DTALite / CARLA 安装检测、启动和仿真文件上传能力。
浏览器只能访问服务器接口，不能直接扫描或启动访问端电脑上的本地软件。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import logging
import threading
import time
import uuid
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ..paths import ALGORITHMS_DIR, PROJECT_ROOT, UPLOADS_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/simulators", tags=["仿真器状态"])


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

SIMULATOR_UPLOAD_ROOT = os.path.join(UPLOADS_DIR, "simulator_files")
ALLOWED_SIM_FILE_SUFFIXES = (
    ".sumocfg",
    ".net.xml",
    ".rou.xml",
    ".add.xml",
    ".poly.xml",
    ".view.xml",
    ".netccfg",
    ".xml",
    ".json",
    ".xodr",
    ".osm",
    ".csv",
    ".txt",
    ".py",
    ".zip",
)
CONFIG_CANDIDATE_SUFFIXES = (
    ".sumocfg",
    ".net.xml",
    ".rou.xml",
    ".add.xml",
    ".poly.xml",
    ".netccfg",
    ".xodr",
    ".json",
    ".xml",
)
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
STATUS_CACHE_TTL_SECONDS = 30.0
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE_BUILD_LOCK = threading.Lock()
_STATUS_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}


class LaunchRequest(BaseModel):
    """Request body for server-side simulator launch."""

    upload_id: str | None = Field(default=None, description="上传批次 ID")
    file_id: str | None = Field(default=None, description="上传批次中的文件名")
    config_path: str | None = Field(default=None, description="服务器上的配置文件路径")
    args: list[str] = Field(default_factory=list, description="追加命令行参数")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_process_running(name_fragment: str) -> bool:
    """检查是否有匹配名称片段的进程正在运行（Windows only）。"""
    try:
        result = subprocess.run(
            ['tasklist', '/FI', f'IMAGENAME eq {name_fragment}', '/NH'],
            capture_output=True, text=True, timeout=1.5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return name_fragment.lower() in result.stdout.lower()
    except Exception:
        return False


def _server_process_kwargs(cwd: str | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "cwd": cwd or PROJECT_ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _dedupe_existing(paths: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if not path:
            continue
        normalized = os.path.abspath(os.path.expandvars(path))
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(normalized):
            result.append(normalized)
    return result


def _sumo_bin_candidates() -> list[str]:
    candidates: list[str] = []
    sumo_home = os.environ.get("SUMO_HOME", "").strip().strip('"').rstrip(";")
    if sumo_home:
        candidates.append(os.path.join(sumo_home, "bin"))

    candidates.extend(
        [
            os.path.join(PROJECT_ROOT, "software", "SUMO", "bin"),
            os.path.join(PROJECT_ROOT, "tools", "sumo", "bin"),
            r"C:\Program Files (x86)\Eclipse\Sumo\bin",
            r"C:\Program Files\Eclipse\Sumo\bin",
            r"D:\SUMO\bin",
            r"D:\software\SUMO\bin",
            r"D:\Download\SUMO\bin",
        ]
    )
    return candidates


def _find_executable(tool: str) -> str | None:
    """Resolve a known simulator executable on the server."""
    tool_key = tool.lower()
    env = os.environ
    candidates: list[str | None] = []

    if tool_key in {"sumo", "sumo-gui", "netedit"}:
        exe_name = f"{tool_key}.exe" if os.name == "nt" else tool_key
        candidates.append(shutil.which(tool_key))
        candidates.extend(os.path.join(bin_dir, exe_name) for bin_dir in _sumo_bin_candidates())
    elif tool_key == "dtalite":
        exe_name = "DTALite.exe" if os.name == "nt" else "DTALite"
        candidates.append(shutil.which("DTALite"))
        candidates.append(os.path.join(ALGORITHMS_DIR, "traffic_reconstruction", "dtalite", exe_name))
        candidates.append(os.path.join(PROJECT_ROOT, "backend", "algorithms", "traffic_reconstruction", "dtalite", exe_name))
    elif tool_key == "nexta":
        exe_name = "NEXTA.exe" if os.name == "nt" else "NEXTA"
        candidates.append(shutil.which("NEXTA"))
        candidates.append(os.path.join(ALGORITHMS_DIR, "traffic_reconstruction", "dtalite", exe_name))
    elif tool_key == "carla":
        carla_root = env.get("CARLA_ROOT", "").strip().strip('"').rstrip(";")
        common_roots = [
            carla_root,
            os.path.join(PROJECT_ROOT, "software", "CARLA"),
            os.path.join(PROJECT_ROOT, "software", "CARLA_0.9.16"),
            r"D:\CARLA",
            r"D:\CARLA_0.9.16",
            r"D:\software\CARLA",
        ]
        for root in common_roots:
            if not root:
                continue
            candidates.extend(
                [
                    os.path.join(root, "CarlaUE4.exe"),
                    os.path.join(root, "WindowsNoEditor", "CarlaUE4.exe"),
                ]
            )

    resolved = _dedupe_existing(candidates)
    return resolved[0] if resolved else None


def _installed_root(executable: str | None, tool: str) -> str | None:
    if not executable:
        return None
    if tool.lower() in {"sumo", "sumo-gui", "netedit"}:
        return os.path.dirname(os.path.dirname(executable))
    return os.path.dirname(executable)


@lru_cache(maxsize=16)
def _tool_version(executable: str | None) -> str | None:
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        output = (result.stdout or result.stderr or "").strip()
        if not output:
            return None
        first_line = output.splitlines()[0].strip()
        return first_line[:160]
    except Exception:
        return None


def _tool_status(tool: str, display_name: str | None = None, process_names: list[str] | None = None) -> dict:
    executable = _find_executable(tool)
    running = any(_is_process_running(name) for name in (process_names or []))
    return {
        "name": display_name or tool,
        "key": tool,
        "installed": bool(executable),
        "installed_path": _installed_root(executable, tool),
        "executable_path": executable,
        "running": running,
        "version": _tool_version(executable),
    }


def _check_sumo() -> dict:
    """检测 SUMO 安装与运行状态。"""
    sumo_gui = _find_executable("sumo-gui")
    sumo = _find_executable("sumo")
    executable = sumo_gui or sumo
    running = _is_process_running("sumo-gui.exe") or _is_process_running("sumo.exe")
    return {
        "name": "SUMO",
        "key": "sumo",
        "installed": bool(executable),
        "installed_path": _installed_root(executable, "sumo") if executable else None,
        "executable_path": executable,
        "running": running,
        "version": _tool_version(sumo or sumo_gui),
    }


def _check_dtalite() -> dict:
    """检测 DTALite 安装与运行状态。"""
    executable = _find_executable("dtalite")
    running = _is_process_running("DTALite.exe")
    return {
        "name": "DTALite",
        "key": "dtalite",
        "installed": bool(executable),
        "installed_path": _installed_root(executable, "dtalite"),
        "executable_path": executable,
        "running": running,
        "version": _tool_version(executable),
    }


def _check_carla() -> dict:
    """检测 CARLA 安装与运行状态。"""
    executable = _find_executable("carla")
    running = _is_process_running("CarlaUE4.exe") or _is_process_running("CarlaUE4-Win64-Shipping.exe")
    return {
        "name": "CARLA",
        "key": "carla",
        "installed": bool(executable),
        "installed_path": _installed_root(executable, "carla"),
        "executable_path": executable,
        "running": running,
        "version": None,
    }


def _tools_status() -> dict[str, dict]:
    return {
        "sumo": _tool_status("sumo", "SUMO", ["sumo.exe"]),
        "sumo-gui": _tool_status("sumo-gui", "SUMO-GUI", ["sumo-gui.exe"]),
        "netedit": _tool_status("netedit", "NetEdit", ["netedit.exe"]),
        "dtalite": _check_dtalite(),
        "carla": _check_carla(),
    }


def _build_simulators_status_payload() -> dict:
    return {
        "success": True,
        "server_side": True,
        "message": "检测和启动均发生在服务器端；访问端电脑的软件安装状态无法由浏览器直接读取。",
        "simulators": [
            _check_sumo(),
            _check_dtalite(),
            _check_carla(),
        ],
        "tools": _tools_status(),
        "upload": {
            "enabled": True,
            "allowed_extensions": list(ALLOWED_SIM_FILE_SUFFIXES),
            "max_file_size_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
        },
    }


def _get_cached_simulators_status() -> dict:
    now = time.monotonic()
    with _STATUS_CACHE_LOCK:
        cached = _STATUS_CACHE.get("payload")
        if cached is not None and now < float(_STATUS_CACHE.get("expires_at", 0.0)):
            return cached

    # 构建一份完整状态要好几秒。缓存过期时如果每个并发请求各建一份，十几个学生
    # 同时刷新就会互相抢 GIL，实测 12 并发要 17 秒。这里用单独的构建锁做单飞，
    # 保证同一时刻只有一个线程在真正探测，其余请求等它出结果后复用。
    with _STATUS_CACHE_BUILD_LOCK:
        now = time.monotonic()
        with _STATUS_CACHE_LOCK:
            cached = _STATUS_CACHE.get("payload")
            if cached is not None and now < float(_STATUS_CACHE.get("expires_at", 0.0)):
                return cached
        payload = _build_simulators_status_payload()
        with _STATUS_CACHE_LOCK:
            _STATUS_CACHE["payload"] = payload
            _STATUS_CACHE["expires_at"] = time.monotonic() + STATUS_CACHE_TTL_SECONDS
    return payload


def _allowed_filename(filename: str) -> bool:
    lower_name = filename.lower()
    return any(lower_name.endswith(suffix) for suffix in ALLOWED_SIM_FILE_SUFFIXES)


def _classify_file(filename: str) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".sumocfg"):
        return "sumo_config"
    if lower_name.endswith(".net.xml"):
        return "sumo_network"
    if lower_name.endswith(".rou.xml"):
        return "sumo_route"
    if lower_name.endswith((".add.xml", ".poly.xml", ".view.xml", ".xml")):
        return "sumo_related"
    if lower_name.endswith(".xodr"):
        return "opendrive"
    if lower_name.endswith(".json"):
        return "scenario_json"
    if lower_name.endswith(".zip"):
        return "archive"
    return "supporting_file"


def _launchable_with(filename: str) -> list[str]:
    lower_name = filename.lower()
    tools: list[str] = []
    if lower_name.endswith(".sumocfg"):
        tools.append("sumo-gui")
    if lower_name.endswith((".net.xml", ".sumocfg", ".netccfg", ".xml", ".osm")):
        tools.append("netedit")
    if lower_name.endswith((".xodr", ".json")):
        tools.append("carla")
    return tools


def _safe_filename(filename: str) -> str:
    base_name = os.path.basename(filename).strip().replace("\\", "_").replace("/", "_")
    base_name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base_name)
    return base_name[:160] or f"file_{uuid.uuid4().hex[:8]}"


def _is_within(child: str, parent: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(child), os.path.abspath(parent)]) == os.path.abspath(parent)
    except ValueError:
        return False


def _file_payload(path: str, upload_dir: str | None = None) -> dict:
    filename = os.path.basename(path)
    return {
        "file_id": filename,
        "filename": filename,
        "server_path": path,
        "relative_path": os.path.relpath(path, upload_dir) if upload_dir else filename,
        "size": os.path.getsize(path),
        "role": _classify_file(filename),
        "launchable_with": _launchable_with(filename),
    }


def _resolve_uploaded_file(upload_id: str | None, file_id: str | None) -> str | None:
    if not upload_id or not file_id:
        return None
    upload_dir = os.path.abspath(os.path.join(SIMULATOR_UPLOAD_ROOT, _safe_filename(upload_id)))
    candidate = os.path.abspath(os.path.join(upload_dir, _safe_filename(file_id)))
    if not _is_within(candidate, upload_dir) or not os.path.isfile(candidate):
        return None
    return candidate


def _resolve_launch_file(payload: LaunchRequest) -> str | None:
    uploaded = _resolve_uploaded_file(payload.upload_id, payload.file_id)
    if uploaded:
        return uploaded

    if not payload.config_path:
        return None

    candidate = os.path.abspath(os.path.expandvars(payload.config_path))
    allowed_roots = [
        SIMULATOR_UPLOAD_ROOT,
        os.path.join(PROJECT_ROOT, "backend", "algorithms"),
        os.path.join(PROJECT_ROOT, "backend", "uploads"),
    ]
    if not any(_is_within(candidate, root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="配置文件路径不在允许的服务器目录内")
    if not os.path.isfile(candidate):
        raise HTTPException(status_code=404, detail="配置文件不存在")
    return candidate


def _launch_command(tool: str, payload: LaunchRequest) -> tuple[list[str], str | None, str]:
    tool_key = tool.lower()
    aliases = {"sumogui": "sumo-gui", "sumo_gui": "sumo-gui"}
    tool_key = aliases.get(tool_key, tool_key)

    if tool_key not in {"sumo-gui", "netedit", "carla"}:
        raise HTTPException(status_code=400, detail="仅支持启动 SUMO-GUI、NetEdit 和 CARLA")

    executable = _find_executable(tool_key)
    if not executable:
        raise HTTPException(status_code=409, detail=f"服务器未检测到 {tool_key} 安装路径")

    selected_file = _resolve_launch_file(payload)
    args = [arg for arg in payload.args if isinstance(arg, str) and arg.strip()]

    if tool_key == "sumo-gui":
        command = [executable]
        if selected_file:
            if not selected_file.lower().endswith(".sumocfg"):
                raise HTTPException(status_code=400, detail="SUMO-GUI 启动需要 .sumocfg 配置文件")
            command.extend(["-c", selected_file])
        command.extend(args)
    elif tool_key == "netedit":
        command = [executable]
        if selected_file:
            command.append(selected_file)
        command.extend(args)
    else:
        command = [executable]
        command.extend(args)

    cwd = os.path.dirname(selected_file) if selected_file else os.path.dirname(executable)
    return command, cwd, selected_file or ""


def _safe_extract_zip(zip_path: str, target_dir: str) -> list[str]:
    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            inner_name = _safe_filename(os.path.basename(info.filename))
            if not inner_name or not _allowed_filename(inner_name) or inner_name.lower().endswith(".zip"):
                continue
            output_path = os.path.abspath(os.path.join(target_dir, inner_name))
            if not _is_within(output_path, target_dir):
                continue
            with archive.open(info) as source, open(output_path, "wb") as target:
                shutil.copyfileobj(source, target)
            extracted.append(output_path)
    return extracted


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_simulators_status():
    return await run_in_threadpool(_get_cached_simulators_status)
    """返回所有仿真器的安装与运行状态。"""
    return {
        "success": True,
        "server_side": True,
        "message": "检测和启动均发生在服务器端；访问端电脑的软件安装状态无法由浏览器直接读取。",
        "simulators": [
            _check_sumo(),
            _check_dtalite(),
            _check_carla(),
        ],
        "tools": _tools_status(),
        "upload": {
            "enabled": True,
            "allowed_extensions": list(ALLOWED_SIM_FILE_SUFFIXES),
            "max_file_size_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
        },
    }


@router.get("/{name}/status")
async def get_simulator_status(name: str):
    """返回单个仿真器的状态。"""
    checkers = {
        "sumo": _check_sumo,
        "sumo-gui": lambda: _tool_status("sumo-gui", "SUMO-GUI", ["sumo-gui.exe"]),
        "sumogui": lambda: _tool_status("sumo-gui", "SUMO-GUI", ["sumo-gui.exe"]),
        "netedit": lambda: _tool_status("netedit", "NetEdit", ["netedit.exe"]),
        "dtalite": _check_dtalite,
        "carla": _check_carla,
    }
    checker = checkers.get(name.lower())
    if not checker:
        return {"success": False, "message": f"未知仿真器: {name}"}
    simulator = await run_in_threadpool(checker)
    return {"success": True, "server_side": True, "simulator": simulator}


@router.post("/{name}/launch")
async def launch_simulator(name: str, payload: LaunchRequest | None = None):
    """在服务器上启动仿真工具。"""
    payload = payload or LaunchRequest()
    command, cwd, selected_file = _launch_command(name, payload)
    try:
        proc = subprocess.Popen(command, **_server_process_kwargs(cwd))
    except Exception as exc:
        logger.exception("Failed to launch simulator %s", name)
        raise HTTPException(status_code=500, detail=f"启动失败: {exc}") from exc

    return {
        "success": True,
        "server_side": True,
        "tool": name,
        "pid": proc.pid,
        "selected_file": selected_file or None,
        "message": "已向服务器发出启动命令；GUI 会出现在服务器桌面或服务器会话中，不会出现在访问端浏览器电脑上。",
    }


@router.post("/uploads")
async def upload_simulator_files(files: list[UploadFile] = File(...)):
    """上传学生自定义仿真配置文件到服务器。"""
    if not files:
        raise HTTPException(status_code=400, detail="未收到上传文件")

    upload_id = time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
    upload_dir = os.path.abspath(os.path.join(SIMULATOR_UPLOAD_ROOT, upload_id))
    os.makedirs(upload_dir, exist_ok=True)

    saved_paths: list[str] = []
    rejected: list[dict] = []
    total_bytes = 0

    for upload in files:
        original_name = upload.filename or "unnamed"
        filename = _safe_filename(original_name)
        if not _allowed_filename(filename):
            rejected.append({"filename": original_name, "reason": "文件类型不支持"})
            continue

        output_path = os.path.abspath(os.path.join(upload_dir, filename))
        if not _is_within(output_path, upload_dir):
            rejected.append({"filename": original_name, "reason": "文件名不安全"})
            continue

        written = 0
        with open(output_path, "wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                total_bytes += len(chunk)
                if written > MAX_UPLOAD_BYTES or total_bytes > MAX_UPLOAD_BYTES:
                    handle.close()
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                    raise HTTPException(status_code=413, detail="上传文件总量超过限制")
                handle.write(chunk)

        saved_paths.append(output_path)
        if filename.lower().endswith(".zip"):
            try:
                saved_paths.extend(_safe_extract_zip(output_path, upload_dir))
            except zipfile.BadZipFile:
                rejected.append({"filename": original_name, "reason": "ZIP 文件无法解压"})

    if not saved_paths:
        raise HTTPException(status_code=400, detail={"message": "没有可用的仿真文件", "rejected": rejected})

    file_payloads = [_file_payload(path, upload_dir) for path in saved_paths if os.path.isfile(path)]
    config_candidates = [
        item for item in file_payloads
        if any(item["filename"].lower().endswith(suffix) for suffix in CONFIG_CANDIDATE_SUFFIXES)
    ]

    return {
        "success": True,
        "upload_id": upload_id,
        "server_side": True,
        "message": "文件已上传到服务器，可选择 .sumocfg 启动 SUMO-GUI，或选择 .net.xml 使用 NetEdit 编辑。",
        "files": file_payloads,
        "config_candidates": config_candidates,
        "rejected": rejected,
    }
