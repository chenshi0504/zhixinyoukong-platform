"""
知识库检索器
整合文档加载、向量化、存储和检索功能
"""

import os
import logging
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime

from .document_loader import DocumentLoader, Document
from .text_splitter import RecursiveCharacterTextSplitter, MarkdownTextSplitter, CodeTextSplitter
from .embeddings import OpenAIEmbedding, CachedEmbedding
from .vector_store import ChromaVectorStore, HybridRetriever
from .index_manager import (
    get_index_metadata,
    get_incremental_indexer,
    get_quality_evaluator,
    get_scheduled_indexer
)

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """知识库检索器"""

    def __init__(
        self,
        collection_name: str = "platform_knowledge",
        persist_directory: str = None,
        embedding_model: str = "text-embedding-3-small"
    ):
        """初始化检索器"""
        # 设置持久化目录
        if persist_directory is None:
            persist_directory = os.path.join(
                Path(__file__).parent, "indexes"
            )

        # 初始化嵌入生成器（带缓存）
        base_embedding = OpenAIEmbedding(model=embedding_model)
        self.embedding = CachedEmbedding(base_embedding)

        # 初始化向量存储
        self.vector_store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory
        )

        # 初始化混合检索器
        self.retriever = HybridRetriever(self.vector_store)

        logger.info("知识库检索器初始化完成")

    def add_documents_from_directory(
        self,
        directory: str,
        file_pattern: str = "*",
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> int:
        """从目录加载文档并添加到知识库"""
        logger.info(f"开始加载目录: {directory}")

        # 加载文档
        documents = DocumentLoader.load_directory(directory, file_pattern)

        if not documents:
            logger.warning(f"未找到文档: {directory}")
            return 0

        # 根据文档类型选择分块器
        chunks = []
        for doc in documents:
            doc_type = doc.metadata.get('type', 'text')

            if doc_type == 'markdown':
                splitter = MarkdownTextSplitter(chunk_size, chunk_overlap)
            elif doc_type in ['python', 'javascript']:
                splitter = CodeTextSplitter(chunk_size, chunk_overlap)
            else:
                splitter = RecursiveCharacterTextSplitter(chunk_size, chunk_overlap)

            doc_chunks = splitter.split_documents([doc])
            chunks.extend(doc_chunks)

        logger.info(f"文档分块完成: {len(documents)} 个文档 -> {len(chunks)} 个块")

        # 生成嵌入
        texts = [chunk.content for chunk in chunks]
        embeddings = self.embedding.embed_documents(texts)

        # 添加到向量库
        self.vector_store.add_documents(chunks, embeddings)

        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        context: Optional[Dict] = None
    ) -> List[Dict]:
        """搜索知识库

        Args:
            query: 查询文本
            top_k: 返回结果数量
            use_hybrid: 是否使用混合检索
            context: 上下文信息，支持：
                - module: 模块名称（用于过滤）
                - boost_recent: 是否提升最近内容权重
                - user_history: 用户历史访问记录
        """
        # 生成查询嵌入
        query_embedding = self.embedding.embed_query(query)

        # 检索
        if use_hybrid:
            results = self.retriever.search(
                query,
                query_embedding,
                top_k=top_k,
                context=context
            )
        else:
            results = self.vector_store.similarity_search(query_embedding, top_k=top_k)

        return results

    def get_stats(self) -> Dict:
        """获取知识库统计信息"""
        return self.vector_store.get_collection_stats()

    def reset(self):
        """重置知识库"""
        self.vector_store.reset()
        logger.info("知识库已重置")


