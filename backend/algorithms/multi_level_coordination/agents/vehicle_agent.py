"""车辆智能体

负责单个车辆的路径选择和速度控制决策。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent, AgentStepResult


class VehicleAgent(BaseAgent):
    """车辆智能体

    职责：
    - 接收路口引导信号
    - 路径选择决策
    - 速度控制决策
    """

    name = "vehicle"

    def __init__(
        self,
        agent_id: str,
        vehicle_id: str,
        is_cav: bool = False,
    ) -> None:
        super().__init__(agent_id)
        self.vehicle_id = vehicle_id
        self.is_cav = is_cav  # 是否为网联自动驾驶车辆
        self.current_route: List[str] = []
        self.target_speed: Optional[float] = None
        self.guidance_history: List[Dict[str, Any]] = []

    def execute(self, context: Dict[str, Any]) -> AgentStepResult:
        """执行车辆决策

        Args:
            context: {
                "current_position": str,  # 当前边 ID
                "destination": str,       # 目的地边 ID
                "current_speed": float,   # 当前速度 (m/s)
                "guidance": Optional[Dict],  # 路口引导信号
                "road_network": Dict,     # 路网信息
            }

        Returns:
            AgentStepResult: {
                "route": List[str],       # 路径决策
                "target_speed": float,    # 目标速度
                "action": str,            # 动作类型
            }
        """
        start_time = time.time()
        self._step_count += 1

        try:
            current_pos = context.get("current_position")
            destination = context.get("destination")
            current_speed = context.get("current_speed", 0.0)
            guidance = context.get("guidance")

            # 如果是 CAV 且收到引导信号，则遵循引导
            if self.is_cav and guidance:
                self._apply_guidance(guidance)

            # 路径决策
            route = self._plan_route(current_pos, destination, context.get("road_network", {}))

            # 速度决策
            target_speed = self._decide_speed(current_speed, guidance)

            # 确定动作类型
            action = self._determine_action(current_speed, target_speed)

            execution_time = time.time() - start_time
            self._total_execution_time += execution_time

            return self._make_result(
                success=True,
                data={
                    "route": route,
                    "target_speed": target_speed,
                    "action": action,
                    "is_cav": self.is_cav,
                },
            )

        except Exception as e:
            self.logger.error(f"Vehicle {self.vehicle_id} execution failed: {e}")
            execution_time = time.time() - start_time
            self._total_execution_time += execution_time
            return self._make_result(success=False, error=str(e))

    def _apply_guidance(self, guidance: Dict[str, Any]) -> None:
        """应用路口引导信号"""
        self.guidance_history.append(guidance)

        # 提取引导信息
        if "recommended_route" in guidance:
            self.current_route = guidance["recommended_route"]

        if "recommended_speed" in guidance:
            self.target_speed = guidance["recommended_speed"]

        self.logger.debug(
            f"Vehicle {self.vehicle_id} received guidance: "
            f"route={self.current_route}, speed={self.target_speed}"
        )

    def _plan_route(
        self,
        current_pos: str,
        destination: str,
        road_network: Dict[str, Any],
    ) -> List[str]:
        """规划路径

        如果已有引导路径则使用，否则使用最短路径。
        """
        if self.current_route:
            return self.current_route

        # 简化实现：返回直达路径
        # 实际应使用 Dijkstra 或 A* 算法
        return [current_pos, destination]

    def _decide_speed(
        self,
        current_speed: float,
        guidance: Optional[Dict[str, Any]],
    ) -> float:
        """决策目标速度"""
        # 如果有引导速度且是 CAV，则使用引导速度
        if self.is_cav and guidance and "recommended_speed" in guidance:
            return guidance["recommended_speed"]

        # 如果有目标速度，则使用
        if self.target_speed is not None:
            return self.target_speed

        # 默认保持当前速度
        return current_speed

    def _determine_action(self, current_speed: float, target_speed: float) -> str:
        """确定动作类型"""
        speed_diff = target_speed - current_speed

        if abs(speed_diff) < 0.5:
            return "maintain"
        elif speed_diff > 0:
            return "accelerate"
        else:
            return "decelerate"

    def get_state(self) -> Dict[str, Any]:
        """获取车辆状态"""
        return {
            "vehicle_id": self.vehicle_id,
            "agent_id": self.agent_id,
            "is_cav": self.is_cav,
            "current_route": self.current_route,
            "target_speed": self.target_speed,
            "step_count": self._step_count,
        }
