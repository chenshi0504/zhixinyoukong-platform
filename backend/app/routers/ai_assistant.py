"""
AI实验助手路由
仅使用 DeepSeek 模型，提供实验指导和代码理解功能
"""
import os
import json
import logging
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from .ai_assistant_tools import AIAssistantTools

logger = logging.getLogger(__name__)

# 导入用户历史管理器和对话管理器
import sys
from pathlib import Path
kb_path = Path(__file__).parent.parent.parent / "knowledge_base"
if str(kb_path) not in sys.path:
    sys.path.insert(0, str(kb_path))

try:
    from dotenv import load_dotenv

    _backend_dir = Path(__file__).resolve().parents[2]
    _project_dir = _backend_dir.parent
    for _env_path, _override in ((_project_dir / ".env", False), (_backend_dir / ".env", True)):
        if _env_path.exists():
            load_dotenv(_env_path, override=_override)
except Exception as e:
    logger.warning(f"AI助手环境变量加载失败: {e}")

try:
    from user_history import get_history_manager
    history_manager = get_history_manager()
except Exception as e:
    logger.warning(f"用户历史管理器初始化失败: {e}")
    history_manager = None

try:
    from conversation_manager import get_conversation_manager
    conversation_manager = get_conversation_manager()
except Exception as e:
    logger.warning(f"对话管理器初始化失败: {e}")
    conversation_manager = None

try:
    from index_manager import (
        get_index_metadata,
        get_incremental_indexer,
        get_quality_evaluator,
        get_scheduled_indexer
    )
    from retriever import get_knowledge_manager
    knowledge_manager = get_knowledge_manager()
    index_metadata = get_index_metadata()
    incremental_indexer = get_incremental_indexer(knowledge_manager.retriever if knowledge_manager else None)
    quality_evaluator = get_quality_evaluator(knowledge_manager.retriever if knowledge_manager else None)
    scheduled_indexer = get_scheduled_indexer(knowledge_manager.retriever if knowledge_manager else None)
except Exception as e:
    logger.warning(f"索引管理器初始化失败: {e}")
    knowledge_manager = None
    index_metadata = None
    incremental_indexer = None
    quality_evaluator = None
    scheduled_indexer = None

try:
    from monitoring import monitoring_system
except Exception as e:
    logger.warning(f"监控系统初始化失败: {e}")
    monitoring_system = None

router = APIRouter()


# ========== 请求/响应模型 ==========
class ChatMessage(BaseModel):
    role: str  # 'user' | 'assistant' | 'system'
    content: str


class ChatRequest(BaseModel):
    message: str
    model: str = "deepseek"
    context: Optional[str] = None  # 当前实验模块上下文
    history: Optional[List[ChatMessage]] = []
    session_id: Optional[str] = None  # 会话ID，用于对话管理


class AIConfig(BaseModel):
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: Optional[str] = None
    deepseek_model: Optional[str] = None
    deepseek_reasoning_effort: Optional[str] = None


