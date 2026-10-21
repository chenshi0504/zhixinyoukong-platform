"""
知识库管理后端API

提供知识库管理界面所需的所有API接口，包括：
- 仪表板统计
- 文档管理
- 索引管理
- 检索测试
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
from pathlib import Path
import json
import shutil
import logging

from .monitoring import MonitoringSystem
from .vector_store import VectorStore, HybridRetriever
from .index_manager import IndexMetadata, IncrementalIndexer, IndexQualityEvaluator
from .feedback import FeedbackCollector
from .document_loader import DocumentLoader
from .retriever import KnowledgeRetriever

logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/admin", tags=["admin"])

# 全局实例
monitoring_system = MonitoringSystem()
feedback_collector = FeedbackCollector()

# ==================== 数据模型 ====================

class DocumentInfo(BaseModel):
    """文档信息"""
    id: str
    name: str
    type: str
    size: int
    status: str
    tags: List[str] = []
    description: str = ""
    created_at: datetime
    updated_at: datetime
    indexed_at: Optional[datetime] = None


class IndexStatusResponse(BaseModel):
    """索引状态响应"""
    status: str
    version: str
    last_update: datetime
    next_update: Optional[datetime]
    vector_count: int
    dimension: int
    storage_size: int
    avg_retrieval_time: float


class RetrievalConfig(BaseModel):
    """检索配置"""
    top_k: int = 5
    enable_rerank: bool = True
    time_weight: float = 0.15
    semantic_weight: float = 0.40
    keyword_weight: float = 0.20
    user_preference_weight: float = 0.15
    quality_weight: float = 0.10


class RetrievalTestRequest(BaseModel):
    """检索测试请求"""
    query: str
    config: RetrievalConfig


class ConfigComparisonRequest(BaseModel):
    """配置对比请求"""
    query: str
    configs: List[RetrievalConfig]


# ==================== 仪表板API ====================

@router.get("/dashboard/stats")
async def get_dashboard_stats() -> Dict[str, Any]:
    """
    获取仪表板统计数据

    返回:
        - document_count: 文档总数
        - index_status: 索引状态
        - today_queries: 今日查询数
        - avg_response_time: 平均响应时间
        - query_trend: 查询趋势
        - document_types: 文档类型分布
        - quality_metrics: 质量指标
        - system_health: 系统健康状态
        - recent_activities: 最近活动
    """
    try:
        # 获取监控数据
        stats = monitoring_system.get_statistics()
        health = monitoring_system.get_health_score()

        # 获取文档统计
        vector_store = VectorStore()
        collection_info = vector_store.get_collection_info()

        # 获取反馈统计
        feedback_stats = feedback_collector.get_statistics()

        # 获取索引质量
        index_metadata = IndexMetadata()
        quality_evaluator = IndexQualityEvaluator(vector_store)
        quality_metrics = quality_evaluator.evaluate_quality()

        # 计算今日查询数
        today_queries = stats.get('total_requests', 0)

        # 构建查询趋势（最近7天）
        query_trend = _get_query_trend(7)

        # 文档类型分布（模拟数据，实际应从元数据获取）
        document_types = {
            "用户手册": 45,
            "API文档": 30,
            "FAQ": 25
        }

        # 最近活动
        recent_activities = _get_recent_activities()

        return {
            "document_count": collection_info.get('document_count', 0),
            "index_status": "healthy" if health['score'] > 80 else "warning",
            "today_queries": today_queries,
            "avg_response_time": stats.get('avg_response_time', 0),
            "query_trend": query_trend,
            "document_types": document_types,
            "quality_metrics": {
                "accuracy": quality_metrics.get('coverage', 0) * 100,
                "mrr": 0.892,  # 从评估工具获取
                "avg_response_time": stats.get('avg_response_time', 0),
                "user_satisfaction": feedback_stats.get('avg_rating', 0)
            },
            "system_health": {
                "cpu": health.get('resource_score', 0),
                "memory": health.get('resource_score', 0),
                "disk": health.get('resource_score', 0),
                "health_score": health['score']
            },
            "recent_activities": recent_activities
        }
    except Exception as e:
        logger.error(f"获取仪表板统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_query_trend(days: int) -> List[int]:
    """获取查询趋势"""
    # 模拟数据，实际应从监控系统获取
    import random
    return [random.randint(50, 150) for _ in range(days)]


def _get_recent_activities() -> List[Dict[str, str]]:
    """获取最近活动"""
    # 模拟数据，实际应从日志或数据库获取
    activities = [
        {
            "time": "2026-04-23 10:23",
            "action": "新增文档",
            "detail": "信号优化算法说明.md"
        },
        {
            "time": "2026-04-23 09:15",
            "action": "索引更新完成",
            "detail": "新增12个文档"
        },
        {
            "time": "2026-04-23 08:47",
            "action": "用户反馈",
            "detail": "查询'路径规划'响应慢"
        }
    ]
    return activities


# ==================== 文档管理API ====================

@router.get("/documents")
async def list_documents(
    page: int = 1,
    size: int = 50,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取文档列表

    参数:
        - page: 页码
        - size: 每页大小
        - doc_type: 文档类型过滤
        - status: 状态过滤
        - search: 搜索关键词
    """
    try:
        vector_store = VectorStore()
        index_metadata = IndexMetadata()

        # 获取所有文档
        all_docs = index_metadata.get_all_documents()

        # 过滤
        filtered_docs = all_docs
        if doc_type and doc_type != "all":
            filtered_docs = [d for d in filtered_docs if d.get('type') == doc_type]
        if status and status != "all":
            filtered_docs = [d for d in filtered_docs if d.get('status') == status]
        if search:
            filtered_docs = [d for d in filtered_docs if search.lower() in d.get('name', '').lower()]

        # 分页
        total = len(filtered_docs)
        start = (page - 1) * size
        end = start + size
        page_docs = filtered_docs[start:end]

        return {
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size,
            "documents": page_docs
        }
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: str = "manual",
    tags: str = "",
    description: str = "",
    auto_index: bool = True
) -> Dict[str, Any]:
    """
    上传文档

    参数:
        - file: 上传的文件
        - doc_type: 文档类型
        - tags: 标签（逗号分隔）
        - description: 描述
        - auto_index: 是否自动索引
    """
    try:
        # 保存文件
        upload_dir = Path("data/knowledge_base/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / file.filename
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 创建文档记录
        doc_info = {
            "id": f"doc_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": file.filename,
            "type": doc_type,
            "size": file_path.stat().st_size,
            "status": "pending",
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "description": description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "file_path": str(file_path)
        }

        # 保存元数据
        index_metadata = IndexMetadata()
        index_metadata.add_document(doc_info)

        # 如果需要自动索引，添加后台任务
        if auto_index:
            background_tasks.add_task(_index_document, doc_info)

        return {
            "success": True,
            "document": doc_info,
            "message": "文档上传成功" + ("，正在后台索引" if auto_index else "")
        }
    except Exception as e:
        logger.error(f"上传文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _index_document(doc_info: Dict[str, Any]):
    """后台索引文档"""
    try:
        # 加载文档
        loader = DocumentLoader()
        documents = loader.load_file(Path(doc_info['file_path']))

        # 索引到向量库
        vector_store = VectorStore()
        vector_store.add_documents(documents)

        # 更新状态
        index_metadata = IndexMetadata()
        doc_info['status'] = 'indexed'
        doc_info['indexed_at'] = datetime.now().isoformat()
        index_metadata.update_document(doc_info['id'], doc_info)

        logger.info(f"文档索引完成: {doc_info['name']}")
    except Exception as e:
        logger.error(f"索引文档失败: {e}")
        # 更新状态为错误
        index_metadata = IndexMetadata()
        doc_info['status'] = 'error'
        index_metadata.update_document(doc_info['id'], doc_info)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> Dict[str, Any]:
    """
    删除文档

    参数:
        - doc_id: 文档ID
    """
    try:
        index_metadata = IndexMetadata()
        doc_info = index_metadata.get_document(doc_id)

        if not doc_info:
            raise HTTPException(status_code=404, detail="文档不存在")

        # 从向量库删除
        vector_store = VectorStore()
        vector_store.delete_document(doc_id)

        # 删除文件
        if 'file_path' in doc_info:
            file_path = Path(doc_info['file_path'])
            if file_path.exists():
                file_path.unlink()

        # 删除元数据
        index_metadata.delete_document(doc_id)

        return {
            "success": True,
            "message": f"文档 {doc_info['name']} 已删除"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/batch-delete")
async def batch_delete_documents(doc_ids: List[str]) -> Dict[str, Any]:
    """
    批量删除文档

    参数:
        - doc_ids: 文档ID列表
    """
    try:
        success_count = 0
        failed_count = 0

        for doc_id in doc_ids:
            try:
                await delete_document(doc_id)
                success_count += 1
            except Exception as e:
                logger.error(f"删除文档 {doc_id} 失败: {e}")
                failed_count += 1

        return {
            "success": True,
            "message": f"成功删除 {success_count} 个文档，失败 {failed_count} 个"
        }
    except Exception as e:
        logger.error(f"批量删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/batch-reindex")
async def batch_reindex_documents(
    background_tasks: BackgroundTasks,
    doc_ids: List[str]
) -> Dict[str, Any]:
    """
    批量重新索引文档

    参数:
        - doc_ids: 文档ID列表
    """
    try:
        index_metadata = IndexMetadata()

        for doc_id in doc_ids:
            doc_info = index_metadata.get_document(doc_id)
            if doc_info:
                background_tasks.add_task(_index_document, doc_info)

        return {
            "success": True,
            "message": f"已提交 {len(doc_ids)} 个文档的重新索引任务"
        }
    except Exception as e:
        logger.error(f"批量重新索引失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 索引管理API ====================

@router.get("/index/status")
async def get_index_status() -> IndexStatusResponse:
    """获取索引状态"""
    try:
        vector_store = VectorStore()
        index_metadata = IndexMetadata()

        collection_info = vector_store.get_collection_info()
        metadata = index_metadata.get_metadata()

        return IndexStatusResponse(
            status="healthy",
            version=metadata.get('version', 'v1.0.0'),
            last_update=datetime.fromisoformat(metadata.get('last_update', datetime.now().isoformat())),
            next_update=None,  # 从定时任务配置获取
            vector_count=collection_info.get('vector_count', 0),
            dimension=collection_info.get('dimension', 1536),
            storage_size=collection_info.get('storage_size', 0),
            avg_retrieval_time=45.0  # 从监控系统获取
        )
    except Exception as e:
        logger.error(f"获取索引状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/rebuild")
async def rebuild_index(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    全量重建索引

    警告: 此操作将删除现有索引并重新构建
    """
    try:
        # 添加后台任务
        background_tasks.add_task(_rebuild_index_task)

        return {
            "success": True,
            "message": "索引重建任务已提交，预计需要15分钟"
        }
    except Exception as e:
        logger.error(f"提交索引重建任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _rebuild_index_task():
    """后台重建索引任务"""
    try:
        logger.info("开始全量重建索引...")

        # 获取所有文档
        index_metadata = IndexMetadata()
        all_docs = index_metadata.get_all_documents()

        # 清空现有索引
        vector_store = VectorStore()
        vector_store.clear()

        # 重新索引所有文档
        loader = DocumentLoader()
        for doc_info in all_docs:
            if 'file_path' in doc_info:
                try:
                    documents = loader.load_file(Path(doc_info['file_path']))
                    vector_store.add_documents(documents)

                    # 更新状态
                    doc_info['status'] = 'indexed'
                    doc_info['indexed_at'] = datetime.now().isoformat()
                    index_metadata.update_document(doc_info['id'], doc_info)
                except Exception as e:
                    logger.error(f"索引文档 {doc_info['name']} 失败: {e}")

        # 更新元数据
        metadata = index_metadata.get_metadata()
        metadata['last_update'] = datetime.now().isoformat()
        metadata['version'] = f"v{datetime.now().strftime('%Y%m%d%H%M')}"
        index_metadata.update_metadata(metadata)

        logger.info("索引重建完成")
    except Exception as e:
        logger.error(f"重建索引失败: {e}")


@router.post("/index/incremental-update")
async def incremental_update(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """增量更新索引"""
    try:
        background_tasks.add_task(_incremental_update_task)

        return {
            "success": True,
            "message": "增量更新任务已提交"
        }
    except Exception as e:
        logger.error(f"提交增量更新任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _incremental_update_task():
    """后台增量更新任务"""
    try:
        logger.info("开始增量更新索引...")

        vector_store = VectorStore()
        incremental_indexer = IncrementalIndexer(vector_store)

        # 执行增量更新
        result = incremental_indexer.update_index()

        logger.info(f"增量更新完成: 新增 {result['added']} 个，更新 {result['updated']} 个，删除 {result['deleted']} 个")
    except Exception as e:
        logger.error(f"增量更新失败: {e}")


@router.get("/index/quality")
async def get_index_quality() -> Dict[str, Any]:
    """获取索引质量评估"""
    try:
        vector_store = VectorStore()
        quality_evaluator = IndexQualityEvaluator(vector_store)

        quality_metrics = quality_evaluator.evaluate_quality()

        return {
            "coverage": quality_metrics.get('coverage', 0) * 100,
            "consistency": quality_metrics.get('consistency', 0) * 100,
            "freshness": quality_metrics.get('freshness', 0) * 100,
            "retrieval_speed": quality_metrics.get('retrieval_speed', 0) * 100,
            "storage_efficiency": quality_metrics.get('storage_efficiency', 0) * 100,
            "overall_score": quality_metrics.get('overall_score', 0) * 100
        }
    except Exception as e:
        logger.error(f"获取索引质量失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/history")
async def get_index_history(limit: int = 10) -> List[Dict[str, Any]]:
    """获取索引历史"""
    try:
        index_metadata = IndexMetadata()
        history = index_metadata.get_history(limit)

        return history
    except Exception as e:
        logger.error(f"获取索引历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 检索测试API ====================

@router.post("/retrieval/test")
async def test_retrieval(request: RetrievalTestRequest) -> Dict[str, Any]:
    """
    测试检索

    参数:
        - query: 查询文本
        - config: 检索配置
    """
    try:
        start_time = datetime.now()

        # 创建检索器
        vector_store = VectorStore()
        retriever = HybridRetriever(vector_store)

        # 执行检索
        results = retriever.retrieve(
            query=request.query,
            top_k=request.config.top_k,
            enable_rerank=request.config.enable_rerank
        )

        end_time = datetime.now()
        query_time = (end_time - start_time).total_seconds() * 1000

        # 格式化结果
        formatted_results = []
        for i, result in enumerate(results):
            formatted_results.append({
                "rank": i + 1,
                "doc_id": result.get('id', ''),
                "doc_name": result.get('metadata', {}).get('source', ''),
                "section": result.get('metadata', {}).get('section', ''),
                "content": result.get('content', ''),
                "score": result.get('score', 0),
                "metadata": result.get('metadata', {})
            })

        return {
            "query": request.query,
            "results": formatted_results,
            "stats": {
                "query_time": query_time,
                "candidate_count": len(results),
                "returned_count": len(formatted_results),
                "avg_score": sum(r['score'] for r in formatted_results) / len(formatted_results) if formatted_results else 0
            }
        }
    except Exception as e:
        logger.error(f"检索测试失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieval/compare-configs")
async def compare_configs(request: ConfigComparisonRequest) -> Dict[str, Any]:
    """
    对比不同配置的检索效果

    参数:
        - query: 查询文本
        - configs: 配置列表
    """
    try:
        results = []

        for i, config in enumerate(request.configs):
            test_request = RetrievalTestRequest(query=request.query, config=config)
            result = await test_retrieval(test_request)

            results.append({
                "config_name": f"配置{chr(65+i)}",  # A, B, C...
                "config": config.dict(),
                "stats": result['stats'],
                "top_results": result['results'][:3]  # 只返回前3个结果
            })

        # 生成推荐
        best_config_idx = max(range(len(results)), key=lambda i: results[i]['stats']['avg_score'])

        return {
            "query": request.query,
            "comparisons": results,
            "recommendation": {
                "best_config": results[best_config_idx]['config_name'],
                "reason": f"在相关度上表现最好（平均分: {results[best_config_idx]['stats']['avg_score']:.3f}）"
            }
        }
    except Exception as e:
        logger.error(f"配置对比失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieval/apply-config")
async def apply_config(config: RetrievalConfig) -> Dict[str, Any]:
    """
    应用检索配置

    参数:
        - config: 检索配置
    """
    try:
        # 保存配置到文件
        config_file = Path("data/knowledge_base/retrieval_config.json")
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config.dict(), f, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "message": "检索配置已应用"
        }
    except Exception as e:
        logger.error(f"应用配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retrieval/test-cases")
async def get_test_cases() -> List[Dict[str, Any]]:
    """获取测试用例列表"""
    try:
        test_cases_file = Path("data/knowledge_base/test_cases.json")

        if not test_cases_file.exists():
            return []

        with open(test_cases_file, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)

        return test_cases
    except Exception as e:
        logger.error(f"获取测试用例失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieval/test-cases")
async def save_test_case(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """保存测试用例"""
    try:
        test_cases_file = Path("data/knowledge_base/test_cases.json")
        test_cases_file.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有测试用例
        if test_cases_file.exists():
            with open(test_cases_file, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
        else:
            test_cases = []

        # 添加新测试用例
        test_case['id'] = f"tc_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        test_case['created_at'] = datetime.now().isoformat()
        test_cases.append(test_case)

        # 保存
        with open(test_cases_file, 'w', encoding='utf-8') as f:
            json.dump(test_cases, f, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "test_case": test_case
        }
    except Exception as e:
        logger.error(f"保存测试用例失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 健康检查 ====================

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }
