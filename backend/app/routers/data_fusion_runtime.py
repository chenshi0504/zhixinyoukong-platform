# -*- coding: utf-8 -*-
"""多源数据融合的无窗口、会话隔离运行路由。"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

from ..client_session import client_session_id
from ..paths import ALGORITHMS_DIR
from ..runtime_exec import build_script_command


router = APIRouter(prefix="/api/fusion", tags=["多源数据融合"])

_BASE_DIR = Path(ALGORITHMS_DIR) / "data_fusion"
_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "data_fusion_sessions"
_MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("ZXK_FUSION_MAX_CONCURRENT_JOBS", "4")))
_SESSION_TTL_SECONDS = max(3600, int(os.environ.get("ZXK_FUSION_SESSION_TTL", str(24 * 3600))))
_TASK_KEYS = ("image_entropy", "pointcloud_entropy", "fusion", "charts", "custom")
_LOCK = threading.RLock()

# 与 algorithms/data_fusion/bayesian_fusion.py 的 LAMBDA_VAL 保持一致。
# 页面用它把"点云熵"换算成 0~1 的"点云可靠性"，让读者看清融合提升到底从哪来。
_ENTROPY_LAMBDA = 0.1

# 融合脚本在"该帧没有该类别"时写入的兜底置信度（见 bayesian_fusion.py）。
# 聚合时必须剔除，否则稀疏类别的均值会被严重拉低。
_ABSENT_YOLO_CONF = 0.1


def _pc_reliability(entropy: float | None) -> float | None:
    """点云熵 → 点云对目标的支持度 P_pc = exp(-λ·熵)。

    > 0.5 表示点云支持目标存在（此时融合概率高于单源 YOLO），
    ≈ 0.5 表示中性（融合结果与单源持平），< 0.5 则会拉低。
    """
    if entropy is None:
        return None
    return round(math.exp(-_ENTROPY_LAMBDA * entropy), 4)
_TASKS: dict[str, dict[str, dict]] = {}
_PROCESSES: dict[tuple[str, str], subprocess.Popen] = {}
_LAST_SEEN: dict[str, float] = {}

_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _new_tasks() -> dict[str, dict]:
    return {key: {"running": False, "success": None, "message": "未运行"} for key in _TASK_KEYS}


def _session_tasks(session_id: str) -> dict[str, dict]:
    with _LOCK:
        _LAST_SEEN[session_id] = time.time()
        return _TASKS.setdefault(session_id, _new_tasks())


def _link_or_copy(source: str, destination: str) -> str:
    try:
        os.link(source, destination)
        return destination
    except OSError:
        return shutil.copy2(source, destination)


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


# 工作区里需要随源码更新而刷新的算法脚本
_ALGORITHM_SCRIPTS = (
    "贝叶斯融合_新版.py",
    "bayesian_fusion.py",
    "图像熵结果输出.py",
    "点云熵结果输出.py",
    "custom_fusion.py",
    os.path.join("results", "分析结果_简化版.py"),
)


def _sync_algorithm_scripts(workspace: Path) -> None:
    """把算法源码同步进已存在的工作区。

    工作区只在首次访问时整体复制一次，之后源码改动不会生效——学生会话会一直跑旧
    算法。这里在每次取工作区时做一次"源文件更新则覆盖"的检查（只 stat，不复制），
    保证后端算法一改所有在线会话立刻用上；学生自己生成的脚本不受影响。
    """
    refreshed = []
    for name in _ALGORITHM_SCRIPTS:
        source = _BASE_DIR / name
        target = workspace / name
        try:
            if source.is_file() and (not target.is_file()
                                     or source.stat().st_mtime > target.stat().st_mtime):
                shutil.copy2(source, target)
                refreshed.append(name)
        except OSError:
            pass

    # 刷新过源码时，顺手清掉工作区里会遮蔽它的编译产物：.pyd 的导入优先级高于 .py，
    # 留着的话即使 .py 更新了也仍然跑旧的 .pyd（这正是本次融合结论错误的根因之一）。
    if refreshed:
        for pyd in workspace.glob("*.cp3*-win_amd64.pyd"):
            if (workspace / (pyd.name.split(".cp3")[0] + ".py")).is_file():
                try:
                    pyd.unlink()
                except OSError:
                    pass


def _prepare_workspace(session_id: str) -> Path:
    workspace = _RUNTIME_ROOT / session_id
    if workspace.is_dir():
        _sync_algorithm_scripts(workspace)
        return workspace

    with _workspace_lock(session_id):
        if workspace.is_dir():
            _sync_algorithm_scripts(workspace)
            return workspace

        temporary = _RUNTIME_ROOT / f".{session_id}.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copytree(
                _BASE_DIR,
                temporary,
                copy_function=_link_or_copy,
                # 忽略编译产物：.pyd 在导入优先级上高于 .py，历史上一度让算法源码的
                # 修改完全失效（改了 .py，跑的仍是旧 .pyd）。
                ignore=shutil.ignore_patterns("output", "results", "tests", "__pycache__",
                                              "*.pyd", "*.pyd.disabled"),
            )
            if (_BASE_DIR / "output").is_dir():
                shutil.copytree(_BASE_DIR / "output", temporary / "output")
            else:
                (temporary / "output").mkdir(parents=True)
            if (_BASE_DIR / "results").is_dir():
                shutil.copytree(
                    _BASE_DIR / "results",
                    temporary / "results",
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            else:
                (temporary / "results").mkdir(parents=True)
            try:
                _publish_workspace(temporary, workspace)
            except OSError:
                if not workspace.is_dir():
                    raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
    return workspace


def _workspace_for_request(request: Request) -> tuple[str, Path]:
    session_id = client_session_id(request)
    workspace = _prepare_workspace(session_id)
    with _LOCK:
        _LAST_SEEN[session_id] = time.time()
    return session_id, workspace


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


def _script_command(script_path: Path, workspace: Path) -> tuple[list[str], dict]:
    if getattr(sys, "frozen", False):
        return build_script_command(str(script_path), cwd=str(workspace))
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    configured = os.environ.get("ZXK_ALGO_PYTHON_EXE", "").strip().strip('"')
    python_exe = configured if configured and Path(configured).is_file() else sys.executable
    return [python_exe, "-u", str(script_path)], env


def _set_status(session_id: str, task_key: str, **values) -> None:
    with _LOCK:
        _session_tasks(session_id)[task_key].update(values)


def _run_task(
    session_id: str,
    task_key: str,
    workspace: Path,
    script_path: Path,
    cleanup_path: Path | None = None,
) -> None:
    log_dir = workspace / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task_key}.log"
    process = None
    try:
        command, env = _script_command(script_path, workspace)
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(command, env=env, **_process_options(log, workspace))
            with _LOCK:
                _PROCESSES[(session_id, task_key)] = process
                _session_tasks(session_id)[task_key].update(pid=process.pid, message="运行中")
            returncode = process.wait()
        if returncode != 0:
            raise RuntimeError(f"后台进程退出码 {returncode}，请查看 {log_path.name}")
        _set_status(session_id, task_key, running=False, success=True, message="完成", pid=None)
    except Exception as exc:
        _set_status(session_id, task_key, running=False, success=False, message=str(exc), pid=None)
    finally:
        with _LOCK:
            if _PROCESSES.get((session_id, task_key)) is process:
                _PROCESSES.pop((session_id, task_key), None)
        if cleanup_path is not None:
            cleanup_path.unlink(missing_ok=True)


def _cleanup_stale_sessions() -> None:
    cutoff = time.time() - _SESSION_TTL_SECONDS
    with _LOCK:
        active_sessions = {session_id for session_id, _ in _PROCESSES}
        stale = [
            session_id
            for session_id, touched in _LAST_SEEN.items()
            if touched < cutoff and session_id not in active_sessions
        ]
        for session_id in stale:
            _TASKS.pop(session_id, None)
            _LAST_SEEN.pop(session_id, None)
    for session_id in stale:
        shutil.rmtree(_RUNTIME_ROOT / session_id, ignore_errors=True)


def _submit_task(
    session_id: str,
    task_key: str,
    workspace: Path,
    script_path: Path,
    cleanup_path: Path | None = None,
) -> dict | JSONResponse:
    if not script_path.is_file():
        return {"success": False, "message": f"{script_path.name}不存在"}

    _cleanup_stale_sessions()
    with _LOCK:
        tasks = _session_tasks(session_id)
        if any(task["running"] for task in tasks.values()):
            return {"success": False, "message": "当前会话已有融合任务在运行，请等待完成"}
        active_count = sum(
            1
            for session_tasks in _TASKS.values()
            for task in session_tasks.values()
            if task.get("running")
        )
        if active_count >= _MAX_CONCURRENT_JOBS:
            # 与数据采集保持一致：并发上限统一返回 429，便于前端与监控按状态码识别。
            # 响应体仍保留 success/code，老前端逻辑不受影响。
            return JSONResponse(
                {
                    "success": False,
                    "code": "FUSION_CAPACITY",
                    "message": "多源数据融合已达到并发上限，请稍后重试",
                },
                status_code=429,
            )
        tasks[task_key] = {
            "running": True,
            "success": None,
            "message": "正在启动服务器后台任务",
            "pid": None,
        }

    threading.Thread(
        target=_run_task,
        args=(session_id, task_key, workspace, script_path, cleanup_path),
        daemon=True,
        name=f"data-fusion-{session_id[:8]}",
    ).start()
    return {
        "success": True,
        "message": "已提交到服务器后台运行",
        "async": True,
        "session_id": session_id,
    }


@router.post("/process-image-entropy")
async def process_image_entropy(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    return _submit_task(session_id, "image_entropy", workspace, workspace / "图像熵结果输出.py")


@router.post("/process-pointcloud-entropy")
async def process_pointcloud_entropy(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    return _submit_task(session_id, "pointcloud_entropy", workspace, workspace / "点云熵结果输出.py")


@router.post("/start")
async def start_fusion(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    return _submit_task(session_id, "fusion", workspace, workspace / "贝叶斯融合_新版.py")


@router.post("/generate-charts")
async def generate_charts(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    return _submit_task(session_id, "charts", workspace, workspace / "results" / "分析结果_简化版.py")


@router.post("/generate-report")
async def generate_report(request: Request):
    session_id, _ = await run_in_threadpool(_workspace_for_request, request)
    return {"success": True, "message": "报告已生成", "file": "数据融合实验报告.txt", "session_id": session_id}


@router.post("/run-custom-fusion")
async def run_custom_fusion(request: Request):
    session_id, workspace = await run_in_threadpool(_workspace_for_request, request)
    try:
        body = await request.json()
        code = body.get("code", "")
    except Exception:
        return {"success": False, "message": "请求格式错误"}
    if not isinstance(code, str) or not code.strip():
        return {"success": False, "message": "代码不能为空"}

    script_path = workspace / f"custom_fusion_{uuid.uuid4().hex}.py"
    try:
        script_path.write_text(code, encoding="utf-8")
    except OSError as exc:
        return {"success": False, "message": f"写入临时脚本失败: {exc}"}
    result = _submit_task(session_id, "custom", workspace, script_path, cleanup_path=script_path)
    # 达到并发上限时 _submit_task 返回的是 JSONResponse(429) 而不是 dict。
    if isinstance(result, dict) and not result.get("success"):
        script_path.unlink(missing_ok=True)
    return result


@router.get("/status")
async def task_status(request: Request):
    session_id = client_session_id(request)
    with _LOCK:
        return {
            "success": True,
            "session_id": session_id,
            "tasks": {key: dict(value) for key, value in _session_tasks(session_id).items()},
        }


@router.post("/reset")
async def reset_tasks(request: Request):
    session_id = client_session_id(request)
    with _LOCK:
        processes = [
            process for (owner, _), process in _PROCESSES.items() if owner == session_id and process.poll() is None
        ]
        _TASKS[session_id] = _new_tasks()
        _LAST_SEEN[session_id] = time.time()
    for process in processes:
        try:
            process.terminate()
        except OSError:
            pass
    return {"success": True, "message": "当前会话状态已重置", "session_id": session_id}


def _count_json(folder: Path) -> int:
    return len(list(folder.glob("*.json"))) if folder.is_dir() else 0


def _first_json(folder: Path) -> dict:
    try:
        return json.loads(next(folder.glob("*.json")).read_text(encoding="utf-8"))
    except (StopIteration, OSError, json.JSONDecodeError):
        return {}


def _load_json_folder(folder: Path) -> dict:
    frames = {}
    if not folder.is_dir():
        return frames
    for path in folder.glob("*.json"):
        try:
            frames[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return frames


def _aggregate_inputs(yolo_frames: dict, pc_frames: dict) -> dict:
    """按类别聚合原始输入，供页面"原始数据对比"表使用。

    统计口径（很重要，否则数字会被误读）：
      - yolo_mean_conf / pc_entropy_mean 只统计"确实有该类别数据"的帧。若把缺省占位
        值（YOLO 0.1、点云熵 10.0）混进平均，平均值会被严重拉低，出现"YOLO 平均
        置信度 0.10"这种没有意义的数字。
      - yolo_coverage / pc_coverage 是该类别在总帧数中的出现比例，必须和均值一起
        展示，读者才知道这个均值背后有多少数据。
    """
    stats: dict[str, dict] = {}

    def entry(name: str) -> dict:
        return stats.setdefault(name, {
            "yolo_conf_sum": 0.0, "yolo_present": 0, "yolo_detections": 0,
            "pc_entropy_sum": 0.0, "pc_present": 0, "pc_count": 0,
        })

    for frame in yolo_frames.values():
        for item in frame.values():
            if not isinstance(item, dict):
                continue
            name = str(item.get("class_name") or "").strip()
            if not name:
                continue
            row = entry(name)
            row["yolo_conf_sum"] += float(item.get("mean_conf") or 0.0)
            row["yolo_present"] += 1
            row["yolo_detections"] += int(item.get("count") or 0)

    for frame in pc_frames.values():
        for name, item in frame.items():
            if not isinstance(item, dict):
                continue
            row = entry(str(name))
            row["pc_entropy_sum"] += float(item.get("entropy") or 0.0)
            row["pc_present"] += 1
            row["pc_count"] += int(item.get("count") or 0)

    total = len(yolo_frames)
    classes = {}
    for name, row in stats.items():
        yolo_present, pc_present = row["yolo_present"], row["pc_present"]
        entropy_mean = round(row["pc_entropy_sum"] / pc_present, 4) if pc_present else None
        classes[name] = {
            "yolo_mean_conf": round(row["yolo_conf_sum"] / yolo_present, 4) if yolo_present else None,
            "yolo_detections": row["yolo_detections"],
            "yolo_frames": yolo_present,
            "yolo_coverage": round(yolo_present / total, 4) if total else 0.0,
            "pc_entropy_mean": entropy_mean,
            "pc_count": row["pc_count"],
            "pc_frames": pc_present,
            "pc_coverage": round(pc_present / total, 4) if total else 0.0,
        }
    return {"frames": total, "classes": classes}


def _aggregate_fusion(fusion_frames: dict, pc_frames: dict) -> dict:
    """按类别聚合融合结果，供页面"贝叶斯融合结果对比"表使用。

    统计口径（不显式排除兜底值，页面上的数字就会互相矛盾）：
      - 融合脚本对"该帧没有该类别"的条目会写入兜底值：yolo_mean_conf=0.1、
        pc_entropy=10.0、fused_prob=0.1。若把它们混进平均，Bus 这类稀疏类别的
        平均置信度会从真实的 0.73 被拉到 0.34，并且与"原始数据对比"表里同一类别
        的数字对不上。因此 YOLO 侧只统计确实检出该类别的帧，与
        _aggregate_inputs 保持同一口径。
      - "提升"必须在同一帧集合上做差：融合前、融合后取平均用的帧集合完全一致，
        差值才有意义。
      - 覆盖率必须一起给出：点云几乎没有该类别数据时，融合结果会回退到单源
        （提升≈0），只给概率会让读者误以为融合算法无效。
    """
    stats: dict[str, dict] = {}
    for frame in fusion_frames.values():
        for name, item in frame.items():
            if not isinstance(item, dict):
                continue
            yolo_conf = float(item.get("yolo_mean_conf") or 0.0)
            # 兜底条目代表"该帧 YOLO 没检出该类别"，不是一次真实检测，不能进均值。
            if yolo_conf <= _ABSENT_YOLO_CONF:
                continue
            row = stats.setdefault(name, {"yolo": [], "fused": []})
            row["yolo"].append(yolo_conf)
            row["fused"].append(float(item.get("fused_prob") or 0.0))

    # 点云熵只统计"确实有该类别数据"的帧，并且直接取自点云输入。
    # 融合输出里的 pc_entropy 在缺数据时是兜底的 10.0，混进平均会把熵值整体抬高，
    # 让读者误判点云质量（例如 Truck 实际有数据帧只有 4.63，平均后却显示 9.79）。
    pc_entropy: dict[str, list[float]] = {}
    for frame in pc_frames.values():
        for name, item in frame.items():
            if isinstance(item, dict):
                pc_entropy.setdefault(str(name), []).append(float(item.get("entropy") or 0.0))

    pc_present: dict[str, int] = {name: len(values) for name, values in pc_entropy.items()}

    total = len(fusion_frames)
    classes = {}
    for name, row in stats.items():
        count = len(row["fused"])
        if not count:
            continue
        yolo_mean = sum(row["yolo"]) / count
        fused_mean = sum(row["fused"]) / count
        entropies = pc_entropy.get(name) or []
        entropy_mean = round(sum(entropies) / len(entropies), 4) if entropies else None
        classes[name] = {
            "yolo_mean": round(yolo_mean, 4),
            "entropy_mean": entropy_mean,
            "reliability_mean": _pc_reliability(entropy_mean),
            "fused_mean": round(fused_mean, 4),
            "improvement": round(fused_mean - yolo_mean, 4),
            "pc_coverage": round(pc_present.get(name, 0) / total, 4) if total else 0.0,
        }
    return {"frames": total, "classes": classes}


def _collect_input_data() -> dict:
    yolo_val = _BASE_DIR / "input" / "yolo" / "val"
    yolo_test = _BASE_DIR / "input" / "yolo" / "test"
    pc_val = _BASE_DIR / "input" / "pointcloud" / "val"
    pc_test = _BASE_DIR / "input" / "pointcloud" / "test"
    return {
        "yolo": {"val_count": _count_json(yolo_val), "test_count": _count_json(yolo_test),
                 "sample": _first_json(yolo_val)},
        "pointcloud": {"val_count": _count_json(pc_val), "test_count": _count_json(pc_test),
                       "sample": _first_json(pc_val)},
        "aggregate": {
            "val": _aggregate_inputs(_load_json_folder(yolo_val), _load_json_folder(pc_val)),
            "test": _aggregate_inputs(_load_json_folder(yolo_test), _load_json_folder(pc_test)),
        },
    }


@router.get("/get-input-data")
async def get_input_data():
    # 聚合要读上百个 JSON，放到线程池执行，别占用事件循环
    return await run_in_threadpool(_collect_input_data)


def _collect_fusion_data(workspace: Path) -> dict:
    fusion_val = workspace / "output" / "fusion" / "val"
    fusion_test = workspace / "output" / "fusion" / "test"
    sample = {}
    try:
        sample = json.loads(next(fusion_val.glob("*.json")).read_text(encoding="utf-8"))
    except (StopIteration, OSError, json.JSONDecodeError):
        pass
    return {
        "val_count": _count_json(fusion_val),
        "test_count": _count_json(fusion_test),
        "sample": sample,
        "aggregate": {
            "val": _aggregate_fusion(_load_json_folder(fusion_val),
                                     _load_json_folder(workspace / "input" / "pointcloud" / "val")),
            "test": _aggregate_fusion(_load_json_folder(fusion_test),
                                      _load_json_folder(workspace / "input" / "pointcloud" / "test")),
        },
    }


@router.get("/get-fusion-data")
async def get_fusion_data(request: Request):
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    return await run_in_threadpool(_collect_fusion_data, workspace)


@router.get("/download-report")
async def download_report(request: Request):
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    report_path = workspace / "results" / "数据融合实验报告.txt"
    if report_path.is_file():
        return FileResponse(report_path, media_type="text/plain; charset=utf-8", filename="数据融合实验报告.txt")
    return Response(
        content="数据融合实验报告\n\n请先生成可视化图表。",
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="report.txt"'},
    )


@router.get("/list-charts")
async def list_charts(request: Request):
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    charts_dir = workspace / "results" / "charts"
    charts = sorted(
        path.name for path in charts_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ) if charts_dir.is_dir() else []
    return {"success": bool(charts), "charts": charts, "message": "" if charts else "当前会话图表目录为空"}


@router.get("/charts/{filename}")
async def get_chart_image(request: Request, filename: str):
    safe_name = Path(filename).name
    _, workspace = await run_in_threadpool(_workspace_for_request, request)
    path = workspace / "results" / "charts" / safe_name
    if safe_name != filename or not path.is_file():
        return Response(content="Not found", status_code=404)
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "data_fusion", "execution": "background_no_window", "session_isolation": True}


def reset_fusion_runtime_state() -> None:
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
