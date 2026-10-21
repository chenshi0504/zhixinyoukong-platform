"""
索引管理器
负责知识库索引的增量更新、定期更新、质量评估等功能
"""
import os
import json
import logging
import hashlib
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


class IndexMetadata:
    """索引元数据管理"""

    def __init__(self, metadata_file: str = "backend/knowledge_base/indexes/metadata.json"):
        """
        初始化元数据管理器

        Args:
            metadata_file: 元数据文件路径
        """
        self.metadata_file = Path(metadata_file)
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        self.metadata: Dict = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """加载元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载元数据失败: {e}")
                return self._create_empty_metadata()
        return self._create_empty_metadata()

    def _create_empty_metadata(self) -> Dict:
        """创建空元数据结构"""
        return {
            "version": "1.0",
            "last_full_index": None,
            "last_incremental_index": None,
            "files": {},  # 文件路径 -> {hash, mtime, indexed_at, chunks_count}
            "sources": {},  # 知识源 -> {last_indexed, file_count, chunks_count}
            "statistics": {
                "total_files": 0,
                "total_chunks": 0,
                "total_size_bytes": 0
            }
        }

    def save_metadata(self):
        """保存元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            logger.info(f"元数据已保存到 {self.metadata_file}")
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")

    def get_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败 {file_path}: {e}")
            return ""

    def is_file_changed(self, file_path: str) -> bool:
        """检查文件是否发生变化"""
        file_path = str(file_path)

        # 如果文件不在元数据中，说明是新文件
        if file_path not in self.metadata["files"]:
            return True

        # 检查修改时间
        try:
            current_mtime = os.path.getmtime(file_path)
            stored_mtime = self.metadata["files"][file_path].get("mtime", 0)

            if current_mtime > stored_mtime:
                # 修改时间变化，进一步检查哈希值
                current_hash = self.get_file_hash(file_path)
                stored_hash = self.metadata["files"][file_path].get("hash", "")
                return current_hash != stored_hash

            return False
        except Exception as e:
            logger.error(f"检查文件变化失败 {file_path}: {e}")
            return True

    def update_file_metadata(
        self,
        file_path: str,
        chunks_count: int,
        source: Optional[str] = None
    ):
        """更新文件元数据"""
        file_path = str(file_path)

        try:
            file_stat = os.stat(file_path)
            file_hash = self.get_file_hash(file_path)

            self.metadata["files"][file_path] = {
                "hash": file_hash,
                "mtime": file_stat.st_mtime,
                "size": file_stat.st_size,
                "indexed_at": datetime.now().isoformat(),
                "chunks_count": chunks_count,
                "source": source
            }

            # 更新统计信息
            self._update_statistics()

        except Exception as e:
            logger.error(f"更新文件元数据失败 {file_path}: {e}")

    def _update_statistics(self):
        """更新统计信息"""
        total_files = len(self.metadata["files"])
        total_chunks = sum(f.get("chunks_count", 0) for f in self.metadata["files"].values())
        total_size = sum(f.get("size", 0) for f in self.metadata["files"].values())

        self.metadata["statistics"] = {
            "total_files": total_files,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size,
            "updated_at": datetime.now().isoformat()
        }

    def get_changed_files(self, source_dir: str, pattern: str = "*") -> List[str]:
        """获取发生变化的文件列表"""
        from glob import glob

        changed_files = []
        source_path = Path(source_dir)

        # 递归查找匹配的文件
        if "**" in pattern:
            files = source_path.glob(pattern)
        else:
            files = source_path.rglob(pattern)

        for file_path in files:
            if file_path.is_file():
                if self.is_file_changed(str(file_path)):
                    changed_files.append(str(file_path))

        return changed_files

    def remove_deleted_files(self, source_dir: str):
        """移除已删除文件的元数据"""
        source_path = Path(source_dir)
        deleted_files = []

        for file_path in list(self.metadata["files"].keys()):
            # 检查文件是否属于该源目录
            if file_path.startswith(str(source_path)):
                if not Path(file_path).exists():
                    deleted_files.append(file_path)
                    del self.metadata["files"][file_path]

        if deleted_files:
            logger.info(f"移除了 {len(deleted_files)} 个已删除文件的元数据")
            self._update_statistics()

        return deleted_files


