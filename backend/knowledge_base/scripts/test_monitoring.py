"""
监控系统测试脚本
验证性能监控、资源监控、告警等功能
"""

import sys
import os
import time
import random
from pathlib import Path
from datetime import datetime

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.monitoring import (
    monitoring_system,
    PerformanceMonitor,
    ResourceMonitor,
    KnowledgeBaseMonitor,
    AlertManager
)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_performance_monitor():
    """测试性能监控"""
    print_section("测试1: 性能监控")

    monitor = PerformanceMonitor()

    # 模拟记录请求
    endpoints = ['/api/search', '/api/chat', '/api/documents']

    print("\n模拟记录20个请求...")
    for i in range(20):
        endpoint = random.choice(endpoints)
        response_time = random.uniform(100, 2000)  # 100-2000ms
        success = random.random() > 0.1  # 90%成功率

        monitor.record_request(
            endpoint=endpoint,
            response_time=response_time,
            success=success,
            error_message=None if success else "模拟错误",
            user_id=f"user_{random.randint(1, 5)}"
        )

    # 获取统计信息
    stats = monitor.get_statistics(minutes=60)

    print("\n性能统计:")
    print(f"  总请求数: {stats['total_requests']}")
    print(f"  成功率: {stats['success_rate']:.2%}")
    print(f"  平均响应时间: {stats['avg_response_time']:.2f}ms")
    print(f"  错误率: {stats['error_rate']:.2%}")

    print("\n按端点统计:")
    for endpoint, ep_stats in stats['endpoint_stats'].items():
        print(f"  {endpoint}:")
        print(f"    请求数: {ep_stats['count']}")
        print(f"    成功率: {ep_stats['success_rate']:.2%}")
        print(f"    平均响应时间: {ep_stats['avg_response_time']:.2f}ms")

    # 获取最近错误
    errors = monitor.get_recent_errors(limit=5)
    print(f"\n最近错误数: {len(errors)}")

    print("\n✅ 性能监控测试通过")
    return True


def test_resource_monitor():
    """测试资源监控"""
    print_section("测试2: 资源监控")

    monitor = ResourceMonitor()

    # 收集当前资源状态
    print("\n收集资源指标...")
    status = monitor.get_current_status()

    print("\n当前资源状态:")
    print(f"  CPU使用率: {status['cpu_percent']:.1f}%")
    print(f"  内存使用率: {status['memory_percent']:.1f}%")
    print(f"  内存使用量: {status['memory_used_mb']:.1f}MB")
    print(f"  磁盘使用率: {status['disk_percent']:.1f}%")
    print(f"  磁盘使用量: {status['disk_used_gb']:.1f}GB")

    # 模拟收集多次
    print("\n模拟收集10次资源指标...")
    for i in range(10):
        monitor.collect_metrics()
        time.sleep(0.1)

    # 获取统计信息
    stats = monitor.get_statistics(minutes=60)

    print("\n资源统计:")
    print(f"  平均CPU使用率: {stats['avg_cpu_percent']:.1f}%")
    print(f"  平均内存使用率: {stats['avg_memory_percent']:.1f}%")
    print(f"  最大CPU使用率: {stats['max_cpu_percent']:.1f}%")
    print(f"  最大内存使用率: {stats['max_memory_percent']:.1f}%")

    print("\n✅ 资源监控测试通过")
    return True


def test_knowledge_base_monitor():
    """测试知识库监控"""
    print_section("测试3: 知识库监控")

    monitor = KnowledgeBaseMonitor()

    # 模拟记录检索时间
    print("\n模拟记录20次检索时间...")
    for i in range(20):
        retrieval_time = random.uniform(100, 1000)  # 100-1000ms
        monitor.record_retrieval_time(retrieval_time)

    # 记录索引状态
    print("\n记录索引状态...")
    monitor.record_index_status(
        total_documents=1500,
        quality_score=85.5,
        last_update_time=datetime.now().isoformat(),
        update_success=True
    )

    # 获取当前状态
    status = monitor.get_current_status()

    print("\n当前知识库状态:")
    print(f"  文档总数: {status['total_documents']}")
    print(f"  质量评分: {status['index_quality_score']:.1f}")
    print(f"  平均检索时间: {status['avg_retrieval_time']:.2f}ms")
    print(f"  最后更新: {status['last_update_time']}")
    print(f"  更新成功: {status['update_success']}")

    # 获取统计信息
    stats = monitor.get_statistics()

    print("\n知识库统计:")
    print(f"  平均质量评分: {stats['avg_quality_score']:.1f}")
    print(f"  平均检索时间: {stats['avg_retrieval_time']:.2f}ms")
    print(f"  更新成功率: {stats['update_success_rate']:.2%}")

    print("\n✅ 知识库监控测试通过")
    return True


