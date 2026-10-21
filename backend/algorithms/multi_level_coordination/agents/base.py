"""基础 Agent 类

参考 Claw-AI-Lab 的 BaseAgent 和 AgentOrchestrator 设计模式。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentStepResult:
    """Agent 执行步骤的结果"""

    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    step_count: int = 0
    execution_time: float = 0.0

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"AgentStepResult({status}, steps={self.step_count}, time={self.execution_time:.2f}s)"


class BaseAgent:
    """基础 Agent 类

    所有智能体的基类，提供统一的执行接口和状态追踪。
    """

    name: str = "base"

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._step_count = 0
        self._total_execution_time = 0.0
        self.logger = logging.getLogger(f"{__name__}.{self.name}.{agent_id}")

    def execute(self, context: Dict[str, Any]) -> AgentStepResult:
        """执行 Agent 任务

        Args:
            context: 执行上下文，包含输入数据

        Returns:
            AgentStepResult: 执行结果
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def _make_result(
        self,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: str = "",
    ) -> AgentStepResult:
        """创建执行结果"""
        return AgentStepResult(
            success=success,
            data=data or {},
            error=error,
            step_count=self._step_count,
            execution_time=self._total_execution_time,
        )

    def reset(self) -> None:
        """重置 Agent 状态"""
        self._step_count = 0
        self._total_execution_time = 0.0


class AgentOrchestrator:
    """Agent 协调器

    协调多个 Agent 的工作流，支持串行、并行、迭代等执行模式。
    """

    def __init__(self, orchestrator_id: str, *, max_iterations: int = 3) -> None:
        self.orchestrator_id = orchestrator_id
        self.max_iterations = max_iterations
        self.logger = logging.getLogger(f"{__name__}.orchestrator.{orchestrator_id}")
        self.total_step_count = 0
        self.total_execution_time = 0.0

    def _accumulate(self, result: AgentStepResult) -> None:
        """累积统计信息"""
        self.total_step_count += result.step_count
        self.total_execution_time += result.execution_time

    def orchestrate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行协调工作流

        Args:
            context: 执行上下文

        Returns:
            Dict[str, Any]: 协调结果
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement orchestrate()")

    def reset(self) -> None:
        """重置协调器状态"""
        self.total_step_count = 0
        self.total_execution_time = 0.0
