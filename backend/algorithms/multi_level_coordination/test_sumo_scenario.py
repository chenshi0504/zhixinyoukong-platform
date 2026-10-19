"""测试 SUMO 场景是否可以正常运行

这是一个简单的测试脚本，不涉及多层级协调，仅验证 SUMO 场景配置是否正确。
"""

import os
import sys
import time
from pathlib import Path

try:
    import traci
except ImportError:
    print("Error: SUMO TraCI not found. Please install SUMO and set SUMO_HOME.")
    sys.exit(1)


def test_sumo_scenario(scenario_path: Path, max_steps: int = 100):
    """测试 SUMO 场景

    Args:
        scenario_path: 场景目录路径
        max_steps: 测试步数
    """
    print("=" * 60)
    print("Testing SUMO Scenario")
    print("=" * 60)
    print(f"Scenario: {scenario_path}")
    print(f"Max steps: {max_steps}")
    print()

    # 检查场景文件
    sumo_cfg = scenario_path / "grid.sumocfg"
    if not sumo_cfg.exists():
        print(f"Error: Configuration file not found: {sumo_cfg}")
        return False

    print(f"[1/3] Configuration file found: {sumo_cfg}")

    # 启动 SUMO
    print(f"[2/3] Starting SUMO...")
    sumo_cmd = [
        "sumo",  # 使用命令行版本（不带 GUI）
        "-c", str(sumo_cfg),
        "--no-warnings",
        "--no-step-log",
    ]

    try:
        traci.start(sumo_cmd)
        print(f"      SUMO started successfully")
    except Exception as e:
        print(f"      Error starting SUMO: {e}")
        return False

    # 运行仿真
    print(f"[3/3] Running simulation for {max_steps} steps...")

    try:
        step = 0
        vehicle_count_history = []

        while step < max_steps and traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            step += 1

            # 每 10 步统计一次
            if step % 10 == 0:
                vehicle_ids = traci.vehicle.getIDList()
                vehicle_count = len(vehicle_ids)
                vehicle_count_history.append(vehicle_count)

                # 统计 CAV 数量
                cav_count = sum(1 for vid in vehicle_ids if traci.vehicle.getTypeID(vid) == "cav")

                print(f"      Step {step:4d}: {vehicle_count:3d} vehicles ({cav_count} CAV)")

        print()
        print("=" * 60)
        print("Test Results")
        print("=" * 60)
        print(f"Total steps: {step}")
        print(f"Max vehicles: {max(vehicle_count_history) if vehicle_count_history else 0}")
        print(f"Avg vehicles: {sum(vehicle_count_history) / len(vehicle_count_history) if vehicle_count_history else 0:.1f}")
        print()
        print("[SUCCESS] SUMO scenario test passed!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n[ERROR] Simulation error: {e}")
        return False

    finally:
        traci.close()
        print("\nSUMO closed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="测试 SUMO 场景")
    parser.add_argument(
        "--scenario",
        type=str,
        default="grid_4x4",
        help="场景名称",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="测试步数",
    )

    args = parser.parse_args()

    # 确定场景路径
    scenario_path = Path(__file__).parent / "scenarios" / args.scenario

    if not scenario_path.exists():
        print(f"Error: Scenario not found: {scenario_path}")
        print("\nAvailable scenarios:")
        scenarios_dir = Path(__file__).parent / "scenarios"
        if scenarios_dir.exists():
            for scenario in scenarios_dir.iterdir():
                if scenario.is_dir():
                    print(f"  - {scenario.name}")
        sys.exit(1)

    # 运行测试
    success = test_sumo_scenario(scenario_path, args.max_steps)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