# ========== AI模型服务 ==========
class AIModelService:
    """AI模型调用服务：平台仅启用 DeepSeek。"""

    def __init__(self):
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        self.deepseek_thinking = os.getenv("DEEPSEEK_THINKING", "disabled").strip().lower()
        self.deepseek_reasoning_effort = self._normalize_reasoning_effort(
            os.getenv("DEEPSEEK_REASONING_EFFORT", "max")
        )
        self.enable_rag = os.getenv("AI_ASSISTANT_ENABLE_RAG", "false").strip().lower() in {"1", "true", "yes", "on"}
        self.enable_tools = os.getenv("AI_ASSISTANT_ENABLE_TOOLS", "false").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _normalize_reasoning_effort(value: Optional[str]) -> str:
        effort = (value or "max").strip().lower()
        if effort in {"max", "xhigh"}:
            return "max"
        return "high"

    def _check_api_key(self, model: str) -> None:
        """检查API密钥是否配置，未配置则抛出友好错误"""
        if not self.deepseek_key:
            raise HTTPException(
                status_code=400,
                detail="DeepSeek API密钥未配置。请在安装目录创建 .env 文件并配置 DEEPSEEK_API_KEY。"
            )

    async def chat_stream(
        self,
        message: str,
        model: str,
        history: List[ChatMessage],
        context: Optional[str] = None,
        tools: Optional[Any] = None,
        db: Optional[Session] = None,
        current_user: Optional[User] = None
    ):
        """流式对话接口"""
        try:
            self._check_api_key("deepseek")
        except HTTPException as e:
            yield f"data: {json.dumps({'error': e.detail}, ensure_ascii=False)}\n\n"
            return

        if model != "deepseek":
            logger.info("AI助手收到旧模型参数 %s，已强制切换到 DeepSeek", model)

        async for chunk in self._chat_deepseek_stream(message, history, context, tools, db, current_user):
            yield chunk

    async def _chat_deepseek_stream(
        self,
        message: str,
        history: List[ChatMessage],
        context: Optional[str] = None,
        tools: Optional[Any] = None,
        db: Optional[Session] = None,
        current_user: Optional[User] = None
    ):
        """DeepSeek流式对话（支持工具调用）"""
        try:
            import httpx

            if not self.deepseek_key:
                yield 'data: {"error": "DeepSeek API Key未配置"}\n\n'
                return

            allow_code_examples = self._explicit_code_requested(message)

            # 构建系统提示词
            system_prompt = self._build_system_prompt(context, allow_code_examples=allow_code_examples)

            # 构建消息列表
            messages = [{"role": "system", "content": system_prompt}]
            for msg in history[-20:]:  # 保留最近20轮对话
                messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": message})

            payload = {
                "model": self.deepseek_model,
                "messages": messages,
                "stream": True,
                "thinking": {"type": self.deepseek_thinking},
                "max_tokens": 3200 if allow_code_examples else 1800
            }
            if self.deepseek_thinking != "disabled":
                payload["reasoning_effort"] = self.deepseek_reasoning_effort

            # 调用 DeepSeek API。默认关闭 thinking，确保前端优先收到正文 content。
            timeout = httpx.Timeout(180.0, connect=20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.deepseek_base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.deepseek_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_body = error_text.decode(errors="replace")
                        logger.error(
                            "DeepSeek API错误 status=%s model=%s base_url=%s body=%s",
                            response.status_code,
                            self.deepseek_model,
                            self.deepseek_base_url,
                            error_body[:1000],
                        )
                        error_message = "DeepSeek API错误: " + error_body
                        yield f"data: {json.dumps({'error': error_message}, ensure_ascii=False)}\n\n"
                        return

                    last_keepalive = time.time()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue

                        data = line[6:].strip()
                        if not data or data == "[DONE]":
                            break

                        try:
                            chunk_data = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk_data.get("choices") or []
                        if not choices:
                            continue

                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            chunk = {
                                "choices": [{
                                    "delta": {"content": content},
                                    "index": choices[0].get("index", 0)
                                }]
                            }
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                            last_keepalive = time.time()
                        elif isinstance(delta.get("reasoning_content"), str) and self.deepseek_thinking != "disabled":
                            # thinking 阶段不把推理内容展示给学生，但保持前端流连接活跃。
                            if time.time() - last_keepalive >= 3:
                                yield 'data: {"choices":[{"delta":{},"index":0}]}\n\n'
                                last_keepalive = time.time()
                        elif time.time() - last_keepalive >= 10:
                            yield 'data: {"choices":[{"delta":{},"index":0}]}\n\n'
                            last_keepalive = time.time()

        except Exception as e:
            logger.error("DeepSeek调用失败: %s", e, exc_info=True)
            error_message = f"DeepSeek调用失败: {type(e).__name__}: {e}"
            yield f"data: {json.dumps({'error': error_message}, ensure_ascii=False)}\n\n"

    @staticmethod
    def _explicit_code_requested(message: str) -> bool:
        """判断用户本轮是否明确要求生成或修改代码。"""
        text = (message or "").strip().lower()
        compact = "".join(text.split())
        markers = (
            "写代码", "生成代码", "给出代码", "提供代码", "完整代码", "可运行代码",
            "代码实现", "python代码", "帮我实现", "实现一下", "写个函数", "写一个函数",
            "写脚本", "生成脚本", "补全代码", "修改代码", "修复代码", "调试代码",
            "debug", "报错", "traceback", "write code", "generate code", "python code",
            "implement", "script",
        )
        return any(marker in compact or marker in text for marker in markers)

    def _build_system_prompt(self, context: Optional[str] = None, *, allow_code_examples: bool = False) -> str:
        """构建系统提示词"""
        base_prompt = """你是智信优控平台的AI实验助手，面向车路云一体化综合交通实验教学。你的回答应体现交通工程、智能交通、仿真建模和数据分析的专业性。

你的职责：
1. 解答实验理论、实验流程、算法原理、数据指标和结果分析问题。
2. 帮助学生理解平台模块、任务要求、输入输出数据和实验报告写法。
3. 指导学生定位实验现象、日志信息、仿真配置和常见运行问题。
4. 在需要时解释代码思路，但不要把代码输出作为默认回答方式。

平台包含以下实验模块：
- 多源数据采集与融合：视频/点云感知、目标检测、坐标标定、融合评价。
- 交通流重构与预测：OD 反推、路段流量重构、短时预测、MAE/RMSE 等指标。
- 三层级协同优化控制：路径诱导、信号配时、车速控制、CAV 协同。
- 虚实结合仿真：SUMO、CARLA、DTALite、VIC-Sim 与联合仿真场景。

回答要求：
- 使用中文回答，表述专业、准确、克制，避免口语化和空泛鼓励。
- 默认控制在 3-6 个要点；复杂问题可分为“结论、依据、建议操作、验证指标”。
- 优先说明实验目的、输入数据、关键参数、操作步骤、评价指标、结果判读和常见问题。
- 涉及交通工程时尽量使用规范术语，如 OD 矩阵、路段流量、排队长度、延误、通行能力、CAV、路径诱导、信号配时等。
- 不确定的信息要明确说明需要查看具体配置、日志、数据或实验输出，不能编造版本、路径、结果或性能结论。
- 除非用户明确要求“写代码、生成代码、给出代码、可运行代码、修改/调试代码”，否则不要主动输出完整代码块，不要用大段 Python 示例替代专业解释。
- 如果用户只是询问算法原理、实验流程、结果解释或报告写法，只给公式、伪代码思路、流程步骤或参数说明即可。
"""

        if allow_code_examples:
            base_prompt += """

本轮用户明确要求代码：
- 可以提供代码，但必须紧扣用户问题，只给必要片段或最小可运行示例。
- 代码前先说明适用场景、输入/输出、依赖版本和运行位置。
- 代码注释要简明，避免一次性输出无关模块、完整工程或大段模板。
"""
        else:
            base_prompt += """

本轮用户未明确要求写代码：
- 禁止主动输出完整代码块或大段脚本。
- 如确需说明实现方式，只用自然语言、短公式、参数表或不超过 5 行的伪代码描述。
- 不要以“下面给出 Python 实现”作为默认回答结构。
"""

        if context:
            base_prompt += f"\n\n当前实验模块：{context}"

        return base_prompt


# 全局AI服务实例
ai_service = AIModelService()


# ========== 知识库服务 ==========
class KnowledgeBaseService:
    """实验教材和代码知识库（基于RAG）"""

    def __init__(self):
        from ..paths import PROJECT_ROOT
        self.docs_dir = os.path.join(PROJECT_ROOT, "docs", "教材")
        self.algorithms_dir = os.path.join(PROJECT_ROOT, "backend", "algorithms")
        self.index_file = os.path.join(PROJECT_ROOT, "backend", "data", "knowledge_index.json")
        self._index = None
        self._rag_retriever = None
        self._load_index()
        self._init_rag()

    def _init_rag(self):
        """初始化RAG检索器"""
        try:
            import sys
            from pathlib import Path

            # 添加knowledge_base到路径
            kb_path = Path(__file__).parent.parent.parent / "knowledge_base"
            if str(kb_path) not in sys.path:
                sys.path.insert(0, str(kb_path))

            from retriever import KnowledgeRetriever

            self._rag_retriever = KnowledgeRetriever()
            logger.info("RAG检索器初始化成功")
        except Exception as e:
            logger.warning(f"RAG检索器初始化失败，将使用传统检索: {e}")
            self._rag_retriever = None

    def _load_index(self):
        """加载知识库索引"""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self._index = json.load(f)
                logger.info(f"知识库索引已加载，包含 {len(self._index)} 个类别")
            except Exception as e:
                logger.warning(f"加载知识库索引失败: {e}")
                self._index = {}
        else:
            logger.warning(f"知识库索引文件不存在: {self.index_file}")
            self._index = {}

    def search_docs(self, query: str, top_k: int = 3, context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """搜索实验教材相关内容（优先使用RAG，支持上下文感知）

        Args:
            query: 查询文本
            top_k: 返回结果数量
            context: 上下文信息
                - module: 当前实验模块
                - boost_recent: 是否提升最新内容权重
        """
        # 优先使用RAG检索
        if self._rag_retriever:
            try:
                rag_results = self._rag_retriever.search(
                    query,
                    top_k=top_k,
                    context=context
                )

                # 转换为统一格式
                formatted_results = []
                for result in rag_results:
                    formatted_results.append({
                        'file': result['metadata'].get('filename', 'unknown'),
                        'section': result['metadata'].get('title', ''),
                        'content': result['content'][:500],
                        'score': result.get('score', result.get('distance', 0)),
                        'source': 'rag'
                    })

                if formatted_results:
                    logger.info(f"RAG检索返回 {len(formatted_results)} 个结果")
                    return formatted_results
            except Exception as e:
                logger.error(f"RAG检索失败，回退到传统检索: {e}")

        # 回退到传统检索
        results = []

        # 使用索引进行快速检索
        if self._index:
            query_lower = query.lower()
            matched_items = []

            # 在所有类别中搜索
            for category, items in self._index.items():
                if any(term in query_lower for term in category.lower().split()):
                    matched_items.extend(items[:2])  # 每个类别取前2条

            # 按分数排序并去重
            seen = set()
            for item in sorted(matched_items, key=lambda x: x.get('score', 0), reverse=True):
                key = (item['file'], item['section'])
                if key not in seen:
                    item['source'] = 'index'
                    results.append(item)
                    seen.add(key)
                    if len(results) >= top_k:
                        break

        # 如果索引检索结果不足，回退到全文搜索
        if len(results) < top_k and os.path.exists(self.docs_dir):
            try:
                for root, dirs, files in os.walk(self.docs_dir):
                    for file in files:
                        if file.endswith('.md'):
                            filepath = os.path.join(root, file)
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    if query.lower() in content.lower():
                                        # 提取相关段落
                                        lines = content.split('\n')
                                        relevant_lines = []
                                        for i, line in enumerate(lines):
                                            if query.lower() in line.lower():
                                                start = max(0, i - 2)
                                                end = min(len(lines), i + 3)
                                                relevant_lines.extend(lines[start:end])

                                        results.append({
                                            'file': file,
                                            'section': '全文搜索',
                                            'content': '\n'.join(relevant_lines[:500]),
                                            'score': 1,
                                            'source': 'fulltext'
                                        })

                                        if len(results) >= top_k:
                                            return results
                            except Exception as e:
                                logger.warning(f"读取文件失败 {filepath}: {e}")
                                continue
            except Exception as e:
                logger.error(f"搜索文档失败: {e}")

        return results[:top_k]

    def get_algorithm_info(self, module: str) -> Optional[str]:
        """获取算法模块信息"""
        module_map = {
            'data-collection': 'data_collection',
            'data-fusion': 'data_fusion',
            'traffic-reconstruction': 'traffic_reconstruction',
            'traffic-prediction': 'traffic_prediction',
            'signal-optimization': 'signal_optimization',
            'path-guidance': 'path_guidance',
            'speed-control': 'vehicle_speed_control',
            'cooperative-control': 'three_level_control',
        }

        algo_dir = module_map.get(module)
        if not algo_dir:
            return None

        readme_path = os.path.join(self.algorithms_dir, algo_dir, 'README.md')
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"读取算法说明失败: {e}")

        return None


# 全局知识库实例
kb_service = KnowledgeBaseService()


# ========== API路由 ==========
@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """流式对话接口（支持工具调用、对话管理、引用追踪）"""

    # 记录请求开始时间
    start_time = time.time()
    request_success = True
    error_message = None

    # 生成或使用会话ID：只接受归属当前账号的标识，其它值一律忽略并按账号重新生成，
    # 否则任何登录用户都能把消息写进别人的会话文件，形成"写得进但读不出"的错配。
    requested_session = str(request.session_id or "").strip()
    owned_prefix = f"user_{current_user.id}_"
    session_id = (
        requested_session
        if requested_session.startswith(owned_prefix)
        else f"{owned_prefix}{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    try:
        # 记录用户消息到对话管理器
        if conversation_manager:
            try:
                conversation_manager.add_message(
                    session_id=session_id,
                    role="user",
                    content=request.message,
                    metadata={"module": request.context, "user_id": current_user.id}
                )
            except Exception as e:
                logger.warning(f"记录对话失败: {e}")

        # 记录用户查询历史
        if history_manager and request.message:
            try:
                history_manager.add_query(
                    user_id=current_user.id,
                    query=request.message,
                    module=request.context
                )
            except Exception as e:
                logger.warning(f"记录用户历史失败: {e}")

        # 纯对话模式默认不读取历史检索/RAG，只保留当前页面上下文。
        user_history = []
        if ai_service.enable_rag and history_manager:
            try:
                user_history = history_manager.get_recent_queries(
                    user_id=current_user.id,
                    limit=5,
                    days=30
                )
            except Exception as e:
                logger.warning(f"获取用户历史失败: {e}")

        enhanced_context = request.context or ""
        if ai_service.enable_rag and request.message:
            # 构建检索上下文
            search_context = {
                'module': request.context,  # 当前实验模块
                'boost_recent': True,  # 提升最新内容权重
                'user_history': user_history  # 用户历史查询
            }
            docs = kb_service.search_docs(request.message, top_k=2, context=search_context)
            if docs:
                retrieved_docs = docs
                enhanced_context += "\n\n相关教材内容：\n"
                for doc in docs:
                    enhanced_context += f"\n【{doc['file']}】\n{doc['content']}\n"

                    # 记录引用来源
                    if conversation_manager:
                        try:
                            conversation_manager.add_citation(
                                session_id=session_id,
                                source=doc['file'],
                                content=doc['content'],
                                metadata={"section": doc.get('section', ''), "score": doc.get('score', 0)}
                            )
                        except Exception as e:
                            logger.warning(f"记录引用来源失败: {e}")

        # 如果有实验模块上下文，添加算法说明
        if ai_service.enable_rag and request.context:
            algo_info = kb_service.get_algorithm_info(request.context)
            if algo_info:
                enhanced_context += f"\n\n算法模块说明：\n{algo_info[:1000]}\n"

        tools = None
        if ai_service.enable_tools:
            tools_instance = AIAssistantTools(db, current_user)
            tools = tools_instance.get_available_tools()

        # 收集助手响应内容（用于记录到对话管理器）
        assistant_response = []

        async def generate():
            async for chunk in ai_service.chat_stream(
                request.message,
                request.model,
                request.history or [],
                enhanced_context,
                tools=tools,
                db=db,
                current_user=current_user
            ):
                # 提取文本内容
                try:
                    chunk_data = json.loads(chunk.replace("data: ", "").strip())
                    if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                        delta = chunk_data["choices"][0].get("delta", {})
                        if "content" in delta:
                            assistant_response.append(delta["content"])
                except:
                    pass

                yield chunk

            # 流式响应结束后，记录助手响应到对话管理器
            if conversation_manager and assistant_response:
                try:
                    full_response = "".join(assistant_response)
                    conversation_manager.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=full_response,
                        metadata={"model": request.model, "module": request.context}
                    )
                except Exception as e:
                    logger.warning(f"记录助手响应失败: {e}")

            # 记录性能指标
            if monitoring_system:
                try:
                    response_time = (time.time() - start_time) * 1000  # 转换为毫秒
                    monitoring_system.performance_monitor.record_request(
                        endpoint="/chat/stream",
                        response_time=response_time,
                        success=request_success,
                        error_message=error_message,
                        user_id=str(current_user.id)
                    )
                except Exception as e:
                    logger.warning(f"记录性能指标失败: {e}")

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    except Exception as e:
        # 记录错误
        request_success = False
        error_message = str(e)

        # 记录性能指标（失败情况）
        if monitoring_system:
            try:
                response_time = (time.time() - start_time) * 1000
                monitoring_system.performance_monitor.record_request(
                    endpoint="/chat/stream",
                    response_time=response_time,
                    success=False,
                    error_message=error_message,
                    user_id=str(current_user.id)
                )
            except:
                pass

        raise


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """非流式对话接口（备用）"""
    # 简化版本，直接返回固定回复
    return {
        "success": True,
        "message": "AI助手功能需要配置API Key，请使用流式接口",
        "model": request.model
    }


@router.get("/config")
async def get_config(current_user: User = Depends(get_current_user)):
    """获取AI配置状态"""
    return {
        "success": True,
        "model_provider": "DeepSeek",
        "default_model": "deepseek",
        "provider_model": ai_service.deepseek_model,
        "deepseek_configured": bool(ai_service.deepseek_key),
        "deepseek_base_url": ai_service.deepseek_base_url,
        "deepseek_thinking": ai_service.deepseek_thinking,
        "deepseek_reasoning_effort": ai_service.deepseek_reasoning_effort,
        "rag_enabled": ai_service.enable_rag,
        "tools_enabled": ai_service.enable_tools,
        "available_models": [
            {
                "id": "deepseek",
                "name": "DeepSeek V4 Pro",
                "available": bool(ai_service.deepseek_key),
                "provider": "DeepSeek",
                "provider_model": ai_service.deepseek_model,
                "thinking": ai_service.deepseek_thinking != "disabled",
                "reasoning_effort": ai_service.deepseek_reasoning_effort
            }
        ]
    }


@router.post("/config")
async def update_config(
    config: AIConfig,
    current_user: User = Depends(get_current_user)
):
    """更新AI配置（仅管理员）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可配置")

    if config.deepseek_api_key:
        ai_service.deepseek_key = config.deepseek_api_key
        os.environ["DEEPSEEK_API_KEY"] = config.deepseek_api_key

    if config.deepseek_base_url:
        ai_service.deepseek_base_url = config.deepseek_base_url.rstrip("/")
        os.environ["DEEPSEEK_API_BASE"] = ai_service.deepseek_base_url

    if config.deepseek_model:
        ai_service.deepseek_model = config.deepseek_model.strip()
        os.environ["DEEPSEEK_MODEL"] = ai_service.deepseek_model

    if config.deepseek_reasoning_effort:
        ai_service.deepseek_reasoning_effort = ai_service._normalize_reasoning_effort(
            config.deepseek_reasoning_effort
        )
        os.environ["DEEPSEEK_REASONING_EFFORT"] = ai_service.deepseek_reasoning_effort

    return {"success": True, "message": "配置已更新"}


@router.get("/knowledge/search")
async def search_knowledge(
    q: str,
    module: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """搜索知识库（支持模块过滤和个性化）"""
    # 获取用户历史查询
    user_history = []
    if history_manager:
        try:
            user_history = history_manager.get_recent_queries(
                user_id=current_user.id,
                limit=5,
                days=30
            )
        except Exception as e:
            logger.warning(f"获取用户历史失败: {e}")

    # 构建检索上下文
    search_context = {
        'module': module,
        'boost_recent': True,
        'user_history': user_history
    }
    results = kb_service.search_docs(q, top_k=5, context=search_context)

    # 记录查询历史
    if history_manager:
        try:
            history_manager.add_query(
                user_id=current_user.id,
                query=q,
                module=module
            )
        except Exception as e:
            logger.warning(f"记录用户历史失败: {e}")

    return {
        "success": True,
        "query": q,
        "module": module,
        "results": results
    }


@router.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "service": "ai-assistant",
        "models": {
            "provider": "DeepSeek",
            "deepseek": bool(ai_service.deepseek_key),
            "default": "deepseek",
            "provider_model": ai_service.deepseek_model,
            "reasoning_effort": ai_service.deepseek_reasoning_effort
        }
    }


# ========== 对话管理API ==========
def _require_owned_session(current_user: User, session_id: str) -> str:
    """校验对话会话归属。

    会话 ID 在写入时统一为 ``user_<用户ID>_<时间戳>``。若不做校验，任何已登录
    用户只要猜到 session_id，就能读取、导出甚至删除他人的对话内容。
    """

    if not str(session_id).startswith(f"user_{current_user.id}_"):
        raise HTTPException(
            status_code=403,
            detail="无权访问该会话，请使用当前账号自己的会话标识",
        )
    return session_id


@router.get("/conversation/{session_id}/history")
async def get_conversation_history(
    session_id: str,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """获取对话历史"""
    _require_owned_session(current_user, session_id)
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="对话管理器未初始化")

    history = conversation_manager.get_history(session_id, limit=limit)

    return {
        "success": True,
        "session_id": session_id,
        "history": history,
        "count": len(history)
    }


@router.get("/conversation/{session_id}/citations")
async def get_conversation_citations(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取对话引用来源"""
    _require_owned_session(current_user, session_id)
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="对话管理器未初始化")

    citations = conversation_manager.get_citations(session_id)
    formatted_citations = conversation_manager.format_citations(session_id)

    return {
        "success": True,
        "session_id": session_id,
        "citations": citations,
        "formatted": formatted_citations
    }


