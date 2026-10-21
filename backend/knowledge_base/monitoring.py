"""
AI助手监控告警系统

提供全面的监控和告警功能：
- 性能监控：API响应时间、成功率、错误率
- 资源监控：内存、CPU、磁盘使用
- 知识库监控：索引质量、更新状态
- 告警机制：阈值配置、通知发送
- 数据存储：历史监控数据
"""

import time
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import deque
from pathlib import Path
import json
import threading

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    timestamp: str
    endpoint: str
    response_time: float  # 毫秒
    success: bool
    error_message: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class ResourceMetrics:
    """资源指标"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_percent: float
    disk_used_gb: float


@dataclass
class KnowledgeBaseMetrics:
    """知识库指标"""
    timestamp: str
    total_documents: int
    index_quality_score: float
    last_update_time: str
    update_success: bool
    avg_retrieval_time: float  # 毫秒


@dataclass
class Alert:
    """告警"""
    timestamp: str
    level: str  # info, warning, error, critical
    category: str  # performance, resource, knowledge_base
    message: str
    details: Dict[str, Any]
    resolved: bool = False


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics: deque = deque(maxlen=max_history)
        self._lock = threading.Lock()

    def record_request(
        self,
        endpoint: str,
        response_time: float,
        success: bool,
        error_message: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """记录请求性能"""
        metric = PerformanceMetrics(
            timestamp=datetime.now().isoformat(),
            endpoint=endpoint,
            response_time=response_time,
            success=success,
            error_message=error_message,
            user_id=user_id
        )

        with self._lock:
            self.metrics.append(metric)

    def get_statistics(self, minutes: int = 60) -> Dict[str, Any]:
        """获取统计信息"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        with self._lock:
            recent_metrics = [
                m for m in self.metrics
                if datetime.fromisoformat(m.timestamp) > cutoff_time
            ]

        if not recent_metrics:
            return {
                "total_requests": 0,
                "success_rate": 0.0,
                "avg_response_time": 0.0,
                "error_rate": 0.0
            }

        total = len(recent_metrics)
        successful = sum(1 for m in recent_metrics if m.success)
        total_time = sum(m.response_time for m in recent_metrics)

        # 按端点统计
        endpoint_stats = {}
        for metric in recent_metrics:
            if metric.endpoint not in endpoint_stats:
                endpoint_stats[metric.endpoint] = {
                    "count": 0,
                    "success": 0,
                    "total_time": 0.0
                }

            stats = endpoint_stats[metric.endpoint]
            stats["count"] += 1
            if metric.success:
                stats["success"] += 1
            stats["total_time"] += metric.response_time

        # 计算每个端点的平均响应时间和成功率
        for endpoint, stats in endpoint_stats.items():
            stats["avg_response_time"] = stats["total_time"] / stats["count"]
            stats["success_rate"] = stats["success"] / stats["count"]
            del stats["total_time"]

        return {
            "total_requests": total,
            "success_rate": successful / total,
            "avg_response_time": total_time / total,
            "error_rate": (total - successful) / total,
            "endpoint_stats": endpoint_stats,
            "time_window_minutes": minutes
        }

    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的错误"""
        with self._lock:
            errors = [
                asdict(m) for m in self.metrics
                if not m.success
            ]

        return errors[-limit:]


class ResourceMonitor:
    """资源监控器"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics: deque = deque(maxlen=max_history)
        self._lock = threading.Lock()

    def collect_metrics(self) -> ResourceMetrics:
        """收集资源指标"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        metric = ResourceMetrics(
            timestamp=datetime.now().isoformat(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 * 1024 * 1024)
        )

        with self._lock:
            self.metrics.append(metric)

        return metric

    def get_current_status(self) -> Dict[str, Any]:
        """获取当前资源状态"""
        metric = self.collect_metrics()
        return asdict(metric)

    def get_statistics(self, minutes: int = 60) -> Dict[str, Any]:
        """获取统计信息"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        with self._lock:
            recent_metrics = [
                m for m in self.metrics
                if datetime.fromisoformat(m.timestamp) > cutoff_time
            ]

        if not recent_metrics:
            return {
                "avg_cpu_percent": 0.0,
                "avg_memory_percent": 0.0,
                "avg_disk_percent": 0.0,
                "max_cpu_percent": 0.0,
                "max_memory_percent": 0.0
            }

        return {
            "avg_cpu_percent": sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics),
            "avg_memory_percent": sum(m.memory_percent for m in recent_metrics) / len(recent_metrics),
            "avg_disk_percent": sum(m.disk_percent for m in recent_metrics) / len(recent_metrics),
            "max_cpu_percent": max(m.cpu_percent for m in recent_metrics),
            "max_memory_percent": max(m.memory_percent for m in recent_metrics),
            "time_window_minutes": minutes
        }


