"""区域协调器

协调多个路口的信号配时和车辆引导，实现全局优化。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .base import AgentOrchestrator, AgentStepResult
from .intersection_agent import IntersectionAgent


class RegionOrchestrator(AgentOrchestrator):
    """区域协调器

    职责：
    - 收集各路口状态
    - 计算全局最优策略
    - 分发协调指令
    - 验证执行效果

    工作流：Collect → Optimize → Dispatch → Validate
    """

    def __init__(
        self,
        orchestrator_id: str,
        intersections: List[IntersectionAgent],
        *,
        max_iterations: int = 3,
    ) -> None:
        super().__init__(orchestrator_id, max_iterations=max_iterations)
        self.intersections = {agent.intersection_id: agent for agent in intersections}
        self.coordination_history: List[Dict[str, Any]] = []

    def orchestrate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行区域协调

        Args:
            context: {
                "vehicle_states": Dict[str, Dict],  # 所有车辆状态
                "detector_data": Dict[str, Dict],   # 所有检测器数据
                "coordination_mode": str,           # 协调模式
            }

        Returns:
            Dict: {
                "coordination_strategy": Dict,      # 协调策略
                "intersection_results": Dict,       # 各路口执行结果
                "performance_metrics": Dict,        # 性能指标
            }
        """
        start_time = time.time()

        vehicle_states = context.get("vehicle_states", {})
        detector_data = context.get("detector_data", {})
        coordination_mode = context.get("coordination_mode", "full")

        self.logger.info(
            f"Region orchestrator starting: mode={coordination_mode}, "
            f"intersections={len(self.intersections)}, vehicles={len(vehicle_states)}"
        )

        # Phase 1: Collect - 收集各路口状态
        self.logger.debug("Phase 1: Collecting intersection states")
        intersection_states = self._collect_states(detector_data)

        # Phase 2: Optimize - 计算全局最优策略
        self.logger.debug("Phase 2: Computing global optimization strategy")
        coordination_strategy = self._optimize_global(
            intersection_states,
            vehicle_states,
            coordination_mode,
        )

        # Phase 3: Dispatch - 分发协调指令到各路口
        self.logger.debug("Phase 3: Dispatching coordination strategy")
        intersection_results = self._dispatch_strategy(
            coordination_strategy,
            vehicle_states,
            detector_data,
        )

        # Phase 4: Validate - 验证执行效果
        self.logger.debug("Phase 4: Validating execution results")
        validation_result = self._validate_results(intersection_results)

        # 记录协调历史
        execution_time = time.time() - start_time
        self.total_execution_time += execution_time

        coordination_record = {
            "timestamp": time.time(),
            "coordination_mode": coordination_mode,
            "intersection_count": len(self.intersections),
            "vehicle_count": len(vehicle_states),
            "execution_time": execution_time,
            "validation_passed": validation_result["passed"],
        }
        self.coordination_history.append(coordination_record)

        self.logger.info(
            f"Region orchestration complete: "
            f"validation={'PASS' if validation_result['passed'] else 'FAIL'}, "
            f"time={execution_time:.2f}s"
        )

        return {
            "coordination_strategy": coordination_strategy,
            "intersection_results": intersection_results,
            "performance_metrics": self._calculate_metrics(intersection_states),
            "validation": validation_result,
        }

    def _collect_states(
        self,
        detector_data: Dict[str, Dict[str, float]],
    ) -> Dict[str, Dict[str, Any]]:
        """收集各路口状态"""
        states = {}

        for intersection_id, agent in self.intersections.items():
            intersection_detector = detector_data.get(intersection_id, {})

            # 构造路口状态上下文
            state_context = {
                "detector_data": intersection_detector,
                "vehicle_states": {},  # 简化：不传递车辆状态
            }

            # 收集状态（不执行完整决策）
            state = {
                "intersection_id": intersection_id,
                "detector_data": intersection_detector,
                "current_phase": agent.current_phase_index,
                "phase_remaining_time": agent.phase_remaining_time,
            }

            states[intersection_id] = state

        return states

    def _optimize_global(
        self,
        intersection_states: Dict[str, Dict[str, Any]],
        vehicle_states: Dict[str, Dict[str, Any]],
        coordination_mode: str,
    ) -> Dict[str, Any]:
        """计算全局最优策略

        Args:
            intersection_states: 各路口状态
            vehicle_states: 车辆状态
            coordination_mode: 协调模式 (none/local/full)

        Returns:
            Dict: 协调策略
        """
        if coordination_mode == "none":
            # 无协调模式：返回空策略
            return {"mode": "none"}

        elif coordination_mode == "local":
            # 局部协调模式：相邻路口绿波协调
            return self._optimize_green_wave(intersection_states)

        elif coordination_mode == "full":
            # 全局协调模式：多路口联合优化
            return self._optimize_full_coordination(
                intersection_states,
                vehicle_states,
            )

        else:
            self.logger.warning(f"Unknown coordination mode: {coordination_mode}")
            return {"mode": "none"}

    def _optimize_green_wave(
        self,
        intersection_states: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """优化绿波协调"""
        # 计算绿波速度（假设路口间距 200m，周期 120s）
        distance = 200  # 米
        cycle_time = 120  # 秒
        green_wave_speed = distance / (cycle_time / 4)  # m/s

        # 计算相位差
        phase_offsets = {}
        intersection_ids = list(intersection_states.keys())

        for i, intersection_id in enumerate(intersection_ids):
            # 简化：线性相位差
            phase_offsets[intersection_id] = i * 30  # 30秒间隔

        return {
            "mode": "local",
            "green_wave_speed": green_wave_speed,
            "phase_offsets": phase_offsets,
            "cycle_time": cycle_time,
        }

    def _optimize_full_coordination(
        self,
        intersection_states: Dict[str, Dict[str, Any]],
        vehicle_states: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """全局协调优化"""
        # 1. 绿波协调
        green_wave_strategy = self._optimize_green_wave(intersection_states)

        # 2. 流量均衡：识别拥堵路口，引导车辆绕行
        congestion_map = self._identify_congestion(intersection_states)
        route_guidance = self._generate_route_guidance(
            vehicle_states,
            congestion_map,
        )

        # 3. CAV 编队：将 CAV 车辆编组以提高通行效率
        platoon_strategy = self._generate_platoon_strategy(vehicle_states)

        return {
            "mode": "full",
            "green_wave_speed": green_wave_strategy["green_wave_speed"],
            "phase_offsets": green_wave_strategy["phase_offsets"],
            "cycle_time": green_wave_strategy["cycle_time"],
            "route_guidance": route_guidance,
            "platoon_strategy": platoon_strategy,
            "congestion_map": congestion_map,
        }

    def _identify_congestion(
        self,
        intersection_states: Dict[str, Dict[str, Any]],
    ) -> Dict[str, float]:
        """识别拥堵路口

        Returns:
            Dict[intersection_id, congestion_level]: 拥堵程度 (0-1)
        """
        congestion_map = {}

        for intersection_id, state in intersection_states.items():
            detector_data = state.get("detector_data", {})

            # 计算拥堵指数：基于各方向车辆数
            total_vehicles = sum(
                detector_data.get(f"{direction}_count", 0)
                for direction in ["north", "south", "east", "west"]
            )

            # 归一化到 0-1
            congestion_level = min(1.0, total_vehicles / 40.0)  # 假设 40 辆为饱和
            congestion_map[intersection_id] = congestion_level

        return congestion_map

    def _generate_route_guidance(
        self,
        vehicle_states: Dict[str, Dict[str, Any]],
        congestion_map: Dict[str, float],
    ) -> Dict[str, List[str]]:
        """生成路径引导

        为 CAV 车辆生成避开拥堵的路径建议。
        """
        route_guidance = {}

        # 识别拥堵路口（拥堵度 > 0.7）
        congested_intersections = {
            iid for iid, level in congestion_map.items() if level > 0.7
        }

        for vehicle_id, state in vehicle_states.items():
            # 只为 CAV 生成引导
            if not state.get("is_cav", False):
                continue

            # 简化实现：如果目标路径经过拥堵路口，建议绕行
            # 实际应使用动态路径规划算法
            current_route = state.get("route", [])

            # 检查路径是否经过拥堵路口
            has_congestion = any(
                edge in congested_intersections for edge in current_route
            )

            if has_congestion:
                # 生成替代路径（简化：添加 "_alt" 后缀）
                alternative_route = [edge + "_alt" for edge in current_route]
                route_guidance[vehicle_id] = alternative_route

        return route_guidance

    def _generate_platoon_strategy(
        self,
        vehicle_states: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """生成 CAV 编队策略"""
        # 识别 CAV 车辆
        cav_vehicles = [
            vid for vid, state in vehicle_states.items()
            if state.get("is_cav", False)
        ]

        # 简化实现：按位置分组
        platoons = []
        platoon_size = 5

        for i in range(0, len(cav_vehicles), platoon_size):
            platoon = cav_vehicles[i:i + platoon_size]
            if len(platoon) >= 2:  # 至少 2 辆车才能编队
                platoons.append({
                    "platoon_id": f"platoon_{len(platoons)}",
                    "vehicles": platoon,
                    "leader": platoon[0],
                    "target_spacing": 5.0,  # 米
                })

        return {
            "platoons": platoons,
            "total_platoons": len(platoons),
            "total_vehicles": len(cav_vehicles),
        }

    def _dispatch_strategy(
        self,
        coordination_strategy: Dict[str, Any],
        vehicle_states: Dict[str, Dict[str, Any]],
        detector_data: Dict[str, Dict[str, float]],
    ) -> Dict[str, AgentStepResult]:
        """分发协调策略到各路口"""
        results = {}

        for intersection_id, agent in self.intersections.items():
            # 构造路口执行上下文
            context = {
                "vehicle_states": vehicle_states,
                "detector_data": detector_data.get(intersection_id, {}),
                "neighbor_states": self._get_neighbor_states(intersection_id),
                "coordination_strategy": coordination_strategy,
            }

            # 执行路口决策
            result = agent.execute(context)
            results[intersection_id] = result

            # 累积统计
            self._accumulate(result)

        return results

    def _get_neighbor_states(self, intersection_id: str) -> Dict[str, Dict[str, Any]]:
        """获取相邻路口状态"""
        # 简化实现：返回所有其他路口的状态
        neighbor_states = {}

        for other_id, agent in self.intersections.items():
            if other_id != intersection_id:
                neighbor_states[other_id] = agent.get_state()

        return neighbor_states

    def _validate_results(
        self,
        intersection_results: Dict[str, AgentStepResult],
    ) -> Dict[str, Any]:
        """验证执行结果"""
        failed_intersections = []
        warnings = []

        for intersection_id, result in intersection_results.items():
            if not result.success:
                failed_intersections.append(intersection_id)
                warnings.append(f"Intersection {intersection_id} failed: {result.error}")

        passed = len(failed_intersections) == 0

        return {
            "passed": passed,
            "failed_intersections": failed_intersections,
            "warnings": warnings,
            "total_intersections": len(intersection_results),
            "success_rate": (len(intersection_results) - len(failed_intersections)) / max(len(intersection_results), 1),
        }

    def _calculate_metrics(
        self,
        intersection_states: Dict[str, Dict[str, Any]],
    ) -> Dict[str, float]:
        """计算性能指标"""
        total_vehicles = 0
        total_congestion = 0.0

        for state in intersection_states.values():
            detector_data = state.get("detector_data", {})
            vehicles = sum(
                detector_data.get(f"{direction}_count", 0)
                for direction in ["north", "south", "east", "west"]
            )
            total_vehicles += vehicles

        avg_vehicles_per_intersection = total_vehicles / max(len(intersection_states), 1)

        return {
            "total_vehicles": total_vehicles,
            "avg_vehicles_per_intersection": avg_vehicles_per_intersection,
            "total_intersections": len(intersection_states),
        }
