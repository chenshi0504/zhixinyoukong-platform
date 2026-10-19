"""CARLA-SUMO scene construction API for the teaching platform."""
from __future__ import annotations

import csv
import json
import math
import os
import urllib.request
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ..paths import ALGORITHMS_DIR, PROJECT_ROOT, algo_output_dir, resolve_external_project_root

router = APIRouter(prefix="/api/carla-sim", tags=["CARLA-SUMO联合仿真"])

SCENARIO_ROOT = Path(ALGORITHMS_DIR) / "carla_cosim_scenarios"
OUTPUT_DIR = Path(algo_output_dir("carla_cosim_scenarios", "output"))
# VIC-Sim 根目录：环境变量优先，其次是平台根目录下的 VIC-Sim 子目录，
# 最后回退到开发机上的历史路径，保证本地启动学生端能正常跳转。
VIC_SIM_ROOT = Path(resolve_external_project_root(
    "VIC-Sim",
    "VIC_SIM_ROOT",
    legacy_default=r"D:\chenshi\VIC-Sim",
    marker=os.path.join("backend", "server.py"),
))
NATIVE_VIC_SIM_HOST = os.environ.get("NATIVE_VIC_SIM_HOST", "127.0.0.1")
NATIVE_VIC_SIM_PORT = int(os.environ.get("NATIVE_VIC_SIM_PORT", "8090"))
NATIVE_VIC_SIM_URL = os.environ.get("NATIVE_VIC_SIM_URL", f"http://{NATIVE_VIC_SIM_HOST}:{NATIVE_VIC_SIM_PORT}")
NATIVE_VIC_SIM_LOG = OUTPUT_DIR / "native_vic_sim_server.log"


def _scenario_path(*parts: str) -> str:
    return str((SCENARIO_ROOT.joinpath(*parts)).resolve())


SCENARIOS: dict[str, dict[str, Any]] = {
    "hil_town05": {
        "id": "hil_town05",
        "name": "HIL协同仿真（Town05）",
        "subtitle": "VIC-Sim HIL闭环 · Town05 · CARLA-SUMO联合仿真",
        "scene_type": "hil_cosim",
        "carla_map": "Town05",
        "sumo_config": _scenario_path("hil_town05", "hil_town05.sumocfg"),
        "sumo_net": _scenario_path("hil_town05", "hil_town05.net.xml"),
        "route_file": _scenario_path("hil_town05", "hil_town05.rou.xml"),
        "vic_config": _scenario_path("hil_town05", "hil_town05_vic.yaml"),
        "trace_a": _scenario_path("hil_town05", "virtual_gps_trace.json"),
        "trace_b": _scenario_path("hil_town05", "virtual_gps_trace_b.json"),
        "default_route": "hil_ego",
        "default_speed": 10.0,
        "step_length": 0.05,
        "source": "D:\\chenshi\\VIC-Sim\\scenarios\\hil_town05",
        "entry": "python -m vic_sim hil-cosim-loop --town Town05 --sumo-cfg hil_town05.sumocfg --sumo-gui",
        "logic": [
            "CARLA侧加载Town05城市路网，提供三维道路、交通参与者和传感器视角。",
            "SUMO侧使用VIC-Sim的hil_town05网络，HIL车辆通过本地桥接端口19876同步到CARLA。",
            "虚拟GPS轨迹A/B驱动硬件在环闭环，支持路线切换与控制指令回灌。",
        ],
        "objectives": ["理解HIL闭环数据链路", "观察SUMO-CARLA车辆映射", "分析GPS轨迹与三维视角同步"],
        "resources": [
            "hil_town05.net.xml",
            "hil_town05.rou.xml",
            "hil_town05.sumocfg",
            "hil_town05_vic.yaml",
            "virtual_gps_trace.json",
            "virtual_gps_trace_b.json",
        ],
    },
    "campus_school": {
        "id": "campus_school",
        "name": "校园底图联合仿真",
        "subtitle": "校园SUMO底图 · school.xodr · CARLA-SUMO同步展示",
        "scene_type": "sumo_carla_cosim",
        "carla_map": "school.xodr",
        "sumo_config": _scenario_path("campus_school", "school.sumocfg"),
        "sumo_net": _scenario_path("campus_school", "school.net.xml"),
        "route_file": _scenario_path("campus_school", "school.rou.xml"),
        "xodr": _scenario_path("campus_school", "school.xodr"),
        "default_route": "econ_loop",
        "default_speed": 5.0,
        "step_length": 0.05,
        "source": "平台校园路网 + 历史SUMO-CARLA协同仿真资料",
        "entry": "run_sumo_carla_cosim.py --xodr school.xodr --sumo-cfg school.sumocfg --sumo-gui",
        "logic": [
            "SUMO侧加载校园school.sumocfg，使用校园环线econ_loop表达车辆运行路径。",
            "CARLA侧优先加载school.xodr生成校园OpenDRIVE世界，再由CARLA官方SUMO同步脚本完成车辆映射。",
            "前端展示SUMO平面路网和CARLA三维视窗，便于课堂说明底图、路由和同步关系。",
        ],
        "objectives": ["掌握校园底图联合仿真", "理解OpenDRIVE与SUMO路网关系", "观察车辆在平面/三维视角中的同步"],
        "resources": [
            "school.net.xml",
            "school.rou.xml",
            "school.sumocfg",
            "school.poly.xml",
            "school.view.xml",
            "school.xodr",
        ],
    },
}

