"""
Embedding生成模块
使用OpenAI text-embedding-3-small模型生成向量嵌入
"""

import os
import logging
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """向量嵌入生成器基类"""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量生成文档嵌入"""
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        """生成查询嵌入"""
        raise NotImplementedError


class OpenAIEmbedding(EmbeddingGenerator):
    """OpenAI Embedding API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: str = "text-embedding-3-small"
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.api_base = api_base or os.getenv("OPENAI_API_BASE", "https://cc-vibe.com/v1")
        self.model = model

        if not self.api_key:
            raise ValueError("需要配置OPENAI_API_KEY或CLAUDE_API_KEY")

        logger.info(f"初始化OpenAI Embedding: {self.model}")

    async def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用OpenAI API"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.api_base}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": texts
                    }
                )

                if response.status_code != 200:
                    error_text = response.text
                    raise Exception(f"API调用失败: {error_text}")

                result = response.json()
                embeddings = [item['embedding'] for item in result['data']]
                return embeddings

        except Exception as e:
            logger.error(f"生成嵌入失败: {e}")
            raise

    def embed_documents(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """批量生成文档嵌入"""
        import asyncio

        all_embeddings = []

        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"生成嵌入: {i}/{len(texts)}")

            try:
                embeddings = asyncio.run(self._call_api(batch))
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"批次 {i} 失败: {e}")
                # 失败时返回零向量
                all_embeddings.extend([[0.0] * 1536 for _ in batch])

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """生成查询嵌入"""
        import asyncio
        embeddings = asyncio.run(self._call_api([text]))
        return embeddings[0] if embeddings else [0.0] * 1536


class CachedEmbedding(EmbeddingGenerator):
    """带缓存的嵌入生成器"""

    def __init__(self, base_embedding: EmbeddingGenerator, cache_dir: str = None):
        self.base_embedding = base_embedding
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(__file__), "cache"
        )
        os.makedirs(self.cache_dir, exist_ok=True)

        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        """加载缓存"""
        import json
        cache_file = os.path.join(self.cache_dir, "embeddings_cache.json")

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self):
        """保存缓存"""
        import json
        cache_file = os.path.join(self.cache_dir, "embeddings_cache.json")

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量生成文档嵌入（带缓存）"""
        embeddings = []
        uncached_texts = []
        uncached_indices = []

        # 检查缓存
        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)
            if cache_key in self.cache:
                embeddings.append(self.cache[cache_key])
            else:
                embeddings.append(None)
                uncached_texts.append(text)
                uncached_indices.append(i)

        # 生成未缓存的嵌入
        if uncached_texts:
            logger.info(f"缓存命中: {len(texts) - len(uncached_texts)}/{len(texts)}")
            new_embeddings = self.base_embedding.embed_documents(uncached_texts)

            # 更新缓存和结果
            for i, embedding in zip(uncached_indices, new_embeddings):
                embeddings[i] = embedding
                cache_key = self._get_cache_key(texts[i])
                self.cache[cache_key] = embedding

            self._save_cache()

        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """生成查询嵌入（带缓存）"""
        cache_key = self._get_cache_key(text)

        if cache_key in self.cache:
            return self.cache[cache_key]

        embedding = self.base_embedding.embed_query(text)
        self.cache[cache_key] = embedding
        self._save_cache()

        return embedding
