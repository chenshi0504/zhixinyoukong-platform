"""
知识库索引构建脚本
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.retriever import KnowledgeManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='构建知识库索引')
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['tutorials', 'api_docs', 'backend_code', 'frontend_code', 'config',
                 'algorithm_docs', 'experiment_results', 'execution_logs'],
        help='指定要索引的知识源（默认全部）'
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='重置知识库（清空现有数据）'
    )
    parser.add_argument(
        '--incremental',
        action='store_true',
        help='增量更新（不清空现有数据）'
    )

    args = parser.parse_args()

    try:
        # 初始化管理器
        logger.info("初始化知识库管理器...")
        manager = KnowledgeManager(base_dir=str(project_root))

        # 构建索引
        if args.incremental:
            logger.info("开始增量更新索引...")
            total = manager.update_index(sources=args.sources)
        else:
            logger.info("开始构建索引...")
            total = manager.build_index(sources=args.sources, reset=args.reset)

        logger.info(f"✓ 索引构建完成！共处理 {total} 个文档块")

        # 显示统计信息
        stats = manager.retriever.get_stats()
        logger.info(f"知识库统计信息:")
        logger.info(f"  - 集合名称: {stats.get('name')}")
        logger.info(f"  - 文档数量: {stats.get('count')}")

        # 测试搜索
        logger.info("\n测试搜索功能...")
        test_queries = [
            "如何配置CARLA仿真环境？",
            "信号优化算法的原理是什么？",
            "如何启动平台？"
        ]

        for query in test_queries:
            logger.info(f"\n查询: {query}")
            results = manager.search(query, top_k=3)

            for i, result in enumerate(results, 1):
                logger.info(f"  {i}. [{result['metadata'].get('filename', 'unknown')}]")
                logger.info(f"     分数: {result.get('score', result.get('distance', 0)):.4f}")
                logger.info(f"     内容: {result['content'][:100]}...")

    except Exception as e:
        logger.error(f"构建索引失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
