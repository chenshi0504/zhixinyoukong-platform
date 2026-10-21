"""批量运行对比实验脚本

运行三种协调模式（none, local, full）的对比实验。
"""

import argparse
import logging
import subprocess
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run_experiment(
    scenario: str,
    traffic_level: str,
    cav_penetration: float,
    coordination_mode: str,
    max_steps: int = 3600,
) -> bool:
    """运行单个实验

    Args:
        scenario: 场景名称
        traffic_level: 流量等级
        cav_penetration: CAV 渗透率
        coordination_mode: 协调模式
        max_steps: 最大步数

    Returns:
        bool: 是否成功
    """
    logger.info(f"Running experiment: mode={coordination_mode}, traffic={traffic_level}, CAV={cav_penetration}")

    # 构建命令
    cmd = [
        "python",
        "run_multi_level_coordination.py",
        "--scenario", scenario,
        "--traffic-level", traffic_level,
        "--cav-penetration", str(cav_penetration),
        "--coordination-mode", coordination_mode,
        "--max-steps", str(max_steps),
    ]

    try:
        # 运行实验
        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=max_steps * 2,  # 超时时间为仿真时间的2倍
        )

        if result.returncode == 0:
            logger.info(f"Experiment completed: {coordination_mode}")
            return True
        else:
            logger.error(f"Experiment failed: {coordination_mode}")
            logger.error(f"Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Experiment timeout: {coordination_mode}")
        return False
    except Exception as e:
        logger.error(f"Experiment error: {e}")
        return False


def run_comparison_experiments(
    scenario: str = "grid_4x4",
    traffic_level: str = "medium",
    cav_penetration: float = 0.6,
    max_steps: int = 3600,
) -> None:
    """运行对比实验

    Args:
        scenario: 场景名称
        traffic_level: 流量等级
        cav_penetration: CAV 渗透率
        max_steps: 最大步数
    """
    modes = ["none", "local", "full"]

    logger.info("=" * 80)
    logger.info("Starting comparison experiments")
    logger.info(f"  Scenario: {scenario}")
    logger.info(f"  Traffic Level: {traffic_level}")
    logger.info(f"  CAV Penetration: {cav_penetration * 100:.0f}%")
    logger.info(f"  Max Steps: {max_steps}")
    logger.info(f"  Modes: {', '.join(modes)}")
    logger.info("=" * 80)

    results = {}

    for mode in modes:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Running mode: {mode}")
        logger.info(f"{'=' * 80}\n")

        success = run_experiment(
            scenario=scenario,
            traffic_level=traffic_level,
            cav_penetration=cav_penetration,
            coordination_mode=mode,
            max_steps=max_steps,
        )

        results[mode] = success

        # 等待一段时间再运行下一个实验
        if mode != modes[-1]:
            logger.info("Waiting 10 seconds before next experiment...")
            time.sleep(10)

    # 输出结果汇总
    logger.info("\n" + "=" * 80)
    logger.info("Comparison experiments completed")
    logger.info("=" * 80)

    for mode, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"  {mode:10s}: {status}")

    # 运行评估
    if all(results.values()):
        logger.info("\nRunning evaluation...")
        try:
            subprocess.run(
                ["python", "evaluation/metrics.py"],
                cwd=Path(__file__).parent,
                timeout=60,
            )
            logger.info("Evaluation completed")
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="批量运行对比实验")
    parser.add_argument(
        "--scenario",
        type=str,
        default="grid_4x4",
        help="场景名称",
    )
    parser.add_argument(
        "--traffic-level",
        type=str,
        default="medium",
        choices=["low", "medium", "high"],
        help="流量等级",
    )
    parser.add_argument(
        "--cav-penetration",
        type=float,
        default=0.6,
        help="CAV 渗透率 (0-1)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=3600,
        help="最大仿真步数",
    )

    args = parser.parse_args()

    run_comparison_experiments(
        scenario=args.scenario,
        traffic_level=args.traffic_level,
        cav_penetration=args.cav_penetration,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()
