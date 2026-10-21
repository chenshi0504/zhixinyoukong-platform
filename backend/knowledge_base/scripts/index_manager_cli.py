"""
索引管理命令行工具
整合增量更新、定期更新、质量评估等功能
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.retriever import get_knowledge_manager


def cmd_status():
    """显示索引状态"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print("知识库索引状态")
    print("="*70 + "\n")

    # 获取统计信息
    stats = manager.retriever.get_stats()
    print(f"集合名称: {stats.get('name', 'N/A')}")
    print(f"文档数量: {stats.get('count', 0)}")
    print(f"元数据: {stats.get('metadata', {})}")

    # 获取元数据信息
    metadata = manager.metadata.metadata
    print(f"\n最后全量索引: {metadata.get('last_full_index', '从未')}")
    print(f"最后增量索引: {metadata.get('last_incremental_index', '从未')}")

    # 统计信息
    statistics = metadata.get('statistics', {})
    print(f"\n总文件数: {statistics.get('total_files', 0)}")
    print(f"总文档块数: {statistics.get('total_chunks', 0)}")
    print(f"总大小: {statistics.get('total_size_bytes', 0) / 1024 / 1024:.2f} MB")

    # 知识源统计
    sources = metadata.get('sources', {})
    if sources:
        print(f"\n知识源统计:")
        for source_name, source_info in sources.items():
            print(f"  {source_name}:")
            print(f"    最后索引: {source_info.get('last_indexed', '从未')}")
            print(f"    文件数: {source_info.get('file_count', 0)}")
            print(f"    文档块数: {source_info.get('chunks_count', 0)}")

    print("\n" + "="*70 + "\n")