class IncrementalIndexer:
    """增量索引器"""

    def __init__(self, retriever, metadata: IndexMetadata):
        """
        初始化增量索引器

        Args:
            retriever: KnowledgeRetriever实例
            metadata: IndexMetadata实例
        """
        self.retriever = retriever
        self.metadata = metadata

    def incremental_update(
        self,
        source_name: str,
        source_dir: str,
        file_pattern: str = "*"
    ) -> Dict:
        """
        增量更新指定知识源

        Args:
            source_name: 知识源名称
            source_dir: 知识源目录
            file_pattern: 文件匹配模式

        Returns:
            更新统计信息
        """
        logger.info(f"开始增量更新: {source_name} ({source_dir})")

        # 获取发生变化的文件
        changed_files = self.metadata.get_changed_files(source_dir, file_pattern)

        # 移除已删除文件的元数据
        deleted_files = self.metadata.remove_deleted_files(source_dir)

        if not changed_files and not deleted_files:
            logger.info(f"{source_name}: 没有变化，跳过更新")
            return {
                "source": source_name,
                "changed_files": 0,
                "deleted_files": 0,
                "chunks_added": 0,
                "status": "no_changes"
            }

        logger.info(f"{source_name}: 发现 {len(changed_files)} 个变化的文件, {len(deleted_files)} 个删除的文件")

        # 处理变化的文件
        total_chunks = 0
        for file_path in changed_files:
            try:
                # 加载单个文件
                from .document_loader import DocumentLoader
                documents = DocumentLoader.load_file(file_path)

                if not documents:
                    continue

                # 分块
                from .text_splitter import RecursiveCharacterTextSplitter
                splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                chunks = splitter.split_documents(documents)

                # 生成嵌入
                texts = [chunk.content for chunk in chunks]
                embeddings = self.retriever.embedding.embed_documents(texts)

                # 添加到向量库
                self.retriever.vector_store.add_documents(chunks, embeddings)

                # 更新元数据
                self.metadata.update_file_metadata(file_path, len(chunks), source_name)

                total_chunks += len(chunks)
                logger.info(f"  已更新: {Path(file_path).name} ({len(chunks)} 个块)")

            except Exception as e:
                logger.error(f"处理文件失败 {file_path}: {e}")

        # 保存元数据
        self.metadata.save_metadata()

        logger.info(f"{source_name}: 增量更新完成，添加了 {total_chunks} 个文档块")

        return {
            "source": source_name,
            "changed_files": len(changed_files),
            "deleted_files": len(deleted_files),
            "chunks_added": total_chunks,
            "status": "success"
        }


class IndexQualityEvaluator:
    """索引质量评估器"""

    def __init__(self, retriever, metadata: IndexMetadata):
        """
        初始化质量评估器

        Args:
            retriever: KnowledgeRetriever实例
            metadata: IndexMetadata实例
        """
        self.retriever = retriever
        self.metadata = metadata

    def evaluate(self) -> Dict:
        """
        评估索引质量

        Returns:
            评估报告
        """
        logger.info("开始评估索引质量...")

        report = {
            "timestamp": datetime.now().isoformat(),
            "basic_stats": self._get_basic_stats(),
            "coverage": self._evaluate_coverage(),
            "freshness": self._evaluate_freshness(),
            "consistency": self._evaluate_consistency(),
            "recommendations": []
        }

        # 生成建议
        report["recommendations"] = self._generate_recommendations(report)

        return report

    def _get_basic_stats(self) -> Dict:
        """获取基础统计信息"""
        stats = self.metadata.metadata.get("statistics", {})
        vector_stats = self.retriever.get_stats()

        return {
            "total_files": stats.get("total_files", 0),
            "total_chunks": stats.get("total_chunks", 0),
            "total_size_mb": round(stats.get("total_size_bytes", 0) / 1024 / 1024, 2),
            "vector_store_count": vector_stats.get("count", 0),
            "last_updated": stats.get("updated_at", "未知")
        }

    def _evaluate_coverage(self) -> Dict:
        """评估知识覆盖度"""
        files_by_source = {}
        chunks_by_source = {}

        for file_path, file_info in self.metadata.metadata["files"].items():
            source = file_info.get("source", "unknown")
            files_by_source[source] = files_by_source.get(source, 0) + 1
            chunks_by_source[source] = chunks_by_source.get(source, 0) + file_info.get("chunks_count", 0)

        return {
            "sources_count": len(files_by_source),
            "files_by_source": files_by_source,
            "chunks_by_source": chunks_by_source
        }

    def _evaluate_freshness(self) -> Dict:
        """评估数据新鲜度"""
        now = datetime.now()
        outdated_files = []

        for file_path, file_info in self.metadata.metadata["files"].items():
            indexed_at = file_info.get("indexed_at")
            if indexed_at:
                try:
                    indexed_time = datetime.fromisoformat(indexed_at)
                    days_old = (now - indexed_time).days

                    if days_old > 30:  # 超过30天视为过时
                        outdated_files.append({
                            "file": file_path,
                            "days_old": days_old
                        })
                except:
                    pass

        return {
            "outdated_files_count": len(outdated_files),
            "outdated_files": outdated_files[:10]  # 只返回前10个
        }

    def _evaluate_consistency(self) -> Dict:
        """评估数据一致性"""
        inconsistencies = []

        # 检查元数据中的文件是否实际存在
        missing_files = []
        for file_path in self.metadata.metadata["files"].keys():
            if not Path(file_path).exists():
                missing_files.append(file_path)

        if missing_files:
            inconsistencies.append({
                "type": "missing_files",
                "count": len(missing_files),
                "description": "元数据中记录的文件不存在"
            })

        # 检查统计信息是否一致
        calculated_chunks = sum(
            f.get("chunks_count", 0)
            for f in self.metadata.metadata["files"].values()
        )
        stored_chunks = self.metadata.metadata["statistics"].get("total_chunks", 0)

        if calculated_chunks != stored_chunks:
            inconsistencies.append({
                "type": "chunks_mismatch",
                "calculated": calculated_chunks,
                "stored": stored_chunks,
                "description": "文档块数量统计不一致"
            })

        return {
            "is_consistent": len(inconsistencies) == 0,
            "inconsistencies": inconsistencies
        }

    def _generate_recommendations(self, report: Dict) -> List[str]:
        """生成优化建议"""
        recommendations = []

        # 检查过时文件
        freshness = report["freshness"]
        if freshness["outdated_files_count"] > 0:
            recommendations.append(
                f"发现 {freshness['outdated_files_count']} 个超过30天未更新的文件，建议执行增量更新"
            )

        # 检查一致性
        consistency = report["consistency"]
        if not consistency["is_consistent"]:
            recommendations.append(
                f"发现 {len(consistency['inconsistencies'])} 个一致性问题，建议执行完整重建"
            )

        # 检查覆盖度
        coverage = report["coverage"]
        if coverage["sources_count"] < 5:
            recommendations.append(
                "知识源覆盖较少，建议添加更多知识源"
            )

        if not recommendations:
            recommendations.append("索引质量良好，无需特别优化")

        return recommendations


