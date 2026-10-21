"""Visible backend launchers for SUMO experiment modules."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import run_mode

router = APIRouter()

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.dirname(APP_ROOT)
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_ROOT, ".."))

PATH_GUIDANCE_DIR = os.path.join(PROJECT_ROOT, "backend", "algorithms", "path_guidance")
PATH_GUIDANCE_SCRIPT = os.path.join(PATH_GUIDANCE_DIR, "run_path_guidance.py")
PATH_GUIDANCE_OUTPUT_DIR = os.path.join(PATH_GUIDANCE_DIR, "output")
THREE_LEVEL_DIR = os.path.join(PROJECT_ROOT, "backend", "algorithms", "three_level_control")
THREE_LEVEL_SCRIPT = os.path.join(THREE_LEVEL_DIR, "run_three_level.py")
THREE_LEVEL_OUTPUT_DIR = os.path.join(THREE_LEVEL_DIR, "output")

PATH_GUIDANCE_ALGOS = {"dijkstra": 1, "astar": 2, "ssp": 3}
PATH_GUIDANCE_FLOW_MODES = {
    "normal": {"label": "普通模式（当前流量）", "multiplier": 1.0},
    "high": {"label": "高流量模式（当前流量 × 1.7）", "multiplier": 1.7},
}
THREE_SIGNAL_ALGOS = {"turbo", "bo", "dqn", "ppo", "ga", "pso"}
THREE_PATH_ALGOS = {"dijkstra", "ssp", "astar"}
THREE_SPEED_ALGOS = {"idm", "acc", "cacc", "pid"}

path_lock = threading.Lock()
path_process = None
path_started_at = 0.0
path_status_data = {
    "running": False,
    "success": None,
    "message": "未运行",
    "config_name": None,
    "algorithm": None,
    "flow_level": None,
    "flow_mode": None,
    "flow_multiplier": None,
    "pr": None,
    "elapsed": 0,
    "pid": None,
    "results": None,
    "log_path": None,
    "started_at": None,
}

three_lock = threading.Lock()
three_process = None
three_started_at = 0.0
three_status_data = {
    "running": False,
    "success": None,
    "message": "未运行",
    "config_name": None,
    "elapsed": 0,
    "pid": None,
    "results": None,
    "log_path": None,
    "started_at": None,
}


def resolve_sumo_home():
    env_home = os.environ.get("SUMO_HOME", "").strip().strip('"').rstrip(";")
    candidates = [
        env_home,
        os.path.join(PROJECT_ROOT, "software", "SUMO"),
        os.path.join(PROJECT_ROOT, "tools", "sumo"),
        r"D:\Download\SUMO",
        r"D:\chenshi\World Model\software\SUMO",
        r"D:\SUMO",
        r"D:\software\SUMO",
        r"C:\Program Files (x86)\Eclipse\Sumo",
        r"C:\Program Files\Eclipse\Sumo",
    ]
    which_gui = shutil.which("sumo-gui")
    if which_gui:
        candidates.insert(0, os.path.dirname(os.path.dirname(which_gui)))
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(os.path.join(candidate, "bin", "sumo-gui.exe")) or os.path.isfile(os.path.join(candidate, "bin", "sumo.exe")):
            return os.path.abspath(candidate)
    return None


def process_env():
    env = run_mode.child_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["ZXK_ALGO_PYTHON_EXE"] = sys.executable
    sumo_home = resolve_sumo_home()
    if sumo_home:
        env["SUMO_HOME"] = sumo_home
        env["PATH"] = os.path.join(sumo_home, "bin") + os.pathsep + env.get("PATH", "")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = PROJECT_ROOT if not existing_pythonpath else PROJECT_ROOT + os.pathsep + existing_pythonpath
    return env


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def launch_visible_console(title, cwd, args, env, log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    safe_title = title.replace("&", " ").replace("|", " ").replace("<", " ").replace(">", " ")
    if run_mode.is_student_mode():
        # 学生模式：不弹 CMD 窗口，算法进程输出直接写入 backend_cmd.log。
        # 前端仍通过 /status、/results 轮询获得同样的反馈。
        with open(log_path, "a", encoding="utf-8", errors="replace") as log:
            log.write(f"\n[{datetime.now().isoformat()}] LAUNCH {safe_title} (student mode, no window)\n")
            log.write("ARGS " + " ".join(args) + "\n")
        log_handle = open(log_path, "a", encoding="utf-8", errors="replace")
        return subprocess.Popen(
            args,
            cwd=cwd,
            env=run_mode.child_env(env),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            **run_mode.server_process_kwargs(),
        )
    if os.name == "nt":
        launcher_id = f"{int(time.time() * 1000)}_{os.getpid()}"
        cmd_path = os.path.join(os.path.dirname(log_path), f"launch_{launcher_id}.cmd")
        tee_script = os.path.join(APP_ROOT, "tee_console.py")
        tee_args = [
            sys.executable,
            "-u",
            tee_script,
            "--cwd",
            cwd,
            "--log",
            log_path,
            "--title",
            safe_title,
            "--",
            *args,
        ]
        tee_command = subprocess.list2cmdline(tee_args)
        title_ascii = "ZXK Experiment CMD"
        if "dijkstra" in safe_title.lower() or "ssp" in safe_title.lower() or "astar" in safe_title.lower():
            title_ascii = "ZXK PathGuidance CMD"
        title_ascii = (title_ascii + " - " + "".join(ch if 32 <= ord(ch) < 127 and ch not in "&|<>" else "_" for ch in safe_title))[:100]
        cmd_script = "\r\n".join([
            "@echo off",
            "chcp 65001 >nul",
            f"title {title_ascii}",
            "set PYTHONIOENCODING=utf-8",
            "set PYTHONUTF8=1",
            "set PYTHONUNBUFFERED=1",
            "cls",
            "echo ============================================================",
            "echo 路径诱导 CMD 输出窗口 / Path Guidance CMD Output",
            "echo ============================================================",
            f"echo 实验: {safe_title}",
            f"echo 日志: {log_path}",
            "echo 说明: 下方会实时显示每30s路径诱导决策、CAV改道和拥堵路段信息。",
            "echo.",
            tee_command,
            "set ZXK_EXIT=%ERRORLEVEL%",
            "echo.",
            "echo Backend command finished. ExitCode=%ZXK_EXIT%",
            "echo.",
            "echo This window will stay open so you can inspect CMD output.",
            "",
        ])
        with open(cmd_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(cmd_script)
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"\n[{datetime.now().isoformat()}] LAUNCH {safe_title}\n")
            log.write("ARGS " + " ".join(args) + "\n")
            log.write(f"CMD {cmd_path}\n")
            log.write(f"TEE {tee_script}\n")
        return subprocess.Popen(
            ["cmd.exe", "/k", cmd_path],
            cwd=cwd,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    log = open(log_path, "a", encoding="utf-8", errors="replace")
    return subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)


def read_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def file_modified_after(path, timestamp):
    if not timestamp or not os.path.isfile(path):
        return False
    try:
        return os.path.getmtime(path) >= timestamp - 0.5
    except OSError:
        return False


def safe_output_dir(base_dir, config_name):
    if not config_name or any(ch in config_name for ch in "\\/:*?\"<>|"):
        return None
    path = os.path.abspath(os.path.join(base_dir, config_name))
    base = os.path.abspath(base_dir)
    if path != base and path.startswith(base + os.sep):
        return path
    return None


def list_output_files(base_dir, config_name):
    out_dir = safe_output_dir(base_dir, config_name)
    if not out_dir or not os.path.isdir(out_dir):
        return None
    files = []
    for name in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, name)
        if os.path.isfile(path):
            files.append({
                "name": name,
                "size": os.path.getsize(path),
                "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
            })
    return {"config_name": config_name, "files": files}


def output_file_response(base_dir, config_name, filename):
    out_dir = safe_output_dir(base_dir, config_name)
    if not out_dir:
        return JSONResponse({"detail": "invalid output path"}, status_code=400)
    safe_name = os.path.basename(filename)
    path = os.path.abspath(os.path.join(out_dir, safe_name))
    if not path.startswith(os.path.abspath(out_dir) + os.sep) or not os.path.isfile(path):
        return JSONResponse({"detail": "file not found"}, status_code=404)
    media_type = "application/octet-stream"
    lower = safe_name.lower()
    if lower.endswith((".png", ".jpg", ".jpeg")):
        media_type = "image/png" if lower.endswith(".png") else "image/jpeg"
    elif lower.endswith(".json"):
        media_type = "application/json"
    elif lower.endswith(".csv"):
        media_type = "text/csv"
    elif lower.endswith(".xml"):
        media_type = "application/xml"
    return FileResponse(path, media_type=media_type, filename=safe_name)


def path_config_name(algorithm, flow_level, pr):
    return f"2_{PATH_GUIDANCE_ALGOS[algorithm]}_{flow_level}_{pr}"


def refresh_path_status_locked():
    global path_process, path_started_at
    proc = path_process
    if proc is None or not path_status_data.get("running"):
        return
    elapsed = max(0, time.time() - path_started_at)
    returncode = proc.poll()
    if returncode is None:
        path_status_data.update(
            running=True,
            success=None,
            elapsed=elapsed,
            pid=proc.pid,
            message=f"路径诱导CMD正在后端运行（PID {proc.pid}，已运行{elapsed:.1f}秒）",
        )
        return
    config_name = path_status_data.get("config_name")
    results = read_json(os.path.join(PATH_GUIDANCE_OUTPUT_DIR, config_name or "", "results.json"))
    path_process = None
    path_started_at = 0.0
    is_fresh = file_modified_after(os.path.join(PATH_GUIDANCE_OUTPUT_DIR, config_name or "", "results.json"), path_status_data.get("started_at"))
    if returncode == 0 and results and is_fresh:
        path_status_data.update(
            running=False,
            success=True,
            elapsed=elapsed,
            pid=None,
            results=results,
            message=f"路径诱导仿真完成（耗时{elapsed:.1f}秒）",
        )
    else:
        path_status_data.update(
            running=False,
            success=False,
            elapsed=elapsed,
            pid=None,
            results=results,
            message=f"路径诱导仿真未正常完成（退出码{returncode}，新结果={is_fresh}），请查看后端CMD或 backend_cmd.log",
        )


@router.post("/api/path-guidance/run", tags=["path-guidance"])
async def run_path_guidance(request: Request):
    global path_process, path_started_at
    try:
        body = await request.json()
    except Exception:
        body = {}
    algorithm = str(body.get("algorithm", "dijkstra")).lower()
    if algorithm not in PATH_GUIDANCE_ALGOS:
        return JSONResponse({"success": False, "message": "不支持的路径诱导算法"}, status_code=400)
    flow_mode_raw = body.get("flow_mode")
    if flow_mode_raw is None:
        flow_mode = "normal"
    else:
        flow_mode = str(flow_mode_raw).strip().lower()
    if flow_mode not in PATH_GUIDANCE_FLOW_MODES:
        return JSONResponse({"success": False, "message": "流量模式必须是 normal 或 high"}, status_code=400)
    try:
        # 新模式以当前的 flow=4 作为统一基准；保留旧请求的数值流量等级兼容性。
        flow_level = 4 if flow_mode_raw is not None else int(body.get("flow_level", 4))
        pr = int(body.get("pr", 40))
    except Exception:
        return JSONResponse({"success": False, "message": "参数格式错误"}, status_code=400)
    if flow_level not in {2, 4, 6}:
        return JSONResponse({"success": False, "message": "流量等级必须为 2/4/6"}, status_code=400)
    raw_use_gui = body.get("use_gui", True)
    if isinstance(raw_use_gui, str):
        use_gui = raw_use_gui.strip().lower() not in {"0", "false", "no", "off"}
    else:
        use_gui = bool(raw_use_gui)
    # 学生模式一律不打开 SUMO-GUI，改用无界面 sumo 完成同样的仿真与结果输出。
    if run_mode.is_student_mode():
        use_gui = False

    with path_lock:
        refresh_path_status_locked()
        if path_status_data.get("running"):
            return {"success": False, "message": path_status_data.get("message"), "running": True}
    if not os.path.isfile(PATH_GUIDANCE_SCRIPT):
        return JSONResponse({"success": False, "message": f"路径诱导脚本不存在: {PATH_GUIDANCE_SCRIPT}"}, status_code=404)

    config_name = path_config_name(algorithm, flow_level, pr)
    if flow_mode == "high":
        config_name += "_high"
    out_dir = os.path.join(PATH_GUIDANCE_OUTPUT_DIR, config_name)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "backend_cmd.log")
    args = [
        sys.executable, "-u", PATH_GUIDANCE_SCRIPT,
        "--algorithm", algorithm,
        "--flow", str(flow_level),
        "--flow-mode", flow_mode,
        "--pr", str(pr),
    ]
    if not use_gui:
        args.append("--no-gui")
    try:
        proc = launch_visible_console(
            f"路径诱导仿真 {algorithm} {config_name}",
            PATH_GUIDANCE_DIR,
            args,
            process_env(),
            log_path,
        )
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"路径诱导CMD启动失败: {exc}"}, status_code=500)
    with path_lock:
        path_process = proc
        path_started_at = time.time()
        path_status_data.update(
            running=True,
            success=None,
            message=(
                f"路径诱导已在后端后台启动（学生模式，不弹窗，PID {proc.pid}）"
                if run_mode.is_student_mode()
                else f"路径诱导可见CMD已在后端电脑启动（PID {proc.pid}）"
            ),
            config_name=config_name,
            algorithm=algorithm,
            flow_level=flow_level,
            flow_mode=flow_mode,
            flow_multiplier=PATH_GUIDANCE_FLOW_MODES[flow_mode]["multiplier"],
            pr=pr,
            elapsed=0,
            pid=proc.pid,
            results=None,
            log_path=log_path,
            started_at=path_started_at,
        )
    return {
        "success": True,
        "message": "路径诱导已启动（学生模式后台静默运行）" if run_mode.is_student_mode() else "路径诱导可见CMD已启动",
        "async": True,
        "pid": proc.pid,
        "config_name": config_name,
        "run_mode": run_mode.get_run_mode(),
        "use_gui": use_gui,
    }


@router.get("/api/path-guidance/status", tags=["path-guidance"])
async def path_status():
    with path_lock:
        refresh_path_status_locked()
        return dict(path_status_data)


@router.post("/api/path-guidance/reset", tags=["path-guidance"])
async def reset_path_status():
    with path_lock:
        refresh_path_status_locked()
        if path_status_data.get("running"):
            return {"success": False, "message": "路径诱导CMD仍在运行，等待完成后再重置", "running": True}
        path_status_data.update(
            running=False,
            success=None,
            message="已重置",
            config_name=None,
            algorithm=None,
            flow_level=None,
            flow_mode=None,
            flow_multiplier=None,
            pr=None,
            elapsed=0,
            pid=None,
            results=None,
            log_path=None,
            started_at=None,
        )
    return {"success": True, "message": "状态已重置"}


@router.get("/api/path-guidance/results/{config_name}", tags=["path-guidance"])
async def get_path_results(config_name: str):
    out_dir = safe_output_dir(PATH_GUIDANCE_OUTPUT_DIR, config_name)
    if not out_dir:
        return JSONResponse({"detail": "invalid config name"}, status_code=400)
    results = read_json(os.path.join(out_dir, "results.json"))
    if results is None:
        return JSONResponse({"detail": "results not found"}, status_code=404)
    return results


@router.get("/api/path-guidance/output/{config_name}", tags=["path-guidance"])
async def list_path_output(config_name: str):
    listing = list_output_files(PATH_GUIDANCE_OUTPUT_DIR, config_name)
    if listing is None:
        return JSONResponse({"detail": "output not found", "files": []}, status_code=404)
    return listing


@router.get("/api/path-guidance/output-file/{config_name}/{filename}", tags=["path-guidance"])
async def get_path_output_file(config_name: str, filename: str):
    return output_file_response(PATH_GUIDANCE_OUTPUT_DIR, config_name, filename)


def three_config_name(signal, path, speed, flow, pr, enable_signal, enable_path, enable_speed):
    parts = ["3L"]
    if enable_signal:
        parts.append(f"s{signal}")
    if enable_path:
        parts.append(f"p{path}")
    if enable_speed:
        parts.append(f"v{speed}")
    parts.append(f"f{flow}")
    parts.append(f"pr{pr}")
    return "_".join(parts)


def refresh_three_status_locked():
    global three_process, three_started_at
    proc = three_process
    if proc is None or not three_status_data.get("running"):
        return
    elapsed = max(0, time.time() - three_started_at)
    returncode = proc.poll()
    if returncode is None:
        three_status_data.update(
            running=True,
            success=None,
            elapsed=elapsed,
            pid=proc.pid,
            message=f"三层级统一仿真CMD正在后端运行（PID {proc.pid}，已运行{elapsed:.1f}秒）",
        )
        return
    config_name = three_status_data.get("config_name")
    results = read_json(os.path.join(THREE_LEVEL_OUTPUT_DIR, config_name or "", "results.json"))
    three_process = None
    three_started_at = 0.0
    is_fresh = file_modified_after(os.path.join(THREE_LEVEL_OUTPUT_DIR, config_name or "", "results.json"), three_status_data.get("started_at"))
    if returncode == 0 and results and is_fresh:
        three_status_data.update(
            running=False,
            success=True,
            elapsed=elapsed,
            pid=None,
            results=results,
            message=f"三层级统一仿真完成（耗时{elapsed:.1f}秒）",
        )
    else:
        three_status_data.update(
            running=False,
            success=False,
            elapsed=elapsed,
            pid=None,
            results=results,
            message=f"三层级统一仿真未正常完成（退出码{returncode}，新结果={is_fresh}），请查看后端CMD或 backend_cmd.log",
        )


@router.post("/api/three-level/run", tags=["three-level"])
async def run_three_level(request: Request):
    global three_process, three_started_at
    try:
        body = await request.json()
    except Exception:
        body = {}
    signal = str(body.get("signal", body.get("signal_algorithm", "turbo"))).lower()
    path = str(body.get("path", body.get("path_algorithm", "dijkstra"))).lower()
    speed = str(body.get("speed", body.get("speed_algorithm", "idm"))).lower()
    if signal not in THREE_SIGNAL_ALGOS or path not in THREE_PATH_ALGOS or speed not in THREE_SPEED_ALGOS:
        return JSONResponse({"success": False, "message": "三层级算法参数不支持"}, status_code=400)
    try:
        flow = int(body.get("flow", body.get("flow_level", 4)))
        pr = int(body.get("pr", 40))
        signal_interval = int(body.get("signal_interval", 600))
        path_interval = int(body.get("path_interval", body.get("path_reroute_interval", 30)))
        speed_dt = float(body.get("speed_dt", 0.5))
        max_time = int(body.get("max_time", 3600))
        accept_rate = int(body.get("accept_rate", 100))
    except Exception:
        return JSONResponse({"success": False, "message": "三层级参数格式错误"}, status_code=400)
    enable_signal = bool(body.get("enable_signal", True))
    enable_path = bool(body.get("enable_path", True))
    enable_speed = bool(body.get("enable_speed", True))
    if sum([enable_signal, enable_path, enable_speed]) < 2:
        return JSONResponse({"success": False, "message": "三层级协同至少需要启用两个层级"}, status_code=400)
    if flow not in {2, 4, 6}:
        return JSONResponse({"success": False, "message": "流量等级必须为 2/4/6"}, status_code=400)

    with three_lock:
        refresh_three_status_locked()
        if three_status_data.get("running"):
            return {"success": False, "message": three_status_data.get("message"), "running": True}
    if not os.path.isfile(THREE_LEVEL_SCRIPT):
        return JSONResponse({"success": False, "message": f"三层级脚本不存在: {THREE_LEVEL_SCRIPT}"}, status_code=404)

    config_name = three_config_name(signal, path, speed, flow, pr, enable_signal, enable_path, enable_speed)
    out_dir = os.path.join(THREE_LEVEL_OUTPUT_DIR, config_name)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "backend_cmd.log")
    args = [
        sys.executable, "-u", THREE_LEVEL_SCRIPT,
        "--signal", signal,
        "--path", path,
        "--speed", speed,
        "--flow", str(flow),
        "--pr", str(pr),
        "--signal-interval", str(signal_interval),
        "--path-interval", str(path_interval),
        "--speed-dt", str(speed_dt),
        "--max-time", str(max_time),
        "--accept-rate", str(accept_rate),
    ]
    if not enable_signal:
        args.append("--no-signal")
    if not enable_path:
        args.append("--no-path")
    if not enable_speed:
        args.append("--no-speed")
    # 学生模式不打开 SUMO-GUI，算法脚本改用无界面 sumo 输出同样结果。
    if run_mode.is_student_mode():
        args.append("--no-gui")
    try:
        proc = launch_visible_console(
            f"三层级统一仿真 {config_name}",
            THREE_LEVEL_DIR,
            args,
            process_env(),
            log_path,
        )
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"三层级CMD启动失败: {exc}"}, status_code=500)
    with three_lock:
        three_process = proc
        three_started_at = time.time()
        three_status_data.update(
            running=True,
            success=None,
            message=(
                f"三层级统一仿真已启动（学生模式，不弹窗，PID {proc.pid}）"
                if run_mode.is_student_mode()
                else f"三层级统一仿真可见CMD已在后端电脑启动（PID {proc.pid}）"
            ),
            config_name=config_name,
            elapsed=0,
            pid=proc.pid,
            results=None,
            log_path=log_path,
            started_at=three_started_at,
            params={
                "signal": signal,
                "path": path,
                "speed": speed,
                "flow": flow,
                "pr": pr,
                "accept_rate": accept_rate,
                "max_time": max_time,
                "enable_signal": enable_signal,
                "enable_path": enable_path,
                "enable_speed": enable_speed,
            },
        )
    return {
        "success": True,
        "message": "三层级统一仿真已启动（学生模式后台静默运行）" if run_mode.is_student_mode() else "三层级统一仿真可见CMD已启动",
        "async": True,
        "pid": proc.pid,
        "config_name": config_name,
        "run_mode": run_mode.get_run_mode(),
    }


@router.get("/api/three-level/status", tags=["three-level"])
async def three_status():
    with three_lock:
        refresh_three_status_locked()
        return dict(three_status_data)


@router.post("/api/three-level/reset", tags=["three-level"])
async def reset_three_status():
    with three_lock:
        refresh_three_status_locked()
        if three_status_data.get("running"):
            return {"success": False, "message": "三层级CMD仍在运行，等待完成后再重置", "running": True}
        three_status_data.update(
            running=False,
            success=None,
            message="已重置",
            config_name=None,
            elapsed=0,
            pid=None,
            results=None,
            log_path=None,
            started_at=None,
        )
    return {"success": True, "message": "状态已重置"}


@router.get("/api/three-level/results/{config_name}", tags=["three-level"])
async def get_three_results(config_name: str):
    out_dir = safe_output_dir(THREE_LEVEL_OUTPUT_DIR, config_name)
    if not out_dir:
        return JSONResponse({"detail": "invalid config name"}, status_code=400)
    results = read_json(os.path.join(out_dir, "results.json"))
    if results is None:
        return JSONResponse({"detail": "results not found"}, status_code=404)
    return results


@router.get("/api/three-level/output/{config_name}", tags=["three-level"])
async def list_three_output(config_name: str):
    listing = list_output_files(THREE_LEVEL_OUTPUT_DIR, config_name)
    if listing is None:
        return JSONResponse({"detail": "output not found", "files": []}, status_code=404)
    return listing


@router.get("/api/three-level/output-file/{config_name}/{filename}", tags=["three-level"])
async def get_three_output_file(config_name: str, filename: str):
    return output_file_response(THREE_LEVEL_OUTPUT_DIR, config_name, filename)
