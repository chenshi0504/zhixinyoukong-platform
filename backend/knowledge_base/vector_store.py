"""
向量存储和检索模块
基于ChromaDB实现向量数据库功能
"""

import os
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储基类"""

    def add_documents(self, documents: List[Any], embeddings: List[List[float]]) -> List[str]:
        """添加文档和向量"""
        raise NotImplementedError

    def similarity_search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        """相似度搜索"""
        raise NotImplementedError

    def delete(self, ids: List[str]) -> bool:
        """删除文档"""
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    """ChromaDB向量存储"""

    def __init__(self, collection_name: str = "platform_knowledge", persist_directory: str = None):
        try:
            import chromadb
            from chromadb.config import Settings

            self.collection_name = collection_name

            # 设置持久化目录
            if persist_directory is None:
                persist_directory = os.path.join(
                    Path(__file__).parent, "indexes"
                )

            os.makedirs(persist_directory, exist_ok=True)

            # 初始化ChromaDB客户端
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )

            # 获取或创建集合
            try:
                self.collection = self.client.get_collection(name=collection_name)
                logger.info(f"加载已存在的集合: {collection_name}")
            except:
                self.collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"description": "智信优控平台知识库"}
                )
                logger.info(f"创建新集合: {collection_name}")

        except ImportError:
            logger.error("ChromaDB未安装，请运行: pip install chromadb")
            raise

    def add_documents(
        self,
        documents: List[Any],
        embeddings: List[List[float]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """添加文档到向量库"""
        try:
            # 生成ID
            if ids is None:
                ids = [f"doc_{i}_{hash(doc.content)}" for i, doc in enumerate(documents)]

            # 提取内容和元数据
            texts = [doc.content for doc in documents]
            metadatas = [doc.metadata for doc in documents]

            # 添加到ChromaDB
            self.collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )

            logger.info(f"成功添加 {len(documents)} 个文档到向量库")
            return ids

        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            raise

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict] = None
    ) -> List[Dict]:
        """向量相似度搜索"""
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter
            )

            # 格式化结果
            documents = []
            if results['documents'] and len(results['documents']) > 0:
                for i in range(len(results['documents'][0])):
                    doc = {
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else 0,
                        'id': results['ids'][0][i]
                    }
                    documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            return []

    def delete(self, ids: List[str]) -> bool:
        """删除文档"""
        try:
            self.collection.delete(ids=ids)
            logger.info(f"成功删除 {len(ids)} 个文档")
            return True
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False

    def get_collection_stats(self) -> Dict:
        """获取集合统计信息"""
        try:
            count = self.collection.count()
            return {
                "name": self.collection_name,
                "count": count,
                "metadata": self.collection.metadata
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

    def reset(self):
        """重置集合（清空所有数据）"""
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "智信优控平台知识库"}
            )
            logger.info(f"集合 {self.collection_name} 已重置")
        except Exception as e:
            logger.error(f"重置集合失败: {e}")
            raise


class HybridRetriever:
    """混合检索器：结合向量检索和关键词检索"""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

        # 重排序权重配置
        self.rerank_weights = {
            'semantic': 0.4,      # 语义相似度
            'keyword': 0.2,       # 关键词匹配
            'recency': 0.15,      # 时间新鲜度
            'user_preference': 0.15,  # 用户偏好
            'quality': 0.1        # 文档质量
        }

    def search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        use_keyword: bool = True,
        context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        混合检索（支持上下文感知）

        Args:
            query: 查询文本
            query_embedding: 查询向量
            top_k: 返回结果数量
            use_keyword: 是否使用关键词检索
            context: 上下文信息
                - module: 当前实验模块ID
                - user_role: 用户角色
                - user_id: 用户ID
                - boost_recent: 是否提升最新内容权重
        """
        # 构建过滤条件
        filter_dict = None
        if context and context.get('module'):
            filter_dict = {'module_id': context['module']}

        # 向量检索
        vector_results = self.vector_store.similarity_search(
            query_embedding,
            top_k=top_k * 3,  # 获取更多候选结果用于重排序
            filter=filter_dict
        )

        if not use_keyword:
            # 即使不使用关键词，也应用智能重排序
            reranked = self.rerank(query, vector_results[:top_k * 2], context)
            return reranked[:top_k]

        # 关键词过滤和初步打分
        keywords = self._extract_keywords(query)
        scored_results = []

        for doc in vector_results:
            # 计算关键词匹配分数
            keyword_score = self._calculate_keyword_score(doc['content'], keywords)

            # 向量距离转换为相似度分数（距离越小，分数越高）
            vector_score = 1 / (1 + doc['distance'])

            # 综合分数（可调整权重）
            final_score = 0.7 * vector_score + 0.3 * keyword_score

            doc['score'] = final_score
            scored_results.append(doc)

        # 按分数排序，取top_k*2用于重排序
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        candidates = scored_results[:top_k * 2]

        # 应用智能重排序
        reranked = self.rerank(query, candidates, context)

        return reranked[:top_k]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简单实现）"""
        import re
        # 移除标点符号，分词
        words = re.findall(r'\w+', text.lower())
        # 过滤停用词（简化版）
        stopwords = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个'}
        keywords = [w for w in words if w not in stopwords and len(w) > 1]
        return keywords

    def _calculate_keyword_score(self, text: str, keywords: List[str]) -> float:
        """计算关键词匹配分数"""
        if not keywords:
            return 0.0

        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw in text_lower)
        return matches / len(keywords)

    def _apply_context_boost(self, results: List[Dict], context: Optional[Dict]) -> List[Dict]:
        """应用上下文增强（时间权重、用户偏好等）"""
        if not context:
            return results

        # 1. 时间感知：提升最近内容的权重
        boost_recent = context.get('boost_recent', False)
        if boost_recent:
            from datetime import datetime
            import os

            for doc in results:
                # 获取文档时间戳
                timestamp = doc['metadata'].get('timestamp')
                if not timestamp:
                    # 尝试从文件路径获取修改时间
                    file_path = doc['metadata'].get('source')
                    if file_path and os.path.exists(file_path):
                        mtime = os.path.getmtime(file_path)
                        timestamp = datetime.fromtimestamp(mtime).isoformat()

                if timestamp:
                    try:
                        doc_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        now = datetime.now()
                        days_old = (now - doc_time).days

                        # 时间衰减因子：30天内权重1.0，之后每30天衰减10%
                        time_boost = max(0.5, 1.0 - (days_old / 300))
                        doc['score'] = doc.get('score', 1.0) * time_boost
                    except Exception:
                        pass

        # 2. 用户个性化：根据用户历史调整权重
        user_history = context.get('user_history', [])
        if user_history:
            # 提取用户历史中的关键词
            history_keywords = set()
            for hist_query in user_history:
                keywords = self._extract_keywords(hist_query)
                history_keywords.update(keywords)

            # 根据历史关键词匹配度调整权重
            for doc in results:
                content_lower = doc['content'].lower()
                matches = sum(1 for kw in history_keywords if kw in content_lower)
                if matches > 0:
                    # 历史匹配度提升：每匹配一个关键词提升5%
                    history_boost = 1.0 + (matches * 0.05)
                    doc['score'] = doc.get('score', 1.0) * history_boost

        # 重新排序
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results

    def rerank(
        self,
        query: str,
        results: List[Dict],
        context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        智能重排序算法
        综合考虑多个因素：语义相似度、关键词匹配、时间新鲜度、用户偏好、文档质量

        Args:
            query: 查询文本
            results: 初始检索结果
            context: 上下文信息

        Returns:
            重排序后的结果
        """
        if not results:
            return results

        keywords = self._extract_keywords(query)
        user_history = context.get('user_history', []) if context else []
        history_keywords = set()
        for hist_query in user_history:
            history_keywords.update(self._extract_keywords(hist_query))

        from datetime import datetime
        import os

        for doc in results:
            scores = {}

            # 1. 语义相似度分数（已有的distance转换）
            scores['semantic'] = 1 / (1 + doc.get('distance', 1.0))

            # 2. 关键词匹配分数
            scores['keyword'] = self._calculate_keyword_score(doc['content'], keywords)

            # 3. 时间新鲜度分数
            timestamp = doc['metadata'].get('timestamp')
            if not timestamp:
                file_path = doc['metadata'].get('source')
                if file_path and os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    timestamp = datetime.fromtimestamp(mtime).isoformat()

            if timestamp:
                try:
                    doc_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    days_old = (datetime.now() - doc_time).days
                    scores['recency'] = max(0.3, 1.0 - (days_old / 365))  # 一年内衰减
                except Exception:
                    scores['recency'] = 0.5
            else:
                scores['recency'] = 0.5

            # 4. 用户偏好分数
            if history_keywords:
                content_lower = doc['content'].lower()
                matches = sum(1 for kw in history_keywords if kw in content_lower)
                scores['user_preference'] = min(1.0, matches / max(len(history_keywords), 1))
            else:
                scores['user_preference'] = 0.5

            # 5. 文档质量分数（基于长度、结构等）
            content_len = len(doc['content'])
            has_code = '```' in doc['content'] or 'def ' in doc['content'] or 'class ' in doc['content']
            has_structure = any(marker in doc['content'] for marker in ['##', '###', '1.', '2.'])

            quality_score = 0.5
            if 200 <= content_len <= 2000:  # 适中长度
                quality_score += 0.2
            if has_code:  # 包含代码示例
                quality_score += 0.2
            if has_structure:  # 有良好结构
                quality_score += 0.1

            scores['quality'] = min(1.0, quality_score)

            # 综合加权分数
            final_score = sum(
                scores[factor] * self.rerank_weights[factor]
                for factor in self.rerank_weights
            )

            doc['rerank_score'] = final_score
            doc['score_breakdown'] = scores  # 保存详细分数用于调试

        # 按重排序分数排序
        results.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
        return results