class ScheduledIndexer:
    """定期索引器"""

    def __init__(
        self,
        retriever,
        metadata: IndexMetadata,
        incremental_indexer: IncrementalIndexer
    ):
        """
        初始化定期索引器

        Args:
            retriever: KnowledgeRetriever实例
            metadata: IndexMetadata实例
            incremental_indexer: IncrementalIndexer实例
        """
        self.retriever = retriever
        self.metadata = metadata
        self.incremental_indexer = incremental_indexer
        self.is_running = False

    def should_run_incremental_update(self, interval_hours: int = 24) -> bool:
        """
        检查是否应该运行增量更新

        Args:
            interval_hours: 更新间隔（小时）

        Returns:
            是否应该更新
        """
        last_update = self.metadata.metadata.get("last_incremental_index")
        if not last_update:
            return True

        try:
            last_update_time = datetime.fromisoformat(last_update)
            elapsed = datetime.now() - last_update_time
            return elapsed.total_seconds() / 3600 >= interval_hours
        except:
            return True

    def run_scheduled_update(
        self,
        knowledge_sources: Dict[str, Path],
        source_patterns: Dict[str, str]
    ) -> Dict:
        """
        运行定期更新

        Args:
            knowledge_sources: 知识源字典
            source_patterns: 文件模式字典

        Returns:
            更新结果
        """
        if self.is_running:
            logger.warning("定期更新已在运行中，跳过本次执行")
            return {"status": "skipped", "reason": "already_running"}

        self.is_running = True
        start_time = time.time()

        try:
            logger.info("开始定期索引更新...")

            results = []
            for source_name, source_dir in knowledge_sources.items():
                if not source_dir.exists():
                    continue

                pattern = source_patterns.get(source_name, "*")

                result = self.incremental_indexer.incremental_update(
                    source_name,
                    str(source_dir),
                    pattern
                )
                results.append(result)

            # 更新最后更新时间
            self.metadata.metadata["last_incremental_index"] = datetime.now().isoformat()
            self.metadata.save_metadata()

            elapsed = time.time() - start_time

            summary = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "sources_updated": len(results),
                "total_changed_files": sum(r["changed_files"] for r in results),
                "total_chunks_added": sum(r["chunks_added"] for r in results),
                "results": results
            }

            logger.info(f"定期更新完成，耗时 {elapsed:.2f} 秒")
            return summary

        except Exception as e:
            logger.error(f"定期更新失败: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        finally:
            self.is_running = False


# 全局实例
_index_metadata = None
_incremental_indexer = None
_quality_evaluator = None
_scheduled_indexer = None


def get_index_metadata() -> IndexMetadata:
    """获取索引元数据单例"""
    global _index_metadata
    if _index_metadata is None:
        _index_metadata = IndexMetadata()
    return _index_metadata


def get_incremental_indexer(retriever) -> IncrementalIndexer:
    """获取增量索引器单例"""
    global _incremental_indexer
    if _incremental_indexer is None:
        metadata = get_index_metadata()
        _incremental_indexer = IncrementalIndexer(retriever, metadata)
    return _incremental_indexer


def get_quality_evaluator(retriever) -> IndexQualityEvaluator:
    """获取质量评估器单例"""
    global _quality_evaluator
    if _quality_evaluator is None:
        metadata = get_index_metadata()
        _quality_evaluator = IndexQualityEvaluator(retriever, metadata)
    return _quality_evaluator


def get_scheduled_indexer(retriever) -> ScheduledIndexer:
    """获取定期索引器单例"""
    global _scheduled_indexer
    if _scheduled_indexer is None:
        metadata = get_index_metadata()
        incremental_indexer = get_incremental_indexer(retriever)
        _scheduled_indexer = ScheduledIndexer(retriever, metadata, incremental_indexer)
    return _scheduled_indexer