_processes: dict[str, subprocess.Popen] = {}
_state: dict[str, Any] = {
    "status": "idle",
    "scene_id": None,
    "scene_name": None,
    "started_at": None,
    "step": 0,
    "total_steps": 120,
    "demo": True,
    "process_key": None,
    "message": "就绪",
    "logs": [],
    "trajectory": [],
    "last_outputs": [],
}

_native_processes: dict[str, subprocess.Popen] = {}
_native_start_lock = threading.Lock()


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(message: str, level: str = "info") -> None:
    _state.setdefault("logs", []).append({"time": _now(), "level": level, "message": message})
    _state["logs"] = _state["logs"][-240:]


def _is_process_running(image_name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return image_name.lower() in (result.stdout or "").lower()
    except Exception:
        return False


def _dedupe_existing(paths: list[str | Path | None], file_required: bool = True) -> list[Path]:
    seen: set[str] = set()
    resolved: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(str(raw).strip().strip('"')).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if (path.is_file() if file_required else path.is_dir()):
            resolved.append(path)
    return resolved


def _http_ready(url: str, timeout: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 500
    except Exception:
        return False


def _native_vic_sim_status() -> dict[str, Any]:
    index_ready = _http_ready(NATIVE_VIC_SIM_URL)
    api_ready = _http_ready(f"{NATIVE_VIC_SIM_URL}/api/status")
    proc = _native_processes.get("vic-sim")
    managed_pid = proc.pid if proc and proc.poll() is None else None
    running = index_ready or api_ready
    return {
        "url": NATIVE_VIC_SIM_URL,
        "api_url": f"{NATIVE_VIC_SIM_URL}/api/status",
        "root": str(VIC_SIM_ROOT),
        "frontend": str(VIC_SIM_ROOT / "frontend" / "index.html"),
        "server": str(VIC_SIM_ROOT / "backend" / "server.py"),
        "installed": (VIC_SIM_ROOT / "backend" / "server.py").is_file(),
        "running": running,
        "api_ready": api_ready,
        "managed_pid": managed_pid,
        "starting": bool(managed_pid and not running),
        "log": str(NATIVE_VIC_SIM_LOG),
    }


def _launch_native_vic_sim() -> tuple[bool, str, dict[str, Any]]:
    with _native_start_lock:
        status = _native_vic_sim_status()
        if status["running"]:
            return True, "VIC-Sim 原生界面已连接", status
        if status.get("managed_pid"):
            return True, "VIC-Sim 正在后台启动，页面可先打开，稍后自动连通", status

        server = VIC_SIM_ROOT / "backend" / "server.py"
        if not server.is_file():
            return False, f"未找到 VIC-Sim 后端入口: {server}", status
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "VIC_SIM_HOST": "0.0.0.0",
            "VIC_SIM_PORT": str(NATIVE_VIC_SIM_PORT),
        }
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        log_handle = NATIVE_VIC_SIM_LOG.open("a", encoding="utf-8", errors="replace")
        try:
            proc = subprocess.Popen(
                [sys.executable, str(server)],
                cwd=str(VIC_SIM_ROOT),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
            )
        except Exception as exc:
            log_handle.close()
            return False, f"启动 VIC-Sim 失败: {exc}", status
        _native_processes["vic-sim"] = proc
        status = _native_vic_sim_status()
        status["managed_pid"] = proc.pid
        status["starting"] = not status["running"]
        return True, "已在后台启动 VIC-Sim，原生页面已打开，稍后自动连接", status


def _find_carla_root() -> Path | None:
    candidates = [
        os.environ.get("CARLA_ROOT"),
        SCENARIO_ROOT / ".." / ".." / ".." / "software" / "CARLA",
        r"D:\carla\CARLA_0.9.15\WindowsNoEditor",
        r"D:\carla\CARLA_0.9.12\WindowsNoEditor",
        r"D:\CARLA_0.9.15\WindowsNoEditor",
        r"D:\CARLA_0.9.12\WindowsNoEditor",
    ]
    for root in _dedupe_existing(candidates, file_required=False):
        if (root / "CarlaUE4.exe").is_file():
            return root
    return None


def _find_carla_exe() -> Path | None:
    root = _find_carla_root()
    return root / "CarlaUE4.exe" if root else None


def _find_sumo_home() -> Path | None:
    candidates = [
        os.environ.get("SUMO_HOME"),
        Path(PROJECT_ROOT) / "software" / "SUMO",
        r"D:\Download\SUMO",
        r"D:\SUMO",
        r"C:\Program Files (x86)\Eclipse\Sumo",
        r"C:\Program Files\Eclipse\Sumo",
    ]
    for root in _dedupe_existing(candidates, file_required=False):
        if (root / "bin" / "sumo-gui.exe").is_file() or (root / "bin" / "sumo.exe").is_file():
            return root
    return None


def _find_tool(tool: str) -> Path | None:
    tool_key = tool.lower()
    if tool_key == "carla":
        return _find_carla_exe()
    if tool_key in {"sumo", "sumo-gui", "netedit"}:
        exe = "netedit.exe" if tool_key in {"sumo", "netedit"} else "sumo-gui.exe"
        candidates = [shutil.which(exe.replace(".exe", ""))]
        sumo_home = _find_sumo_home()
        if sumo_home:
            candidates.append(sumo_home / "bin" / exe)
        found = _dedupe_existing(candidates)
        return found[0] if found else None
    if tool_key == "nexta":
        candidates = [
            shutil.which("NEXTA"),
            Path(ALGORITHMS_DIR) / "traffic_reconstruction" / "dtalite" / "NEXTA.exe",
            Path(ALGORITHMS_DIR) / "traffic_reconstruction" / "dtalite" / "DTALite.exe",
        ]
        found = _dedupe_existing(candidates)
        return found[0] if found else None
    return None


def _software_status() -> list[dict[str, Any]]:
    carla_exe = _find_tool("carla")
    netedit = _find_tool("netedit")
    nexta = _find_tool("nexta")
    return [
        {
            "id": "carla",
            "name": "CARLA",
            "installed": bool(carla_exe),
            "path": str(carla_exe.parent) if carla_exe else None,
            "executable": str(carla_exe) if carla_exe else None,
            "running": _is_process_running("CarlaUE4.exe") or _is_process_running("CarlaUE4-Win64-Shipping.exe"),
            "message": "Ready" if carla_exe else "未检测到CARLA_ROOT或CarlaUE4.exe",
        },
        {
            "id": "sumo",
            "name": "NETEDIT (SUMO)",
            "installed": bool(netedit),
            "path": str(netedit.parent.parent) if netedit else None,
            "executable": str(netedit) if netedit else None,
            "running": _is_process_running("netedit.exe") or _is_process_running("sumo-gui.exe"),
            "message": "Ready" if netedit else "未检测到SUMO_HOME或NetEdit",
        },
        {
            "id": "nexta",
            "name": "NEXTA / DTALite",
            "installed": bool(nexta),
            "path": str(nexta.parent) if nexta else None,
            "executable": str(nexta) if nexta else None,
            "running": _is_process_running("NEXTA.exe") or _is_process_running("DTALite.exe"),
            "message": "Ready" if nexta else "未检测到NEXTA/DTALite",
        },
    ]


def _scene_or_404(scene_id: str) -> dict[str, Any]:
    scene = SCENARIOS.get(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"未知场景: {scene_id}")
    return scene


def _public_scene(scene: dict[str, Any]) -> dict[str, Any]:
    required_files = {
        "sumo_config": scene.get("sumo_config"),
        "sumo_net": scene.get("sumo_net"),
        "route_file": scene.get("route_file"),
        "xodr": scene.get("xodr"),
        "trace_a": scene.get("trace_a"),
        "trace_b": scene.get("trace_b"),
        "vic_config": scene.get("vic_config"),
    }
    return {
        **scene,
        "resource_status": {
            key: {"path": value, "exists": bool(value and Path(value).is_file())}
            for key, value in required_files.items()
            if value
        },
        "preview": {
            "sumo": f"/api/carla-sim/scenarios/{scene['id']}/preview/sumo.svg",
            "carla": f"/api/carla-sim/scenarios/{scene['id']}/preview/carla.svg",
            "combined": f"/api/carla-sim/scenarios/{scene['id']}/preview/combined.svg",
        },
    }


def _environment_ready(scene: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if not Path(scene["sumo_config"]).is_file():
        missing.append("SUMO场景配置文件")
    if not _is_carla_server_ready():
        missing.append("CARLA服务端未运行或端口2000不可连接")
    if scene["id"] == "hil_town05":
        if not VIC_SIM_ROOT.is_dir():
            missing.append("VIC-Sim根目录")
        if not _find_sumo_home():
            missing.append("SUMO_HOME")
    else:
        carla_root = _find_carla_root()
        sumo_home = _find_sumo_home()
        if not carla_root:
            missing.append("CARLA安装目录")
        elif not (carla_root / "Co-Simulation" / "Sumo" / "run_synchronization.py").is_file():
            missing.append("CARLA Co-Simulation/Sumo脚本")
        if not sumo_home:
            missing.append("SUMO_HOME")
        if scene.get("xodr") and not Path(scene["xodr"]).is_file():
            missing.append("校园OpenDRIVE文件")
    return not missing, missing


def _is_carla_server_ready(host: str = "127.0.0.1", port: int = 2000, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_carla_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_carla_server_ready():
            return True
        time.sleep(1.0)
    return _is_carla_server_ready()


def _ensure_carla_server(timeout: float = 35.0) -> tuple[bool, str]:
    if _is_carla_server_ready():
        return True, "CARLA服务端已连接。"

    carla_exe = _find_carla_exe()
    if not carla_exe:
        return False, "未检测到CarlaUE4.exe，无法自动启动CARLA服务端。"

    try:
        proc = subprocess.Popen(
            [str(carla_exe), "-quality-level=Low"],
            **_server_process_kwargs(carla_exe.parent, visible=True),
        )
        _processes[f"software:carla:{proc.pid}"] = proc
        _log(f"CARLA服务端未运行，已自动启动 CarlaUE4.exe，PID={proc.pid}。")
    except Exception as exc:
        return False, f"自动启动CARLA失败: {exc}"

    if _wait_for_carla_server(timeout=timeout):
        return True, "CARLA服务端已自动启动并连接。"
    return False, "CARLA已发起启动，但端口2000尚未就绪，本次先进入演示模式。"


@lru_cache(maxsize=16)
def _read_lanes(net_path: str) -> tuple[list[list[tuple[float, float]]], tuple[float, float, float, float]]:
    lanes: list[list[tuple[float, float]]] = []
    try:
        root = ET.parse(net_path).getroot()
    except Exception:
        return [], (0.0, 0.0, 100.0, 100.0)

    boundary = (0.0, 0.0, 100.0, 100.0)
    location = root.find("location")
    if location is not None and location.get("convBoundary"):
        try:
            boundary = tuple(float(x) for x in location.get("convBoundary", "").split(","))  # type: ignore[assignment]
        except Exception:
            boundary = (0.0, 0.0, 100.0, 100.0)

    for edge in root.findall("edge"):
        if edge.get("function") == "internal":
            continue
        for lane in edge.findall("lane"):
            shape = lane.get("shape", "").strip()
            points: list[tuple[float, float]] = []
            for pair in shape.split():
                try:
                    x_text, y_text = pair.split(",")
                    points.append((float(x_text), float(y_text)))
                except ValueError:
                    continue
            if len(points) >= 2:
                lanes.append(points)
    return lanes, boundary  # type: ignore[return-value]


@lru_cache(maxsize=16)
def _trajectory(scene_id: str) -> tuple[dict[str, Any], ...]:
    scene = _scene_or_404(scene_id)
    if scene_id == "hil_town05":
        trace_path = Path(scene["trace_a"])
        if trace_path.is_file():
            raw = json.loads(trace_path.read_text(encoding="utf-8"))
            stride = max(1, len(raw) // 180)
            result = []
            for item in raw[::stride][:220]:
                x = float(item.get("sumo_x", item.get("x", item.get("lon", 0.0))))
                y = float(item.get("sumo_y", item.get("y", item.get("lat", 0.0))))
                result.append(
                    {
                        "x": round(x, 3),
                        "y": round(y, 3),
                        "speed": round(float(item.get("speed", scene["default_speed"])), 2),
                        "heading": round(float(item.get("heading", 0.0)), 1),
                        "edge": "hil_ego",
                        "time": round(float(item.get("sim_time", item.get("step", 0))), 2),
                    }
                )
            return tuple(result)

    lanes, _ = _read_lanes(scene["sumo_net"])
    points: list[tuple[float, float]] = []
    route_edges = _read_route_edges(scene["route_file"], scene["default_route"])
    if route_edges:
        points = _lane_points_for_edges(scene["sumo_net"], route_edges)
    if not points:
        for lane in lanes[:12]:
            points.extend(lane)

    result = []
    for idx, (x, y) in enumerate(points[:180]):
        heading = 0.0
        if idx + 1 < len(points):
            nx, ny = points[idx + 1]
            heading = math.degrees(math.atan2(ny - y, nx - x))
        result.append(
            {
                "x": round(x, 3),
                "y": round(y, 3),
                "speed": scene["default_speed"],
                "heading": round(heading, 1),
                "edge": scene["default_route"],
                "time": round(idx * scene["step_length"], 2),
            }
        )
    return tuple(result)


def _read_route_edges(route_file: str, route_id: str) -> list[str]:
    try:
        root = ET.parse(route_file).getroot()
        for route in root.findall("route"):
            if route.get("id") == route_id:
                return [item for item in route.get("edges", "").split() if item]
    except Exception:
        return []
    return []


def _lane_points_for_edges(net_path: str, edge_ids: list[str]) -> list[tuple[float, float]]:
    try:
        root = ET.parse(net_path).getroot()
    except Exception:
        return []
    edge_set = set(edge_ids)
    points: list[tuple[float, float]] = []
    for edge in root.findall("edge"):
        if edge.get("id") not in edge_set:
            continue
        lane = edge.find("lane")
        if lane is None:
            continue
        for pair in lane.get("shape", "").split():
            try:
                x_text, y_text = pair.split(",")
                points.append((float(x_text), float(y_text)))
            except ValueError:
                continue
    return points


def _scale_points(
    points: list[tuple[float, float]],
    boundary: tuple[float, float, float, float],
    width: int,
    height: int,
    pad: int,
) -> list[tuple[float, float]]:
    min_x, min_y, max_x, max_y = boundary
    if max_x <= min_x or max_y <= min_y:
        xs = [p[0] for p in points] or [0, 100]
        ys = [p[1] for p in points] or [0, 100]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    scale = min((width - pad * 2) / max(max_x - min_x, 1), (height - pad * 2) / max(max_y - min_y, 1))
    return [(pad + (x - min_x) * scale, height - pad - (y - min_y) * scale) for x, y in points]


def _sumo_svg(scene: dict[str, Any]) -> str:
    width, height, pad = 920, 520, 42
    lanes, boundary = _read_lanes(scene["sumo_net"])
    all_points = [point for lane in lanes for point in lane]
    route_edges = _read_route_edges(scene.get("route_file", ""), scene.get("default_route", ""))
    route_points = _lane_points_for_edges(scene["sumo_net"], route_edges)
    trace_points = [(p["x"], p["y"]) for p in _trajectory(scene["id"])]

    lane_markup = []
    for lane in lanes[:420]:
        scaled = _scale_points(lane, boundary, width, height, pad)
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in scaled)
        lane_markup.append(f'<polyline points="{pts}" fill="none" stroke="#9fb3c8" stroke-width="3" stroke-linecap="round"/>')

    route_markup = ""
    if route_points:
        scaled = _scale_points(route_points, boundary, width, height, pad)
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in scaled)
        route_markup = f'<polyline points="{pts}" fill="none" stroke="#22a06b" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'
    elif trace_points:
        scaled = _scale_points(trace_points, boundary, width, height, pad)
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in scaled)
        route_markup = f'<polyline points="{pts}" fill="none" stroke="#22a06b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'

    vehicle_markup = ""
    if trace_points:
        for idx, point in enumerate([trace_points[0], trace_points[len(trace_points) // 2], trace_points[-1]]):
            x, y = _scale_points([point], boundary, width, height, pad)[0]
            fill = "#28a745" if idx == 0 else "#2c5aa0" if idx == 1 else "#dc3545"
            vehicle_markup += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{fill}" stroke="#fff" stroke-width="2"/>'

    count_text = f"{len(lanes)} lanes / {len(route_points) or len(trace_points)} trajectory points"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="{width}" height="{height}" rx="0" fill="#f7fafc"/>
<rect x="14" y="14" width="{width-28}" height="{height-28}" rx="8" fill="#ffffff" stroke="#dbe3ec"/>
<rect x="14" y="14" width="{width-28}" height="38" rx="8" fill="#eef4fb"/>
<text x="34" y="39" font-size="16" font-family="Microsoft YaHei, Arial" fill="#2c5aa0" font-weight="700">SUMO-GUI | {scene['name']}</text>
<text x="{width-34}" y="39" text-anchor="end" font-size="12" font-family="Consolas, monospace" fill="#60758a">{count_text}</text>
<g opacity="0.55">{''.join(lane_markup)}</g>
{route_markup}
{vehicle_markup}
<g transform="translate(34,{height-62})">
  <rect width="262" height="28" rx="4" fill="#ffffff" stroke="#d8e2ef"/>
  <circle cx="16" cy="14" r="6" fill="#22a06b"/><text x="30" y="18" font-size="12" font-family="Microsoft YaHei, Arial" fill="#465a69">路由/轨迹同步</text>
  <circle cx="128" cy="14" r="6" fill="#2c5aa0"/><text x="142" y="18" font-size="12" font-family="Microsoft YaHei, Arial" fill="#465a69">车辆映射</text>
  <circle cx="214" cy="14" r="6" fill="#dc3545"/><text x="228" y="18" font-size="12" font-family="Microsoft YaHei, Arial" fill="#465a69">终点</text>
</g>
</svg>"""


def _carla_svg(scene: dict[str, Any]) -> str:
    width, height = 920, 520
    campus = scene["id"] == "campus_school"
    sky = "#dceeff" if campus else "#d7e7f7"
    ground = "#dfe9df" if campus else "#e7e5df"
    title = "CARLA View | " + ("Campus OpenDRIVE" if campus else "Town05 HIL")
    far_buildings = """
<rect x="72" y="173" width="86" height="94" fill="#c7d2dd"/>
<rect x="186" y="143" width="118" height="124" fill="#b8c7d5"/>
<rect x="642" y="160" width="100" height="107" fill="#c5d0dc"/>
<rect x="770" y="128" width="78" height="139" fill="#b2c3d2"/>
"""
    if campus:
        far_buildings = """
<rect x="86" y="165" width="146" height="94" fill="#d5ddce"/>
<rect x="252" y="145" width="112" height="114" fill="#cad7c4"/>
<rect x="626" y="158" width="170" height="102" fill="#d4dccb"/>
<path d="M90 257 L180 188 L270 257 Z" fill="#b6c9b5"/>
<path d="M622 258 L714 182 L810 258 Z" fill="#b6c9b5"/>
"""
    road_label = "school.xodr + school.sumocfg" if campus else "Town05 + hil_town05.sumocfg"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="{width}" height="{height}" fill="#f7fafc"/>
<rect x="14" y="14" width="{width-28}" height="{height-28}" rx="8" fill="#ffffff" stroke="#dbe3ec"/>
<rect x="14" y="14" width="{width-28}" height="38" rx="8" fill="#eef4fb"/>
<text x="34" y="39" font-size="16" font-family="Microsoft YaHei, Arial" fill="#2c5aa0" font-weight="700">{title}</text>
<text x="{width-34}" y="39" text-anchor="end" font-size="12" font-family="Consolas, monospace" fill="#60758a">{road_label}</text>
<rect x="34" y="66" width="{width-68}" height="400" fill="{sky}"/>
<rect x="34" y="258" width="{width-68}" height="208" fill="{ground}"/>
{far_buildings}
<path d="M390 466 L515 466 L486 258 L424 258 Z" fill="#38414a"/>
<path d="M442 466 L458 258" stroke="#f2f4f5" stroke-width="4" stroke-dasharray="20 18"/>
<path d="M344 466 L408 258" stroke="#627181" stroke-width="6"/>
<path d="M568 466 L500 258" stroke="#627181" stroke-width="6"/>
<path d="M214 466 C318 392 378 312 425 258" fill="none" stroke="#718093" stroke-width="12" stroke-linecap="round"/>
<path d="M706 466 C620 396 548 316 486 258" fill="none" stroke="#718093" stroke-width="12" stroke-linecap="round"/>
<g transform="translate(471 350)">
  <path d="M-34 20 L34 20 L24 -16 L-22 -16 Z" fill="#2c5aa0"/>
  <rect x="-26" y="-24" width="52" height="18" rx="5" fill="#4f8bd6"/>
  <circle cx="-22" cy="24" r="8" fill="#202833"/><circle cx="22" cy="24" r="8" fill="#202833"/>
</g>
<g transform="translate(578 304) scale(.72)">
  <path d="M-34 20 L34 20 L24 -16 L-22 -16 Z" fill="#22a06b"/>
  <rect x="-26" y="-24" width="52" height="18" rx="5" fill="#62c695"/>
  <circle cx="-22" cy="24" r="8" fill="#202833"/><circle cx="22" cy="24" r="8" fill="#202833"/>
</g>
<rect x="54" y="83" width="230" height="76" rx="6" fill="rgba(255,255,255,.88)" stroke="#d6e0ea"/>
<text x="72" y="108" font-size="13" font-family="Microsoft YaHei, Arial" fill="#2c5aa0" font-weight="700">同步状态</text>
<text x="72" y="131" font-size="12" font-family="Microsoft YaHei, Arial" fill="#44515c">SUMO车辆生成 -> CARLA Actor映射</text>
<text x="72" y="150" font-size="12" font-family="Microsoft YaHei, Arial" fill="#44515c">固定步长 {scene['step_length']} s，车辆/信号灯同步</text>
<rect x="684" y="84" width="166" height="30" rx="4" fill="#1f2937"/>
<text x="767" y="104" text-anchor="middle" font-size="12" font-family="Consolas, monospace" fill="#b6f3d1">frame transfer OK</text>
</svg>"""


def _combined_svg(scene: dict[str, Any]) -> str:
    sumo = _sumo_svg(scene)
    carla = _carla_svg(scene)
    return sumo.replace('width="920" height="520"', 'width="920" height="520" data-view="sumo"') if sumo and carla else sumo


def _server_process_kwargs(cwd: Path | None = None, visible: bool = False) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd or PROJECT_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt" and not visible:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    elif os.name != "nt":
        kwargs["start_new_session"] = True
    return kwargs


def _launch_scene_process(scene: dict[str, Any], payload: dict[str, Any]) -> tuple[subprocess.Popen | None, str, list[str]]:
    if payload.get("auto_launch_carla", False) and not _is_carla_server_ready():
        ready, carla_message = _ensure_carla_server()
        _log(carla_message, "info" if ready else "error")

    ready, missing = _environment_ready(scene)
    if not ready:
        return None, "当前服务器缺少真实联调环境，已切换为可交互演示模式。", missing

    use_gui = bool(payload.get("sumo_gui", True))
    step_length = float(payload.get("step_length") or scene["step_length"])

    if scene["id"] == "hil_town05":
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(VIC_SIM_ROOT), env.get("PYTHONPATH", "")]).strip(os.pathsep)
        sumo_home = _find_sumo_home()
        carla_root = _find_carla_root()
        if sumo_home:
            env["SUMO_HOME"] = str(sumo_home)
        if carla_root:
            env["CARLA_ROOT"] = str(carla_root)
        cmd = [
            sys.executable,
            "-m",
            "vic_sim",
            "hil-cosim-loop",
            "--town",
            "Town05",
            "--sumo-cfg",
            scene["sumo_config"],
            "--trace-a",
            scene["trace_a"],
            "--trace-b",
            scene["trace_b"],
            "--step-length",
            str(step_length),
        ]
        if use_gui:
            cmd.append("--sumo-gui")
        proc = subprocess.Popen(cmd, env=env, **_server_process_kwargs(VIC_SIM_ROOT))
        return proc, "已调用VIC-Sim HIL Town05联合仿真入口。", []

    carla_root = _find_carla_root()
    sumo_home = _find_sumo_home()
    assert carla_root is not None and sumo_home is not None
    wrapper = SCENARIO_ROOT / "run_sumo_carla_cosim.py"
    cmd = [
        sys.executable,
        str(wrapper),
        "--carla-root",
        str(carla_root),
        "--sumo-home",
        str(sumo_home),
        "--sumo-cfg",
        scene["sumo_config"],
        "--xodr",
        scene["xodr"],
        "--step-length",
        str(step_length),
        "--spectator-view",
        "third",
        "--follow-first-vehicle",
        "--sync-vehicle-all",
    ]
    if use_gui:
        cmd.append("--sumo-gui")
    proc = subprocess.Popen(cmd, **_server_process_kwargs(SCENARIO_ROOT))
    return proc, "已调用校园OpenDRIVE + CARLA官方SUMO同步入口。", []


def _write_output_files(scene: dict[str, Any], trajectory: tuple[dict[str, Any], ...]) -> list[dict[str, str]]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{scene['id']}_{stamp}"
    csv_path = OUTPUT_DIR / f"{base}_trajectory.csv"
    json_path = OUTPUT_DIR / f"{base}_summary.json"
    sample = list(trajectory[:260])

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "x", "y", "speed", "heading", "edge"])
        writer.writeheader()
        writer.writerows(sample)

    summary = {
        "scene_id": scene["id"],
        "scene_name": scene["name"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "points": len(sample),
        "step_length": scene["step_length"],
        "resources": scene["resources"],
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return [
        {"name": csv_path.name, "path": csv_path.name},
        {"name": json_path.name, "path": json_path.name},
    ]


def _current_status() -> dict[str, Any]:
    if _state["status"] in {"running", "starting"}:
        proc = _processes.get(_state.get("process_key"))
        if proc is not None and proc.poll() is not None:
            _state["status"] = "completed" if proc.returncode == 0 else "error"
            _state["message"] = "真实联合仿真进程已结束。" if proc.returncode == 0 else f"真实联合仿真进程退出码: {proc.returncode}"
            _log(_state["message"], "info" if proc.returncode == 0 else "error")

    elapsed = 0.0
    if _state.get("started_at"):
        elapsed = max(0.0, time.time() - float(_state["started_at"]))

    if _state["status"] == "running" and _state.get("demo"):
        total = int(_state.get("total_steps") or 120)
        step = min(total, max(1, int(elapsed * 6)))
        _state["step"] = step
        if step >= total:
            _state["status"] = "completed"
            _state["message"] = "演示联调流程已完成。"
            _log("演示联调流程已完成，输出轨迹文件可下载。")

    trajectory = _state.get("trajectory") or []
    cav = None
    if trajectory:
        idx = min(len(trajectory) - 1, int(_state.get("step") or 0) % len(trajectory))
        point = trajectory[idx]
        cav = {
            "edge": point.get("edge", "--"),
            "speed": point.get("speed", 0),
            "x": point.get("x", 0),
            "y": point.get("y", 0),
            "heading": point.get("heading", 0),
        }

    return {
        "success": True,
        "status": _state["status"],
        "message": _state.get("message", ""),
        "scene_id": _state.get("scene_id"),
        "scene_name": _state.get("scene_name"),
        "demo": _state.get("demo", True),
        "step": _state.get("step", 0),
        "total_steps": _state.get("total_steps", 120),
        "elapsed": round(elapsed, 1),
        "cav": cav,
    }


@router.get("/health")
async def health():
    missing_by_scene = {scene_id: _environment_ready(scene)[1] for scene_id, scene in SCENARIOS.items()}
    return {
        "status": "ok",
        "service": "carla-sumo-scene-builder",
        "demo_mode": any(bool(missing) for missing in missing_by_scene.values()),
        "scene_count": len(SCENARIOS),
        "scenarios": list(SCENARIOS.keys()),
        "missing": missing_by_scene,
        "software": _software_status(),
        "native": _native_vic_sim_status(),
    }


@router.get("/native/status")
async def native_status():
    return {"success": True, **_native_vic_sim_status()}


@router.post("/native/start")
async def native_start():
    ok, message, status = _launch_native_vic_sim()
    code = 202 if status.get("starting") or not ok else 200
    return JSONResponse({"success": ok, "message": message, **status}, status_code=code)


@router.get("/scenarios")
async def list_scenarios():
    return {"success": True, "scenarios": [_public_scene(scene) for scene in SCENARIOS.values()]}


@router.get("/scenarios/{scene_id}")
async def get_scenario(scene_id: str):
    return {"success": True, "scenario": _public_scene(_scene_or_404(scene_id))}


@router.get("/scenarios/{scene_id}/preview/{view}.svg")
async def scenario_preview(scene_id: str, view: str):
    scene = _scene_or_404(scene_id)
    if view == "sumo":
        svg = _sumo_svg(scene)
    elif view == "carla":
        svg = _carla_svg(scene)
    elif view == "combined":
        svg = _combined_svg(scene)
    else:
        raise HTTPException(status_code=404, detail="预览类型仅支持sumo/carla/combined")
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/scene-preview/{scene_id}/{view}.svg")
async def scenario_preview_alias(scene_id: str, view: str):
    return await scenario_preview(scene_id, view)


@router.post("/start-mqtt")
async def start_sync_channel():
    _state["status"] = "preparing"
    _state["message"] = "同步通道已准备"
    _log("CARLA-SUMO同步通道已准备：车辆、信号灯与时间步将按场景配置同步。")
    return {"success": True, "demo": True, "message": "同步通道已准备"}


@router.post("/start-receiver")
async def start_preview_receiver():
    _log("效果展示传输已启动：前端正在通过预览图接口接收SUMO/CARLA视窗。")
    return {"success": True, "demo": True, "message": "效果展示传输已启动"}


@router.post("/start")
async def start_simulation(request: Request):
    payload = await request.json()
    scene_id = payload.get("scene_id") or payload.get("scenario_id") or "hil_town05"
    scene = _scene_or_404(scene_id)
    mode = (payload.get("mode") or "auto").lower()
    trajectory = _trajectory(scene_id)
    proc = None
    message = ""
    missing: list[str] = []
    demo = mode == "demo"

    if not demo:
        proc, message, missing = _launch_scene_process(scene, payload)
        demo = proc is None

    if proc is not None:
        process_key = f"scene:{scene_id}:{int(time.time())}"
        _processes[process_key] = proc
        _state["process_key"] = process_key
    else:
        _state["process_key"] = None

    _state.update(
        {
            "status": "running",
            "scene_id": scene_id,
            "scene_name": scene["name"],
            "started_at": time.time(),
            "step": 0,
            "total_steps": int(payload.get("total_steps") or 120),
            "demo": demo,
            "message": message or "联合仿真已启动。",
            "trajectory": list(trajectory),
            "last_outputs": _write_output_files(scene, trajectory),
        }
    )
    _log(f"已选择场景：{scene['name']}。")
    _log(f"场景资源：{', '.join(scene['resources'])}。")
    if demo:
        detail = "；缺少：" + "、".join(missing) if missing else ""
        _log("以演示模式运行联合仿真流程" + detail + "。", "info")
    else:
        _log(message or "真实联合仿真进程已启动。")

    return {
        "success": True,
        "scene": _public_scene(scene),
        "demo": demo,
        "pid": proc.pid if proc else None,
        "message": _state["message"],
        "missing": missing,
    }


@router.post("/stop")
async def stop_simulation():
    proc = _processes.get(_state.get("process_key"))
    if proc is not None and proc.poll() is None:
        proc.terminate()
    _state["status"] = "stopped"
    _state["message"] = "仿真已停止"
    _log("仿真已停止。")
    return {"success": True, "message": "仿真已停止"}


@router.get("/status")
async def status():
    return _current_status()


@router.get("/logs")
async def logs():
    return {"success": True, "logs": _state.get("logs", [])}


@router.get("/demo-trajectory")
async def demo_trajectory(scene_id: str = "hil_town05"):
    scene = _scene_or_404(scene_id)
    trajectory = list(_trajectory(scene_id))
    avg_speed = sum(float(p.get("speed", 0)) for p in trajectory) / max(1, len(trajectory))
    duration = len(trajectory) * float(scene.get("step_length", 0.05))
    return {
        "success": True,
        "scene_id": scene_id,
        "trajectory": trajectory,
        "summary": {
            "duration": f"{duration:.1f}s",
            "avg_speed": f"{avg_speed:.2f} m/s",
            "points": len(trajectory),
        },
    }


@router.get("/output-files")
async def output_files():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(OUTPUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "path": path.name,
                "size": f"{stat.st_size / 1024:.1f} KB",
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return {"success": True, "files": files}


@router.get("/download/{file_path:path}")
async def download_output(file_path: str):
    target = (OUTPUT_DIR / file_path).resolve()
    try:
        if os.path.commonpath([str(target), str(OUTPUT_DIR.resolve())]) != str(OUTPUT_DIR.resolve()):
            raise HTTPException(status_code=400, detail="文件路径不合法")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="文件路径不合法") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(target), filename=target.name)


@router.get("/software-status")
async def software_status():
    return {"success": True, "software": _software_status()}


@router.post("/launch-software")
async def launch_software(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    tool_id = (body.get("id") or body.get("software") or "").lower()
    aliases = {"sumo": "netedit", "sumo-gui": "sumo-gui"}
    tool_key = aliases.get(tool_id, tool_id)
    exe = _find_tool(tool_key)
    if not exe:
        return JSONResponse(
            {"success": False, "message": f"服务器未检测到 {tool_id or '软件'} 可执行文件", "software": _software_status()},
            status_code=409,
        )
    args = body.get("args") or []
    if not isinstance(args, list):
        args = []
    try:
        proc = subprocess.Popen([str(exe), *[str(item) for item in args]], **_server_process_kwargs(exe.parent, visible=True))
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"启动失败: {exc}"}, status_code=500)
    _processes[f"software:{tool_id}:{proc.pid}"] = proc
    _log(f"已启动 {tool_id.upper()}，PID={proc.pid}。")
    return {"success": True, "message": f"{tool_id.upper()} 已在服务器侧启动", "pid": proc.pid}


@router.post("/stop-software")
async def stop_software(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    tool_id = (body.get("id") or "").lower()
    names = {
        "carla": ["CarlaUE4.exe", "CarlaUE4-Win64-Shipping.exe"],
        "sumo": ["netedit.exe", "sumo-gui.exe"],
        "nexta": ["NEXTA.exe", "DTALite.exe"],
    }.get(tool_id, [])
    stopped = []
    if os.name == "nt":
        for name in names:
            try:
                subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True, timeout=5)
                stopped.append(name)
            except Exception:
                pass
    _log(f"已发送停止命令：{tool_id}。")
    return {"success": True, "message": f"已发送停止命令: {tool_id}", "stopped": stopped}
