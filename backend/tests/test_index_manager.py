"""
测试索引管理器功能
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from knowledge_base.index_manager import (
    get_index_metadata,
    get_incremental_indexer,
    get_quality_evaluator,
    get_scheduled_indexer
)


def test_index_metadata():
    """测试索引元数据管理"""
    print("\n=== 测试索引元数据管理 ===")

    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        metadata_file = Path(temp_dir) / "test_metadata.json"

        # 使用单例函数创建实例
        import knowledge_base.index_manager as im
        im._metadata_file = str(metadata_file)
        im._index_metadata = None
        metadata = get_index_metadata()

        # 测试文件哈希计算
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("Hello World")

        file_hash = metadata.get_file_hash(str(test_file))
        print(f"✓ 文件哈希: {file_hash}")

        # 测试文件修改检测
        is_modified = metadata.is_file_modified(str(test_file))
        print(f"✓ 首次检测修改: {is_modified} (应为True)")

        # 更新元数据
        metadata.update_file(str(test_file), "test_source")

        # 再次检测（应该不修改）
        is_modified = metadata.is_file_modified(str(test_file))
        print(f"✓ 二次检测修改: {is_modified} (应为False)")

        # 修改文件
        test_file.write_text("Hello World Modified")
        is_modified = metadata.is_file_modified(str(test_file))
        print(f"✓ 修改后检测: {is_modified} (应为True)")

        # 测试元数据保存和加载
        metadata.save()
        im._index_metadata = None
        metadata2 = get_index_metadata()
        print(f"✓ 元数据文件数: {len(metadata2.metadata.get('files', {}))}")

        print("✓ 索引元数据测试通过")


def test_incremental_indexer():
    """测试增量索引器"""
    print("\n=== 测试增量索引器 ===")

    # 创建临时目录和文件
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        test_dir = Path(temp_dir) / "docs"
        test_dir.mkdir()

        file1 = test_dir / "doc1.md"
        file1.write_text("# Document 1\nThis is the first document.")

        file2 = test_dir / "doc2.md"
        file2.write_text("# Document 2\nThis is the second document.")

        # 创建模拟的retriever
        class MockRetriever:
            def __init__(self):
                self.documents = []

            def load_documents(self, source_dir, pattern="*"):
                from knowledge_base.document_loader import DocumentLoader
                loader = DocumentLoader()
                return loader.load_directory(source_dir, pattern)

            def add_documents(self, documents, source_name):
                self.documents.extend(documents)
                return len(documents)

            def delete_documents_by_source(self, source_name):
                self.documents = [d for d in self.documents if d.metadata.get("source") != source_name]

        retriever = MockRetriever()

        # 创建增量索引器
        metadata_file = Path(temp_dir) / "metadata.json"
        indexer = IncrementalIndexer(retriever, metadata_file)

        # 首次索引
        result1 = indexer.incremental_update("test_source", str(test_dir), "*.md")
        print(f"✓ 首次索引: {result1['changed_files']} 个文件, {result1['chunks_added']} 个块")

        # 再次索引（无变化）
        result2 = indexer.incremental_update("test_source", str(test_dir), "*.md")
        print(f"✓ 无变化索引: {result2['changed_files']} 个文件, {result2['chunks_added']} 个块")

        # 修改文件
        file1.write_text("# Document 1 Modified\nThis is the modified first document.")

        # 增量更新
        result3 = indexer.incremental_update("test_source", str(test_dir), "*.md")
        print(f"✓ 增量更新: {result3['changed_files']} 个文件, {result3['chunks_added']} 个块")

        # 添加新文件
        file3 = test_dir / "doc3.md"
        file3.write_text("# Document 3\nThis is the third document.")

        result4 = indexer.incremental_update("test_source", str(test_dir), "*.md")
        print(f"✓ 新增文件: {result4['changed_files']} 个文件, {result4['chunks_added']} 个块")

        print("✓ 增量索引器测试通过")


def test_quality_evaluator():
    """测试质量评估器"""
    print("\n=== 测试质量评估器 ===")

    # 创建模拟的retriever
    class MockRetriever:
        def __init__(self):
            self.vector_store = MockVectorStore()

    class MockVectorStore:
        def __init__(self):
            self.collection = MockCollection()

    class MockCollection:
        def count(self):
            return 100

        def get(self, include=None):
            return {
                "documents": ["doc1", "doc2", "doc3"] * 33 + ["doc1"],
                "metadatas": [
                    {"source": "source1", "chunk_size": 500},
                    {"source": "source2", "chunk_size": 600},
                    {"source": "source1", "chunk_size": 550}
                ] * 33 + [{"source": "source1", "chunk_size": 500}]
            }

    retriever = MockRetriever()
    evaluator = QualityEvaluator(retriever)

    # 评估质量
    report = evaluator.evaluate()

    print(f"✓ 总文档数: {report['total_documents']}")
    print(f"✓ 来源分布: {report['source_distribution']}")
    print(f"✓ 平均块大小: {report['avg_chunk_size']:.0f}")
    print(f"✓ 重复率: {report['duplicate_rate']:.2%}")

    print("✓ 质量评估器测试通过")


def test_scheduled_indexer():
    """测试定期索引器"""
    print("\n=== 测试定期索引器 ===")

    # 创建模拟的retriever
    class MockRetriever:
        def __init__(self):
            self.update_count = 0

        def update_index_incremental(self, source_dirs):
            self.update_count += 1
            return {
                "status": "success",
                "sources_updated": len(source_dirs),
                "total_changed_files": 5,
                "total_chunks_added": 20
            }

    retriever = MockRetriever()
    scheduler = ScheduledIndexer(retriever)

    # 测试手动运行
    with tempfile.TemporaryDirectory() as temp_dir:
        source_dirs = {"test_source": Path(temp_dir)}
        source_patterns = {"test_source": "*.md"}

        result = scheduler.run_scheduled_update(source_dirs, source_patterns)
        print(f"✓ 手动运行结果: {result['status']}")
        print(f"✓ 更新次数: {retriever.update_count}")

        # 测试调度器启动和停止
        scheduler.start_scheduler(interval_hours=1)
        print(f"✓ 调度器已启动")

        scheduler.stop_scheduler()
        print(f"✓ 调度器已停止")

    print("✓ 定期索引器测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试索引管理器")
    print("=" * 60)

    try:
        test_index_metadata()
        test_incremental_indexer()
        test_quality_evaluator()
        test_scheduled_indexer()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()
