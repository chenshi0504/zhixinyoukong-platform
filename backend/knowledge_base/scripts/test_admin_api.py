"""
测试知识库管理API

验证所有管理API端点的功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from datetime import datetime
from typing import Dict, Any
import json
import os

# 设置UTF-8编码
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    sys.stdout.reconfigure(encoding='utf-8')

# 模拟FastAPI测试环境
class MockRequest:
    """模拟请求对象"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockUploadFile:
    """模拟上传文件"""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.content = content
        self.file = None

    def __enter__(self):
        import io
        self.file = io.BytesIO(self.content)
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()


class MockBackgroundTasks:
    """模拟后台任务"""
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


async def test_dashboard_stats():
    """测试仪表板统计API"""
    print("\n=== 测试仪表板统计 ===")

    try:
        from backend.knowledge_base.admin_api import get_dashboard_stats

        stats = await get_dashboard_stats()

        # 验证返回数据结构
        required_keys = [
            'document_count', 'index_status', 'today_queries',
            'avg_response_time', 'query_trend', 'document_types',
            'quality_metrics', 'system_health', 'recent_activities'
        ]

        for key in required_keys:
            assert key in stats, f"缺少字段: {key}"

        print(f"✓ 文档总数: {stats['document_count']}")
        print(f"✓ 索引状态: {stats['index_status']}")
        print(f"✓ 今日查询: {stats['today_queries']}")
        print(f"✓ 平均响应时间: {stats['avg_response_time']:.2f}ms")
        print(f"✓ 系统健康分数: {stats['system_health']['health_score']:.1f}")

        return True
    except Exception as e:
        print(f"X 测试失败: {e}")
        return False


