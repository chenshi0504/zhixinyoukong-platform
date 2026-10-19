r"""HIL-style vehicle development and control API.

This router ports the useful runtime behavior from D:\chenshi\HIL into the
teaching platform's FastAPI backend.  It keeps the old /api/vehicle-control
surface for the existing page, while exposing HIL-like map, car, command,
MQTT, road-topology and telemetry endpoints.
"""
from __future__ import annotations

import asyncio
import csv
import json
import math
import os
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from ..paths import FRONTEND_DIR, algo_output_dir

router = APIRouter(prefix="/api/vehicle-control", tags=["车规级HIL智能车辆控制"])
compat_router = APIRouter(prefix="/api", tags=["HIL原生兼容接口"])

HIL_ROOT = Path(os.environ.get("HIL_PROJECT_ROOT", r"D:\chenshi\HIL"))
HIL_MAP_DIR = HIL_ROOT / "frontend" / "public" / "map"
PLATFORM_MAP_DIR = Path(FRONTEND_DIR) / "public" / "map"
OUTPUT_DIR = Path(algo_output_dir("vehicle_dev_control", "output"))
NATIVE_HIL_URL = os.environ.get("NATIVE_HIL_URL", "http://10.8.129.232:5173/%E3%80%81")
NATIVE_HIL_API_URL = os.environ.get("NATIVE_HIL_API_URL", "http://10.8.129.232:5173/api")
NATIVE_HIL_HEALTH_URL = os.environ.get("NATIVE_HIL_HEALTH_URL", "http://10.8.129.232:5173/api/auth/csrf")
NATIVE_HIL_LOG_DIR = HIL_ROOT / ".logs"
NATIVE_HIL_FRONTEND_LOG = NATIVE_HIL_LOG_DIR / "platform-native-frontend.log"
NATIVE_HIL_BACKEND_LOG = NATIVE_HIL_LOG_DIR / "platform-native-backend.log"
NATIVE_HIL_POSTGRES_LOG = NATIVE_HIL_LOG_DIR / "platform-native-postgres.log"

MAP_CODE = "DLUT-SEM-CAMPUS"
NAVIGATION_ROUTE_CODE = "NAVIGATION_WAYPOINTS_LATEST"
SEM_LOOP_ROUTE_CODE = "SEM_10M_BUILDING_LOOP"
HOLD_ROUTE_CODE = "HOLD_POSITION"

DEFAULT_BROKER_URL = os.environ.get("HIL_MQTT_BROKER_URL", "tcp://10.8.129.232:1883")
DEFAULT_CLIENT_ID = os.environ.get("HIL_MQTT_CLIENT_ID", "hil-platform-server")
DEFAULT_TELEMETRY_TOPIC = os.environ.get("HIL_MQTT_TELEMETRY_TOPIC", "agilex/odom/#")
DEFAULT_TOPOLOGY_DISPLAY_TOPIC = os.environ.get(
    "HIL_MQTT_ROAD_TOPOLOGY_DISPLAY_TOPIC", "agilex/road_topology/display/#"
)
DEFAULT_TOPOLOGY_GOAL_TOPIC = os.environ.get(
    "HIL_MQTT_ROAD_TOPOLOGY_GOAL_TOPIC", "agilex/road_topology/goal_node"
)

ANCHOR_LAT = float(os.environ.get("HIL_MQTT_TELEMETRY_ANCHOR_LAT", "38.8841831004763"))
ANCHOR_LON = float(os.environ.get("HIL_MQTT_TELEMETRY_ANCHOR_LON", "121.520019502113"))
LOCAL_ANCHOR_X = float(os.environ.get("HIL_MQTT_TELEMETRY_LOCAL_ANCHOR_X", "41.23796463012695"))
LOCAL_ANCHOR_Y = float(os.environ.get("HIL_MQTT_TELEMETRY_LOCAL_ANCHOR_Y", "-40.61397933959961"))
HEADING_OFFSET_DEG = float(os.environ.get("HIL_MQTT_TELEMETRY_HEADING_OFFSET_DEG", "90.0"))


SEM_OUTER_LOOP = [
    {"name": "SEM-LOOP-NW", "latitude": 38.88553000, "longitude": 121.51942000, "headingDeg": 90.0},
    {"name": "SEM-LOOP-N", "latitude": 38.88552500, "longitude": 121.52027000, "headingDeg": 97.0},
    {"name": "SEM-LOOP-NE", "latitude": 38.88543000, "longitude": 121.52108000, "headingDeg": 177.0},
    {"name": "SEM-LOOP-E", "latitude": 38.88450000, "longitude": 121.52113000, "headingDeg": 185.0},
    {"name": "SEM-LOOP-SE", "latitude": 38.88310000, "longitude": 121.52098000, "headingDeg": 269.0},
    {"name": "SEM-LOOP-S", "latitude": 38.88309000, "longitude": 121.52025000, "headingDeg": 274.0},
    {"name": "SEM-LOOP-SW", "latitude": 38.88313000, "longitude": 121.51946000, "headingDeg": 358.0},
    {"name": "SEM-LOOP-W", "latitude": 38.88446000, "longitude": 121.51940500, "headingDeg": 10.0},
]

_lock = threading.RLock()
_mqtt_client: Any = None
_command_seq = 1
_native_processes: dict[str, subprocess.Popen] = {}
_native_start_lock = threading.Lock()
_native_start_thread: threading.Thread | None = None
_native_start_state: dict[str, Any] = {"starting": False, "message": None, "success": None}