@router.get("/conversation/{session_id}/context")
async def get_conversation_context(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """提取对话上下文信息"""
    _require_owned_session(current_user, session_id)
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="对话管理器未初始化")

    context = conversation_manager.extract_context(session_id)

    return {
        "success": True,
        "session_id": session_id,
        "context": context
    }


@router.get("/conversation/{session_id}/export")
async def export_conversation(
    session_id: str,
    format: str = "json",
    current_user: User = Depends(get_current_user)
):
    """导出对话记录"""
    _require_owned_session(current_user, session_id)
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="对话管理器未初始化")

    if format not in ["json", "markdown", "txt"]:
        raise HTTPException(status_code=400, detail="不支持的导出格式")

    try:
        content = conversation_manager.export_conversation(session_id, format=format)

        # 设置响应头
        media_types = {
            "json": "application/json",
            "markdown": "text/markdown",
            "txt": "text/plain"
        }

        from fastapi.responses import Response
        return Response(
            content=content,
            media_type=media_types[format],
            headers={
                "Content-Disposition": f"attachment; filename=conversation_{session_id}.{format}"
            }
        )
    except Exception as e:
        logger.error(f"导出对话失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/conversation/{session_id}/save")
async def save_conversation(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """保存对话到文件"""
    _require_owned_session(current_user, session_id)
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="对话管理器未初始化")

    try:
        conversation_manager.save_to_file(session_id)
        return {
            "success": True,
            "message": "对话已保存"
        }
    except Exception as e:
        logger.error(f"保存对话失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.delete("/conversation/{session_id}")
async def clear_conversation(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """清除对话会话"""
    _require_owned_session(current_user, session_id)
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="对话管理器未初始化")

    conversation_manager.clear_session(session_id)

    return {
        "success": True,
        "message": "对话已清除"
    }


# ========== 索引管理API ==========

@router.post("/knowledge/index/update")
async def update_knowledge_index(
    sources: Optional[List[str]] = None,
    current_user: User = Depends(get_current_user)
):
    """
    手动触发知识库增量更新

    Args:
        sources: 要更新的知识源列表，如 ["实验文档", "代码库"]。不指定则更新所有源

    Returns:
        更新结果，包括变更文件数、添加的文档块数等
    """
    if not knowledge_manager:
        raise HTTPException(status_code=503, detail="知识库管理器未初始化")

    try:
        result = knowledge_manager.update_index(sources)
        return result
    except Exception as e:
        logger.error(f"更新索引失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.get("/knowledge/index/status")
async def get_index_status(
    current_user: User = Depends(get_current_user)
):
    """
    获取索引状态信息

    Returns:
        索引元数据，包括文件数量、最后更新时间等
    """
    if not index_metadata:
        raise HTTPException(status_code=503, detail="索引元数据管理器未初始化")

    try:
        metadata = index_metadata.metadata

        # 统计信息
        total_files = len(metadata.get("files", {}))
        sources = {}
        for file_path, file_info in metadata.get("files", {}).items():
            source = file_info.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1

        return {
            "total_files": total_files,
            "sources": sources,
            "last_update": metadata.get("last_update"),
            "metadata_file": str(index_metadata.metadata_file)
        }
    except Exception as e:
        logger.error(f"获取索引状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")


@router.get("/knowledge/index/quality")
async def get_index_quality(
    current_user: User = Depends(get_current_user)
):
    """
    获取索引质量评估报告

    Returns:
        质量评估结果，包括文档覆盖率、平均块大小、重复率等指标
    """
    if not knowledge_manager:
        raise HTTPException(status_code=503, detail="知识库管理器未初始化")

    try:
        quality_report = knowledge_manager.evaluate_index_quality()
        return quality_report
    except Exception as e:
        logger.error(f"评估索引质量失败: {e}")
        raise HTTPException(status_code=500, detail=f"评估失败: {str(e)}")


@router.post("/knowledge/index/schedule")
async def start_scheduled_indexing(
    interval_hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """
    启动定期索引更新任务

    Args:
        interval_hours: 更新间隔（小时），默认24小时

    Returns:
        调度器状态
    """
    if not scheduled_indexer:
        raise HTTPException(status_code=503, detail="定期索引器未初始化")

    try:
        scheduled_indexer.start_scheduler(interval_hours)
        return {
            "success": True,
            "message": f"定期更新已启动，间隔 {interval_hours} 小时",
            "interval_hours": interval_hours
        }
    except Exception as e:
        logger.error(f"启动定期更新失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")


@router.delete("/knowledge/index/schedule")
async def stop_scheduled_indexing(
    current_user: User = Depends(get_current_user)
):
    """
    停止定期索引更新任务

    Returns:
        停止结果
    """
    if not scheduled_indexer:
        raise HTTPException(status_code=503, detail="定期索引器未初始化")

    try:
        scheduled_indexer.stop_scheduler()
        return {
            "success": True,
            "message": "定期更新已停止"
        }
    except Exception as e:
        logger.error(f"停止定期更新失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")


# ========== 监控告警API ==========

@router.get("/monitoring/health")
async def get_system_health(
    current_user: User = Depends(get_current_user)
):
    """
    获取系统健康状态

    Returns:
        系统健康评分、性能指标、资源使用、活跃告警等
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        health = monitoring_system.get_system_health()
        return health
    except Exception as e:
        logger.error(f"获取系统健康状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/monitoring/performance")
async def get_performance_stats(
    minutes: int = 60,
    current_user: User = Depends(get_current_user)
):
    """
    获取性能统计信息

    Args:
        minutes: 统计时间窗口（分钟），默认60分钟

    Returns:
        性能指标，包括请求数、成功率、平均响应时间、错误率等
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        stats = monitoring_system.performance_monitor.get_statistics(minutes=minutes)
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"获取性能统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/monitoring/performance/errors")
async def get_recent_errors(
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """
    获取最近的错误记录

    Args:
        limit: 返回的错误数量，默认10条

    Returns:
        最近的错误列表
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        errors = monitoring_system.performance_monitor.get_recent_errors(limit=limit)
        return {
            "success": True,
            "errors": errors,
            "count": len(errors)
        }
    except Exception as e:
        logger.error(f"获取错误记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/monitoring/resources")
async def get_resource_stats(
    minutes: int = 60,
    current_user: User = Depends(get_current_user)
):
    """
    获取资源使用统计

    Args:
        minutes: 统计时间窗口（分钟），默认60分钟

    Returns:
        资源使用指标，包括CPU、内存、磁盘使用情况
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        current = monitoring_system.resource_monitor.get_current_status()
        stats = monitoring_system.resource_monitor.get_statistics(minutes=minutes)

        return {
            "success": True,
            "current": current,
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"获取资源统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/monitoring/knowledge-base")
async def get_kb_monitoring_stats(
    current_user: User = Depends(get_current_user)
):
    """
    获取知识库监控统计

    Returns:
        知识库相关指标，包括索引质量、检索性能等
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        current = monitoring_system.kb_monitor.get_current_status()
        stats = monitoring_system.kb_monitor.get_statistics()

        return {
            "success": True,
            "current": current,
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"获取知识库监控统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/monitoring/alerts")
async def get_alerts(
    active_only: bool = False,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    获取告警列表

    Args:
        active_only: 是否只返回活跃告警，默认False
        limit: 返回的告警数量，默认100条

    Returns:
        告警列表
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        if active_only:
            alerts = monitoring_system.alert_manager.get_active_alerts()
        else:
            alerts = monitoring_system.alert_manager.get_all_alerts(limit=limit)

        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts)
        }
    except Exception as e:
        logger.error(f"获取告警列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/monitoring/alerts/{timestamp}/resolve")
async def resolve_alert(
    timestamp: str,
    current_user: User = Depends(get_current_user)
):
    """
    解决告警

    Args:
        timestamp: 告警时间戳

    Returns:
        操作结果
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        monitoring_system.alert_manager.resolve_alert(timestamp)
        return {
            "success": True,
            "message": "告警已解决"
        }
    except Exception as e:
        logger.error(f"解决告警失败: {e}")
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")


@router.get("/monitoring/thresholds")
async def get_alert_thresholds(
    current_user: User = Depends(get_current_user)
):
    """
    获取告警阈值配置

    Returns:
        当前的告警阈值配置
    """
    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        thresholds = monitoring_system.alert_manager.thresholds
        return {
            "success": True,
            "thresholds": thresholds
        }
    except Exception as e:
        logger.error(f"获取告警阈值失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.put("/monitoring/thresholds/{category}")
async def update_alert_thresholds(
    category: str,
    thresholds: Dict[str, float],
    current_user: User = Depends(get_current_user)
):
    """
    更新告警阈值配置（仅管理员）

    Args:
        category: 告警类别（performance/resource/knowledge_base）
        thresholds: 新的阈值配置

    Returns:
        操作结果
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可配置")

    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    if category not in ["performance", "resource", "knowledge_base"]:
        raise HTTPException(status_code=400, detail="无效的告警类别")

    try:
        monitoring_system.alert_manager.update_thresholds(category, thresholds)
        return {
            "success": True,
            "message": f"{category} 阈值已更新",
            "thresholds": monitoring_system.alert_manager.thresholds[category]
        }
    except Exception as e:
        logger.error(f"更新告警阈值失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.post("/monitoring/start")
async def start_monitoring(
    interval_seconds: int = 60,
    current_user: User = Depends(get_current_user)
):
    """
    启动自动监控（仅管理员）

    Args:
        interval_seconds: 监控间隔（秒），默认60秒

    Returns:
        操作结果
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        monitoring_system.start_monitoring(interval_seconds=interval_seconds)
        return {
            "success": True,
            "message": f"监控已启动，间隔 {interval_seconds} 秒"
        }
    except Exception as e:
        logger.error(f"启动监控失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")


@router.post("/monitoring/stop")
async def stop_monitoring(
    current_user: User = Depends(get_current_user)
):
    """
    停止自动监控（仅管理员）

    Returns:
        操作结果
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    if not monitoring_system:
        raise HTTPException(status_code=503, detail="监控系统未初始化")

    try:
        monitoring_system.stop_monitoring()
        return {
            "success": True,
            "message": "监控已停止"
        }
    except Exception as e:
        logger.error(f"停止监控失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")