async def test_list_documents():
    """测试文档列表API"""
    print("\n=== 测试文档列表 ===")

    try:
        from backend.knowledge_base.admin_api import list_documents

        # 测试基本列表
        result = await list_documents(page=1, size=10)

        assert 'total' in result
        assert 'documents' in result
        assert 'page' in result
        assert 'size' in result

        print(f"✓ 文档总数: {result['total']}")
        print(f"✓ 当前页: {result['page']}/{result['pages']}")
        print(f"✓ 每页大小: {result['size']}")

        # 测试过滤
        result_filtered = await list_documents(
            page=1, size=10, doc_type="manual", status="indexed"
        )
        print(f"✓ 过滤后文档数: {result_filtered['total']}")

        # 测试搜索
        result_search = await list_documents(
            page=1, size=10, search="算法"
        )
        print(f"✓ 搜索结果数: {result_search['total']}")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_upload_document():
    """测试文档上传API"""
    print("\n=== 测试文档上传 ===")

    try:
        from backend.knowledge_base.admin_api import upload_document

        # 创建模拟文件
        test_content = b"# Test Document\n\nThis is a test document for upload."
        mock_file = MockUploadFile("test_upload.md", test_content)

        background_tasks = MockBackgroundTasks()

        with mock_file:
            result = await upload_document(
                background_tasks=background_tasks,
                file=mock_file,
                doc_type="manual",
                tags="test,upload",
                description="测试上传文档",
                auto_index=True
            )

        assert result['success'] is True
        assert 'document' in result

        doc = result['document']
        print(f"✓ 文档ID: {doc['id']}")
        print(f"✓ 文档名称: {doc['name']}")
        print(f"✓ 文档类型: {doc['type']}")
        print(f"✓ 文档大小: {doc['size']} bytes")
        print(f"✓ 标签: {', '.join(doc['tags'])}")
        print(f"✓ 后台任务数: {len(background_tasks.tasks)}")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_index_status():
    """测试索引状态API"""
    print("\n=== 测试索引状态 ===")

    try:
        from backend.knowledge_base.admin_api import get_index_status

        status = await get_index_status()

        print(f"✓ 索引状态: {status.status}")
        print(f"✓ 索引版本: {status.version}")
        print(f"✓ 最后更新: {status.last_update}")
        print(f"✓ 向量数量: {status.vector_count}")
        print(f"✓ 向量维度: {status.dimension}")
        print(f"✓ 存储大小: {status.storage_size} bytes")
        print(f"✓ 平均检索时间: {status.avg_retrieval_time:.2f}ms")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_index_quality():
    """测试索引质量API"""
    print("\n=== 测试索引质量 ===")

    try:
        from backend.knowledge_base.admin_api import get_index_quality

        quality = await get_index_quality()

        print(f"✓ 覆盖率: {quality['coverage']:.1f}%")
        print(f"✓ 一致性: {quality['consistency']:.1f}%")
        print(f"✓ 新鲜度: {quality['freshness']:.1f}%")
        print(f"✓ 检索速度: {quality['retrieval_speed']:.1f}%")
        print(f"✓ 存储效率: {quality['storage_efficiency']:.1f}%")
        print(f"✓ 总体评分: {quality['overall_score']:.1f}%")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_retrieval():
    """测试检索API"""
    print("\n=== 测试检索功能 ===")

    try:
        from backend.knowledge_base.admin_api import (
            test_retrieval, RetrievalTestRequest, RetrievalConfig
        )

        # 创建测试请求
        config = RetrievalConfig(
            top_k=5,
            enable_rerank=True,
            semantic_weight=0.4,
            keyword_weight=0.2
        )

        request = RetrievalTestRequest(
            query="如何配置信号优化算法？",
            config=config
        )

        result = await test_retrieval(request)

        print(f"✓ 查询: {result['query']}")
        print(f"✓ 结果数量: {len(result['results'])}")
        print(f"✓ 查询时间: {result['stats']['query_time']:.2f}ms")
        print(f"✓ 平均分数: {result['stats']['avg_score']:.3f}")

        # 显示前3个结果
        for i, res in enumerate(result['results'][:3], 1):
            print(f"\n  结果 {i}:")
            print(f"    文档: {res['doc_name']}")
            print(f"    分数: {res['score']:.3f}")
            print(f"    内容: {res['content'][:100]}...")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_config_comparison():
    """测试配置对比API"""
    print("\n=== 测试配置对比 ===")

    try:
        from backend.knowledge_base.admin_api import (
            compare_configs, ConfigComparisonRequest, RetrievalConfig
        )

        # 创建不同配置
        configs = [
            RetrievalConfig(
                top_k=5,
                semantic_weight=0.5,
                keyword_weight=0.3,
                time_weight=0.2
            ),
            RetrievalConfig(
                top_k=5,
                semantic_weight=0.4,
                keyword_weight=0.4,
                time_weight=0.2
            ),
            RetrievalConfig(
                top_k=5,
                semantic_weight=0.6,
                keyword_weight=0.2,
                time_weight=0.2
            )
        ]

        request = ConfigComparisonRequest(
            query="路径规划算法的参数如何设置？",
            configs=configs
        )

        result = await compare_configs(request)

        print(f"✓ 查询: {result['query']}")
        print(f"✓ 对比配置数: {len(result['comparisons'])}")

        for comp in result['comparisons']:
            print(f"\n  {comp['config_name']}:")
            print(f"    平均分数: {comp['stats']['avg_score']:.3f}")
            print(f"    查询时间: {comp['stats']['query_time']:.2f}ms")

        print(f"\n✓ 推荐配置: {result['recommendation']['best_config']}")
        print(f"  理由: {result['recommendation']['reason']}")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_rebuild_index():
    """测试索引重建API"""
    print("\n=== 测试索引重建 ===")

    try:
        from backend.knowledge_base.admin_api import rebuild_index

        background_tasks = MockBackgroundTasks()

        result = await rebuild_index(background_tasks)

        assert result['success'] is True
        assert len(background_tasks.tasks) > 0

        print(f"✓ 重建任务已提交")
        print(f"✓ 消息: {result['message']}")
        print(f"✓ 后台任务数: {len(background_tasks.tasks)}")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_incremental_update():
    """测试增量更新API"""
    print("\n=== 测试增量更新 ===")

    try:
        from backend.knowledge_base.admin_api import incremental_update

        background_tasks = MockBackgroundTasks()

        result = await incremental_update(background_tasks)

        assert result['success'] is True
        assert len(background_tasks.tasks) > 0

        print(f"✓ 增量更新任务已提交")
        print(f"✓ 消息: {result['message']}")
        print(f"✓ 后台任务数: {len(background_tasks.tasks)}")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_health_check():
    """测试健康检查API"""
    print("\n=== 测试健康检查 ===")

    try:
        from backend.knowledge_base.admin_api import health_check

        result = await health_check()

        assert result['status'] == 'healthy'
        assert 'timestamp' in result

        print(f"✓ 状态: {result['status']}")
        print(f"✓ 时间戳: {result['timestamp']}")

        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("知识库管理API测试")
    print("=" * 60)

    tests = [
        ("仪表板统计", test_dashboard_stats),
        ("文档列表", test_list_documents),
        ("文档上传", test_upload_document),
        ("索引状态", test_index_status),
        ("索引质量", test_index_quality),
        ("检索功能", test_retrieval),
        ("配置对比", test_config_comparison),
        ("索引重建", test_rebuild_index),
        ("增量更新", test_incremental_update),
        ("健康检查", test_health_check)
    ]

    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 生成测试报告
    print("\n" + "=" * 60)
    print("测试报告")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "通过" if result else "失败"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {name}: {status}")

    print(f"\n总计: {passed}/{total} 通过 ({passed/total*100:.1f}%)")

    # 保存测试报告
    report = {
        "test_time": datetime.now().isoformat(),
        "total_tests": total,
        "passed_tests": passed,
        "failed_tests": total - passed,
        "pass_rate": passed / total * 100,
        "test_results": [
            {"name": name, "passed": result}
            for name, result in results
        ]
    }

    report_file = Path(__file__).parent.parent.parent.parent / ".RAG" / "admin_api_test_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n测试报告已保存到: {report_file}")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