_state: dict[str, Any] = {
    "status": "idle",
    "running": False,
    "started_at": None,
    "last_update": None,
    "duration_s": 300.0,
    "step": 0,
    "step_length": 0.1,
    "distance_m": 0.0,
    "target_speed": 1.2,
    "route_code": SEM_LOOP_ROUTE_CODE,
    "route_mode": "REPLACE_ROUTE",
    "selected_car_id": 1,
    "selected_car_code": "REAL-001",
    "last_motion": None,
    "trajectory": [],
    "commands": [],
    "logs": [],
    "last_outputs": [],
    "last_output_session": None,
    "mqtt": {
        "enabled": False,
        "connected": False,
        "brokerUrl": DEFAULT_BROKER_URL,
        "clientId": DEFAULT_CLIENT_ID,
        "telemetryTopic": DEFAULT_TELEMETRY_TOPIC,
        "displayTopic": DEFAULT_TOPOLOGY_DISPLAY_TOPIC,
        "goalTopic": DEFAULT_TOPOLOGY_GOAL_TOPIC,
        "lastError": None,
        "lastConnectedAt": None,
        "lastMessageAt": None,
        "lastMqttTopic": None,
        "topicCounts": {},
    },
    "road_topology": {
        "messageCount": 0,
        "lastDisplayAt": None,
        "lastMqttTopic": None,
        "lastRosTopic": None,
        "lastMessageType": None,
        "activeGoalNodeId": None,
        "lastGoalAt": None,
        "lastRouteSummary": None,
        "lastOdometry": None,
        "lastRoutePath": None,
    },
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _log(message: str, level: str = "info") -> None:
    _state.setdefault("logs", []).append({"time": _now_iso(), "level": level, "message": message})
    _state["logs"] = _state["logs"][-240:]


def _asset_path(filename: str) -> Path | None:
    safe = Path(filename).name
    candidates = [PLATFORM_MAP_DIR / safe, HIL_MAP_DIR / safe]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _http_ready(url: str, timeout: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 500
    except Exception:
        return False


def _native_hil_is_local() -> bool:
    return any(host in NATIVE_HIL_URL.lower() for host in ("127.0.0.1", "localhost"))


def _native_hil_status() -> dict[str, Any]:
    frontend_ready = _http_ready(NATIVE_HIL_URL)
    backend_ready = _http_ready(NATIVE_HIL_HEALTH_URL)
    fe_proc = _native_processes.get("frontend")
    be_proc = _native_processes.get("backend")
    fe_pid = fe_proc.pid if fe_proc and fe_proc.poll() is None else None
    be_pid = be_proc.pid if be_proc and be_proc.poll() is None else None
    start_snapshot = dict(_native_start_state)
    return {
        "url": NATIVE_HIL_URL,
        "api_url": NATIVE_HIL_API_URL,
        "health_url": NATIVE_HIL_HEALTH_URL,
        "root": str(HIL_ROOT),
        "frontend": str(HIL_ROOT / "frontend"),
        "backend": str(HIL_ROOT / "backend"),
        "installed": (HIL_ROOT / "frontend" / "package.json").is_file(),
        "running": frontend_ready,
        "frontend_ready": frontend_ready,
        "backend_ready": backend_ready,
        "managed_frontend_pid": fe_pid,
        "managed_backend_pid": be_pid,
        "starting": bool(start_snapshot.get("starting") or ((fe_pid or be_pid) and not (frontend_ready and backend_ready))),
        "start_message": start_snapshot.get("message"),
        "start_success": start_snapshot.get("success"),
        "frontend_log": str(NATIVE_HIL_FRONTEND_LOG),
        "backend_log": str(NATIVE_HIL_BACKEND_LOG),
        "postgres_log": str(NATIVE_HIL_POSTGRES_LOG),
    }


def _run_native_hil_script(script_name: str, log_path: Path, timeout: float | None = None) -> subprocess.CompletedProcess | None:
    script = HIL_ROOT / "scripts" / script_name
    if not script.is_file():
        return None
    NATIVE_HIL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with log_path.open("a", encoding="utf-8", errors="replace") as log_handle:
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(HIL_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            timeout=timeout,
            check=False,
        )


def _launch_native_hil_backend() -> tuple[bool, str, dict[str, Any]]:
    status = _native_hil_status()
    if status["backend_ready"]:
        return True, "HIL 原生后端已在运行", status

    postgres_script = HIL_ROOT / "scripts" / "start-local-postgres.ps1"
    if postgres_script.is_file():
        try:
            _run_native_hil_script("start-local-postgres.ps1", NATIVE_HIL_POSTGRES_LOG, timeout=45)
        except subprocess.TimeoutExpired:
            return False, "HIL 本地 PostgreSQL 启动超时", _native_hil_status()
        except Exception as exc:
            return False, f"HIL 本地 PostgreSQL 启动失败: {exc}", _native_hil_status()

    script = HIL_ROOT / "scripts" / "run-backend.ps1"
    if not script.is_file():
        return False, f"未找到 HIL 后端启动脚本: {script}", status

    NATIVE_HIL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    log_handle = NATIVE_HIL_BACKEND_LOG.open("a", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(HIL_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as exc:
        log_handle.close()
        return False, f"启动 HIL 后端失败: {exc}", status

    _native_processes["backend"] = proc
    for _ in range(80):
        time.sleep(0.5)
        status = _native_hil_status()
        if status["backend_ready"]:
            return True, "HIL 原生后端已启动", status
        if proc.poll() is not None:
            return False, "HIL 原生后端启动进程已退出，请查看日志", _native_hil_status()
    return False, "已发起 HIL 后端启动，但端口 8080 暂未就绪", _native_hil_status()


def _launch_native_hil_frontend() -> tuple[bool, str, dict[str, Any]]:
    status = _native_hil_status()
    if status["frontend_ready"]:
        return True, "HIL 原生前端已在运行", status
    script = HIL_ROOT / "scripts" / "run-frontend.ps1"
    if not script.is_file():
        return False, f"未找到 HIL 前端启动脚本: {script}", status
    NATIVE_HIL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    log_handle = NATIVE_HIL_FRONTEND_LOG.open("a", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(HIL_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as exc:
        log_handle.close()
        return False, f"启动 HIL 前端失败: {exc}", status
    _native_processes["frontend"] = proc
    for _ in range(24):
        time.sleep(0.5)
        status = _native_hil_status()
        if status["frontend_ready"]:
            return True, "HIL 原生前端已启动", status
    return False, "已发起 HIL 前端启动，但端口 5173 暂未就绪", _native_hil_status()


def _set_native_start_state(starting: bool, message: str | None = None, success: bool | None = None) -> None:
    _native_start_state.update(
        {
            "starting": starting,
            "message": message,
            "success": success,
            "updated_at": _now_iso(),
        }
    )


def _native_hil_background_start() -> None:
    messages: list[str] = []
    _set_native_start_state(True, "HIL 原生服务正在后台启动", None)
    try:
        backend_ok, backend_message, _ = _launch_native_hil_backend()
        messages.append(backend_message)
        frontend_ok, frontend_message, status = _launch_native_hil_frontend()
        messages.append(frontend_message)
        status = _native_hil_status()
        ok = bool(status["frontend_ready"] and status["backend_ready"])
        if frontend_ok and not backend_ok:
            ok = False
        _set_native_start_state(False, "；".join(messages), ok)
    except Exception as exc:
        _set_native_start_state(False, f"HIL 原生服务后台启动失败: {exc}", False)


def _launch_native_hil_stack() -> tuple[bool, str, dict[str, Any]]:
    if not _native_hil_is_local():
        status = _native_hil_status()
        ok = bool(status["frontend_ready"])
        message = "HIL 原生界面使用远端固定入口，已直接连接" if ok else "HIL 远端固定入口暂不可达"
        return ok, message, status

    status = _native_hil_status()
    if status["frontend_ready"] and status["backend_ready"]:
        return True, "HIL 原生完整服务已连接", status

    global _native_start_thread
    with _native_start_lock:
        if _native_start_thread and _native_start_thread.is_alive():
            status["starting"] = True
            return True, "HIL 原生服务正在后台启动，页面可先打开，稍后自动连通", status
        _native_start_thread = threading.Thread(target=_native_hil_background_start, daemon=True)
        _native_start_thread.start()

    status = _native_hil_status()
    status["starting"] = True
    return True, "已在后台启动 HIL 原生服务，页面已打开，稍后自动连接", status




def _load_json_asset(filename: str, fallback: dict[str, Any]) -> dict[str, Any]:
    path = _asset_path(filename)
    if not path:
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _meters_per_degree_lat(lat: float) -> float:
    lat_rad = math.radians(lat)
    return 111132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)


def _meters_per_degree_lon(lat: float) -> float:
    lat_rad = math.radians(lat)
    return 111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)


def _local_to_wgs84(x: float, y: float) -> tuple[float, float]:
    lat_scale = _meters_per_degree_lat(ANCHOR_LAT)
    lon_scale = _meters_per_degree_lon(ANCHOR_LAT)
    east = x - LOCAL_ANCHOR_X
    north = y - LOCAL_ANCHOR_Y
    return ANCHOR_LAT + north / lat_scale, ANCHOR_LON + east / lon_scale


def _wgs84_to_local(lat: float, lon: float) -> tuple[float, float]:
    x = LOCAL_ANCHOR_X + (lon - ANCHOR_LON) * _meters_per_degree_lon(ANCHOR_LAT)
    y = LOCAL_ANCHOR_Y + (lat - ANCHOR_LAT) * _meters_per_degree_lat(ANCHOR_LAT)
    return x, y


def _distance_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay = float(a.get("x", 0.0)), float(a.get("y", 0.0))
    bx, by = float(b.get("x", 0.0)), float(b.get("y", 0.0))
    if ax or ay or bx or by:
        return math.hypot(bx - ax, by - ay)
    lat_scale = _meters_per_degree_lat(float(a["latitude"]))
    lon_scale = _meters_per_degree_lon(float(a["latitude"]))
    return math.hypot(
        (float(b["longitude"]) - float(a["longitude"])) * lon_scale,
        (float(b["latitude"]) - float(a["latitude"])) * lat_scale,
    )


def _heading_deg(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay = float(a.get("x", 0.0)), float(a.get("y", 0.0))
    bx, by = float(b.get("x", 0.0)), float(b.get("y", 0.0))
    if not (ax or ay or bx or by):
        ax, ay = _wgs84_to_local(float(a["latitude"]), float(a["longitude"]))
        bx, by = _wgs84_to_local(float(b["latitude"]), float(b["longitude"]))
    return (math.degrees(math.atan2(by - ay, bx - ax)) + 360.0) % 360.0


def _fallback_navigation_route() -> dict[str, Any]:
    waypoints = []
    for index, item in enumerate(SEM_OUTER_LOOP):
        x, y = _wgs84_to_local(item["latitude"], item["longitude"])
        waypoints.append(
            {
                "index": index,
                "name": item["name"],
                "x": x,
                "y": y,
                "z": 0,
                "yaw_deg": item["headingDeg"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "display": True,
            }
        )
    return {
        "routeName": "sem_outer_loop_fallback",
        "frameId": "sc_map",
        "loop": True,
        "bidirectionalHeadings": True,
        "visibleWaypointIndices": list(range(len(waypoints))),
        "source": "embedded SEM loop fallback",
        "generatedAt": _now_iso(),
        "transform": {
            "method": "local_xy_to_wgs84_initial_registration",
            "anchorLat": ANCHOR_LAT,
            "anchorLon": ANCHOR_LON,
            "localAnchorX": LOCAL_ANCHOR_X,
            "localAnchorY": LOCAL_ANCHOR_Y,
            "rotationDeg": 0,
            "scale": 1,
        },
        "waypoints": waypoints,
        "topology": {
            "nodeIndexBase": 0,
            "nodes": [{"id": i, "waypoint": wp["name"]} for i, wp in enumerate(waypoints)],
            "undirectedEdges": [[i, (i + 1) % len(waypoints)] for i in range(len(waypoints))],
        },
    }


def _navigation_route() -> dict[str, Any]:
    return _load_json_asset("navigation-waypoints-latest.json", _fallback_navigation_route())


def _pointcloud_layer() -> dict[str, Any]:
    return _load_json_asset(
        "sem-pointcloud-layer.json",
        {
            "mapCode": MAP_CODE,
            "layerCode": "sem-lidar-pointcloud",
            "image": "/api/vehicle-control/assets/sem-pointcloud-layer.png",
            "bounds": {
                "minLat": 38.88271454558923,
                "minLon": 121.51804829050388,
                "maxLat": 38.88565165536337,
                "maxLon": 121.52199071372212,
            },
            "transform": {
                "anchorLat": ANCHOR_LAT,
                "anchorLon": ANCHOR_LON,
                "localAnchorX": LOCAL_ANCHOR_X,
                "localAnchorY": LOCAL_ANCHOR_Y,
            },
        },
    )


def _sem_loop_points() -> list[dict[str, Any]]:
    points = []
    for index, item in enumerate(SEM_OUTER_LOOP):
        x, y = _wgs84_to_local(item["latitude"], item["longitude"])
        points.append(
            {
                "index": index,
                "name": item["name"],
                "x": round(x, 3),
                "y": round(y, 3),
                "z": 0.0,
                "yaw_deg": item["headingDeg"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "display": True,
            }
        )
    return points


def _route_points(route_code: str | None = None) -> list[dict[str, Any]]:
    code = route_code or _state.get("route_code") or SEM_LOOP_ROUTE_CODE
    if code == HOLD_ROUTE_CODE:
        motion = _state.get("last_motion") or _initial_motion()
        return [
            {
                "index": 0,
                "name": "hold_position",
                "x": motion["x"],
                "y": motion["y"],
                "z": 0.0,
                "yaw_deg": motion["headingDeg"],
                "latitude": motion["latitude"],
                "longitude": motion["longitude"],
                "display": True,
            }
        ]
    if code == NAVIGATION_ROUTE_CODE:
        return sorted(_navigation_route().get("waypoints", []), key=lambda item: int(item.get("index", 0)))
    return _sem_loop_points()


def _route_loop(route_code: str | None = None) -> bool:
    return (route_code or _state.get("route_code")) in {SEM_LOOP_ROUTE_CODE}


def _route_total_length(points: list[dict[str, Any]], loop: bool) -> float:
    if len(points) < 2:
        return 0.0
    total = sum(_distance_m(points[i], points[i + 1]) for i in range(len(points) - 1))
    if loop:
        total += _distance_m(points[-1], points[0])
    return total


def _interpolate(points: list[dict[str, Any]], distance_m: float, loop: bool) -> dict[str, Any]:
    if not points:
        return _initial_motion()
    if len(points) == 1:
        point = points[0]
        return _motion_from_point(point, float(point.get("yaw_deg", 0.0)), 0, 0.0)

    total = _route_total_length(points, loop)
    if total <= 0:
        return _motion_from_point(points[0], 0.0, 0, 0.0)
    remaining = distance_m % total if loop else min(distance_m, total)
    segment_count = len(points) if loop else len(points) - 1
    for index in range(segment_count):
        a = points[index]
        b = points[(index + 1) % len(points)]
        length = max(_distance_m(a, b), 0.001)
        if remaining <= length or index == segment_count - 1:
            ratio = max(0.0, min(1.0, remaining / length))
            x = float(a.get("x", 0.0)) + (float(b.get("x", 0.0)) - float(a.get("x", 0.0))) * ratio
            y = float(a.get("y", 0.0)) + (float(b.get("y", 0.0)) - float(a.get("y", 0.0))) * ratio
            if not (x or y):
                ax, ay = _wgs84_to_local(float(a["latitude"]), float(a["longitude"]))
                bx, by = _wgs84_to_local(float(b["latitude"]), float(b["longitude"]))
                x, y = ax + (bx - ax) * ratio, ay + (by - ay) * ratio
            lat = float(a["latitude"]) + (float(b["latitude"]) - float(a["latitude"])) * ratio
            lon = float(a["longitude"]) + (float(b["longitude"]) - float(a["longitude"])) * ratio
            heading = _heading_deg(a, b)
            return {
                "x": round(x, 3),
                "y": round(y, 3),
                "z": 0.0,
                "latitude": round(lat, 8),
                "longitude": round(lon, 8),
                "headingDeg": round(heading, 2),
                "segmentIndex": index,
                "segmentName": f"{a.get('name', index)} -> {b.get('name', (index + 1) % len(points))}",
                "distToNextM": round(max(0.0, length - remaining), 2),
                "routeProgress": round((distance_m % total) / total if loop else distance_m / total, 4),
            }
        remaining -= length
    return _motion_from_point(points[-1], float(points[-1].get("yaw_deg", 0.0)), len(points) - 1, 0.0)


def _motion_from_point(point: dict[str, Any], heading: float, segment_index: int, dist_to_next: float) -> dict[str, Any]:
    x = float(point.get("x", 0.0))
    y = float(point.get("y", 0.0))
    if not (x or y):
        x, y = _wgs84_to_local(float(point["latitude"]), float(point["longitude"]))
    return {
        "x": round(x, 3),
        "y": round(y, 3),
        "z": float(point.get("z", 0.0)),
        "latitude": round(float(point["latitude"]), 8),
        "longitude": round(float(point["longitude"]), 8),
        "headingDeg": round(heading, 2),
        "segmentIndex": segment_index,
        "segmentName": str(point.get("name", "waypoint")),
        "distToNextM": round(dist_to_next, 2),
        "routeProgress": 0.0,
    }


def _initial_motion() -> dict[str, Any]:
    point = _sem_loop_points()[0]
    return _motion_from_point(point, float(point["yaw_deg"]), 0, 0.0)


def _advance_locked() -> None:
    now = time.monotonic()
    if not _state.get("last_update"):
        _state["last_update"] = now
    if _state.get("running"):
        dt = max(0.0, now - float(_state["last_update"]))
        _state["distance_m"] = float(_state.get("distance_m", 0.0)) + float(_state.get("target_speed", 0.0)) * dt
        _state["step"] = int(_state.get("step", 0)) + max(1, int(dt / float(_state.get("step_length", 0.1)))) if dt > 0 else int(_state.get("step", 0))
        _state["last_update"] = now
        if _state.get("started_at") and now - float(_state["started_at"]) >= float(_state.get("duration_s", 300.0)):
            _state["running"] = False
            _state["status"] = "completed"
            _log("HIL闭环实验达到设定时长，已自动结束并生成轨迹文件。")

    points = _route_points(_state.get("route_code"))
    motion = _interpolate(points, float(_state.get("distance_m", 0.0)), _route_loop(_state.get("route_code")))
    motion["speedMps"] = round(float(_state.get("target_speed", 0.0)) if _state.get("running") else 0.0, 3)
    motion["batteryPercent"] = max(12.0, round(96.0 - float(_state.get("distance_m", 0.0)) * 0.003, 1))
    motion["recordedAt"] = _now_iso()
    motion["step"] = int(_state.get("step", 0))
    _state["last_motion"] = motion

    if _state.get("running"):
        trajectory = _state.setdefault("trajectory", [])
        if not trajectory or trajectory[-1].get("step") != motion["step"]:
            trajectory.append(
                {
                    "step": motion["step"],
                    "time": round(motion["step"] * float(_state.get("step_length", 0.1)), 2),
                    "carCode": _state.get("selected_car_code", "REAL-001"),
                    "routeCode": _state.get("route_code"),
                    "x": motion["x"],
                    "y": motion["y"],
                    "latitude": motion["latitude"],
                    "longitude": motion["longitude"],
                    "speedMps": motion["speedMps"],
                    "headingDeg": motion["headingDeg"],
                    "segment": motion["segmentName"],
                    "recordedAt": motion["recordedAt"],
                }
            )
            _state["trajectory"] = trajectory[-800:]

    if _state.get("status") == "completed":
        _write_outputs_locked()


def _route_view(route_code: str) -> dict[str, Any]:
    points = _route_points(route_code)
    loop = _route_loop(route_code)
    coordinates = [{"lat": p["latitude"], "lon": p["longitude"]} for p in points]
    if loop and coordinates:
        coordinates = coordinates + [coordinates[0]]
    return {
        "routeCode": route_code,
        "plannerProfile": "HIL_SERVER_VERIFIED_ROUTE",
        "status": "OK" if points else "UNAVAILABLE",
        "totalLengthM": round(_route_total_length(points, loop), 2),
        "waypointCount": len(points),
        "snappedNodeCount": len(points),
        "edgeCount": len(points) if loop else max(0, len(points) - 1),
        "coordinates": coordinates,
        "snappedWaypoints": [
            {
                "sequence": index + 1,
                "waypointCode": str(point.get("name", f"WP-{index + 1}")),
                "waypointName": str(point.get("name", f"WP-{index + 1}")),
                "originalLat": point["latitude"],
                "originalLon": point["longitude"],
                "snappedLat": point["latitude"],
                "snappedLon": point["longitude"],
                "snapDistanceM": 0,
            }
            for index, point in enumerate(points)
        ],
        "generatedAt": _now_iso(),
    }


def _map_detail() -> dict[str, Any]:
    layer = _pointcloud_layer()
    bounds = layer.get("bounds") or {}
    if not bounds:
        points = _route_points(SEM_LOOP_ROUTE_CODE)
        bounds = {
            "minLat": min(p["latitude"] for p in points),
            "minLon": min(p["longitude"] for p in points),
            "maxLat": max(p["latitude"] for p in points),
            "maxLon": max(p["longitude"] for p in points),
        }
    nav = _navigation_route()
    sem_points = _sem_loop_points()
    return {
        "map": {
            "id": 1,
            "mapCode": MAP_CODE,
            "mapName": "大连理工大学经管学院HIL校园底图",
            "centerLat": (float(bounds["minLat"]) + float(bounds["maxLat"])) / 2,
            "centerLon": (float(bounds["minLon"]) + float(bounds["maxLon"])) / 2,
            "defaultZoom": 18,
            "bbox": bounds,
            "sourceName": "D:\\chenshi\\HIL 点云、导航路点与SUMO校园地图资产",
            "sourceUrl": str(HIL_ROOT),
            "attribution": "HIL project local assets",
            "description": "移植自HIL项目的经管学院真实小车实验地图，包含点云底图、导航路点、外侧环线路径与MQTT通信主题。",
            "areaScope": "DLUT_SEM_HIL_TEST_FIELD",
            "coordinateSystem": "WGS84 + local XY registration",
            "sourceRevision": nav.get("generatedAt"),
            "defaultMap": True,
            "updatedAt": _now_iso(),
        },
        "precisionProfile": {
            "id": 1,
            "profileCode": "DLUT-SEM-HIL-LIDAR-WGS84",
            "horizontalDatum": "WGS84",
            "storageCoordinateSystem": "PLY local XY",
            "renderProjection": "local_xy_to_wgs84_initial_registration",
            "localOriginLat": ANCHOR_LAT,
            "localOriginLon": ANCHOR_LON,
            "metersPerDegreeLat": _meters_per_degree_lat(ANCHOR_LAT),
            "metersPerDegreeLon": _meters_per_degree_lon(ANCHOR_LAT),
            "bboxWidthM": _distance_m(
                {"latitude": bounds["minLat"], "longitude": bounds["minLon"]},
                {"latitude": bounds["minLat"], "longitude": bounds["maxLon"]},
            ),
            "bboxHeightM": _distance_m(
                {"latitude": bounds["minLat"], "longitude": bounds["minLon"]},
                {"latitude": bounds["maxLat"], "longitude": bounds["minLon"]},
            ),
            "displayAspectRatio": 1.2,
            "northUp": True,
            "orthographicTopDown": True,
            "sourceAccuracyClass": "HIL_LIDAR_INITIAL_REGISTRATION",
            "geometryQualityRule": "Use server verified HIL navigation route for command dispatch.",
            "maintenanceNote": "与D:\\chenshi\\HIL\\frontend\\public\\map保持同步。",
            "updatedAt": _now_iso(),
        },
        "roadNetwork": {
            "nodeCount": len(nav.get("waypoints", [])),
            "edgeCount": len(nav.get("topology", {}).get("undirectedEdges", [])),
            "connectorEdgeCount": 0,
            "totalLengthM": _route_view(SEM_LOOP_ROUTE_CODE)["totalLengthM"],
            "updatedAt": nav.get("generatedAt"),
        },
        "layers": [
            {
                "id": 1,
                "layerCode": "sem-lidar-pointcloud",
                "layerName": "SEM点云底图",
                "layerType": "RASTER_POINTCLOUD",
                "visibleByDefault": True,
                "zIndex": 10,
                "minZoom": 16,
                "maxZoom": 22,
                "styleJson": layer,
                "maintenanceNote": "HIL point cloud layer",
            }
        ],
        "features": [
            {
                "id": 1,
                "featureType": "ROAD",
                "layerCode": "sem-loop",
                "osmType": "local",
                "osmId": 1,
                "name": "经管学院10m外侧环线",
                "subtype": "LOCAL_EXPERIMENT_LOOP",
                "geometryType": "LINESTRING",
                "centerLat": sum(p["latitude"] for p in sem_points) / len(sem_points),
                "centerLon": sum(p["longitude"] for p in sem_points) / len(sem_points),
                "coordinates": [{"lat": p["latitude"], "lon": p["longitude"]} for p in sem_points],
                "tags": {"routeCode": SEM_LOOP_ROUTE_CODE, "source": "HIL migration V12/V13"},
                "minZoom": 16,
                "maxZoom": 22,
                "qualityLevel": "SERVER_VERIFIED",
                "sourceUpdatedAt": nav.get("generatedAt"),
            }
        ],
        "waypoints": [
            {
                "id": int(point.get("index", index)) + 1,
                "waypointCode": str(point.get("name", f"WP-{index + 1}")),
                "waypointName": str(point.get("name", f"WP-{index + 1}")),
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "headingDeg": float(point.get("yaw_deg", point.get("headingDeg", 0.0))),
                "sortOrder": index + 1,
                "tags": {"routeEnabled": True, "display": point.get("display", False)},
            }
            for index, point in enumerate(_route_points(NAVIGATION_ROUTE_CODE))
        ],
        "assetStatus": {
            "navigationWaypoints": str(_asset_path("navigation-waypoints-latest.json") or ""),
            "pointcloudLayer": str(_asset_path("sem-pointcloud-layer.json") or ""),
            "pointcloudImage": str(_asset_path("sem-pointcloud-layer.png") or ""),
        },
    }


def _car_view(car_id: int, car_code: str, car_name: str, car_type: str, motion: dict[str, Any]) -> dict[str, Any]:
    mqtt = _state["mqtt"]
    online = bool(_state.get("running")) or bool(mqtt.get("connected")) or car_type == "VIRTUAL"
    return {
        "id": car_id,
        "carCode": car_code,
        "carName": car_name,
        "carType": car_type,
        "ipAddress": "192.168.10.21" if car_type == "REAL" else None,
        "mqttClientId": f"car-{car_code.lower()}",
        "enabled": True,
        "online": online,
        "lifecycleState": "HIL_RUNNING" if _state.get("running") else ("MQTT_ONLINE" if mqtt.get("connected") else "REGISTERED"),
        "batteryPercent": motion.get("batteryPercent", 96.0),
        "speedMps": motion.get("speedMps", 0.0) if car_code == _state.get("selected_car_code") else 0.0,
        "positionX": motion.get("x", 0.0),
        "positionY": motion.get("y", 0.0),
        "headingDeg": motion.get("headingDeg", 0.0),
        "mapCode": MAP_CODE,
        "latitude": motion.get("latitude"),
        "longitude": motion.get("longitude"),
        "accuracyM": 0.35,
        "communicationProtocol": "MQTT" if car_type == "REAL" else "LOCAL_SIM",
        "communicationTopic": f"hil/car/{car_code}/command" if car_type == "REAL" else "local://hil/virtual",
        "lastCommunicationAt": mqtt.get("lastMessageAt") if car_type == "REAL" else motion.get("recordedAt"),
        "lastHeartbeatAt": motion.get("recordedAt") if online else None,
    }


def _cars_locked() -> list[dict[str, Any]]:
    _advance_locked()
    motion = _state.get("last_motion") or _initial_motion()
    odom = _state.get("road_topology", {}).get("lastOdometry")
    if odom and _state.get("selected_car_code") == "REAL-001" and not _state.get("running"):
        motion = {
            **motion,
            "x": odom.get("x", motion["x"]),
            "y": odom.get("y", motion["y"]),
            "latitude": odom.get("latitude", motion["latitude"]),
            "longitude": odom.get("longitude", motion["longitude"]),
            "headingDeg": odom.get("headingDeg", motion["headingDeg"]),
            "speedMps": odom.get("speedMps", motion["speedMps"]),
            "recordedAt": odom.get("recordedAt", motion["recordedAt"]),
        }
    return [
        _car_view(1, "REAL-001", "真实智能小车 001", "REAL", motion),
        _car_view(2, "VIR-001", "虚拟智能小车 001", "VIRTUAL", motion),
    ]


def _summary_locked() -> dict[str, Any]:
    cars = _cars_locked()
    commands = _state.get("commands", [])
    return {
        "totalCars": len(cars),
        "onlineCars": sum(1 for car in cars if car["online"]),
        "realCars": sum(1 for car in cars if car["carType"] == "REAL"),
        "virtualCars": sum(1 for car in cars if car["carType"] == "VIRTUAL"),
        "pendingCommands": sum(1 for command in commands if command.get("status") == "PENDING"),
        "running": bool(_state.get("running")),
        "routeCode": _state.get("route_code"),
        "mqttConnected": bool(_state["mqtt"].get("connected")),
    }


def _command_record(car_id: int, command_type: str, payload: dict[str, Any], accepted: bool, message: str, topic: str) -> dict[str, Any]:
    global _command_seq
    command_id = str(uuid.uuid4())
    now = _now_iso()
    car = next((item for item in _cars_locked() if item["id"] == car_id), _cars_locked()[0])
    record = {
        "id": _command_seq,
        "commandId": command_id,
        "carId": car_id,
        "carCode": car["carCode"],
        "commandType": command_type,
        "payload": json.dumps(payload, ensure_ascii=False),
        "status": "SENT" if accepted else "FAILED",
        "requestedBy": "platform",
        "responsePayload": json.dumps({"transport": "MQTT" if _state["mqtt"].get("connected") else "LOCAL_SIM", "topic": topic}, ensure_ascii=False),
        "errorMessage": None if accepted else message,
        "requestedAt": now,
        "sentAt": now if accepted else None,
        "acknowledgedAt": now if not _state["mqtt"].get("connected") and accepted else None,
        "message": message,
        "topic": topic,
    }
    _command_seq += 1
    _state.setdefault("commands", []).insert(0, record)
    _state["commands"] = _state["commands"][:80]
    return record


def _apply_local_command_locked(command_type: str, payload: dict[str, Any]) -> None:
    upper = command_type.upper()
    action = str(payload.get("action") or "").lower()
    if upper in {"SET_SPEED", "SPEED_CONTROL"} or action == "set_speed":
        speed = float(payload.get("speed", payload.get("targetSpeed", _state.get("target_speed", 1.2))))
        _advance_locked()
        _state["target_speed"] = max(0.0, min(8.0, speed))
        _state["last_update"] = time.monotonic()
        _log(f"已下发速度控制指令：{_state['target_speed']:.2f} m/s。")
    elif upper in {"EMERGENCY_STOP", "STOP"} or action in {"stop", "emergency"}:
        _advance_locked()
        _state["target_speed"] = 0.0
        _state["running"] = False
        _state["status"] = "stopped"
        _write_outputs_locked()
        _log("已执行HIL安全停车指令。", "warning")
    elif upper in {"SET_ROUTE", "ROUTE_FOLLOW", "POINTCLOUD_ROUTE"} or action == "set_route":
        route_code = str(payload.get("routeCode") or payload.get("route") or SEM_LOOP_ROUTE_CODE)
        if route_code not in {NAVIGATION_ROUTE_CODE, SEM_LOOP_ROUTE_CODE, HOLD_ROUTE_CODE}:
            route_code = SEM_LOOP_ROUTE_CODE
        _advance_locked()
        _state["route_code"] = route_code
        _state["route_mode"] = str(payload.get("routeMode") or "REPLACE_ROUTE")
        _state["distance_m"] = 0.0 if _state["route_mode"] == "REPLACE_ROUTE" else float(_state.get("distance_m", 0.0))
        _state["last_update"] = time.monotonic()
        _log(f"已切换HIL路径：{route_code}。")
    elif upper == "TOPOLOGY_GOAL_NODE":
        _state["road_topology"]["activeGoalNodeId"] = int(payload.get("nodeId", 0))
        _state["road_topology"]["lastGoalAt"] = _now_iso()
        _log(f"已记录道路拓扑目标节点：{_state['road_topology']['activeGoalNodeId']}。")


def _parse_broker(url: str) -> tuple[str, int]:
    value = url.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    if "/" in value:
        value = value.split("/", 1)[0]
    if ":" in value:
        host, port = value.rsplit(":", 1)
        return host, int(port)
    return value, 1883


def _mqtt_env_enabled() -> bool:
    return os.environ.get("HIL_MQTT_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def _start_mqtt_bridge(force: bool = False) -> dict[str, Any]:
    global _mqtt_client
    with _lock:
        mqtt_state = _state["mqtt"]
        mqtt_state["enabled"] = bool(force or _mqtt_env_enabled())
        mqtt_state["brokerUrl"] = os.environ.get("HIL_MQTT_BROKER_URL", DEFAULT_BROKER_URL)
        mqtt_state["clientId"] = os.environ.get("HIL_MQTT_CLIENT_ID", DEFAULT_CLIENT_ID)

    if not (force or _mqtt_env_enabled()):
        with _lock:
            mqtt_state["connected"] = False
            mqtt_state["lastError"] = "HIL_MQTT_ENABLED is not true; local HIL bridge is active."
            _log("MQTT未启用，已使用平台本地HIL闭环通道。")
            return {"connected": False, "mode": "local", "message": "已启用本地HIL闭环通道"}

    broker_url = _state["mqtt"]["brokerUrl"]
    host, port = _parse_broker(broker_url)
    try:
        with socket.create_connection((host, port), timeout=1.2):
            pass
    except OSError as exc:
        with _lock:
            _state["mqtt"]["connected"] = False
            _state["mqtt"]["lastError"] = f"MQTT broker unreachable: {exc}"
            _log(f"MQTT broker不可达，保持本地HIL通道：{exc}", "warning")
        return {"connected": False, "mode": "local", "message": str(exc)}

    try:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(client_id=f"{_state['mqtt']['clientId']}-python-bridge")
        username = os.environ.get("HIL_MQTT_USERNAME", "")
        password = os.environ.get("HIL_MQTT_PASSWORD", "")
        if username:
            client.username_pw_set(username, password or None)

        def on_connect(client_obj: Any, _userdata: Any, _flags: Any, rc: int) -> None:
            with _lock:
                _state["mqtt"]["connected"] = rc == 0
                _state["mqtt"]["lastConnectedAt"] = _now_iso() if rc == 0 else None
                _state["mqtt"]["lastError"] = None if rc == 0 else f"MQTT connect rc={rc}"
                if rc == 0:
                    _log(f"MQTT桥接已连接：{broker_url}。")
            if rc == 0:
                client_obj.subscribe(DEFAULT_TELEMETRY_TOPIC, qos=1)
                client_obj.subscribe(DEFAULT_TOPOLOGY_DISPLAY_TOPIC, qos=1)

        def on_disconnect(_client_obj: Any, _userdata: Any, rc: int) -> None:
            with _lock:
                _state["mqtt"]["connected"] = False
                if rc:
                    _state["mqtt"]["lastError"] = f"MQTT disconnected rc={rc}"

        def on_message(_client_obj: Any, _userdata: Any, msg: Any) -> None:
            _handle_mqtt_message(msg.topic, bytes(msg.payload))

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.connect(host, port, keepalive=30)
        client.loop_start()
        with _lock:
            _mqtt_client = client
        return {"connected": True, "mode": "mqtt", "message": "MQTT bridge connecting"}
    except Exception as exc:
        with _lock:
            _state["mqtt"]["connected"] = False
            _state["mqtt"]["lastError"] = str(exc)
            _log(f"MQTT桥接启动失败，保持本地HIL通道：{exc}", "warning")
        return {"connected": False, "mode": "local", "message": str(exc)}


def _handle_mqtt_message(topic: str, payload: bytes) -> None:
    text = payload.decode("utf-8", errors="replace")
    received_at = _now_iso()
    try:
        root = json.loads(text)
    except Exception:
        root = {"raw": text}

    with _lock:
        mqtt_state = _state["mqtt"]
        mqtt_state["lastMessageAt"] = received_at
        mqtt_state["lastMqttTopic"] = topic
        mqtt_state["topicCounts"][topic] = int(mqtt_state["topicCounts"].get(topic, 0)) + 1
        topo = _state["road_topology"]
        topo["messageCount"] = int(topo.get("messageCount", 0)) + 1
        topo["lastDisplayAt"] = received_at
        topo["lastMqttTopic"] = topic

        odom = _extract_odometry(root, topic, received_at)
        if odom:
            topo["lastOdometry"] = odom
            topo["lastMessageType"] = "nav_msgs/Odometry"
            topo["lastRouteSummary"] = f"里程计 {odom['x']:.2f},{odom['y']:.2f} speed={odom['speedMps']:.2f}m/s"
        path = _extract_path(root, topic, received_at)
        if path:
            topo["lastRoutePath"] = path
            topo["lastMessageType"] = "nav_msgs/Path"
            topo["lastRouteSummary"] = f"道路拓扑路径 {path['pointCount']} points"


def _extract_odometry(root: Any, topic: str, received_at: str) -> dict[str, Any] | None:
    if not isinstance(root, dict):
        return None
    pose = root.get("pose", {})
    if isinstance(pose.get("pose"), dict):
        pose = pose.get("pose", {})
    position = pose.get("position", {}) if isinstance(pose, dict) else {}
    if not isinstance(position, dict) or "x" not in position:
        return None
    orientation = pose.get("orientation", {}) if isinstance(pose, dict) else {}
    twist = root.get("twist", {})
    if isinstance(twist.get("twist"), dict):
        twist = twist.get("twist", {})
    linear = twist.get("linear", {}) if isinstance(twist, dict) else {}
    x = float(position.get("x", 0.0))
    y = float(position.get("y", 0.0))
    z = float(position.get("z", 0.0))
    yaw = _yaw_deg(
        float(orientation.get("x", 0.0)),
        float(orientation.get("y", 0.0)),
        float(orientation.get("z", 0.0)),
        float(orientation.get("w", 1.0)),
    )
    heading = (HEADING_OFFSET_DEG - yaw) % 360.0
    speed = math.hypot(float(linear.get("x", 0.0)), float(linear.get("y", 0.0)))
    lat, lon = _local_to_wgs84(x, y)
    return {
        "carCode": "REAL-001",
        "rosTopic": topic,
        "x": round(x, 3),
        "y": round(y, 3),
        "z": round(z, 3),
        "latitude": round(lat, 8),
        "longitude": round(lon, 8),
        "headingDeg": round(heading, 2),
        "speedMps": round(speed, 3),
        "recordedAt": received_at,
    }


def _extract_path(root: Any, topic: str, received_at: str) -> dict[str, Any] | None:
    if not isinstance(root, dict):
        return None
    poses = root.get("poses")
    if not isinstance(poses, list):
        return None
    points = []
    for item in poses[:300]:
        pose = item.get("pose", item) if isinstance(item, dict) else {}
        position = pose.get("position", {}) if isinstance(pose, dict) else {}
        if "x" not in position:
            continue
        x, y, z = float(position.get("x", 0)), float(position.get("y", 0)), float(position.get("z", 0))
        lat, lon = _local_to_wgs84(x, y)
        points.append({"x": x, "y": y, "z": z, "latitude": lat, "longitude": lon})
    if not points:
        return None
    return {"rosTopic": topic, "pointCount": len(points), "points": points, "receivedAt": received_at}


def _yaw_deg(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def _publish_mqtt(topic: str, payload: dict[str, Any]) -> tuple[bool, str]:
    client = _mqtt_client
    if not client or not _state["mqtt"].get("connected"):
        return False, "MQTT未连接，命令已进入本地HIL通道"
    try:
        client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=False)
        return True, "Published to MQTT broker"
    except Exception as exc:
        with _lock:
            _state["mqtt"]["connected"] = False
            _state["mqtt"]["lastError"] = str(exc)
        return False, str(exc)


def _write_outputs_locked() -> None:
    session_key = f"{_state.get('started_at')}:{len(_state.get('trajectory', []))}:{_state.get('status')}"
    if _state.get("last_output_session") == session_key:
        return
    trajectory = list(_state.get("trajectory", []))
    if not trajectory:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"hil_vehicle_trajectory_{stamp}.csv"
    json_path = OUTPUT_DIR / f"hil_vehicle_summary_{stamp}.json"
    fields = [
        "step",
        "time",
        "carCode",
        "routeCode",
        "x",
        "y",
        "latitude",
        "longitude",
        "speedMps",
        "headingDeg",
        "segment",
        "recordedAt",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in trajectory:
            writer.writerow({field: row.get(field, "") for field in fields})
    summary = {
        "generatedAt": _now_iso(),
        "routeCode": _state.get("route_code"),
        "carCode": _state.get("selected_car_code"),
        "points": len(trajectory),
        "distanceM": round(float(_state.get("distance_m", 0.0)), 2),
        "commands": _state.get("commands", [])[:20],
        "mqtt": _state.get("mqtt", {}),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _state["last_outputs"] = [{"name": csv_path.name, "path": csv_path.name}, {"name": json_path.name, "path": json_path.name}]
    _state["last_output_session"] = session_key


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        return {}


@router.get("/health")
async def health() -> dict[str, Any]:
    nav_path = _asset_path("navigation-waypoints-latest.json")
    layer_path = _asset_path("sem-pointcloud-layer.json")
    image_path = _asset_path("sem-pointcloud-layer.png")
    return {
        "status": "ok",
        "service": "vehicle-hil-control",
        "hilRoot": str(HIL_ROOT),
        "mqtt": _state["mqtt"],
        "assets": {
            "navigationWaypoints": {"path": str(nav_path) if nav_path else None, "exists": bool(nav_path)},
            "pointcloudLayer": {"path": str(layer_path) if layer_path else None, "exists": bool(layer_path)},
            "pointcloudImage": {"path": str(image_path) if image_path else None, "exists": bool(image_path)},
        },
        "routes": [NAVIGATION_ROUTE_CODE, SEM_LOOP_ROUTE_CODE, HOLD_ROUTE_CODE],
        "native": _native_hil_status(),
    }


@router.get("/native/status")
async def native_status() -> dict[str, Any]:
    return {"success": True, **_native_hil_status()}


@router.post("/native/start")
async def native_start() -> JSONResponse:
    ok, message, status = _launch_native_hil_stack()
    code = 202 if status.get("starting") or not ok else 200
    return JSONResponse({"success": ok, "message": message, **status}, status_code=code)


@router.get("/assets/{filename}")
async def asset(filename: str):
    path = _asset_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="HIL资产不存在")
    media_type = "application/json"
    if filename.lower().endswith(".png"):
        media_type = "image/png"
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/navigation-waypoints")
async def navigation_waypoints() -> dict[str, Any]:
    return {"success": True, "route": _navigation_route()}


@router.get("/pointcloud-layer")
async def pointcloud_layer() -> dict[str, Any]:
    layer = _pointcloud_layer()
    layer["image"] = "/api/vehicle-control/assets/sem-pointcloud-layer.png"
    return {"success": True, "layer": layer}


@router.get("/dashboard/summary")
async def dashboard_summary() -> dict[str, Any]:
    with _lock:
        return _summary_locked()


@router.get("/maps")
async def maps() -> list[dict[str, Any]]:
    detail = _map_detail()
    return [detail["map"]]


@router.get("/maps/default")
async def default_map() -> dict[str, Any]:
    return _map_detail()


@router.get("/maps/default/route")
async def default_route() -> dict[str, Any]:
    return _route_view(SEM_LOOP_ROUTE_CODE)


@router.get("/maps/{map_code}")
async def map_detail(map_code: str) -> dict[str, Any]:
    if map_code != MAP_CODE:
        raise HTTPException(status_code=404, detail="地图不存在")
    return _map_detail()


@router.get("/maps/{map_code}/route")
async def map_route(map_code: str, route_code: str = SEM_LOOP_ROUTE_CODE) -> dict[str, Any]:
    if map_code != MAP_CODE:
        raise HTTPException(status_code=404, detail="地图不存在")
    if route_code not in {NAVIGATION_ROUTE_CODE, SEM_LOOP_ROUTE_CODE, HOLD_ROUTE_CODE}:
        raise HTTPException(status_code=404, detail="路径不存在")
    return _route_view(route_code)


@router.get("/cars")
async def cars() -> list[dict[str, Any]]:
    with _lock:
        return _cars_locked()


@router.get("/cars/{car_id}")
async def car_detail(car_id: int) -> dict[str, Any]:
    with _lock:
        car = next((item for item in _cars_locked() if item["id"] == car_id), None)
    if not car:
        raise HTTPException(status_code=404, detail="小车不存在")
    return car


@router.get("/commands/recent")
async def recent_commands(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        return list(_state.get("commands", []))[: max(1, min(limit, 80))]


@router.post("/cars/{car_id}/commands")
async def create_command(car_id: int, request: Request) -> dict[str, Any]:
    body = await _request_json(request)
    command_type = str(body.get("commandType") or body.get("command_type") or body.get("action") or "SET_SPEED")
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {k: v for k, v in body.items() if k != "commandType"}
    with _lock:
        cars_now = _cars_locked()
        car = next((item for item in cars_now if item["id"] == car_id), None)
        if not car:
            raise HTTPException(status_code=404, detail="小车不存在")
        topic = f"hil/car/{car['carCode']}/command"
        mqtt_payload = {
            "commandId": str(uuid.uuid4()),
            "carCode": car["carCode"],
            "commandType": command_type,
            "payload": payload,
            "requestedAt": _now_iso(),
        }
    published, message = _publish_mqtt(topic, mqtt_payload)
    with _lock:
        _apply_local_command_locked(command_type, payload)
        record = _command_record(car_id, command_type, payload, True if published or not _state["mqtt"].get("connected") else False, message, topic)
    return record


@router.get("/road-topology/status")
async def road_topology_status() -> dict[str, Any]:
    with _lock:
        mqtt = dict(_state["mqtt"])
        topo = dict(_state["road_topology"])
        return {
            "mqttEnabled": bool(mqtt.get("enabled")),
            "roadTopologyEnabled": True,
            "connected": bool(mqtt.get("connected")),
            "brokerUrl": mqtt.get("brokerUrl"),
            "displayTopic": mqtt.get("displayTopic"),
            "goalTopic": mqtt.get("goalTopic"),
            "messageCount": topo.get("messageCount", 0),
            "lastDisplayAt": topo.get("lastDisplayAt"),
            "lastMqttTopic": topo.get("lastMqttTopic"),
            "lastRosTopic": topo.get("lastRosTopic"),
            "lastMessageType": topo.get("lastMessageType"),
            "activeGoalNodeId": topo.get("activeGoalNodeId"),
            "lastGoalAt": topo.get("lastGoalAt"),
            "lastRouteSummary": topo.get("lastRouteSummary"),
            "lastOdometry": topo.get("lastOdometry"),
            "lastRoutePath": topo.get("lastRoutePath"),
            "topicCounts": mqtt.get("topicCounts", {}),
        }


@router.post("/road-topology/goal-node")
async def road_topology_goal_node(request: Request) -> dict[str, Any]:
    body = await _request_json(request)
    node_id = int(body.get("nodeId", 0))
    payload = {"node_id": node_id, "requested_at": _now_iso(), "source": "zhixin-platform"}
    published, message = _publish_mqtt(DEFAULT_TOPOLOGY_GOAL_TOPIC, payload)
    with _lock:
        _state["road_topology"]["activeGoalNodeId"] = node_id
        _state["road_topology"]["lastGoalAt"] = _now_iso()
        _state["road_topology"]["lastRouteSummary"] = f"目标节点 {node_id} 已下发" if published else f"目标节点 {node_id} 已进入本地通道"
        _command_record(1, "TOPOLOGY_GOAL_NODE", {"nodeId": node_id}, True, message, DEFAULT_TOPOLOGY_GOAL_TOPIC)
    return {
        "accepted": True,
        "nodeId": node_id,
        "topic": DEFAULT_TOPOLOGY_GOAL_TOPIC,
        "payload": json.dumps(payload, ensure_ascii=False),
        "message": message,
        "sentAt": _now_iso(),
    }


@router.post("/start-mqtt")
async def start_mqtt(request: Request) -> dict[str, Any]:
    body = await _request_json(request)
    result = _start_mqtt_bridge(force=bool(body.get("enable") or body.get("mqtt")))
    return {"success": True, **result, "mqtt": _state["mqtt"]}


@router.post("/start-simulation")
async def start_simulation(request: Request) -> dict[str, Any]:
    body = await _request_json(request)
    route_code = str(body.get("routeCode") or body.get("route") or SEM_LOOP_ROUTE_CODE)
    route_aliases = {
        "econ_loop": SEM_LOOP_ROUTE_CODE,
        "sem_loop": SEM_LOOP_ROUTE_CODE,
        "SEM": SEM_LOOP_ROUTE_CODE,
        "navigation": NAVIGATION_ROUTE_CODE,
    }
    route_code = route_aliases.get(route_code, route_code)
    if route_code not in {NAVIGATION_ROUTE_CODE, SEM_LOOP_ROUTE_CODE, HOLD_ROUTE_CODE}:
        route_code = SEM_LOOP_ROUTE_CODE
    if body.get("mqtt") or body.get("enableMqtt"):
        _start_mqtt_bridge(force=True)
    with _lock:
        _state.update(
            {
                "status": "running",
                "running": True,
                "started_at": time.monotonic(),
                "last_update": time.monotonic(),
                "duration_s": float(body.get("duration", 300.0)),
                "step": 0,
                "distance_m": 0.0,
                "target_speed": max(0.0, min(8.0, float(body.get("speed", body.get("targetSpeed", 1.2))))),
                "route_code": route_code,
                "route_mode": str(body.get("routeMode") or "REPLACE_ROUTE"),
                "selected_car_id": int(body.get("carId", 1)),
                "selected_car_code": "REAL-001" if int(body.get("carId", 1)) == 1 else "VIR-001",
                "trajectory": [],
                "last_output_session": None,
            }
        )
        _advance_locked()
        _log(f"HIL小车闭环实验已启动：route={route_code}, speed={_state['target_speed']:.2f}m/s。")
    return {
        "success": True,
        "message": "HIL小车闭环实验已启动",
        "route": _route_view(route_code),
        "mqtt": _state["mqtt"],
    }


@router.post("/stop-simulation")
async def stop_simulation() -> dict[str, Any]:
    with _lock:
        _advance_locked()
        _state["running"] = False
        _state["status"] = "stopped"
        _state["target_speed"] = 0.0
        _write_outputs_locked()
        _log("HIL小车闭环实验已停止。")
    return {"success": True, "message": "HIL小车闭环实验已停止"}


@router.post("/reset")
async def reset() -> dict[str, Any]:
    with _lock:
        _state.update(
            {
                "status": "idle",
                "running": False,
                "started_at": None,
                "last_update": time.monotonic(),
                "step": 0,
                "distance_m": 0.0,
                "target_speed": 1.2,
                "route_code": SEM_LOOP_ROUTE_CODE,
                "trajectory": [],
                "last_motion": _initial_motion(),
            }
        )
        _log("HIL实验状态已重置。")
    return {"success": True, "message": "已重置"}


@router.get("/vehicle-state")
async def vehicle_state() -> dict[str, Any]:
    with _lock:
        _advance_locked()
        motion = _state.get("last_motion") or _initial_motion()
        cars_now = _cars_locked()
        active = next((item for item in cars_now if item["id"] == _state.get("selected_car_id")), cars_now[0])
        legacy_status = _state.get("status", "idle")
        return {
            "success": True,
            "status": legacy_status,
            "running": bool(_state.get("running")),
            "step": int(_state.get("step", 0)),
            "x": motion["x"],
            "y": motion["y"],
            "speed": motion["speedMps"],
            "target_speed": float(_state.get("target_speed", 0.0)),
            "angle": motion["headingDeg"],
            "current_edge": motion["segmentName"],
            "dist_to_junction": motion["distToNextM"],
            "next_edge": _next_segment_name(motion["segmentIndex"]),
            "turn_direction": "route-follow",
            "longitude": motion["longitude"],
            "latitude": motion["latitude"],
            "distance": round(float(_state.get("distance_m", 0.0)), 2),
            "battery_percent": motion["batteryPercent"],
            "route_code": _state.get("route_code"),
            "active_car": active,
            "cars": cars_now,
            "roadTopology": dict(_state["road_topology"]),
            "mqtt": dict(_state["mqtt"]),
        }


def _next_segment_name(segment_index: int) -> str:
    points = _route_points(_state.get("route_code"))
    if not points:
        return "--"
    next_index = (segment_index + 1) % len(points)
    return str(points[next_index].get("name", f"WP-{next_index + 1}"))


@router.post("/send-command")
async def send_legacy_command(request: Request) -> dict[str, Any]:
    body = await _request_json(request)
    action = str(body.get("action") or "").lower()
    if action == "set_speed":
        command_type = "SET_SPEED"
    elif action in {"stop", "emergency"}:
        command_type = "EMERGENCY_STOP"
    elif action == "set_route":
        command_type = "SET_ROUTE"
    else:
        command_type = str(body.get("commandType") or "CONTROL_COMMAND")
    command = await create_command(int(body.get("carId", _state.get("selected_car_id", 1))), _SyntheticRequest({"commandType": command_type, "payload": body}))
    return {"success": command["status"] != "FAILED", "command": command}


class _SyntheticRequest:
    def __init__(self, body: dict[str, Any]):
        self._body = body

    async def json(self) -> dict[str, Any]:
        return self._body


@router.get("/trajectory-files")
async def trajectory_files() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(OUTPUT_DIR.glob("hil_vehicle_*.*"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "path": path.name,
                "size": f"{stat.st_size / 1024:.1f} KB",
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "url": f"/api/vehicle-control/download/{path.name}",
            }
        )
    return {"success": True, "files": files}


@router.get("/download/{filename}")
async def download(filename: str):
    target = (OUTPUT_DIR / Path(filename).name).resolve()
    try:
        if os.path.commonpath([str(target), str(OUTPUT_DIR.resolve())]) != str(OUTPUT_DIR.resolve()):
            raise HTTPException(status_code=400, detail="文件路径不合法")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="文件路径不合法") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=target.name)


@router.get("/logs")
async def logs() -> dict[str, Any]:
    with _lock:
        return {"success": True, "logs": list(_state.get("logs", []))}


@router.websocket("/ws")
async def websocket_status(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            with _lock:
                payload = {"summary": _summary_locked(), "state": awaitable_state_snapshot()}
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


def awaitable_state_snapshot() -> dict[str, Any]:
    motion = _state.get("last_motion") or _initial_motion()
    return {
        "status": _state.get("status"),
        "running": _state.get("running"),
        "step": _state.get("step"),
        "routeCode": _state.get("route_code"),
        "targetSpeed": _state.get("target_speed"),
        "motion": motion,
        "mqtt": _state.get("mqtt"),
        "roadTopology": _state.get("road_topology"),
    }


@compat_router.get("/dashboard/summary")
async def compat_dashboard_summary() -> dict[str, Any]:
    return await dashboard_summary()


@compat_router.get("/maps")
async def compat_maps() -> list[dict[str, Any]]:
    return await maps()


@compat_router.get("/maps/default")
async def compat_default_map() -> dict[str, Any]:
    return await default_map()


@compat_router.get("/maps/default/route")
async def compat_default_route() -> dict[str, Any]:
    return await default_route()


@compat_router.get("/maps/{map_code}")
async def compat_map_detail(map_code: str) -> dict[str, Any]:
    return await map_detail(map_code)


@compat_router.get("/maps/{map_code}/route")
async def compat_map_route(map_code: str, route_code: str = SEM_LOOP_ROUTE_CODE) -> dict[str, Any]:
    return await map_route(map_code, route_code)


@compat_router.get("/cars")
async def compat_cars() -> list[dict[str, Any]]:
    return await cars()


@compat_router.get("/cars/{car_id}")
async def compat_car_detail(car_id: int) -> dict[str, Any]:
    return await car_detail(car_id)


@compat_router.post("/cars/{car_id}/commands")
async def compat_create_command(car_id: int, request: Request) -> dict[str, Any]:
    return await create_command(car_id, request)


@compat_router.get("/commands/recent")
async def compat_recent_commands(limit: int = 20) -> list[dict[str, Any]]:
    return await recent_commands(limit)


@compat_router.get("/road-topology/status")
async def compat_road_topology_status() -> dict[str, Any]:
    return await road_topology_status()


@compat_router.post("/road-topology/goal-node")
async def compat_road_topology_goal_node(request: Request) -> dict[str, Any]:
    return await road_topology_goal_node(request)
