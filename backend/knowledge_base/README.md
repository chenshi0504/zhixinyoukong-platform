# RAG知识库系统

## 目录结构

```
knowledge_base/
├── documents/          # 原始文档存储
│   ├── tutorials/      # 教材文档
│   ├── code/           # 代码文档
│   ├── api/            # API文档
│   └── config/         # 配置文档
├── embeddings/         # 向量嵌入存储
├── indexes/            # ChromaDB索引
├── cache/              # 缓存文件
└── scripts/            # 管理脚本
```

## 功能特性

- **多源文档支持**: Markdown、Word、Python、JavaScript等
- **向量检索**: 基于ChromaDB的语义搜索
- **智能分块**: 自动文档分块和元数据提取
- **增量更新**: 支持文档增量索引
- **混合检索**: 结合向量检索和关键词检索

## 使用方法

### 1. 构建知识库索引

```bash
python backend/knowledge_base/scripts/build_index.py
```

### 2. 查询知识库

```python
from backend.knowledge_base.retriever import KnowledgeRetriever

retriever = KnowledgeRetriever()
results = retriever.search("如何配置CARLA仿真环境？", top_k=5)
```

### 3. 更新知识库

```bash
python backend/knowledge_base/scripts/update_index.py --incremental
```

## 配置说明

在 `.env` 文件中配置：

```env
# OpenAI Embedding API (通过Claude代理)
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://cc-vibe.com/v1

# ChromaDB配置
CHROMA_PERSIST_DIR=backend/knowledge_base/indexes
CHROMA_COLLECTION_NAME=platform_knowledge
```