def cmd_build(sources: list = None, reset: bool = False):
    """构建索引"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print("构建知识库索引")
    print("="*70 + "\n")

    if reset:
        print("⚠️  将重置现有索引...")
        confirm = input("确认重置？(yes/no): ")
        if confirm.lower() != 'yes':
            print("已取消")
            return

    print(f"开始构建索引...")
    if sources:
        print(f"指定知识源: {', '.join(sources)}")
    else:
        print(f"使用所有知识源")

    start_time = datetime.now()

    try:
        total_chunks = manager.build_index(sources=sources, reset=reset)

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n✅ 索引构建完成！")
        print(f"   总文档块数: {total_chunks}")
        print(f"   耗时: {elapsed:.2f}秒")

        # 显示统计信息
        stats = manager.retriever.get_stats()
        print(f"   当前索引总数: {stats.get('count', 0)}")

    except Exception as e:
        print(f"\n❌ 索引构建失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_update(sources: list = None):
    """增量更新索引"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print("增量更新索引")
    print("="*70 + "\n")

    if sources:
        print(f"指定知识源: {', '.join(sources)}")
    else:
        print(f"检查所有知识源")

    start_time = datetime.now()

    try:
        result = manager.update_index(sources=sources)

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n✅ 增量更新完成！")
        print(f"   更新时间: {result.get('timestamp', 'N/A')}")
        print(f"   更新知识源数: {result.get('sources_updated', 0)}")
        print(f"   变化文件数: {result.get('total_changed_files', 0)}")
        print(f"   新增文档块数: {result.get('total_chunks_added', 0)}")
        print(f"   耗时: {elapsed:.2f}秒")

        # 显示详细结果
        if result.get('results'):
            print(f"\n详细结果:")
            for source_result in result['results']:
                source_name = source_result.get('source', 'unknown')
                changed = source_result.get('changed_files', 0)
                chunks = source_result.get('chunks_added', 0)
                if changed > 0:
                    print(f"  {source_name}: {changed}个文件变化, 新增{chunks}个文档块")

    except Exception as e:
        print(f"\n❌ 增量更新失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_evaluate():
    """评估索引质量"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print("评估索引质量")
    print("="*70 + "\n")

    print("开始评估...")

    try:
        result = manager.evaluate_index_quality()

        print(f"\n评估结果:")
        print(f"  评估时间: {result.get('timestamp', 'N/A')}")
        print(f"  总文档数: {result.get('total_documents', 0)}")
        print(f"  平均文档长度: {result.get('avg_document_length', 0):.0f}字符")
        print(f"  文档长度标准差: {result.get('std_document_length', 0):.0f}字符")

        # 长度分布
        length_dist = result.get('length_distribution', {})
        if length_dist:
            print(f"\n文档长度分布:")
            for range_name, count in length_dist.items():
                print(f"    {range_name}: {count}个文档")

        # 知识源分布
        source_dist = result.get('source_distribution', {})
        if source_dist:
            print(f"\n知识源分布:")
            for source, count in source_dist.items():
                print(f"    {source}: {count}个文档")

        # 质量问题
        issues = result.get('quality_issues', [])
        if issues:
            print(f"\n⚠️  发现质量问题:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print(f"\n✅ 未发现质量问题")

    except Exception as e:
        print(f"\n❌ 评估失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_scheduled_update():
    """运行定期更新"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print("运行定期更新")
    print("="*70 + "\n")

    print("检查是否需要更新...")

    try:
        result = manager.run_scheduled_update()

        if result.get('updated'):
            print(f"\n✅ 定期更新完成！")
            print(f"   更新时间: {result.get('timestamp', 'N/A')}")
            print(f"   更新知识源数: {result.get('sources_updated', 0)}")
            print(f"   变化文件数: {result.get('total_changed_files', 0)}")
            print(f"   新增文档块数: {result.get('total_chunks_added', 0)}")
        else:
            print(f"\n✅ 无需更新")
            print(f"   原因: {result.get('reason', '未知')}")
            next_update = result.get('next_update_time')
            if next_update:
                print(f"   下次更新时间: {next_update}")

    except Exception as e:
        print(f"\n❌ 定期更新失败: {e}")
        import traceback
        traceback.print_exc()


def cmd_list_sources():
    """列出所有知识源"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print("知识源列表")
    print("="*70 + "\n")

    for name, path in manager.knowledge_sources.items():
        pattern = manager.source_patterns.get(name, "*")
        exists = "✅" if path.exists() else "❌"
        print(f"{exists} {name}")
        print(f"   路径: {path}")
        print(f"   模式: {pattern}")
        print()


def cmd_search(query: str, top_k: int = 5):
    """测试检索"""
    manager = get_knowledge_manager()

    print("\n" + "="*70)
    print(f"检索测试: {query}")
    print("="*70 + "\n")

    import time
    start_time = time.time()

    try:
        results = manager.search(query, top_k=top_k)

        elapsed = (time.time() - start_time) * 1000

        print(f"找到 {len(results)} 个结果 (耗时: {elapsed:.0f}ms)\n")

        for i, result in enumerate(results, 1):
            print(f"[{i}] 相关度: {result.get('score', 0):.3f}")
            print(f"    来源: {result.get('metadata', {}).get('source', 'N/A')}")
            content = result.get('content', '')
            preview = content[:200] + "..." if len(content) > 200 else content
            print(f"    内容: {preview}")
            print()

    except Exception as e:
        print(f"\n❌ 检索失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='知识库索引管理工具')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    # status命令
    subparsers.add_parser('status', help='显示索引状态')

    # build命令
    build_parser = subparsers.add_parser('build', help='构建索引')
    build_parser.add_argument('--sources', nargs='+', help='指定知识源')
    build_parser.add_argument('--reset', action='store_true', help='重置现有索引')

    # update命令
    update_parser = subparsers.add_parser('update', help='增量更新索引')
    update_parser.add_argument('--sources', nargs='+', help='指定知识源')

    # evaluate命令
    subparsers.add_parser('evaluate', help='评估索引质量')

    # scheduled-update命令
    subparsers.add_parser('scheduled-update', help='运行定期更新')

    # list-sources命令
    subparsers.add_parser('list-sources', help='列出所有知识源')

    # search命令
    search_parser = subparsers.add_parser('search', help='测试检索')
    search_parser.add_argument('query', help='查询文本')
    search_parser.add_argument('--top-k', type=int, default=5, help='返回结果数量')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行命令
    if args.command == 'status':
        cmd_status()
    elif args.command == 'build':
        cmd_build(sources=args.sources, reset=args.reset)
    elif args.command == 'update':
        cmd_update(sources=args.sources)
    elif args.command == 'evaluate':
        cmd_evaluate()
    elif args.command == 'scheduled-update':
        cmd_scheduled_update()
    elif args.command == 'list-sources':
        cmd_list_sources()
    elif args.command == 'search':
        cmd_search(args.query, args.top_k)


if __name__ == '__main__':
    main()
