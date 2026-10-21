"""
知识库更新脚本
用于增量更新知识库索引
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

    parser = argparse.ArgumentParser(description='更新知识库索引')
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['tutorials', 'api_docs', 'backend_code', 'frontend_code', 'config'],
        help='指定要更新的知识源（默认全部）'
    )

    args = parser.parse_args()

    try:
        # 初始化管理器
        logger.info("初始化知识库管理器...")
        manager = KnowledgeManager(base_dir=str(project_root))

        # 增量更新
        logger.info("开始增量更新索引...")
        total = manager.update_index(sources=args.sources)

        logger.info(f"✓ 更新完成！共处理 {total} 个文档块")

        # 显示统计信息
        stats = manager.retriever.get_stats()
        logger.info(f"知识库统计信息:")
        logger.info(f"  - 集合名称: {stats.get('name')}")
        logger.info(f"  - 文档数量: {stats.get('count')}")

    except Exception as e:
        logger.error(f"更新索引失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
