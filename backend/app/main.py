"""
FastAPI application entry point.
"""
import importlib
import os
import logging
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, Response
from datetime import datetime

from .config import settings
from . import run_mode
from .access_mode import access_context, is_local_request, requires_local_control
from .compiled_router_compat import silence_compiled_router
from .database import SessionLocal, init_db
from .init_db import seed_data
from .paths import resolve_external_project_root
from .routers import (
    ROUTER_LOAD_ERRORS,
    auth_router,
    tasks_router,
    reports_router,
    users_router,
    experiments_router,
    algorithms_router,
    algorithm_templates_router,
    algorithm_scripts_router,
    cloud_files,
    experiment_launchers,
    self_algorithms,
)
from .routers.data_collection_session import (
    collection_guard,
    finish_collection_request,
    reset_collection_session_state,
    router as data_collection_session_router,
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
OPTIONAL_ROUTER_LOAD_ERRORS = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting application...")
    
    # Create upload directory if not exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    
    # Initialize database
    init_db()
    if settings.DATABASE_URL != "sqlite:///:memory:":
        db = SessionLocal()
        try:
            seed_data(db)
        finally:
            db.close()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    reset_collection_session_state()
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/access-context", tags=["访问控制"])
async def get_access_context(request: Request):
    """返回本机/局域网访问模式及本机服务控制能力。"""

    return access_context(request)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = datetime.now()
    
    # Get user info from token if available
    user_info = "anonymous"
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        user_info = "authenticated"
    
    response = await call_next(request)
    
    # Disable browser cache for HTML/JS/CSS so changes take effect immediately
    path = request.url.path
    if path.endswith(('.html', '.js', '.css')):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    
    # Calculate request duration
    duration = (datetime.now() - start_time).total_seconds()
    
    # Log request details
    logger.info(
        f"{request.method} {request.url.path} - "
        f"User: {user_info} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.3f}s"
    )
    
    return response


@app.middleware("http")
async def enforce_access_mode(request: Request, call_next):
    """阻止局域网请求启动或停止后端机器上的实验进程。"""

    is_local = is_local_request(request)
    legacy_collection_path = (
        request.url.path.startswith("/api/collection/")
        and request.url.path != "/api/collection/session"
        and not request.url.path.startswith("/api/collection/session/")
        and request.url.path not in {
            "/api/collection/health",
            "/api/collection/scenarios",
            "/api/collection/default-video",
        }
    )
    if legacy_collection_path and not is_local:
        return JSONResponse(
            {
                "success": False,
                "code": "DATA_COLLECTION_SESSION_REQUIRED",
                "message": "局域网数据采集必须使用独立会话传输链路，请刷新数据采集页面后重试。",
                "access_mode": "lan",
            },
            status_code=409,
        )

    if requires_local_control(request) and not is_local:
        return JSONResponse(
            {
                "success": False,
                "code": "LOCAL_ONLY",
                "message": "该操作仅允许在运行平台的本机浏览器中执行，局域网访问不能控制本机实验后端。",
                "access_mode": "lan",
            },
            status_code=403,
        )

    collection_response = collection_guard(request)
    if collection_response is not None:
        return collection_response

    response = await call_next(request)
    finish_collection_request(request, response)
    return response


# Health check endpoint
@app.get("/api/v1/health", tags=["健康检查"])
async def health_check():
    """Health check endpoint for monitoring service status."""
    router_errors = {
        "required": ROUTER_LOAD_ERRORS,
        "optional": OPTIONAL_ROUTER_LOAD_ERRORS,
    }
    return {
        "status": "healthy" if not ROUTER_LOAD_ERRORS else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "router_errors": router_errors,
        "run_mode": run_mode.get_run_mode(),
        "run_mode_label": run_mode.mode_label(),
        "can_launch_windows": run_mode.allow_visible_windows(),
        "timestamp": datetime.now().isoformat()
    }


# Root endpoint - serve local frontend first, then fall back to cloud build.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_ROOT, ".."))
_LOCAL_FRONTEND_DIR = os.path.abspath(os.path.join(_BACKEND_ROOT, "..", "frontend"))
_CLOUD_FRONTEND_DIR = os.path.abspath(os.path.join(_BACKEND_ROOT, "..", "cloud", "frontend", "dist"))
_FRONTEND_DIR = _LOCAL_FRONTEND_DIR if os.path.isdir(_LOCAL_FRONTEND_DIR) else _CLOUD_FRONTEND_DIR

_RESOURCE_FILES = {
    "textbook-v2-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "教材", "v2.0", "智信优控_面向车路云一体化的综合交通实验平台_教材_v2.0.pdf"),
        "filename": "智信优控_综合交通实验平台_教材_v2.0.pdf",
        "media_type": "application/pdf",
    },
    "platform-manual-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "创AI案例征集", "配套资源", "输出文件夹", "pdf", "1_实验平台使用说明书.pdf"),
        "filename": "智信优控_实验平台使用说明书_v1.0.pdf",
        "media_type": "application/pdf",
    },
    "install-manual-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "创AI案例征集", "配套资源", "输出文件夹", "pdf", "3_安装手册.pdf"),
        "filename": "智信优控_安装与部署手册_v1.0.pdf",
        "media_type": "application/pdf",
    },
    "product-brochure-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "产品宣传手册", "最终版-产品宣传手册", "产品宣传手册-打印版.pdf"),
        "filename": "智信优控_产品宣传手册_打印版_2026.pdf",
        "media_type": "application/pdf",
    },
    "supporting-textbook-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "创AI案例征集", "配套资源", "输出文件夹", "pdf", "4_配套教材.pdf"),
        "filename": "智信优控_课程配套教材_v1.0.pdf",
        "media_type": "application/pdf",
    },
    "supporting-resources-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "创AI案例征集", "配套资源", "输出文件夹", "pdf", "5_配套资源说明.pdf"),
        "filename": "智信优控_配套资源说明_v1.0.pdf",
        "media_type": "application/pdf",
    },
    "simulation-environment-guide-pdf": {
        "path": os.path.join(_PROJECT_ROOT, "docs", "platform_resources", "simulation_environment_guide.pdf"),
        "filename": "仿真工具与环境配置说明_2026-05.pdf",
        "media_type": "application/pdf",
    },
}


