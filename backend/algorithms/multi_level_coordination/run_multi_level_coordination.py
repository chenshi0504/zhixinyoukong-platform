"""多层级协调控制主程序

运行基于 SUMO 的三层级车路云协调控制实验。
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _student_mode():
    """平台学生模式：后端不弹出 SUMO-GUI 等窗口。"""
    return os.environ.get('ZXK_RUN_MODE', '').strip().lower() in {
        'student', 'student_mode', '学生', '学生模式', '0', 'false', 'no', 'off',
    }

try:
    import traci
except ImportError:
    print("Error: SUMO TraCI not found. Please install SUMO and set SUMO_HOME.")
    sys.exit(1)

from agents import (
    VehicleAgent,
    IntersectionAgent,
    RegionOrchestrator,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class MultiLevelCoordinationSimulation:
    """多层级协调控制仿真"""

    def __init__(
        self,
        scenario_path: Path,
        coordination_mode: str = "full",
        cav_penetration: float = 0.6,
        output_dir: Path = None,
    ):
        self.scenario_path = scenario_path
        self.coordination_mode = coordination_mode
        self.cav_penetration = cav_penetration
        self.output_dir = output_dir or Path(__file__).parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Agent 实例
        self.vehicle_agents: Dict[str, VehicleAgent] = {}
        self.intersection_agents: Dict[str, IntersectionAgent] = {}
        self.region_orchestrator: RegionOrchestrator = None

        # 仿真数据
        self.step_count = 0
        self.metrics_history: List[Dict[str, Any]] = []

        logger.info(f"Initialized simulation: mode={coordination_mode}, CAV={cav_penetration*100:.0f}%")

    def setup(self) -> None:
        """初始化仿真环境"""
        logger.info("Setting up simulation...")

        # 启动 SUMO（演示模式=sumo-gui，学生模式=无界面 sumo）
        sumo_cfg = self.scenario_path / "grid.sumocfg"
        use_gui = not _student_mode()
        sumo_cmd = [
            "sumo-gui" if use_gui else "sumo",
            "-c", str(sumo_cfg),
            "--no-warnings",
        ]
        if use_gui:
            sumo_cmd += ["--start", "--quit-on-end"]

        traci.start(sumo_cmd)
        logger.info("SUMO started (%s)", "GUI" if use_gui else "headless")

        # 创建路口 Agent
        self._create_intersection_agents()

        # 创建区域协调器
        self._create_region_orchestrator()

        logger.info("Setup complete")

    def _create_intersection_agents(self) -> None:
        """创建路口 Agent"""
        # 获取所有交通灯路口
        tls_ids = traci.trafficlight.getIDList()

        for tls_id in tls_ids:
            # 获取信号相位配置
            logic = traci.trafficlight.getAllProgramLogics(tls_id)[0]
            phases = [
                {
                    "duration": phase.duration,
                    "state": phase.state,
                    "directions": self._parse_phase_directions(phase.state),
                }
                for phase in logic.phases
            ]

            # 创建 Agent
            agent = IntersectionAgent(
                agent_id=f"intersection_agent_{tls_id}",
                intersection_id=tls_id,
                phases=phases,
            )
            self.intersection_agents[tls_id] = agent

        logger.info(f"Created {len(self.intersection_agents)} intersection agents")

    def _parse_phase_directions(self, state: str) -> List[str]:
        """解析信号相位的通行方向"""
        # 简化实现：根据信号状态判断
        directions = []
        if "G" in state or "g" in state:
            # 有绿灯，假设允许通行
            directions = ["north", "south"]  # 简化
        return directions

    def _create_region_orchestrator(self) -> None:
        """创建区域协调器"""
        intersection_list = list(self.intersection_agents.values())
        self.region_orchestrator = RegionOrchestrator(
            orchestrator_id="region_orchestrator",
            intersections=intersection_list,
            max_iterations=3,
        )
        logger.info("Created region orchestrator")

    def run(self, max_steps: int = 3600) -> None:
        """运行仿真

        Args:
            max_steps: 最大仿真步数
        """
        logger.info(f"Starting simulation for {max_steps} steps...")

        try:
            while self.step_count < max_steps and traci.simulation.getMinExpectedNumber() > 0:
                self.step()

                # 每 100 步输出一次进度
                if self.step_count % 100 == 0:
                    logger.info(f"Step {self.step_count}/{max_steps}")

        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")

        finally:
            self.cleanup()

        logger.info(f"Simulation complete: {self.step_count} steps")

    def step(self) -> None:
        """执行一个仿真步"""
        self.step_count += 1

        # 1. 收集车辆状态
        vehicle_states = self._collect_vehicle_states()

        # 2. 收集检测器数据
        detector_data = self._collect_detector_data()

        # 3. 区域协调决策
        if self.coordination_mode != "none":
            coordination_result = self.region_orchestrator.orchestrate({
                "vehicle_states": vehicle_states,
                "detector_data": detector_data,
                "coordination_mode": self.coordination_mode,
            })
        else:
            coordination_result = {"coordination_strategy": {"mode": "none"}}

        # 4. 应用控制指令
        self._apply_control(coordination_result)

        # 5. 推进仿真
        traci.simulationStep()

        # 6. 记录指标
        if self.step_count % 10 == 0:
            metrics = self._calculate_metrics(vehicle_states)
            self.metrics_history.append(metrics)

    def _collect_vehicle_states(self) -> Dict[str, Dict[str, Any]]:
        """收集所有车辆状态"""
        vehicle_ids = traci.vehicle.getIDList()
        states = {}

        for vid in vehicle_ids:
            # 判断是否为 CAV
            vtype = traci.vehicle.getTypeID(vid)
            is_cav = (vtype == "cav")

            # 创建或获取 Vehicle Agent
            if vid not in self.vehicle_agents:
                self.vehicle_agents[vid] = VehicleAgent(
                    agent_id=f"vehicle_agent_{vid}",
                    vehicle_id=vid,
                    is_cav=is_cav,
                )

            # 收集状态
            states[vid] = {
                "vehicle_id": vid,
                "is_cav": is_cav,
                "position": traci.vehicle.getPosition(vid),
                "speed": traci.vehicle.getSpeed(vid),
                "route": traci.vehicle.getRoute(vid),
                "edge": traci.vehicle.getRoadID(vid),
            }

        return states

    def _collect_detector_data(self) -> Dict[str, Dict[str, float]]:
        """收集检测器数据"""
        detector_data = {}

        for tls_id in self.intersection_agents.keys():
            # 获取路口控制的车道
            controlled_lanes = traci.trafficlight.getControlledLanes(tls_id)

            # 统计各方向车辆数（简化实现）
            direction_counts = {
                "north_count": 0,
                "south_count": 0,
                "east_count": 0,
                "west_count": 0,
            }

            # 统计车辆
            for lane in set(controlled_lanes):
                vehicle_count = traci.lane.getLastStepVehicleNumber(lane)
                # 简化：根据车道 ID 判断方向
                if "0" in lane:
                    direction_counts["north_count"] += vehicle_count
                elif "1" in lane:
                    direction_counts["south_count"] += vehicle_count
                elif "2" in lane:
                    direction_counts["east_count"] += vehicle_count
                elif "3" in lane:
                    direction_counts["west_count"] += vehicle_count

            detector_data[tls_id] = direction_counts

        return detector_data

    def _apply_control(self, coordination_result: Dict[str, Any]) -> None:
        """应用控制指令"""
        coordination_strategy = coordination_result.get("coordination_strategy", {})
        intersection_results = coordination_result.get("intersection_results", {})

        # 应用信号配时
        for tls_id, result in intersection_results.items():
            if not result.success:
                continue

            signal_plan = result.data.get("signal_plan", {})
            # 简化：不修改信号配时，仅记录
            # 实际应用中可以通过 traci.trafficlight.setPhase() 修改

        # 应用车辆引导
        for tls_id, result in intersection_results.items():
            if not result.success:
                continue

            vehicle_guidance = result.data.get("vehicle_guidance", {})
            for vid, guidance in vehicle_guidance.items():
                if vid in self.vehicle_agents:
                    # 应用速度引导
                    recommended_speed = guidance.get("recommended_speed")
                    if recommended_speed is not None:
                        try:
                            traci.vehicle.setSpeed(vid, recommended_speed)
                        except traci.exceptions.TraCIException:
                            pass  # 车辆可能已离开

    def _calculate_metrics(self, vehicle_states: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """计算性能指标"""
        total_vehicles = len(vehicle_states)
        cav_count = sum(1 for state in vehicle_states.values() if state.get("is_cav", False))

        # 计算平均速度
        speeds = [state["speed"] for state in vehicle_states.values()]
        avg_speed = sum(speeds) / max(len(speeds), 1)

        # 计算等待车辆数（速度 < 0.1 m/s）
        waiting_count = sum(1 for speed in speeds if speed < 0.1)

        return {
            "step": self.step_count,
            "total_vehicles": total_vehicles,
            "cav_count": cav_count,
            "avg_speed": avg_speed,
            "waiting_count": waiting_count,
            "coordination_mode": self.coordination_mode,
        }

    def cleanup(self) -> None:
        """清理资源"""
        logger.info("Cleaning up...")

        # 保存结果
        self._save_results()

        # 关闭 SUMO
        traci.close()

        logger.info("Cleanup complete")

    def _save_results(self) -> None:
        """保存实验结果"""
        import json

        output_file = self.output_dir / f"metrics_{self.coordination_mode}_{int(time.time())}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.metrics_history, f, indent=2)

        logger.info(f"Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="多层级协调控制仿真")
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
        "--coordination-mode",
        type=str,
        default="full",
        choices=["none", "local", "full"],
        help="协调模式",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=3600,
        help="最大仿真步数",
    )

    args = parser.parse_args()

    # 确定场景路径
    scenario_path = Path(__file__).parent / "scenarios" / args.scenario

    if not scenario_path.exists():
        logger.error(f"Scenario not found: {scenario_path}")
        logger.info("Generating scenario...")
        from generate_scenario import generate_scenario
        scenario_path = generate_scenario(
            scenario_name=args.scenario,
            traffic_level=args.traffic_level,
            cav_penetration=args.cav_penetration,
        )

    # 创建仿真
    sim = MultiLevelCoordinationSimulation(
        scenario_path=scenario_path,
        coordination_mode=args.coordination_mode,
        cav_penetration=args.cav_penetration,
    )

    # 运行仿真
    sim.setup()
    sim.run(max_steps=args.max_steps)


if __name__ == "__main__":
    main()