class KnowledgeBaseMonitor:
    """知识库监控器"""

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.metrics: deque = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self.retrieval_times: deque = deque(maxlen=100)

    def record_index_status(
        self,
        total_documents: int,
        quality_score: float,
        last_update_time: str,
        update_success: bool
    ):
        """记录索引状态"""
        avg_retrieval = (
            sum(self.retrieval_times) / len(self.retrieval_times)
            if self.retrieval_times else 0.0
        )

        metric = KnowledgeBaseMetrics(
            timestamp=datetime.now().isoformat(),
            total_documents=total_documents,
            index_quality_score=quality_score,
            last_update_time=last_update_time,
            update_success=update_success,
            avg_retrieval_time=avg_retrieval
        )

        with self._lock:
            self.metrics.append(metric)

    def record_retrieval_time(self, time_ms: float):
        """记录检索时间"""
        self.retrieval_times.append(time_ms)

    def get_current_status(self) -> Optional[Dict[str, Any]]:
        """获取当前状态"""
        with self._lock:
            if not self.metrics:
                return None
            return asdict(self.metrics[-1])

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            if not self.metrics:
                return {
                    "avg_quality_score": 0.0,
                    "avg_retrieval_time": 0.0,
                    "update_success_rate": 0.0
                }

            total = len(self.metrics)
            successful_updates = sum(1 for m in self.metrics if m.update_success)

            return {
                "avg_quality_score": sum(m.index_quality_score for m in self.metrics) / total,
                "avg_retrieval_time": sum(m.avg_retrieval_time for m in self.metrics) / total,
                "update_success_rate": successful_updates / total,
                "total_documents": self.metrics[-1].total_documents
            }


class AlertManager:
    """告警管理器"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.alerts: List[Alert] = []
        self._lock = threading.Lock()
        self.storage_path = storage_path

        # 告警阈值配置
        self.thresholds = {
            "performance": {
                "response_time_ms": 5000,  # 响应时间超过5秒
                "error_rate": 0.1,  # 错误率超过10%
                "success_rate": 0.9  # 成功率低于90%
            },
            "resource": {
                "cpu_percent": 80,  # CPU使用率超过80%
                "memory_percent": 85,  # 内存使用率超过85%
                "disk_percent": 90  # 磁盘使用率超过90%
            },
            "knowledge_base": {
                "quality_score": 70,  # 质量评分低于70
                "retrieval_time_ms": 3000  # 检索时间超过3秒
            }
        }

        # 加载历史告警
        if self.storage_path and self.storage_path.exists():
            self._load_alerts()

    def check_performance_alerts(self, stats: Dict[str, Any]) -> List[Alert]:
        """检查性能告警"""
        alerts = []
        thresholds = self.thresholds["performance"]

        # 检查响应时间
        if stats["avg_response_time"] > thresholds["response_time_ms"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="warning",
                category="performance",
                message=f"平均响应时间过高: {stats['avg_response_time']:.2f}ms",
                details={"avg_response_time": stats["avg_response_time"]}
            ))

        # 检查错误率
        if stats["error_rate"] > thresholds["error_rate"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="error",
                category="performance",
                message=f"错误率过高: {stats['error_rate']:.2%}",
                details={"error_rate": stats["error_rate"]}
            ))

        # 检查成功率
        if stats["success_rate"] < thresholds["success_rate"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="warning",
                category="performance",
                message=f"成功率过低: {stats['success_rate']:.2%}",
                details={"success_rate": stats["success_rate"]}
            ))

        return alerts

    def check_resource_alerts(self, stats: Dict[str, Any]) -> List[Alert]:
        """检查资源告警"""
        alerts = []
        thresholds = self.thresholds["resource"]

        # 检查CPU
        if stats["avg_cpu_percent"] > thresholds["cpu_percent"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="warning",
                category="resource",
                message=f"CPU使用率过高: {stats['avg_cpu_percent']:.1f}%",
                details={"cpu_percent": stats["avg_cpu_percent"]}
            ))

        # 检查内存
        if stats["avg_memory_percent"] > thresholds["memory_percent"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="error",
                category="resource",
                message=f"内存使用率过高: {stats['avg_memory_percent']:.1f}%",
                details={"memory_percent": stats["avg_memory_percent"]}
            ))

        # 检查磁盘
        if stats["avg_disk_percent"] > thresholds["disk_percent"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="critical",
                category="resource",
                message=f"磁盘使用率过高: {stats['avg_disk_percent']:.1f}%",
                details={"disk_percent": stats["avg_disk_percent"]}
            ))

        return alerts

    def check_knowledge_base_alerts(self, stats: Dict[str, Any]) -> List[Alert]:
        """检查知识库告警"""
        alerts = []
        thresholds = self.thresholds["knowledge_base"]

        # 检查质量评分
        if stats["avg_quality_score"] < thresholds["quality_score"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="warning",
                category="knowledge_base",
                message=f"索引质量评分过低: {stats['avg_quality_score']:.1f}",
                details={"quality_score": stats["avg_quality_score"]}
            ))

        # 检查检索时间
        if stats["avg_retrieval_time"] > thresholds["retrieval_time_ms"]:
            alerts.append(Alert(
                timestamp=datetime.now().isoformat(),
                level="warning",
                category="knowledge_base",
                message=f"平均检索时间过长: {stats['avg_retrieval_time']:.2f}ms",
                details={"retrieval_time": stats["avg_retrieval_time"]}
            ))

        return alerts

    def add_alerts(self, alerts: List[Alert]):
        """添加告警"""
        with self._lock:
            self.alerts.extend(alerts)

            # 保存到文件
            if self.storage_path:
                self._save_alerts()

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """获取活跃告警"""
        with self._lock:
            return [
                asdict(alert) for alert in self.alerts
                if not alert.resolved
            ]

    def get_all_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有告警"""
        with self._lock:
            return [asdict(alert) for alert in self.alerts[-limit:]]

    def resolve_alert(self, timestamp: str):
        """解决告警"""
        with self._lock:
            for alert in self.alerts:
                if alert.timestamp == timestamp:
                    alert.resolved = True
                    break

            if self.storage_path:
                self._save_alerts()

    def update_thresholds(self, category: str, thresholds: Dict[str, float]):
        """更新阈值"""
        if category in self.thresholds:
            self.thresholds[category].update(thresholds)

    def _save_alerts(self):
        """保存告警到文件"""
        try:
            data = [asdict(alert) for alert in self.alerts]
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存告警失败: {e}")

    def _load_alerts(self):
        """从文件加载告警"""
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.alerts = [
                    Alert(**item) for item in data
                ]
        except Exception as e:
            logger.error(f"加载告警失败: {e}")