class KnowledgeManager:
    """知识库管理器"""

    def __init__(self, base_dir: str = None):
        """初始化管理器"""
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.parent

        self.base_dir = Path(base_dir)
        self.retriever = KnowledgeRetriever()

        # 初始化索引管理组件
        self.metadata = get_index_metadata()
        self.incremental_indexer = get_incremental_indexer(self.retriever)
        self.quality_evaluator = get_quality_evaluator(self.retriever)
        self.scheduled_indexer = get_scheduled_indexer(self.retriever)

        # 定义知识源目录
        self.knowledge_sources = {
            # 已有知识源
            'tutorials': self.base_dir / 'docs' / '教材',
            'api_docs': self.base_dir / 'docs' / 'api',
            'backend_code': self.base_dir / 'backend',
            'frontend_code': self.base_dir / 'frontend',
            'config': self.base_dir / 'installer' / 'env',

            # 新增知识源
            'algorithm_docs': self.base_dir / 'backend' / 'algorithms',
            'experiment_results': self.base_dir / 'backend' / 'algorithms',
            'execution_logs': self.base_dir / 'backend' / 'logs',
        }

        # 文件模式映射
        self.source_patterns = {
            'tutorials': "*.md",
            'backend_code': "*.py",
            'frontend_code': "*.js",
            'config': "*.env",
            'algorithm_docs': "*/README.md",
            'experiment_results': "*/output/*_result_*.json",
            'execution_logs': "*.log"
        }

    def build_index(self, sources: Optional[List[str]] = None, reset: bool = False):
        """构建知识库索引"""
        if reset:
            logger.info("重置知识库...")
            self.retriever.reset()

        # 如果未指定源，使用所有源
        if sources is None:
            sources = list(self.knowledge_sources.keys())

        total_chunks = 0

        for source_name in sources:
            if source_name not in self.knowledge_sources:
                logger.warning(f"未知的知识源: {source_name}")
                continue

            source_dir = self.knowledge_sources[source_name]

            if not source_dir.exists():
                logger.warning(f"目录不存在: {source_dir}")
                continue

            logger.info(f"处理知识源: {source_name} ({source_dir})")

            # 获取文件模式
            pattern = self.source_patterns.get(source_name, "*")

            # 添加文档
            try:
                chunks = self.retriever.add_documents_from_directory(
                    str(source_dir),
                    file_pattern=pattern
                )
                total_chunks += chunks
                logger.info(f"{source_name}: 添加了 {chunks} 个文档块")
            except Exception as e:
                logger.error(f"处理 {source_name} 失败: {e}")

        # 更新元数据
        self.metadata.metadata["last_full_index"] = datetime.now().isoformat()
        self.metadata.save_metadata()

        logger.info(f"索引构建完成，共 {total_chunks} 个文档块")

        # 显示统计信息
        stats = self.retriever.get_stats()
        logger.info(f"知识库统计: {stats}")

        return total_chunks

    def update_index(self, sources: Optional[List[str]] = None):
        """增量更新索引（智能检测变更）"""
        from datetime import datetime

        # 如果未指定源，使用所有源
        if sources is None:
            sources = list(self.knowledge_sources.keys())

        results = []
        total_changed = 0
        total_chunks = 0

        for source_name in sources:
            if source_name not in self.knowledge_sources:
                logger.warning(f"未知的知识源: {source_name}")
                continue

            source_dir = self.knowledge_sources[source_name]
            if not source_dir.exists():
                logger.warning(f"目录不存在: {source_dir}")
                continue

            pattern = self.source_patterns.get(source_name, "*")

            # 使用增量索引器更新单个源
            result = self.incremental_indexer.incremental_update(
                source_name,
                str(source_dir),
                pattern
            )
            results.append(result)
            total_changed += result.get("changed_files", 0)
            total_chunks += result.get("chunks_added", 0)

        logger.info(f"增量更新完成：{total_changed} 个文件变化，添加了 {total_chunks} 个文档块")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "sources_updated": len(results),
            "total_changed_files": total_changed,
            "total_chunks_added": total_chunks,
            "results": results
        }

    def evaluate_index_quality(self) -> Dict:
        """评估索引质量"""
        return self.quality_evaluator.evaluate()

    def run_scheduled_update(self) -> Dict:
        """运行定期更新"""
        return self.scheduled_indexer.run_scheduled_update(
            self.knowledge_sources,
            self.source_patterns
        )

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """搜索知识库"""
        return self.retriever.search(query, top_k=top_k)


# 全局单例
_knowledge_manager = None


def get_knowledge_manager() -> KnowledgeManager:
    """获取知识库管理器单例"""
    global _knowledge_manager
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager()
    return _knowledge_manager