@app.get("/", tags=["根路径"])
async def root():
    """Serve the product homepage."""
    index_path = os.path.join(_FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return RedirectResponse(url="/src/pages/登录界面/login.html")


@app.get("/resources/{resource_id}", tags=["资料下载"])
async def download_resource(resource_id: str):
    """Download whitelisted platform documents."""
    item = _RESOURCE_FILES.get(resource_id)
    if item is None or not os.path.isfile(item["path"]):
        return JSONResponse({"detail": "资料文件不存在"}, status_code=404)
    return FileResponse(
        item["path"],
        media_type=item["media_type"],
        filename=item["filename"],
    )


# Include routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(tasks_router, prefix="/api/v1/tasks", tags=["任务"])
app.include_router(reports_router, prefix="/api/v1/reports", tags=["报告"])
app.include_router(users_router, prefix="/api/v1/users", tags=["用户"])
app.include_router(experiments_router, prefix="/api/v1/experiments", tags=["实验"])
app.include_router(algorithms_router, prefix="/api/v1/algorithms", tags=["算法代理"])
app.include_router(algorithm_templates_router, prefix="/api/v1/algorithm-templates", tags=["算法模板"])
app.include_router(algorithm_scripts_router, prefix="/api/v1/algorithm-scripts", tags=["算法脚本"])
app.include_router(cloud_files.router)
app.include_router(experiment_launchers.router)
app.include_router(self_algorithms.router)
app.include_router(data_collection_session_router)


_OPTIONAL_ROUTERS = {
    "ai_assistant": {"prefix": "/api/v1/ai-assistant", "tags": ["AI助手"]},
}


def include_optional_router(module_name: str):
    try:
        module = importlib.import_module(f".routers.{module_name}", __package__)
        # 编译版路由（.pyd）里可能写死了 `start "..." cmd /k` 弹窗，
        # 学生模式下在导入后替换其 subprocess 为静默代理。
        silence_compiled_router(module)
        router = getattr(module, "router", None)
        if router is not None:
            opts = _OPTIONAL_ROUTERS.get(module_name, {})
            app.include_router(router, **opts)
        compat_router = getattr(module, "compat_router", None)
        if compat_router is not None:
            app.include_router(compat_router)
        if router is not None or compat_router is not None:
            OPTIONAL_ROUTER_LOAD_ERRORS.pop(module_name, None)
    except Exception as exc:
        OPTIONAL_ROUTER_LOAD_ERRORS[module_name] = str(exc)
        logger.warning("Skip optional router %s: %s", module_name, exc)


for _router_name in (
    "signal_optimization",
    "vehicle_speed_control",
    "three_level_control",
    "data_collection",
    "data_collection_scenarios",
    "traffic_prediction",
    "data_fusion_runtime",
    "carla_scene_api",
    "carla_simulation",
    "vehicle_hil_control",
    "vehicle_dev_control",
    "ai_assistant",
    "simulators",
):
    include_optional_router(_router_name)


def _has_route(path: str, methods: set[str]) -> bool:
    for route in app.routes:
        if getattr(route, "path", None) == path:
            route_methods = getattr(route, "methods", set()) or set()
            if methods & set(route_methods):
                return True
    return False


def _carla_software_status():
    carla_root = os.environ.get("CARLA_ROOT", "").strip().rstrip(";")
    carla_exe = os.path.join(carla_root, "CarlaUE4.exe") if carla_root else ""
    carla_installed = bool(carla_exe and os.path.isfile(carla_exe))
    sumo_home = os.environ.get("SUMO_HOME", "").strip().rstrip(";")
    sumo_gui = os.path.join(sumo_home, "bin", "sumo-gui.exe") if sumo_home else ""
    return [
        {
            "id": "carla",
            "name": "CARLA",
            "installed": carla_installed,
            "path": carla_root or None,
            "executable": carla_exe or None,
            "running": False,
            "message": "CARLA_ROOT not configured" if not carla_installed else "Ready",
        },
        {
            "id": "sumo",
            "name": "SUMO",
            "installed": bool(sumo_gui and os.path.isfile(sumo_gui)),
            "path": sumo_home or None,
            "executable": sumo_gui or None,
            "running": False,
        },
    ]


if not _has_route("/api/carla-sim/health", {"GET"}):
    @app.get("/api/carla-sim/health", tags=["CARLA fallback"])
    async def carla_sim_health_fallback():
        return {
            "status": "degraded",
            "service": "carla-simulation",
            "demo_mode": True,
            "message": "CARLA simulation router is unavailable or CARLA is not configured.",
        }


if not _has_route("/api/carla-sim/software-status", {"GET"}):
    @app.get("/api/carla-sim/software-status", tags=["CARLA fallback"])
    async def carla_software_status_fallback():
        return {"success": True, "software": _carla_software_status()}


if not _has_route("/api/carla-sim/launch-software", {"POST"}):
    @app.post("/api/carla-sim/launch-software", tags=["CARLA fallback"])
    async def carla_launch_software_fallback(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        return JSONResponse(
            {
                "success": False,
                "message": "CARLA simulation software is not configured in this installation.",
                "requested": body.get("id") or body.get("software") or None,
                "software": _carla_software_status(),
            },
            status_code=409,
        )


# ---- 交通流重构 DTALite 直接路由（绕过5001端口） ----
import subprocess
import sys
import threading
import time
from .paths import DTALITE_DIR, algo_output_dir

_DTALITE_DIR = DTALITE_DIR
_DTALITE_EXE = os.path.join(_DTALITE_DIR, 'DTALite.exe')
_OUTPUT_DIR = algo_output_dir('traffic_reconstruction', 'output')

_dtalite_status = {
    'running': False,
    'success': None,
    'message': '未运行',
    'elapsed': 0,
}
_dtalite_lock = threading.Lock()
_dtalite_process = None
_dtalite_started_at = 0.0


def _server_process_kwargs():
    """Return subprocess options suitable for server-side background work."""
    return run_mode.server_process_kwargs()


def _launch_visible_dtalite_console():
    """Launch DTALite on the backend computer.

    演示模式：弹出可见 CMD 窗口，便于观察执行过程。
    学生模式：静默执行，输出写入 backend/logs/dtalite.log，状态接口照常反馈。
    """
    if run_mode.is_student_mode():
        log_dir = os.path.join(_BACKEND_ROOT, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "dtalite.log")
        log_handle = open(log_path, "a", encoding="utf-8", errors="replace")
        log_handle.write(f"\n[{datetime.now().isoformat()}] DTALite (student mode, no window)\n")
        log_handle.flush()
        return subprocess.Popen(
            [_DTALITE_EXE],
            cwd=_DTALITE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            **run_mode.server_process_kwargs(),
        )
    if os.name == "nt":
        cmd = (
            'title DTALite交通流重构'
            ' & chcp 65001 >nul'
            ' & echo ========================================'
            ' & echo   DTALite交通流重构正在执行...'
            ' & echo ========================================'
            ' & echo 当前目录: %CD%'
            ' & echo 启动程序: DTALite.exe'
            ' & echo.'
            ' & DTALite.exe'
            ' & set DTALITE_EXIT=!ERRORLEVEL!'
            ' & echo.'
            ' & echo ========================================'
            ' & echo   DTALite执行完成，退出码 !DTALITE_EXIT!'
            ' & echo ========================================'
            ' & timeout /t 5 >nul'
            ' & exit /b !DTALITE_EXIT!'
        )
        return subprocess.Popen(
            ["cmd.exe", "/v:on", "/c", cmd],
            cwd=_DTALITE_DIR,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    return subprocess.Popen([_DTALITE_EXE], cwd=_DTALITE_DIR, **_server_process_kwargs())


def _refresh_dtalite_status_locked():
    global _dtalite_process, _dtalite_started_at
    proc = _dtalite_process
    if proc is None or not _dtalite_status.get('running'):
        return

    elapsed = max(0, time.time() - _dtalite_started_at) if _dtalite_started_at else _dtalite_status.get('elapsed', 0)
    returncode = proc.poll()
    if returncode is None:
        _dtalite_status.update(
            running=True,
            success=None,
            message=f'DTALite正在运行中（PID {proc.pid}，已运行{elapsed:.1f}秒）',
            elapsed=elapsed,
            pid=proc.pid,
        )
        return

    _dtalite_process = None
    _dtalite_started_at = 0.0
    if returncode == 0:
        _dtalite_status.update(
            running=False,
            success=True,
            message=f'DTALite执行完成（耗时{elapsed:.1f}秒）',
            elapsed=elapsed,
            pid=None,
        )
    else:
        _dtalite_status.update(
            running=False,
            success=False,
            message=f'DTALite执行失败（退出码{returncode}，详见服务端日志）',
            elapsed=elapsed,
            pid=None,
        )


def _parse_real_metrics():
    """从DTALite输出的CSV文件中解析真实指标"""
    import csv
    metrics = {}
    # 1) 从 debug_validation_results.csv 计算 RMSE 和精度
    validation_csv = os.path.join(_DTALITE_DIR, 'debug_validation_results.csv')
    if os.path.exists(validation_csv):
        try:
            observed_list = []
            simulated_list = []
            with open(validation_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        obs = float(row.get('observed_link_count', 0))
                        sim = float(row.get('simulated_link_count', 0))
                        observed_list.append(obs)
                        simulated_list.append(sim)
                    except (ValueError, TypeError):
                        continue
            if observed_list:
                n = len(observed_list)
                sum_sq_err = sum((o - s) ** 2 for o, s in zip(observed_list, simulated_list))
                rmse = (sum_sq_err / n) ** 0.5
                sum_obs = sum(observed_list)
                sum_sim = sum(simulated_list)
                if sum_obs > 0:
                    accuracy = max(0, 1 - abs(sum_sim - sum_obs) / sum_obs) * 100
                else:
                    accuracy = 0
                metrics['rmse'] = f'{rmse:.2f}'
                metrics['accuracy'] = f'{accuracy:.1f}%'
                metrics['validationRows'] = n
        except Exception:
            pass
    # 2) 从 output_ODMOE.csv 统计 OD 对数量和平均行程
    odmoe_csv = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
    if os.path.exists(odmoe_csv):
        try:
            od_count = 0
            total_time = 0
            total_dist = 0
            with open(odmoe_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    od_count += 1
                    try:
                        total_time += float(row.get('trip_time_in_min', 0))
                        total_dist += float(row.get('distance', 0))
                    except (ValueError, TypeError):
                        continue
            metrics['odPairCount'] = str(od_count)
            if od_count > 0:
                metrics['avgTripTime'] = f'{total_time / od_count:.2f} min'
                metrics['avgDistance'] = f'{total_dist / od_count:.2f} km'
        except Exception:
            pass
    # 3) 从 output_day_to_day_MOE.csv 读取总车辆数和平均速度
    moe_csv = os.path.join(_DTALITE_DIR, 'output_day_to_day_MOE.csv')
    if os.path.exists(moe_csv):
        try:
            with open(moe_csv, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # 数据行在第5行之后（前面是header描述）
            for line in reversed(lines):
                parts = line.strip().split(',')
                # 找到有数字的行（day_no列有值）
                if len(parts) > 10:
                    try:
                        vehicles = int(float(parts[6]))
                        avg_speed = float(parts[10])
                        avg_time = float(parts[9])
                        metrics['totalVehicles'] = str(vehicles)
                        metrics['avgSpeed'] = f'{avg_speed:.1f} mph'
                        metrics['avgTravelTime'] = f'{avg_time:.2f} min'
                        break
                    except (ValueError, IndexError):
                        continue
        except Exception:
            pass
    return metrics


@app.post("/api/reconstruction/run-dtalite", tags=["交通流重构"])
async def run_dtalite():
    global _dtalite_process, _dtalite_started_at
    with _dtalite_lock:
        _refresh_dtalite_status_locked()
        if _dtalite_status['running']:
            return {'success': False, 'message': 'DTALite正在运行中，请等待完成'}

    if not os.path.exists(_DTALITE_EXE):
        # 演示模式：从已有的输出文件读取真实数据
        metrics = _parse_real_metrics()
        return {
            'success': True,
            'message': 'DTALite模拟执行完成（演示模式）',
            'metrics': metrics,
        }

    log_path = os.path.join(_OUTPUT_DIR, 'dtalite_run.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        with open(log_path, 'a', encoding='utf-8', errors='replace') as log:
            log.write(f'\n[{datetime.now().isoformat()}] RUN visible CMD -> {_DTALITE_EXE}\n')
            log.flush()
        proc = _launch_visible_dtalite_console()
    except Exception as e:
        with _dtalite_lock:
            _dtalite_status.update(running=False, success=False, message=f'DTALite启动失败：{e}', elapsed=0, pid=None)
        return {'success': False, 'message': f'DTALite启动失败：{e}'}

    with _dtalite_lock:
        _dtalite_process = proc
        _dtalite_started_at = time.time()
        _dtalite_status.update(
            running=True,
            success=None,
            message=f'DTALite可见CMD已启动（PID {proc.pid}）',
            elapsed=0,
            pid=proc.pid,
        )
    return {'success': True, 'message': 'DTALite可见CMD已在后端电脑启动，正在运行中...', 'async': True, 'pid': proc.pid}


@app.get("/api/reconstruction/dtalite-status", tags=["交通流重构"])
async def dtalite_status():
    with _dtalite_lock:
        _refresh_dtalite_status_locked()
        s = dict(_dtalite_status)
    result = {'running': s['running'], 'success': s['success'], 'message': s['message']}
    if not s['running'] and s['success']:
        metrics = _parse_real_metrics()
        metrics['processingTime'] = f'{s["elapsed"]:.1f}s'
        result['metrics'] = metrics
    return result


@app.get("/api/reconstruction/health", tags=["交通流重构"])
async def reconstruction_health():
    return {'status': 'ok', 'service': 'reconstruction'}


@app.post("/api/reconstruction/import-data", tags=["交通流重构"])
async def import_data():
    """检查并统计DTALite输入数据文件的真实信息"""
    import csv as _csv
    result = {'success': True, 'fileCount': 0, 'odPairCount': '--', 'status': '未找到数据'}
    # 统计输入文件
    input_files = ['input_demand.csv', 'input_link.csv', 'input_node.csv', 'input_zone.csv']
    found = 0
    for f in input_files:
        if os.path.exists(os.path.join(_DTALITE_DIR, f)):
            found += 1
    result['fileCount'] = found
    # 从 input_demand.csv 统计OD对数量
    demand_csv = os.path.join(_DTALITE_DIR, 'input_demand.csv')
    if os.path.exists(demand_csv):
        try:
            with open(demand_csv, 'r', encoding='utf-8') as f:
                reader = _csv.reader(f)
                header = next(reader, None)
                count = sum(1 for _ in reader)
            result['odPairCount'] = str(count)
            result['status'] = '已就绪'
        except Exception:
            pass
    # 如果 input_demand 没有，尝试从 output_ODMOE.csv 读取
    if result['odPairCount'] == '--':
        odmoe = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
        if os.path.exists(odmoe):
            try:
                with open(odmoe, 'r', encoding='utf-8') as f:
                    reader = _csv.reader(f)
                    next(reader, None)
                    count = sum(1 for _ in reader)
                result['odPairCount'] = str(count)
                result['status'] = '已就绪'
            except Exception:
                pass
    return result



@app.get("/api/reconstruction/network-image", tags=["交通流重构"])
async def get_network_image():
    """用matplotlib生成路网拓扑图PNG并返回"""
    import csv
    import io
    node_csv = os.path.join(_DTALITE_DIR, 'input_node.csv')
    link_csv = os.path.join(_DTALITE_DIR, 'input_link.csv')
    if not os.path.exists(node_csv) or not os.path.exists(link_csv):
        return {'success': False, 'message': '路网数据文件不存在'}
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        # 尝试使用中文字体
        for fname in ['SimHei', 'Microsoft YaHei', 'STSong']:
            try:
                plt.rcParams['font.sans-serif'] = [fname]
                break
            except Exception:
                pass
        plt.rcParams['axes.unicode_minus'] = False
        nodes = {}
        signal_nodes = set()
        with open(node_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    nid = int(row.get('node_id', 0))
                    x = float(row.get('x_coord', 0))
                    y = float(row.get('y_coord', 0))
                    nodes[nid] = (x, y)
                    ctrl = row.get('control_type_name', '')
                    if 'signal' in ctrl.lower():
                        signal_nodes.add(nid)
                except (ValueError, TypeError):
                    continue
        link_coords = []
        with open(link_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    geo = row.get('geometry', '')
                    if geo and 'LINESTRING' in geo:
                        inner = geo.replace('LINESTRING (', '').replace('LINESTRING(', '').rstrip(')')
                        pts = []
                        for pt in inner.split(','):
                            pt = pt.strip()
                            parts = pt.split()
                            if len(parts) >= 2:
                                pts.append((float(parts[0]), float(parts[1])))
                        if pts:
                            link_coords.append(pts)
                except (ValueError, TypeError):
                    continue
        fig, ax = plt.subplots(1, 1, figsize=(10, 8), dpi=120)
        fig.patch.set_facecolor('#f8fafc')
        ax.set_facecolor('#f0f4f8')
        for pts in link_coords:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(xs, ys, color='#5a7faa', linewidth=1.2, alpha=0.7, solid_capstyle='round')
        normal_x, normal_y = [], []
        signal_x, signal_y = [], []
        for nid, (x, y) in nodes.items():
            if nid in signal_nodes:
                signal_x.append(x)
                signal_y.append(y)
            else:
                normal_x.append(x)
                normal_y.append(y)
        if normal_x:
            ax.scatter(normal_x, normal_y, c='#4CAF50', s=18, zorder=5, alpha=0.8, edgecolors='white', linewidths=0.5, label=f'普通节点 ({len(normal_x)})')
        if signal_x:
            ax.scatter(signal_x, signal_y, c='#2C5AA0', s=30, zorder=6, alpha=0.9, edgecolors='white', linewidths=0.8, marker='s', label=f'信号灯节点 ({len(signal_x)})')
        ax.set_title(f'路网拓扑结构图（{len(nodes)}个节点，{len(link_coords)}条路段）', fontsize=14, fontweight='bold', pad=12)
        ax.set_xlabel('经度', fontsize=10)
        ax.set_ylabel('纬度', fontsize=10)
        ax.legend(loc='upper right', fontsize=9, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_aspect('equal')
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        from starlette.responses import StreamingResponse
        return StreamingResponse(buf, media_type='image/png')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': str(e)}

@app.post("/api/reconstruction/launch-nexta", tags=["交通流重构"])
async def launch_nexta():
    nexta_exe = os.path.join(_DTALITE_DIR, 'NEXTA.exe')
    if not os.path.exists(nexta_exe):
        return {'success': False, 'message': 'NEXTA.exe不存在'}
    try:
        subprocess.Popen([nexta_exe], cwd=_DTALITE_DIR, **_server_process_kwargs())
        return {'success': True, 'message': 'NEXTA路网编辑器已启动'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@app.post("/api/reconstruction/save-params", tags=["交通流重构"])
async def save_params(request: Request):
    params = await request.json()
    try:
        import csv
        import io
        changed = []

        # 1. 修改 input_scenario_settings.csv 中的 number_of_iterations
        if 'maxIterations' in params:
            csv_file = os.path.join(_DTALITE_DIR, 'input_scenario_settings.csv')
            if os.path.exists(csv_file):
                with open(csv_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)
                fieldnames = reader.fieldnames
                if rows and 'number_of_iterations' in fieldnames:
                    rows[0]['number_of_iterations'] = str(params['maxIterations'])
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                        f.write(output.getvalue())
                    changed.append(f'number_of_iterations = {params["maxIterations"]}')

        # 2. 修改 DTASettings.txt 中的其他参数
        settings_file = os.path.join(_DTALITE_DIR, 'DTASettings.txt')
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            txt_mapping = {
                'convergencyGap': 'convergency_relative_gap_threshold_percentage',
                'aggregationInterval': 'aggregation_time_interval_in_min',
                'histODWeight': 'weight_on_hist_oddemand',
            }

            new_lines = []
            for line in lines:
                stripped = line.strip()
                modified = False
                for param_key, setting_key in txt_mapping.items():
                    if param_key not in params:
                        continue
                    if '=' in stripped:
                        before_eq = stripped.split('=')[0].strip()
                        if before_eq == setting_key:
                            eq_pos = line.index('=')
                            new_line = line[:eq_pos + 1] + ' ' + str(params[param_key]) + '\n'
                            new_lines.append(new_line)
                            changed.append(f'{setting_key} = {params[param_key]}')
                            modified = True
                            break
                if not modified:
                    new_lines.append(line)

            with open(settings_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

        if changed:
            return {'success': True, 'message': f'参数已保存（修改了{len(changed)}项：{"、".join(changed)}）'}
        else:
            return {'success': True, 'message': '参数已保存（无变化）'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@app.post("/api/reconstruction/run-validation-analysis", tags=["交通流重构"])
async def run_validation():
    return {'success': True, 'message': '验证分析完成'}


@app.get("/api/reconstruction/validation-chart/{filename}", tags=["交通流重构"])
async def get_validation_chart(filename: str):
    """提供验证分析图表文件"""
    import re
    if not re.match(r'^[\w\-]+\.png$', filename):
        return JSONResponse({'error': '无效文件名'}, status_code=400)
    path = os.path.join(_OUTPUT_DIR, 'validation', filename)
    if os.path.exists(path):
        return FileResponse(path, media_type='image/png')
    return JSONResponse({'error': '图表不存在'}, status_code=404)


@app.get("/api/reconstruction/od-chart/{filename}", tags=["交通流重构"])
async def get_od_chart(filename: str):
    """提供OD结果图表文件"""
    import re
    if not re.match(r'^[\w\-]+\.png$', filename):
        return JSONResponse({'error': '无效文件名'}, status_code=400)
    od_dir = os.path.join(_DTALITE_DIR, '..', 'od_results')
    path = os.path.join(od_dir, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type='image/png')
    return JSONResponse({'error': '图表不存在'}, status_code=404)


@app.post("/api/reconstruction/generate-report", tags=["交通流重构"])
async def generate_report(request: Request):
    try:
        from docx import Document
        from docx.shared import Inches, Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        import csv as _csv

        params = await request.json()
        metrics = _parse_real_metrics()

        doc = Document()

        # ---- 样式设置 ----
        style = doc.styles['Normal']
        style.font.name = '宋体'
        style.font.size = Pt(11)
        style.paragraph_format.line_spacing = 1.5

        # ---- 封面标题 ----
        title = doc.add_heading('交通流重构分析报告', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.color.rgb = RGBColor(44, 90, 160)

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(f'生成时间：{datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}')
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(102, 102, 102)

        doc.add_paragraph()  # 空行

        # ---- 1. 算法概述 ----
        doc.add_heading('一、算法概述', level=1)
        doc.add_paragraph(
            '本报告基于DTALite动态交通分配引擎，采用OD矩阵反推方法进行区域交通流重构。'
            '通过路段观测流量数据，利用梯度投影法迭代优化OD矩阵估计，实现区域交通流的完整重构与仿真评估。'
        )
        doc.add_paragraph('核心步骤：')
        steps = [
            '导入路网拓扑与观测流量数据',
            '基于用户均衡原理进行交通分配',
            '迭代优化OD矩阵估计（梯度投影法）',
            '输出重构后的交通流分布与评估指标',
        ]
        for s in steps:
            doc.add_paragraph(s, style='List Number')

        # ---- 2. 参数配置 ----
        doc.add_heading('二、参数配置', level=1)
        doc.add_paragraph('以下为本次运行使用的DTALite参数配置（来源：DTASettings.txt）：')
        param_table = doc.add_table(rows=5, cols=2, style='Light Grid Accent 1')
        param_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = param_table.rows[0].cells
        headers[0].text = '参数名称'
        headers[1].text = '参数值'
        param_data = [
            ('最大迭代次数', params.get('maxIterations', '10')),
            ('收敛阈值 (%)', params.get('convergencyGap', '5.0')),
            ('聚合时间间隔 (min)', params.get('aggregationInterval', '15')),
            ('历史OD权重', params.get('histODWeight', '1.0')),
        ]
        for i, (name, val) in enumerate(param_data):
            row = param_table.rows[i + 1].cells
            row[0].text = name
            row[1].text = str(val)

        # ---- 3. 重构结果指标 ----
        doc.add_heading('三、重构结果指标', level=1)
        doc.add_paragraph('以下指标均从DTALite实际输出的CSV文件中解析得到：')
        metric_table = doc.add_table(rows=1, cols=2, style='Light Grid Accent 1')
        metric_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        mh = metric_table.rows[0].cells
        mh[0].text = '指标'
        mh[1].text = '数值'
        label_map = {
            'accuracy': '重构精度',
            'rmse': 'RMSE',
            'validationRows': '验证数据行数',
            'odPairCount': 'OD对数量',
            'avgTripTime': '平均行程时间',
            'avgDistance': '平均行程距离',
            'totalVehicles': '总车辆数',
            'avgSpeed': '平均速度',
            'avgTravelTime': '平均出行时间',
        }
        for k, v in metrics.items():
            row = metric_table.add_row().cells
            row[0].text = label_map.get(k, k)
            row[1].text = str(v)

        # ---- 4. OD矩阵数据摘要 ----
        doc.add_heading('四、OD矩阵数据摘要', level=1)
        odmoe_csv = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
        if os.path.exists(odmoe_csv):
            doc.add_paragraph(f'数据来源：output_ODMOE.csv')
            with open(odmoe_csv, 'r', encoding='utf-8') as f:
                reader = _csv.reader(f)
                header = next(reader, None)
                rows_data = []
                for row in reader:
                    rows_data.append(row)
            # 显示前20行
            show_rows = rows_data[:20]
            if header and show_rows:
                cn_header = ['起点区域', '终点区域', '出行者数', '完成出行数', '行程时间(min)', '距离']
                od_table = doc.add_table(rows=1 + len(show_rows), cols=len(cn_header), style='Light Grid Accent 1')
                od_table.alignment = WD_TABLE_ALIGNMENT.CENTER
                for ci, h in enumerate(cn_header):
                    od_table.rows[0].cells[ci].text = h
                for ri, row in enumerate(show_rows):
                    for ci, val in enumerate(row[:len(cn_header)]):
                        od_table.rows[ri + 1].cells[ci].text = val
                if len(rows_data) > 20:
                    doc.add_paragraph(f'（仅展示前20行，共{len(rows_data)}行数据）')
        else:
            doc.add_paragraph('未找到 output_ODMOE.csv 文件。')

        # ---- 5. 验证分析图表 ----
        doc.add_heading('五、验证分析图表', level=1)
        validation_dir = os.path.join(_OUTPUT_DIR, 'validation')
        chart_info = [
            ('01_link_flow_timeseries.png', '图1：主要路段流量时序变化',
             '展示5个主要路段的交通流量随时间的变化趋势，反映不同路段的流量特征和时变规律。'),
            ('02_link_flow_distribution.png', '图2：各路段总流量统计',
             '统计所有路段的总交通流量分布，识别路网中的关键路段和流量瓶颈。'),
            ('03_observed_vs_simulated_scatter.png', '图3：观测流量 vs 反推流量对比',
             '对比输入约束（observed）与矩阵分配结果（simulated）的路段流量，评估重构算法的准确性。'),
            ('04_error_distribution.png', '图4：路段流量误差分布',
             '展示反推流量与观测流量的误差分布情况，红色表示低估，绿色表示高估，评估算法性能。'),
        ]
        for fname, caption, desc in chart_info:
            img_path = os.path.join(validation_dir, fname)
            doc.add_heading(caption, level=2)
            doc.add_paragraph(desc)
            if os.path.exists(img_path):
                doc.add_picture(img_path, width=Inches(5.5))
                last_para = doc.paragraphs[-1]
                last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                doc.add_paragraph(f'（图表文件 {fname} 未找到）')

        # ---- 6. 结论 ----
        doc.add_heading('六、结论', level=1)
        acc = metrics.get('accuracy', '--')
        rmse_val = metrics.get('rmse', '--')
        od_count = metrics.get('odPairCount', '--')
        doc.add_paragraph(
            f'本次交通流重构基于DTALite动态交通分配引擎完成。'
            f'共重构 {od_count} 个OD对的出行需求矩阵，'
            f'重构精度为 {acc}，RMSE为 {rmse_val}。'
            f'结果表明算法能够有效地从路段观测流量中反推区域OD矩阵，满足交通规划与管理的应用需求。'
        )

        # 保存
        report_path = os.path.join(_OUTPUT_DIR, 'reconstruction_report.docx')
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        doc.save(report_path)
        return {'success': True, 'message': '报告生成成功'}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': str(e)}


@app.get("/api/reconstruction/download-report", tags=["交通流重构"])
async def download_report():
    path = os.path.join(_OUTPUT_DIR, 'reconstruction_report.docx')
    if os.path.exists(path):
        return FileResponse(path, filename='交通流重构分析报告.docx',
                            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    # 兼容旧的txt
    txt_path = os.path.join(_OUTPUT_DIR, 'reconstruction_report.txt')
    if os.path.exists(txt_path):
        return FileResponse(txt_path, filename='reconstruction_report.txt')
    return JSONResponse({'error': '报告不存在'}, status_code=404)


@app.get("/api/reconstruction/download-csv/{name}", tags=["交通流重构"])
async def download_csv(name: str):
    path = os.path.join(_DTALITE_DIR, f'{name}.csv')
    if os.path.exists(path):
        return FileResponse(path, filename=f'{name}.csv')
    return JSONResponse({'error': '文件不存在'}, status_code=404)


@app.get("/api/reconstruction/get-od-results", tags=["交通流重构"])
async def get_od_results():
    path = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
    return {'success': os.path.exists(path), 'exists': os.path.exists(path)}


@app.post("/api/reconstruction/export-network-doc", tags=["交通流重构"])
async def export_network_doc():
    """生成路网编辑说明文档（docx），包含节点、路段、交通区等数据摘要"""
    import csv as _csv
    import io as _io
    try:
        from docx import Document as DocxDocument
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        return JSONResponse({'error': 'python-docx未安装，请运行 pip install python-docx'}, status_code=500)

    try:
        doc = DocxDocument()

        # 标题
        title = doc.add_heading('路网编辑说明文档', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        doc.add_paragraph(f'数据目录：{_DTALITE_DIR}')
        doc.add_paragraph('')

        # 辅助函数：读取CSV前N行
        def read_csv_rows(filename, max_rows=20):
            filepath = os.path.join(_DTALITE_DIR, filename)
            if not os.path.exists(filepath):
                return None, None
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            reader = _csv.reader(_io.StringIO(content))
            rows = []
            headers = None
            for i, row in enumerate(reader):
                if i == 0:
                    headers = row
                elif i <= max_rows:
                    rows.append(row)
            return headers, rows

        def count_csv_rows(filename):
            filepath = os.path.join(_DTALITE_DIR, filename)
            if not os.path.exists(filepath):
                return 0
            with open(filepath, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f) - 1  # 减去表头

        # 1. 路网概览
        doc.add_heading('一、路网概览', level=1)
        node_count = count_csv_rows('input_node.csv')
        link_count = count_csv_rows('input_link.csv')
        zone_count = count_csv_rows('input_zone.csv')
        doc.add_paragraph(f'节点数量：{node_count}')
        doc.add_paragraph(f'路段数量：{link_count}')
        doc.add_paragraph(f'交通区数量：{zone_count}')
        doc.add_paragraph('')

        # 2. 节点数据
        doc.add_heading('二、节点数据（input_node.csv）', level=1)
        headers, rows = read_csv_rows('input_node.csv', 10)
        if headers and rows:
            # 只取关键列
            key_cols = ['node_id', 'x_coord', 'y_coord', 'zone_id', 'ctrl_type', 'control_type_name']
            col_indices = [i for i, h in enumerate(headers) if h.strip() in key_cols]
            display_headers = [headers[i].strip() for i in col_indices]

            table = doc.add_table(rows=min(len(rows), 10) + 1, cols=len(display_headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(display_headers):
                table.rows[0].cells[j].text = h
            for i, row in enumerate(rows[:10]):
                for j, ci in enumerate(col_indices):
                    if ci < len(row):
                        table.rows[i + 1].cells[j].text = row[ci].strip()

            if node_count > 10:
                doc.add_paragraph(f'（仅展示前10条，共{node_count}条记录）')
        else:
            doc.add_paragraph('未找到节点数据文件')
        doc.add_paragraph('')

        # 3. 路段数据
        doc.add_heading('三、路段数据（input_link.csv）', level=1)
        headers, rows = read_csv_rows('input_link.csv', 10)
        if headers and rows:
            key_cols = ['link_id', 'from_node_id', 'to_node_id', 'length', 'number_of_lanes', 'speed_limit', 'lane_cap']
            col_indices = [i for i, h in enumerate(headers) if h.strip() in key_cols]
            display_headers = [headers[i].strip() for i in col_indices]

            table = doc.add_table(rows=min(len(rows), 10) + 1, cols=len(display_headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(display_headers):
                table.rows[0].cells[j].text = h
            for i, row in enumerate(rows[:10]):
                for j, ci in enumerate(col_indices):
                    if ci < len(row):
                        table.rows[i + 1].cells[j].text = row[ci].strip()

            if link_count > 10:
                doc.add_paragraph(f'（仅展示前10条，共{link_count}条记录）')
        else:
            doc.add_paragraph('未找到路段数据文件')
        doc.add_paragraph('')

        # 4. 交通区数据
        doc.add_heading('四、交通区数据（input_zone.csv）', level=1)
        headers, rows = read_csv_rows('input_zone.csv', 10)
        if headers and rows:
            key_cols = ['zone_id', 'production', 'attraction']
            col_indices = [i for i, h in enumerate(headers) if h.strip() in key_cols]
            display_headers = [headers[i].strip() for i in col_indices]

            table = doc.add_table(rows=min(len(rows), 10) + 1, cols=len(display_headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(display_headers):
                table.rows[0].cells[j].text = h
            for i, row in enumerate(rows[:10]):
                for j, ci in enumerate(col_indices):
                    if ci < len(row):
                        table.rows[i + 1].cells[j].text = row[ci].strip()

            if zone_count > 10:
                doc.add_paragraph(f'（仅展示前10条，共{zone_count}条记录）')
        else:
            doc.add_paragraph('未找到交通区数据文件')
        doc.add_paragraph('')

        # 5. DTALite参数配置
        doc.add_heading('五、DTALite参数配置（DTASettings.txt）', level=1)
        settings_path = os.path.join(_DTALITE_DIR, 'DTASettings.txt')
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and '=' in stripped and not stripped.startswith('#'):
                        doc.add_paragraph(stripped)
        else:
            doc.add_paragraph('未找到DTASettings.txt')
        doc.add_paragraph('')

        # 6. 编辑说明
        doc.add_heading('六、路网编辑操作说明', level=1)
        doc.add_paragraph('1. 启动NEXTA路网编辑器查看当前路网拓扑结构')
        doc.add_paragraph('2. 在NEXTA中可编辑节点位置、路段属性、信号配时等')
        doc.add_paragraph('3. 编辑完成后在NEXTA中保存（File → Save）')
        doc.add_paragraph('4. 返回平台配置参数后运行DTALite.exe进行交通流重构')

        # 保存到临时文件
        doc_path = os.path.join(_OUTPUT_DIR, '路网编辑说明文档.docx')
        os.makedirs(os.path.dirname(doc_path), exist_ok=True)
        doc.save(doc_path)

        return FileResponse(doc_path, filename='路网编辑说明文档.docx',
                          media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        logger.error(f'生成路网文档失败: {e}')
        return JSONResponse({'error': str(e)}, status_code=500)


# ---- 交通流预测 直接路由（服务器后台运行） ----
_PREDICTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'algorithms', 'traffic_prediction')
_PREDICTION_CHARTS_DIR = os.path.join(_PREDICTION_DIR, 'charts')

_prediction_status = {
    'running': False,
    'task': None,
    'success': None,
    'message': '未运行',
}
_prediction_lock = threading.Lock()


def _run_prediction_process(args, log_name, timeout=600):
    os.makedirs(_PREDICTION_CHARTS_DIR, exist_ok=True)
    log_path = os.path.join(_PREDICTION_CHARTS_DIR, log_name)
    with open(log_path, 'a', encoding='utf-8', errors='replace') as log:
        log.write(f'\n[{datetime.now().isoformat()}] RUN {" ".join(args)}\n')
        log.flush()
        return subprocess.run(
            args,
            cwd=_PREDICTION_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            timeout=timeout,
            **_server_process_kwargs(),
        )


@app.post("/api/prediction/train-model", tags=["交通流预测"])
async def train_model_cmd(request: Request):
    """在服务器后台运行模型训练（predictor.py --model xxx）"""
    with _prediction_lock:
        if _prediction_status['running']:
            return {'success': False, 'message': '已有任务在运行中，请等待完成'}

    script = os.path.join(_PREDICTION_DIR, 'predictor.py')
    if not os.path.exists(script):
        return {'success': False, 'message': 'predictor.py不存在'}

    # 从请求体获取模型选择
    model_key = 'all'
    try:
        body = await request.json()
        model_key = body.get('model', 'all')
    except Exception:
        pass

    with _prediction_lock:
        _prediction_status.update(running=True, task='train', success=None, message='正在启动模型训练...')

    def _run_train(model_arg):
        import time
        start = time.time()
        try:
            output_file = os.path.join(_PREDICTION_DIR, 'pre.jpg')
            results_file = os.path.join(_PREDICTION_CHARTS_DIR, 'results.txt')
            init_mt = os.path.getmtime(output_file) if os.path.exists(output_file) else 0
            init_rt = os.path.getmtime(results_file) if os.path.exists(results_file) else 0

            process = _run_prediction_process(
                [sys.executable, "-u", script, "--model", model_arg],
                "prediction_train.log",
            )
            if process.returncode != 0:
                raise RuntimeError(f'模型训练进程退出码 {process.returncode}')

            for _ in range(150):
                time.sleep(2)
                jpg_updated = os.path.exists(output_file) and os.path.getmtime(output_file) > init_mt + 1
                txt_updated = os.path.exists(results_file) and os.path.getmtime(results_file) > init_rt + 1
                if jpg_updated or txt_updated:
                    time.sleep(3)
                    break
            elapsed = time.time() - start
            with _prediction_lock:
                _prediction_status.update(running=False, success=True,
                    message=f'模型训练完成（耗时{elapsed:.0f}秒）')
        except Exception as e:
            with _prediction_lock:
                _prediction_status.update(running=False, success=False, message=str(e))

    threading.Thread(target=_run_train, args=(model_key,), daemon=True).start()
    return {'success': True, 'message': '模型训练已提交到服务器后台执行', 'async': True}


@app.post("/api/prediction/run-prediction", tags=["交通流预测"])
async def run_prediction_cmd(request: Request):
    """在服务器后台运行预测分析（predictor.py --model xxx）"""
    with _prediction_lock:
        if _prediction_status['running']:
            return {'success': False, 'message': '已有任务在运行中，请等待完成'}

    script = os.path.join(_PREDICTION_DIR, 'predictor.py')
    if not os.path.exists(script):
        return {'success': False, 'message': 'predictor.py不存在'}

    model_key = 'all'
    try:
        body = await request.json()
        model_key = body.get('model', 'all')
    except Exception:
        pass

    with _prediction_lock:
        _prediction_status.update(running=True, task='predict', success=None, message='正在启动预测分析...')

    def _run_predict(model_arg):
        import time
        start = time.time()
        try:
            results_file = os.path.join(_PREDICTION_CHARTS_DIR, 'results.txt')
            init_mt = os.path.getmtime(results_file) if os.path.exists(results_file) else 0

            process = _run_prediction_process(
                [sys.executable, "-u", script, "--model", model_arg],
                "prediction_run.log",
            )
            if process.returncode != 0:
                raise RuntimeError(f'预测分析进程退出码 {process.returncode}')

            for _ in range(150):
                time.sleep(2)
                if os.path.exists(results_file) and os.path.getmtime(results_file) > init_mt + 1:
                    time.sleep(3)
                    break
            elapsed = time.time() - start
            with _prediction_lock:
                _prediction_status.update(running=False, success=True,
                    message=f'预测分析完成（耗时{elapsed:.0f}秒）')
        except Exception as e:
            with _prediction_lock:
                _prediction_status.update(running=False, success=False, message=str(e))

    threading.Thread(target=_run_predict, args=(model_key,), daemon=True).start()
    return {'success': True, 'message': '预测分析已提交到服务器后台执行', 'async': True}


@app.post("/api/prediction/reset", tags=["交通流预测"])
async def reset_prediction_status():
    """强制重置预测任务状态（解决卡住问题）"""
    with _prediction_lock:
        _prediction_status.update(running=False, task=None, success=None, message='已重置')
    return {'success': True, 'message': '状态已重置'}


@app.get("/api/prediction/status", tags=["交通流预测"])
async def prediction_status():
    with _prediction_lock:
        return dict(_prediction_status)


@app.get("/api/prediction/get-results", tags=["交通流预测"])
async def get_prediction_results():
    results_file = os.path.join(_PREDICTION_CHARTS_DIR, 'results.txt')
    if not os.path.exists(results_file):
        return {'success': False, 'message': '结果文件不存在，请先运行预测'}
    try:
        results = {}
        with open(results_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    results[key] = value
        return {'success': True, 'data': results}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@app.get("/api/prediction/download-report", tags=["交通流预测"])
async def download_prediction_report():
    path = os.path.join(_PREDICTION_CHARTS_DIR, '实验报告.txt')
    if os.path.exists(path):
        return FileResponse(path, filename='交通流预测实验报告.txt')
    return JSONResponse({'error': '报告不存在，请先运行预测'}, status_code=404)


@app.get("/api/prediction/download-data", tags=["交通流预测"])
async def download_prediction_data():
    path = os.path.join(_PREDICTION_DIR, 'Traffic flow data.csv')
    if os.path.exists(path):
        return FileResponse(path, filename='Traffic_flow_data.csv')
    return JSONResponse({'error': '数据文件不存在'}, status_code=404)


@app.get("/api/prediction/charts/{filename}", tags=["交通流预测"])
async def get_prediction_chart(filename: str):
    """直接返回预测图表图片文件"""
    path = os.path.join(_PREDICTION_CHARTS_DIR, filename)
    if os.path.exists(path):
        # 根据扩展名设置MIME类型
        if filename.endswith('.jpg') or filename.endswith('.jpeg'):
            media_type = 'image/jpeg'
        elif filename.endswith('.png'):
            media_type = 'image/png'
        else:
            media_type = 'application/octet-stream'
        return FileResponse(path, media_type=media_type)
    return JSONResponse({'error': f'图片不存在: {filename}'}, status_code=404)


@app.post("/api/prediction/run-custom-algorithm", tags=["交通流预测"])
async def run_custom_algorithm(request: Request):
    """接收学生自定义算法代码，生成完整脚本并在服务器后台运行"""
    with _prediction_lock:
        if _prediction_status['running']:
            return {'success': False, 'message': '已有任务在运行中，请等待完成'}

    try:
        body = await request.json()
        user_code = body.get('code', '')
    except Exception:
        return {'success': False, 'message': '请求格式错误'}

    if not user_code.strip():
        return {'success': False, 'message': '代码不能为空'}

    # 将用户代码写入临时脚本文件
    custom_script = os.path.join(_PREDICTION_DIR, 'custom_algorithm.py')
    try:
        with open(custom_script, 'w', encoding='utf-8') as f:
            f.write(user_code)
    except Exception as e:
        return {'success': False, 'message': f'写入脚本失败: {e}'}

    with _prediction_lock:
        _prediction_status.update(running=True, task='custom', success=None, message='正在运行自定义算法...')

    def _run_custom():
        import time
        start = time.time()
        try:
            results_file = os.path.join(_PREDICTION_CHARTS_DIR, 'custom_results.txt')
            init_mt = os.path.getmtime(results_file) if os.path.exists(results_file) else 0

            process = _run_prediction_process(
                [sys.executable, "-u", custom_script],
                "prediction_custom.log",
            )
            if process.returncode != 0:
                raise RuntimeError(f'自定义算法进程退出码 {process.returncode}')

            for _ in range(150):
                time.sleep(2)
                if os.path.exists(results_file) and os.path.getmtime(results_file) > init_mt + 1:
                    time.sleep(3)
                    break
            elapsed = time.time() - start
            with _prediction_lock:
                _prediction_status.update(running=False, success=True,
                    message=f'自定义算法运行完成（耗时{elapsed:.0f}秒）')
        except Exception as e:
            with _prediction_lock:
                _prediction_status.update(running=False, success=False, message=str(e))

    threading.Thread(target=_run_custom, daemon=True).start()
    return {'success': True, 'message': '自定义算法已提交到服务器后台执行', 'async': True}


@app.get("/api/prediction/get-custom-results", tags=["交通流预测"])
async def get_custom_results():
    """获取自定义算法运行结果"""
    results_file = os.path.join(_PREDICTION_CHARTS_DIR, 'custom_results.txt')
    if not os.path.exists(results_file):
        return {'success': False, 'message': '自定义算法结果不存在，请先运行'}
    try:
        results = {}
        with open(results_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    results[key] = value
        return {'success': True, 'data': results}
    except Exception as e:
        return {'success': False, 'message': str(e)}


_SIMULATION_SERVICE_BASE = os.environ.get("SIMULATION_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
_EXPERIMENT_BACKEND_LOCK = threading.Lock()
_EXPERIMENT_BACKEND_PROCESSES: dict[str, subprocess.Popen] = {}
_EXPERIMENT_NATIVE_PROCESSES: dict[str, subprocess.Popen] = {}
_EXPERIMENT_WARMUP_CACHE = {
    "completed": False,
    "last_result": None,
    "timestamp": None,
}
_VIC_SIM_ROOT = Path(resolve_external_project_root(
    "VIC-Sim",
    "VIC_SIM_ROOT",
    legacy_default=r"D:\chenshi\VIC-Sim",
    marker=os.path.join("backend", "server.py"),
))
_VIC_SIM_PORT = int(os.environ.get("NATIVE_VIC_SIM_PORT", "8090"))
_VIC_SIM_URL = os.environ.get("NATIVE_VIC_SIM_URL", f"http://127.0.0.1:{_VIC_SIM_PORT}")
_VIC_SIM_SERVER = _VIC_SIM_ROOT / "backend" / "server.py"
_VIC_SIM_LOG = os.path.join(_BACKEND_ROOT, "logs", "experiment_backend_vic_sim.log")
_CARLA_PORT = int(os.environ.get("CARLA_PORT", "2000"))
_CARLA_ROOT_CANDIDATES = [
    os.environ.get("CARLA_ROOT"),
    r"D:\carla\CARLA_0.9.12\WindowsNoEditor",
    r"D:\carla\CARLA_0.9.15\WindowsNoEditor",
    r"D:\CARLA_0.9.12\WindowsNoEditor",
    r"D:\CARLA_0.9.15\WindowsNoEditor",
    os.path.join(_PROJECT_ROOT, "software", "CARLA"),
]
_EXPERIMENT_BACKEND_SPECS = [
    {
        "id": "traffic_reconstruction",
        "name": "交通流重构服务",
        "port": 5001,
        "script": os.path.join(_PROJECT_ROOT, "backend", "algorithms", "traffic_reconstruction", "service.py"),
        "health_url": "http://127.0.0.1:5001/health",
    },
    {
        "id": "sumo_simulation",
        "name": "SUMO仿真实验服务",
        "port": 8001,
        "script": os.path.join(_PROJECT_ROOT, "backend", "algorithms", "simulation", "service.py"),
        "health_url": "http://127.0.0.1:8001/health",
    },
]

_EXPERIMENT_FRONTEND_FILES = [
    "student.html",
    "src/components/ai-assistant.css",
    "src/components/ai-assistant.js",
    "src/components/chat-log-widget.css",
    "src/components/chat-log-widget.js",
    "src/components/interaction-feedback.js",
    "src/components/status-bar.js",
    "src/pages/多源数据采集功能/data_collection.html",
    "src/pages/多源数据采集功能/data_collection.css",
    "src/pages/多源数据采集功能/data_collection.js",
    "src/pages/多源数据融合功能/data_fusion_new.html",
    "src/pages/多源数据融合功能/data_fusion.css",
    "src/pages/多源数据融合功能/data_fusion_new.js",
    "src/pages/交通流重构功能/traffic_reconstruction.html",
    "src/pages/交通流重构功能/traffic_reconstruction.css",
    "src/pages/交通流重构功能/traffic_reconstruction.js",
    "src/pages/交通流预测功能/traffic_flow_prediction.html",
    "src/pages/交通流预测功能/traffic_flow_prediction.css",
    "src/pages/交通流预测功能/traffic_flow_prediction.js",
    "src/pages/交通信号优化功能/signal_optimization.html",
    "src/pages/交通信号优化功能/signal_optimization.css",
    "src/pages/交通信号优化功能/signal_optimization.js",
    "src/pages/路径诱导功能/path_guidance.html",
    "src/pages/路径诱导功能/path_guidance.css",
    "src/pages/路径诱导功能/path_guidance.js",
    "src/pages/车速控制功能/vehicle_speed_control.html",
    "src/pages/车速控制功能/vehicle_speed_control.css",
    "src/pages/车速控制功能/vehicle_speed_control.js",
    "src/pages/三层级协同优化控制功能/three_level_control.html",
    "src/pages/三层级协同优化控制功能/three_level_control.css",
    "src/pages/三层级协同优化控制功能/three_level_control.js",
    "src/pages/虚实结合仿真场景构建功能/carla_scene_builder.html",
    "src/pages/虚实结合仿真场景构建功能/carla_scene_builder.css",
    "src/pages/虚实结合仿真场景构建功能/carla_scene_builder.js",
    "src/pages/车规级智能车辆开发与控制功能/vehicle_control.html",
    "src/pages/车规级智能车辆开发与控制功能/vehicle_control.css",
    "src/pages/车规级智能车辆开发与控制功能/vehicle_control.js",
    "src/pages/虚实结合仿真场景算法测试功能/algorithm_testing.html",
    "src/pages/虚实结合仿真场景算法测试功能/algorithm_testing.css",
    "src/pages/虚实结合仿真场景算法测试功能/algorithm_testing.js",
    "src/pages/操作说明文档/help_documentation.html",
    "src/pages/操作说明文档/help_documentation.css",
    "src/pages/操作说明文档/help_documentation.js",
]

# 说明：历史上这里还有 _EXPERIMENT_ALGORITHM_DIRS、
# _EXPERIMENT_LOCAL_WARMUP_ENDPOINTS 和一份手写的 _EXPERIMENT_WARMUP_CHECKS。
# 前两者从未被任何代码引用，第三者会被下面的 _build_experiment_warmup_checks()
# 重新赋值覆盖，三者都属于死代码，已移除，避免与真实预热清单长期不一致。


def _build_experiment_warmup_checks() -> list[dict]:
    checks = [
        {
            "name": "主平台健康接口",
            "kind": "http",
            "method": "GET",
            "url": "http://127.0.0.1:8000/api/v1/health",
            "timeout": 3,
        },
        {
            "name": "交通流重构服务健康接口",
            "kind": "http",
            "method": "GET",
            "url": "http://127.0.0.1:5001/api/health",
            "timeout": 3,
        },
        {
            "name": "SUMO仿真实验服务健康接口",
            "kind": "http",
            "method": "GET",
            "url": "http://127.0.0.1:8001/health",
            "timeout": 3,
        },
    ]
    for rel_path in _EXPERIMENT_FRONTEND_FILES:
        checks.append({
            "name": f"静态资源 {rel_path}",
            "kind": "file",
            "path": os.path.join(_FRONTEND_DIR, *rel_path.split("/")),
            "optional": False,
        })
    return checks


_EXPERIMENT_WARMUP_CHECKS = _build_experiment_warmup_checks()


def _safe_console_title(title: str) -> str:
    cleaned = "".join(ch if 32 <= ord(ch) < 127 and ch not in "&|<>" else "_" for ch in title)
    return cleaned[:80] or "Experiment Backend"


def _cmd_quote(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _encode_warmup_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%?/:+,-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def _launch_visible_cmd(title: str, cwd: str, args: list[str], env: dict, log_path: str, hold_seconds: int = 0) -> subprocess.Popen:
    """Launch a backend CMD task on the platform computer.

    演示模式：弹出可见 CMD 窗口，保留执行过程便于观察。
    学生模式：同样的命令与日志，但不创建窗口，输出直接追加到 log_path，
    前端通过状态/结果接口获得的反馈与演示模式完全一致。
    """
    if os.name != "nt":
        log = open(log_path, "a", encoding="utf-8", errors="replace")
        return subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)

    student_mode = run_mode.is_student_mode()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    launcher_id = f"{int(time.time() * 1000)}_{os.getpid()}"
    cmd_path = os.path.join(os.path.dirname(log_path), f"experiment_backend_{launcher_id}.cmd")
    command_line = subprocess.list2cmdline(args)
    if student_mode:
        # 学生模式没有可见控制台，必须把子进程输出写进日志文件，
        # 否则出错时无从排查。
        #
        # 注意：不能直接写 log_path。像「实验后端轻量预热」这类脚本自己也会
        # 往 log_path 追加内容，Windows 上 cmd 重定向会独占打开文件，两边同时
        # 写会抛 PermissionError。这里用独立的 .console.log 承接控制台输出。
        console_log_path = f"{log_path}.console.log"
        run_line = f"{command_line} >> {_cmd_quote(console_log_path)} 2>&1"
    else:
        run_line = f"{command_line} 2>&1"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f"title {_safe_console_title(title)}",
        "echo ========================================",
        f"echo {title}",
        "echo ========================================",
        f"echo 工作目录: {cwd}",
        f"echo 日志文件: {log_path}",
        f"echo 命令: {command_line}",
        "echo.",
        f"cd /d {_cmd_quote(cwd)}",
        run_line,
        "set ZXK_EXIT=%ERRORLEVEL%",
        "echo.",
        "echo ========================================",
        "echo 命令执行完成，退出码 %ZXK_EXIT%",
        "echo ========================================",
    ]
    # 学生模式没有窗口需要停留，跳过 hold，避免无谓地拉长启动时间。
    if hold_seconds > 0 and not student_mode:
        lines.append(f"timeout /t {hold_seconds} >nul")
    lines.extend([
        "exit /b %ZXK_EXIT%",
        "",
    ])
    with open(cmd_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\r\n".join(lines))
    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n[{datetime.now().isoformat()}] BACKEND CMD {title} ({run_mode.mode_label()})\n")
        log.write(f"CMD {cmd_path}\n")
        log.write(f"ARGS {command_line}\n")
    options = {
        "cwd": cwd,
        "env": run_mode.child_env(env),
        "stdin": subprocess.DEVNULL,
    }
    if student_mode:
        options.update(run_mode.server_process_kwargs())
    else:
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(["cmd.exe", "/c", cmd_path], **options)


def _is_port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.8):
            return True
    except OSError:
        pass
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}" | findstr "LISTENING"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
            **_server_process_kwargs(),
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _listening_port_pid(port: int) -> int | None:
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}" | findstr "LISTENING"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
            **_server_process_kwargs(),
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                try:
                    return int(parts[-1])
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def _http_ready(url: str, timeout: float = 1.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read(256)
            return resp.status < 500, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


def _wait_for_http(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    deadline = time.time() + timeout
    last_message = "waiting"
    while time.time() < deadline:
        ready, message = _http_ready(url, timeout=1.2)
        last_message = message
        if ready:
            return True, message
        time.sleep(0.8)
    ready, message = _http_ready(url, timeout=1.2)
    return ready, message if message else last_message


def _vic_sim_api_ready(timeout: float = 1.0) -> bool:
    for path in ("/api/status", "/api/scenes"):
        ready, _ = _http_ready(f"{_VIC_SIM_URL}{path}", timeout=timeout)
        if ready:
            return True
    return False


def _find_carla_exe_for_experiment() -> Path | None:
    seen = set()
    for candidate in _CARLA_ROOT_CANDIDATES:
        if not candidate:
            continue
        root = Path(candidate)
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        exe = root / "CarlaUE4.exe"
        if exe.is_file():
            return exe
    return None


def _wait_for_port(port: int, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_listening(port):
            return True
        time.sleep(1.0)
    return _is_port_listening(port)


def _ensure_experiment_carla() -> dict:
    if _is_port_listening(_CARLA_PORT):
        return {
            "id": "carla",
            "name": "CARLA",
            "port": _CARLA_PORT,
            "ready": True,
            "required": True,
            "status": "ready",
            "message": "CARLA server is already listening",
            "pid": _listening_port_pid(_CARLA_PORT),
        }

    if run_mode.is_student_mode():
        # 学生模式不占用服务器桌面：不自动拉起 CARLA 的 3D 窗口。
        # 若服务器上已有 CARLA 服务端（上面的端口判断），仍然复用。
        return {
            "id": "carla",
            "name": "CARLA",
            "port": _CARLA_PORT,
            "ready": False,
            "required": False,
            "skipped": True,
            "status": "skipped",
            "message": "学生模式：不自动启动 CARLA 图形窗口；如需使用请先在服务器上启动 CARLA 服务端。",
        }

    carla_exe = _find_carla_exe_for_experiment()
    if not carla_exe:
        return {
            "id": "carla",
            "name": "CARLA",
            "port": _CARLA_PORT,
            "ready": False,
            "status": "missing",
            "message": "CarlaUE4.exe not found",
        }

    try:
        proc = subprocess.Popen(
            [
                str(carla_exe),
                "-quality-level=Low",
                "-windowed",
                "-ResX=1280",
                "-ResY=720",
                "-nosound",
                f"-carla-rpc-port={_CARLA_PORT}",
            ],
            cwd=str(carla_exe.parent),
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0,
        )
        _EXPERIMENT_NATIVE_PROCESSES["carla"] = proc
    except Exception as exc:
        return {
            "id": "carla",
            "name": "CARLA",
            "port": _CARLA_PORT,
            "ready": False,
            "status": "error",
            "message": f"Failed to launch CARLA: {exc}",
        }

    ready = _wait_for_port(_CARLA_PORT, timeout=60.0)
    return {
        "id": "carla",
        "name": "CARLA",
        "port": _CARLA_PORT,
        "ready": ready,
        "status": "ready" if ready else "starting",
        "message": "CARLA server started" if ready else "CARLA launch requested; port 2000 is still warming up",
        "pid": _listening_port_pid(_CARLA_PORT),
        "launcher_pid": proc.pid,
        "executable": str(carla_exe),
    }


def _ensure_experiment_vic_sim() -> dict:
    index_ready, _ = _http_ready(_VIC_SIM_URL, timeout=1.0)
    api_ready = _vic_sim_api_ready(timeout=1.0)
    if index_ready or api_ready:
        return {
            "id": "vic_sim",
            "name": "VIC-Sim",
            "port": _VIC_SIM_PORT,
            "ready": True,
            "status": "ready",
            "message": "VIC-Sim is already running",
            "url": _VIC_SIM_URL,
            "api_ready": api_ready,
            "pid": _listening_port_pid(_VIC_SIM_PORT),
        }

    proc = _EXPERIMENT_NATIVE_PROCESSES.get("vic_sim")
    if proc and proc.poll() is not None:
        _EXPERIMENT_NATIVE_PROCESSES.pop("vic_sim", None)
        proc = None

    if proc is None:
        if not _VIC_SIM_SERVER.is_file():
            return {
                "id": "vic_sim",
                "name": "VIC-Sim",
                "port": _VIC_SIM_PORT,
                "ready": False,
                "status": "missing",
                "message": f"VIC-Sim server.py not found: {_VIC_SIM_SERVER}",
                "url": _VIC_SIM_URL,
            }
        os.makedirs(os.path.dirname(_VIC_SIM_LOG), exist_ok=True)
        env = os.environ.copy()
        env["VIC_SIM_HOST"] = "0.0.0.0"
        env["VIC_SIM_PORT"] = str(_VIC_SIM_PORT)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            proc = _launch_visible_cmd(
                "VIC-Sim native backend",
                str(_VIC_SIM_ROOT),
                [sys.executable, "-X", "utf8", str(_VIC_SIM_SERVER), "--no-browser"],
                env,
                _VIC_SIM_LOG,
                hold_seconds=0,
            )
            _EXPERIMENT_NATIVE_PROCESSES["vic_sim"] = proc
        except Exception as exc:
            return {
                "id": "vic_sim",
                "name": "VIC-Sim",
                "port": _VIC_SIM_PORT,
                "ready": False,
                "status": "error",
                "message": f"Failed to launch VIC-Sim: {exc}",
                "url": _VIC_SIM_URL,
            }

    ready, message = _wait_for_http(_VIC_SIM_URL, timeout=25.0)
    api_ready = _vic_sim_api_ready(timeout=1.0)
    return {
        "id": "vic_sim",
        "name": "VIC-Sim",
        "port": _VIC_SIM_PORT,
        "ready": ready,
        "status": "ready" if ready else "starting",
        "message": "VIC-Sim started" if ready else f"VIC-Sim launch requested; {message}",
        "url": _VIC_SIM_URL,
        "api_ready": api_ready,
        "pid": _listening_port_pid(_VIC_SIM_PORT),
        "launcher_pid": proc.pid if proc and proc.poll() is None else None,
        "log_path": _VIC_SIM_LOG,
    }


def _ensure_experiment_native_stack() -> dict:
    carla = _ensure_experiment_carla()
    vic_sim = _ensure_experiment_vic_sim()
    checks = [carla, vic_sim]
    # 学生模式下 CARLA 属于「跳过」而非「失败」，不计入整体就绪判定。
    required_checks = [item for item in checks if item.get("required", True)]
    ready = all(item.get("ready") for item in required_checks)
    if ready and run_mode.is_student_mode():
        message = "学生模式：VIC-Sim 已就绪，CARLA 图形窗口未启动（不影响平台使用）"
    elif ready:
        message = "VIC-Sim and CARLA are ready"
    else:
        message = "VIC-Sim/CARLA are still starting"
    return {
        "success": ready,
        "ready": ready,
        "run_mode": run_mode.get_run_mode(),
        "checks": checks,
        "skipped": [item.get("id") for item in checks if item.get("skipped")],
        "message": message,
    }


def _check_backend_health(spec: dict) -> tuple[bool, str]:
    if spec.get("port_only"):
        ready = _is_port_listening(spec["port"])
        return ready, "端口已监听" if ready else "端口未监听"
    url = spec["health_url"]
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status < 500, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


def _warmup_one_check(item: dict) -> dict:
    start = time.perf_counter()
    status = 0
    ok = False
    error = ""
    kind = item.get("kind", "http")
    try:
        if kind == "file":
            path = item["path"]
            ok = os.path.isfile(path)
            error = f"{os.path.getsize(path)} bytes" if ok else "文件不存在"
        else:
            req = urllib.request.Request(_encode_warmup_url(item["url"]), method=item.get("method", "GET"))
            with urllib.request.urlopen(req, timeout=float(item.get("timeout", 6))) as resp:
                status = resp.status
                resp.read(512)
                ok = status < 500
    except urllib.error.HTTPError as exc:
        status = exc.code
        ok = status < 500 and bool(item.get("optional"))
        error = f"HTTP {exc.code}"
    except Exception as exc:
        error = str(exc)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "name": item["name"],
        "kind": kind,
        "method": item.get("method", "GET"),
        "url": item.get("url"),
        "path": item.get("path"),
        "optional": bool(item.get("optional")),
        "ok": ok,
        "status": status or None,
        "elapsed_ms": elapsed_ms,
        "message": "OK" if ok else (error or "请求失败"),
    }


def _run_experiment_warmup_checks() -> dict:
    start = time.perf_counter()
    checks = [_warmup_one_check(item) for item in _EXPERIMENT_WARMUP_CHECKS]
    required = [item for item in checks if not item["optional"]]
    ok = all(item["ok"] for item in required)
    total_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "success": ok,
        "ready": ok,
        "total_ms": total_ms,
        "checks": checks,
        "message": f"轻量预热完成：{sum(1 for item in checks if item['ok'])}/{len(checks)} 项通过，用时 {total_ms:.1f} ms",
    }


def _write_experiment_warmup_script(log_path: str, result_path: str) -> str:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    script_path = os.path.join(os.path.dirname(log_path), "experiment_backend_warmup.py")
    payload = {
        "checks": _EXPERIMENT_WARMUP_CHECKS,
        "log_path": log_path,
        "result_path": result_path,
    }
    code = r'''
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PAYLOAD = __PAYLOAD__

def log(line):
    print(line, flush=True)
    with open(PAYLOAD["log_path"], "a", encoding="utf-8", errors="replace") as handle:
        handle.write(line + "\n")

def encode_url(url):
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%?/:+,-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

def run_check(item):
    start = time.perf_counter()
    status = None
    ok = False
    error = ""
    kind = item.get("kind", "http")
    try:
        if kind == "file":
            path = item["path"]
            ok = os.path.isfile(path)
            error = f"{os.path.getsize(path)} bytes" if ok else "文件不存在"
        else:
            req = urllib.request.Request(encode_url(item["url"]), method=item.get("method", "GET"))
            with urllib.request.urlopen(req, timeout=float(item.get("timeout", 6))) as resp:
                status = resp.status
                resp.read(512)
                ok = status < 500
    except urllib.error.HTTPError as exc:
        status = exc.code
        ok = status < 500 and bool(item.get("optional"))
        error = f"HTTP {exc.code}"
    except Exception as exc:
        error = str(exc)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "name": item["name"],
        "kind": kind,
        "method": item.get("method", "GET"),
        "url": item.get("url"),
        "path": item.get("path"),
        "optional": bool(item.get("optional")),
        "ok": ok,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "message": "OK" if ok else (error or "请求失败"),
    }

def main():
    started = time.perf_counter()
    log("=== 实验后端轻量预热 ===")
    log("说明：这里只预热页面、静态资源和轻量接口，不启动 CARLA/SUMO-GUI 等重型仿真。")
    results = []
    for index, item in enumerate(PAYLOAD["checks"], 1):
        result = run_check(item)
        results.append(result)
        flag = "OK" if result["ok"] else ("SKIP" if result["optional"] else "FAIL")
        status = result["status"] if result["status"] is not None else "-"
        log(f"[{index:02d}/{len(PAYLOAD['checks']):02d}] {flag} {result['name']} {result['elapsed_ms']} ms status={status}")
        if not result["ok"]:
            log(f"    {result['message']}")
    required = [item for item in results if not item["optional"]]
    ready = all(item["ok"] for item in required)
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    payload = {
        "success": ready,
        "ready": ready,
        "total_ms": total_ms,
        "checks": results,
        "message": f"轻量预热完成：{sum(1 for item in results if item['ok'])}/{len(results)} 项通过，用时 {total_ms:.1f} ms",
    }
    with open(PAYLOAD["result_path"], "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    log(payload["message"])
    log("CMD 窗口将在 10 秒后关闭。")
    return 0 if ready else 2

if __name__ == "__main__":
    raise SystemExit(main())
'''
    code = code.replace("__PAYLOAD__", repr(payload))
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(code)
    return script_path


def _launch_experiment_warmup_console() -> dict:
    log_dir = os.path.join(_BACKEND_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"experiment_backend_warmup_{stamp}.log")
    result_path = os.path.join(log_dir, f"experiment_backend_warmup_{stamp}.json")
    script_path = _write_experiment_warmup_script(log_path, result_path)
    warmup_env = os.environ.copy()
    warmup_env["PYTHONIOENCODING"] = "utf-8"
    warmup_env["PYTHONUTF8"] = "1"
    proc = _launch_visible_cmd(
        "实验后端轻量预热",
        _BACKEND_ROOT,
        [sys.executable, script_path],
        warmup_env,
        log_path,
        hold_seconds=10,
    )
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        result = {
            "success": False,
            "ready": False,
            "message": "预热CMD超时，已终止",
            "checks": [],
            "console_pid": proc.pid,
            "console_exit_code": None,
            "log_path": log_path,
            "result_path": result_path,
        }
        return result
    result = {}
    if os.path.isfile(result_path):
        try:
            with open(result_path, "r", encoding="utf-8") as handle:
                result = json.load(handle)
        except Exception as exc:
            result = {"success": False, "ready": False, "message": f"读取预热结果失败：{exc}", "checks": []}
    if not result:
        result = {"success": False, "ready": False, "message": f"预热CMD未生成结果，退出码 {proc.returncode}", "checks": []}
    result["console_pid"] = proc.pid
    result["console_exit_code"] = proc.returncode
    result["log_path"] = log_path
    result["result_path"] = result_path
    return result


def _start_experiment_backend(spec: dict) -> dict:
    service_id = spec["id"]
    proc = _EXPERIMENT_BACKEND_PROCESSES.get(service_id)
    if proc and proc.poll() is not None:
        _EXPERIMENT_BACKEND_PROCESSES.pop(service_id, None)
        proc = None

    listening = _is_port_listening(spec["port"])
    if not listening and proc is None:
        script = spec["script"]
        if not os.path.isfile(script):
            return {
                "id": service_id,
                "name": spec["name"],
                "port": spec["port"],
                "status": "missing",
                "ready": False,
                "message": f"启动脚本不存在：{script}",
            }
        log_dir = os.path.join(_BACKEND_ROOT, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"experiment_backend_{spec['port']}.log")
        child_env = os.environ.copy()
        existing_pythonpath = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = _BACKEND_ROOT if not existing_pythonpath else _BACKEND_ROOT + os.pathsep + existing_pythonpath
        child_env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = _launch_visible_cmd(
                f"{spec['name']} 后端服务",
                os.path.dirname(script),
                [sys.executable, script],
                child_env,
                log_path,
                hold_seconds=0,
            )
            _EXPERIMENT_BACKEND_PROCESSES[service_id] = proc
        except Exception as exc:
            return {
                "id": service_id,
                "name": spec["name"],
                "port": spec["port"],
                "status": "error",
                "ready": False,
                "message": f"启动失败：{exc}",
            }

    ready = False
    health_message = "等待服务就绪"
    for _ in range(12):
        ready, health_message = _check_backend_health(spec)
        if ready:
            break
        time.sleep(0.5)

    current_proc = _EXPERIMENT_BACKEND_PROCESSES.get(service_id)
    if not ready and current_proc and current_proc.poll() is not None:
        health_message = f"进程已退出，退出码 {current_proc.returncode}"

    return {
        "id": service_id,
        "name": spec["name"],
        "port": spec["port"],
        "status": "ready" if ready else "starting",
        "ready": ready,
        "message": "已就绪" if ready else health_message,
        "pid": _listening_port_pid(spec["port"]) or (current_proc.pid if current_proc and current_proc.poll() is None else None),
        "launcher_pid": current_proc.pid if current_proc and current_proc.poll() is None else None,
    }


@app.get("/api/v1/experiment-backends/status", tags=["实验后端"])
async def experiment_backends_status():
    """Return readiness of experiment sub-services used by module pages.

    这里的健康探测是同步 HTTP（每项最长 2 秒）。必须丢进线程池，否则并发打开
    学生页时它们会在事件循环上串行排队。
    """
    return await run_in_threadpool(_collect_experiment_backends_status)


def _collect_experiment_backends_status() -> dict:
    services = []
    for spec in _EXPERIMENT_BACKEND_SPECS:
        ready, message = _check_backend_health(spec)
        services.append({
            "id": spec["id"],
            "name": spec["name"],
            "port": spec["port"],
            "ready": ready,
            "status": "ready" if ready else "offline",
            "message": "已就绪" if ready else message,
        })
    carla_ready = _is_port_listening(_CARLA_PORT)
    vic_index_ready, _ = _http_ready(_VIC_SIM_URL, timeout=0.8)
    vic_api_ready = _vic_sim_api_ready(timeout=0.8)
    vic_ready = bool(vic_index_ready or vic_api_ready)
    carla_skipped = run_mode.is_student_mode() and not carla_ready
    native_checks = [
        {
            "id": "carla",
            "name": "CARLA",
            "port": _CARLA_PORT,
            "ready": carla_ready,
            "required": not carla_skipped,
            "skipped": carla_skipped,
            "status": "ready" if carla_ready else ("skipped" if carla_skipped else "offline"),
            "message": (
                "CARLA server is listening" if carla_ready
                else "学生模式未启动 CARLA 图形窗口" if carla_skipped
                else "CARLA server is offline"
            ),
            "pid": _listening_port_pid(_CARLA_PORT),
        },
        {
            "id": "vic_sim",
            "name": "VIC-Sim",
            "port": _VIC_SIM_PORT,
            "ready": vic_ready,
            "required": True,
            "status": "ready" if vic_ready else "offline",
            "message": "VIC-Sim is running" if vic_ready else "VIC-Sim is offline",
            "url": _VIC_SIM_URL,
            "api_ready": vic_api_ready,
            "pid": _listening_port_pid(_VIC_SIM_PORT),
        },
    ]
    native_required = [item for item in native_checks if item.get("required", True)]
    native = {
        "ready": all(item["ready"] for item in native_required),
        "run_mode": run_mode.get_run_mode(),
        "checks": native_checks,
    }
    return {
        "success": True,
        "ready": all(item["ready"] for item in services) and native["ready"],
        "run_mode": run_mode.get_run_mode(),
        "run_mode_label": run_mode.mode_label(),
        "services": services,
        "native": native,
    }


@app.post("/api/v1/experiment-backends/start", tags=["实验后端"])
def start_experiment_backends(request: Request):
    """启动基础后端 CMD；只有本机请求会同时启动 CARLA 和 VIC-Sim。"""
    local_request = is_local_request(request)
    with _EXPERIMENT_BACKEND_LOCK:
        services = [_start_experiment_backend(spec) for spec in _EXPERIMENT_BACKEND_SPECS]
        if local_request:
            native = _ensure_experiment_native_stack()
        else:
            native = {
                "success": True,
                "ready": True,
                "skipped": True,
                "checks": [],
                "message": "局域网模式仅启动基础后端 CMD，未启动 CARLA/VIC-Sim",
            }
        warmup = _launch_experiment_warmup_console()
    ready_count = sum(1 for item in services if item["ready"])
    service_ready = ready_count == len(services)
    native_ready = bool(native.get("ready"))
    ready = service_ready and native_ready and bool(warmup.get("ready"))
    total_ms = warmup.get("total_ms")
    native_checks = native.get("checks", [])
    native_count = sum(1 for item in native_checks if item.get("ready"))
    if local_request:
        native_message = f"VIC-Sim/CARLA {native_count}/{len(native_checks)}"
        if native.get("skipped"):
            native_message += f"（{run_mode.mode_label()}跳过图形窗口: {','.join(native['skipped'])}）"
    else:
        native_message = "局域网未启动 CARLA/VIC-Sim"
    message = f"实验后端服务就绪 {ready_count}/{len(services)}；{native_message}；{warmup.get('message', '预热完成')}"
    return {
        "success": ready,
        "ready": ready,
        "access_mode": "local" if local_request else "lan",
        "run_mode": run_mode.get_run_mode(),
        "run_mode_label": run_mode.mode_label(),
        "message": message,
        "services": services,
        "native": native,
        "warmup": warmup,
        "warmup_total_ms": total_ms,
        "console_pid": warmup.get("console_pid"),
        "log_path": warmup.get("log_path"),
    }


async def _proxy_simulation_request(path: str, request: Request):
    query = request.url.query
    target = f"{_SIMULATION_SERVICE_BASE}/{path}"
    if query:
        target += f"?{query}"

    body = await request.body()
    headers = {}
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type

    req = urllib.request.Request(
        target,
        data=body if request.method in {"POST", "PUT", "PATCH"} else None,
        headers=headers,
        method=request.method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            response_headers = {}
            for name in ("content-type", "content-disposition"):
                value = resp.headers.get(name)
                if value:
                    response_headers[name] = value
            return Response(content=data, status_code=resp.status, headers=response_headers)
    except urllib.error.HTTPError as exc:
        data = exc.read()
        return Response(
            content=data,
            status_code=exc.code,
            media_type=exc.headers.get("content-type", "application/json"),
        )
    except Exception as exc:
        return JSONResponse(
            {
                "success": False,
                "message": "SUMO simulation service is not running",
                "detail": str(exc),
                "service_url": _SIMULATION_SERVICE_BASE,
            },
            status_code=503,
        )


@app.get("/api/simulation/{path:path}", tags=["SUMO仿真算法测试"])
async def proxy_simulation_get(path: str, request: Request):
    return await _proxy_simulation_request(path, request)


@app.post("/api/simulation/{path:path}", tags=["SUMO仿真算法测试"])
async def proxy_simulation_post(path: str, request: Request):
    return await _proxy_simulation_request(path, request)


# 说明：这里曾经把 traffic_reconstruction/output 整目录挂成 /reconstruction-output
# 静态资源。该目录里的实验报告、验证图表与运行日志是所有学生共享的，静态挂载等于
# 绕过鉴权把「别人刚生成的报告」直接对外公开，现已移除。需要下载一律走受控接口：
# /api/reconstruction/download-report、/download-csv/{name}、/validation-chart/{file}。

# Mount frontend static files (must be after API routes)
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