def test_alert_manager():
    """测试告警管理"""
    print_section("测试4: 告警管理")

    # 创建临时告警管理器
    alert_manager = AlertManager()

    # 模拟性能统计（触发告警）
    print("\n模拟性能统计（高错误率）...")
    perf_stats = {
        'total_requests': 100,
        'success_rate': 0.85,  # 低于90%阈值
        'avg_response_time': 3500,  # 低于5000ms阈值
        'error_rate': 0.15  # 高于10%阈值
    }

    alerts = alert_manager.check_performance_alerts(perf_stats)
    print(f"\n检测到 {len(alerts)} 个性能告警:")
    for alert in alerts:
        print(f"  [{alert.level}] {alert.message}")

    # 模拟资源统计（触发告警）
    print("\n模拟资源统计（高CPU使用率）...")
    resource_stats = {
        'avg_cpu_percent': 85,  # 高于80%阈值
        'avg_memory_percent': 75,
        'avg_disk_percent': 70,
        'max_cpu_percent': 90,
        'max_memory_percent': 80
    }

    alerts = alert_manager.check_resource_alerts(resource_stats)
    print(f"\n检测到 {len(alerts)} 个资源告警:")
    for alert in alerts:
        print(f"  [{alert.level}] {alert.message}")

    # 模拟知识库统计（触发告警）
    print("\n模拟知识库统计（低质量评分）...")
    kb_stats = {
        'avg_quality_score': 65,  # 低于70阈值
        'avg_retrieval_time': 2500,  # 低于3000ms阈值
        'update_success_rate': 0.95
    }

    alerts = alert_manager.check_knowledge_base_alerts(kb_stats)
    print(f"\n检测到 {len(alerts)} 个知识库告警:")
    for alert in alerts:
        print(f"  [{alert.level}] {alert.message}")

    # 添加告警
    all_alerts = []
    all_alerts.extend(alert_manager.check_performance_alerts(perf_stats))
    all_alerts.extend(alert_manager.check_resource_alerts(resource_stats))
    all_alerts.extend(alert_manager.check_knowledge_base_alerts(kb_stats))

    alert_manager.add_alerts(all_alerts)

    # 获取活跃告警
    active_alerts = alert_manager.get_active_alerts()
    print(f"\n活跃告警总数: {len(active_alerts)}")

    # 测试阈值更新
    print("\n测试阈值更新...")
    alert_manager.update_thresholds('performance', {
        'response_time_ms': 6000,
        'error_rate': 0.15
    })
    print("  阈值已更新")

    print("\n✅ 告警管理测试通过")
    return True


def test_monitoring_system():
    """测试完整监控系统"""
    print_section("测试5: 完整监控系统")

    # 获取全局监控系统
    system = monitoring_system

    # 模拟记录一些数据
    print("\n模拟系统运行...")

    # 记录性能数据
    for i in range(10):
        system.performance_monitor.record_request(
            endpoint='/api/search',
            response_time=random.uniform(200, 1500),
            success=random.random() > 0.05,
            user_id=f"user_{i % 3}"
        )

    # 记录资源数据
    system.resource_monitor.collect_metrics()

    # 记录知识库数据
    system.kb_monitor.record_retrieval_time(random.uniform(200, 800))
    system.kb_monitor.record_index_status(
        total_documents=1500,
        quality_score=88.0,
        last_update_time=datetime.now().isoformat(),
        update_success=True
    )

    # 获取系统健康状态
    print("\n获取系统健康状态...")
    health = system.get_system_health()

    print(f"\n系统健康状态:")
    print(f"  状态: {health['status']}")
    print(f"  健康评分: {health['health_score']:.1f}/100")
    print(f"  活跃告警数: {health['active_alerts']}")

    print(f"\n性能指标:")
    print(f"  总请求数: {health['performance']['total_requests']}")
    print(f"  成功率: {health['performance']['success_rate']:.2%}")
    print(f"  平均响应时间: {health['performance']['avg_response_time']:.2f}ms")

    print(f"\n资源指标:")
    print(f"  平均CPU: {health['resources']['avg_cpu_percent']:.1f}%")
    print(f"  平均内存: {health['resources']['avg_memory_percent']:.1f}%")

    print(f"\n知识库指标:")
    print(f"  平均质量评分: {health['knowledge_base']['avg_quality_score']:.1f}")
    print(f"  平均检索时间: {health['knowledge_base']['avg_retrieval_time']:.2f}ms")

    print("\n✅ 完整监控系统测试通过")
    return True


def main():
    """主函数"""
    print("=" * 70)
    print("监控系统功能测试")
    print("=" * 70)

    results = []

    # 运行所有测试
    tests = [
        ("性能监控", test_performance_monitor),
        ("资源监控", test_resource_monitor),
        ("知识库监控", test_knowledge_base_monitor),
        ("告警管理", test_alert_manager),
        ("完整监控系统", test_monitoring_system)
    ]

    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name}测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 打印总结
    print_section("测试总结")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\n测试结果: {passed}/{total} 通过")

    for name, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {name}")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
