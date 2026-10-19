"""多层级协调控制 API 路由"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/multi_level_coordination", tags=["多层级协调控制"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CoordinationExperimentRequest(BaseModel):
    """协调实验请求"""
    scenario: str = "grid_4x4"
    traffic_level: str = "medium"
    cav_penetration: float = 0.6
    coordination_mode: str = "full"
    max_steps: int = 3600


class CoordinationExperimentResponse(BaseModel):
    """协调实验响应"""
    success: bool
    message: str
    experiment_id: Optional[str] = None
    output_dir: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/start")
async def start_coordination_experiment(request: CoordinationExperimentRequest):
    """启动多层级协调实验

    Args:
        request: 实验配置

    Returns:
        实验启动结果
    """
    try:
        # 获取算法目录
        from ..paths import ALGORITHMS_DIR
        coordination_dir = Path(ALGORITHMS_DIR) / "multi_level_coordination"

        if not coordination_dir.exists():
            raise HTTPException(
                status_code=404,
                detail="多层级协调模块未找到"
            )

        # 构建命令
        python_exe = os.environ.get("ZXK_PYTHON_EXE", "python")
        run_script = coordination_dir / "run_multi_level_coordination.py"

        cmd = [
            python_exe,
            str(run_script),
            "--scenario", request.scenario,
            "--traffic-level", request.traffic_level,
            "--cav-penetration", str(request.cav_penetration),
            "--coordination-mode", request.coordination_mode,
            "--max-steps", str(request.max_steps),
        ]

        # 启动实验（后台运行）
        logger.info(f"Starting coordination experiment: {request.coordination_mode}")

        log_dir = coordination_dir / "output"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_log = log_dir / "coordination_stdout.log"
        stderr_log = log_dir / "coordination_stderr.log"
        kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
        with open(stdout_log, "a", encoding="utf-8", errors="replace") as stdout, open(stderr_log, "a", encoding="utf-8", errors="replace") as stderr:
            subprocess.Popen(
                cmd,
                cwd=str(coordination_dir),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                **kwargs,
            )

        return CoordinationExperimentResponse(
            success=True,
            message=f"协调实验已提交到服务器后台: {request.coordination_mode} 模式",
            experiment_id=f"{request.coordination_mode}_{request.scenario}",
            output_dir=str(coordination_dir / "output"),
        )

    except Exception as e:
        logger.error(f"Failed to start coordination experiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios")
async def list_scenarios():
    """列出可用的场景"""
    try:
        from ..paths import ALGORITHMS_DIR
        coordination_dir = Path(ALGORITHMS_DIR) / "multi_level_coordination"
        scenarios_dir = coordination_dir / "scenarios"

        if not scenarios_dir.exists():
            return {
                "success": True,
                "scenarios": [],
            }

        scenarios = []
        for scenario_path in scenarios_dir.iterdir():
            if scenario_path.is_dir():
                scenarios.append({
                    "name": scenario_path.name,
                    "path": str(scenario_path),
                    "has_network": (scenario_path / "grid.net.xml").exists(),
                    "has_routes": (scenario_path / "grid.rou.xml").exists(),
                    "has_config": (scenario_path / "grid.sumocfg").exists(),
                })

        return {
            "success": True,
            "scenarios": scenarios,
        }

    except Exception as e:
        logger.error(f"Failed to list scenarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
async def list_results():
    """列出实验结果"""
    try:
        from ..paths import ALGORITHMS_DIR
        coordination_dir = Path(ALGORITHMS_DIR) / "multi_level_coordination"
        output_dir = coordination_dir / "output"

        if not output_dir.exists():
            return {
                "success": True,
                "results": [],
            }

        results = []
        for result_file in output_dir.glob("metrics_*.json"):
            # 解析文件名：metrics_{mode}_{timestamp}.json
            parts = result_file.stem.split("_")
            if len(parts) >= 3:
                mode = parts[1]
                timestamp = parts[2]

                results.append({
                    "file": result_file.name,
                    "path": str(result_file),
                    "mode": mode,
                    "timestamp": timestamp,
                    "size": result_file.stat().st_size,
                })

        # 按时间戳排序（最新的在前）
        results.sort(key=lambda x: x["timestamp"], reverse=True)

        return {
            "success": True,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Failed to list results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_coordination_status():
    """获取协调系统状态"""
    try:
        from ..paths import ALGORITHMS_DIR
        coordination_dir = Path(ALGORITHMS_DIR) / "multi_level_coordination"

        # 检查模块是否存在
        module_exists = coordination_dir.exists()

        # 检查场景是否存在
        scenarios_dir = coordination_dir / "scenarios"
        scenario_count = len(list(scenarios_dir.glob("*"))) if scenarios_dir.exists() else 0

        # 检查结果文件数量
        output_dir = coordination_dir / "output"
        result_count = len(list(output_dir.glob("metrics_*.json"))) if output_dir.exists() else 0

        return {
            "success": True,
            "status": {
                "module_installed": module_exists,
                "module_path": str(coordination_dir) if module_exists else None,
                "scenario_count": scenario_count,
                "result_count": result_count,
            }
        }

    except Exception as e:
        logger.error(f"Failed to get coordination status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
