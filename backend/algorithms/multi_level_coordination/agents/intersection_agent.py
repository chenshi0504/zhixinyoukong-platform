"""路口智能体

负责单个路口的信号优化和车辆引导。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent, AgentStepResult


class IntersectionAgent(BaseAgent):
    """路口智能体

    职责：
    - 收集路口车流状态
    - 优化信号配时
    - 生成车辆引导信号
    - 与相邻路口协调
    """

    name = "intersection"

    def __init__(
        self,
        agent_id: str,
        intersection_id: str,
        phases: List[Dict[str, Any]],
    ) -> None:
        super().__init__(agent_id)
        self.intersection_id = intersection_id
        self.phases = phases  # 信号相位配置
        self.current_phase_index = 0
        self.phase_remaining_time = 0
        self.neighbor_states: Dict[str, Dict[str, Any]] = {}
        self.vehicle_queue: Dict[str, List[str]] = {}  # 各方向排队车辆

    def execute(self, context: Dict[str, Any]) -> AgentStepResult:
        """执行路口决策

        Args:
            context: {
                "vehicle_states": Dict[str, Dict],  # 车辆状态
                "detector_data": Dict[str, float],  # 检测器数据
                "neighbor_states": Dict[str, Dict], # 相邻路口状态
                "coordination_strategy": Optional[Dict],  # 协调策略
            }

        Returns:
            AgentStepResult: {
                "signal_plan": Dict,      # 信号配时方案
                "vehicle_guidance": Dict, # 车辆引导信号
                "intersection_state": Dict,  # 路口状态
            }
        """
        start_time = time.time()
        self._step_count += 1

        try:
            vehicle_states = context.get("vehicle_states", {})
            detector_data = context.get("detector_data", {})
            neighbor_states = context.get("neighbor_states", {})
            coordination_strategy = context.get("coordination_strategy")

            # 更新相邻路口状态
            self.neighbor_states = neighbor_states

            # 收集路口状态
            intersection_state = self._collect_state(vehicle_states, detector_data)

            # 优化信号配时
            signal_plan = self._optimize_signal(
                intersection_state,
                coordination_strategy,
            )

            # 生成车辆引导
            vehicle_guidance = self._generate_guidance(
                vehicle_states,
                signal_plan,
                coordination_strategy,
            )

            execution_time = time.time() - start_time
            self._total_execution_time += execution_time

            return self._make_result(
                success=True,
                data={
                    "signal_plan": signal_plan,
                    "vehicle_guidance": vehicle_guidance,
                    "intersection_state": intersection_state,
                },
            )

        except Exception as e:
            self.logger.error(f"Intersection {self.intersection_id} execution failed: {e}")
            execution_time = time.time() - start_time
            self._total_execution_time += execution_time
            return self._make_result(success=False, error=str(e))

    def _collect_state(
        self,
        vehicle_states: Dict[str, Dict[str, Any]],
        detector_data: Dict[str, float],
    ) -> Dict[str, Any]:
        """收集路口状态"""
        # 统计各方向车辆数
        direction_counts = {}
        for direction in ["north", "south", "east", "west"]:
            direction_counts[direction] = detector_data.get(f"{direction}_count", 0)

        # 计算平均排队长度
        avg_queue_length = sum(direction_counts.values()) / max(len(direction_counts), 1)

        # 计算饱和度
        capacity = 1800  # 每小时每车道通行能力
        saturation = sum(direction_counts.values()) / (capacity / 3600 * 4)  # 4个方向

        return {
            "intersection_id": self.intersection_id,
            "direction_counts": direction_counts,
            "avg_queue_length": avg_queue_length,
            "saturation": saturation,
            "current_phase": self.current_phase_index,
            "phase_remaining_time": self.phase_remaining_time,
        }

    def _optimize_signal(
        self,
        intersection_state: Dict[str, Any],
        coordination_strategy: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """优化信号配时

        如果有协调策略则遵循，否则使用本地优化。
        """
        if coordination_strategy and "signal_timing" in coordination_strategy:
            # 使用协调策略
            return coordination_strategy["signal_timing"]

        # 本地优化：基于排队长度调整绿灯时间
        direction_counts = intersection_state["direction_counts"]

        # 计算各相位权重
        phase_weights = []
        for phase in self.phases:
            phase_directions = phase.get("directions", [])
            phase_demand = sum(direction_counts.get(d, 0) for d in phase_directions)
            phase_weights.append(phase_demand)

        # 分配绿灯时间（总周期 120 秒）
        total_weight = sum(phase_weights) if sum(phase_weights) > 0 else 1
        cycle_time = 120
        min_green = 10

        phase_timings = []
        for i, weight in enumerate(phase_weights):
            green_time = max(min_green, int((weight / total_weight) * cycle_time))
            phase_timings.append({
                "phase_index": i,
                "green_time": green_time,
                "yellow_time": 3,
                "red_time": cycle_time - green_time - 3,
            })

        return {
            "intersection_id": self.intersection_id,
            "cycle_time": cycle_time,
            "phase_timings": phase_timings,
            "optimization_method": "local",
        }

    def _generate_guidance(
        self,
        vehicle_states: Dict[str, Dict[str, Any]],
        signal_plan: Dict[str, Any],
        coordination_strategy: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """生成车辆引导信号"""
        guidance = {}

        for vehicle_id, state in vehicle_states.items():
            # 只为 CAV 车辆生成引导
            if not state.get("is_cav", False):
                continue

            # 计算推荐速度（绿波速度）
            recommended_speed = self._calculate_green_wave_speed(
                state,
                signal_plan,
                coordination_strategy,
            )

            # 推荐路径（如果有协调策略）
            recommended_route = None
            if coordination_strategy and "route_guidance" in coordination_strategy:
                route_guidance = coordination_strategy["route_guidance"]
                recommended_route = route_guidance.get(vehicle_id)

            guidance[vehicle_id] = {
                "intersection_id": self.intersection_id,
                "recommended_speed": recommended_speed,
                "recommended_route": recommended_route,
                "signal_phase": self.current_phase_index,
                "time_to_green": self._calculate_time_to_green(state),
            }

        return guidance

    def _calculate_green_wave_speed(
        self,
        vehicle_state: Dict[str, Any],
        signal_plan: Dict[str, Any],
        coordination_strategy: Optional[Dict[str, Any]],
    ) -> float:
        """计算绿波速度"""
        # 如果有协调策略中的绿波速度，则使用
        if coordination_strategy and "green_wave_speed" in coordination_strategy:
            return coordination_strategy["green_wave_speed"]

        # 默认推荐速度：50 km/h = 13.89 m/s
        return 13.89

    def _calculate_time_to_green(self, vehicle_state: Dict[str, Any]) -> float:
        """计算到达绿灯的时间"""
        # 简化实现：返回当前相位剩余时间
        return self.phase_remaining_time

    def update_phase(self, phase_index: int, remaining_time: float) -> None:
        """更新当前相位"""
        self.current_phase_index = phase_index
        self.phase_remaining_time = remaining_time

    def get_state(self) -> Dict[str, Any]:
        """获取路口状态"""
        return {
            "intersection_id": self.intersection_id,
            "agent_id": self.agent_id,
            "current_phase": self.current_phase_index,
            "phase_remaining_time": self.phase_remaining_time,
            "step_count": self._step_count,
        }