class MonitoringSystem:
    """监控系统（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True

        # 初始化各个监控器
        self.performance_monitor = PerformanceMonitor()
        self.resource_monitor = ResourceMonitor()
        self.kb_monitor = KnowledgeBaseMonitor()

        # 初始化告警管理器
        storage_path = Path("backend/knowledge_base/alerts.json")
        self.alert_manager = AlertManager(storage_path)

        # 自动监控线程
        self._monitoring_thread = None
        self._stop_monitoring = threading.Event()

    def start_monitoring(self, interval_seconds: int = 60):
        """启动自动监控"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("监控已在运行")
            return

        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval_seconds,),
            daemon=True
        )
        self._monitoring_thread.start()
        logger.info(f"监控系统已启动，间隔 {interval_seconds} 秒")

    def stop_monitoring(self):
        """停止自动监控"""
        self._stop_monitoring.set()
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("监控系统已停止")

    def _monitoring_loop(self, interval_seconds: int):
        """监控循环"""
        while not self._stop_monitoring.is_set():
            try:
                # 收集资源指标
                self.resource_monitor.collect_metrics()

                # 检查告警
                self._check_all_alerts()

            except Exception as e:
                logger.error(f"监控循环错误: {e}")

            # 等待下一次检查
            self._stop_monitoring.wait(interval_seconds)

    def _check_all_alerts(self):
        """检查所有告警"""
        alerts = []

        # 检查性能告警
        perf_stats = self.performance_monitor.get_statistics(minutes=10)
        if perf_stats["total_requests"] > 0:
            alerts.extend(self.alert_manager.check_performance_alerts(perf_stats))

        # 检查资源告警
        resource_stats = self.resource_monitor.get_statistics(minutes=10)
        alerts.extend(self.alert_manager.check_resource_alerts(resource_stats))

        # 检查知识库告警
        kb_stats = self.kb_monitor.get_statistics()
        if kb_stats["avg_quality_score"] > 0:
            alerts.extend(self.alert_manager.check_knowledge_base_alerts(kb_stats))

        # 添加告警
        if alerts:
            self.alert_manager.add_alerts(alerts)
            logger.warning(f"检测到 {len(alerts)} 个新告警")

    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        perf_stats = self.performance_monitor.get_statistics(minutes=60)
        resource_stats = self.resource_monitor.get_statistics(minutes=60)
        kb_stats = self.kb_monitor.get_statistics()
        active_alerts = self.alert_manager.get_active_alerts()

        # 计算健康评分
        health_score = 100.0

        # 性能扣分
        if perf_stats["total_requests"] > 0:
            health_score -= perf_stats["error_rate"] * 30
            if perf_stats["avg_response_time"] > 3000:
                health_score -= 10

        # 资源扣分
        if resource_stats["avg_cpu_percent"] > 80:
            health_score -= 15
        if resource_stats["avg_memory_percent"] > 85:
            health_score -= 15

        # 知识库扣分
        if kb_stats["avg_quality_score"] < 70:
            health_score -= 10

        # 告警扣分
        health_score -= len(active_alerts) * 5

        health_score = max(0, health_score)

        # 确定健康状态
        if health_score >= 90:
            status = "healthy"
        elif health_score >= 70:
            status = "degraded"
        elif health_score >= 50:
            status = "unhealthy"
        else:
            status = "critical"

        return {
            "status": status,
            "health_score": health_score,
            "timestamp": datetime.now().isoformat(),
            "performance": perf_stats,
            "resources": resource_stats,
            "knowledge_base": kb_stats,
            "active_alerts": len(active_alerts),
            "alerts": active_alerts[:5]  # 只返回前5个告警
        }


# 全局监控系统实例
monitoring_system = MonitoringSystem()
