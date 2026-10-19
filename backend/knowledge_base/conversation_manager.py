"""
对话管理器
负责对话历史管理、摘要生成、引用追踪等功能
"""
import json
import logging
import re
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 会话ID会被拼进文件名（<session_id>.json）与下载文件名，必须先做白名单校验，
# 否则 Windows 下 %5C 解码出的反斜杠可构成目录越界。
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


class ConversationManager:
    """对话管理器"""

    def __init__(
        self,
        max_history: int = 20,
        summary_threshold: int = 15,
        storage_dir: str = "backend/data/conversations"
    ):
        """
        初始化对话管理器

        Args:
            max_history: 最大保留对话轮数
            summary_threshold: 触发摘要的对话轮数阈值
            storage_dir: 对话存储目录
        """
        self.max_history = max_history
        self.summary_threshold = summary_threshold
        self.storage_dir = Path(storage_dir)
        if not self.storage_dir.is_absolute():
            # 相对路径会随进程工作目录变化，历史上因此出现过
            # backend/data/conversations 与 backend/backend/data/conversations 两份目录。
            self.storage_dir = Path(__file__).resolve().parents[2] / self.storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存：会话ID -> 对话历史
        self._cache: Dict[str, List[Dict]] = {}
        # 引用来源缓存：会话ID -> 引用列表
        self._citations: Dict[str, List[Dict]] = {}

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        """把会话ID规范化为安全的文件名片段，防止路径拼接越界。"""

        value = str(session_id or "").strip()
        if ".." in value or not _SESSION_ID_PATTERN.fullmatch(value):
            raise ValueError(f"非法的会话ID: {session_id!r}")
        return value

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
        citations: Optional[List[Dict]] = None
    ):
        """
        添加消息到对话历史

        Args:
            session_id: 会话ID
            role: 角色 (user/assistant/system)
            content: 消息内容
            metadata: 元数据（实验ID、模块等）
            citations: 引用来源列表
        """
        if session_id not in self._cache:
            self._cache[session_id] = []
            self._citations[session_id] = []

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        self._cache[session_id].append(message)

        # 记录引用来源
        if citations:
            self._citations[session_id].extend(citations)

        # 检查是否需要压缩历史
        if len(self._cache[session_id]) > self.max_history:
            self._compress_history(session_id)

    def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
        include_system: bool = True
    ) -> List[Dict]:
        """
        获取对话历史

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制
            include_system: 是否包含系统消息

        Returns:
            对话历史列表
        """
        if session_id not in self._cache:
            # 尝试从文件加载
            self._load_from_file(session_id)

        history = self._cache.get(session_id, [])

        if not include_system:
            history = [msg for msg in history if msg["role"] != "system"]

        if limit:
            return history[-limit:]

        return history

    def get_citations(self, session_id: str) -> List[Dict]:
        """
        获取对话中的引用来源

        Args:
            session_id: 会话ID

        Returns:
            引用来源列表
        """
        return self._citations.get(session_id, [])

    def _compress_history(self, session_id: str):
        """
        压缩对话历史（当超过最大轮数时）

        策略：
        1. 保留最近的对话（最后10轮）
        2. 对前面的对话生成摘要
        3. 将摘要作为系统消息插入
        """
        history = self._cache[session_id]

        if len(history) <= self.max_history:
            return

        # 分离需要摘要的部分和保留的部分
        to_summarize = history[:-10]
        to_keep = history[-10:]

        # 生成摘要
        summary = self._generate_summary(to_summarize)

        # 构建新的历史：摘要 + 最近对话
        summary_message = {
            "role": "system",
            "content": f"之前对话摘要：\n{summary}",
            "timestamp": datetime.now().isoformat(),
            "metadata": {"type": "summary"}
        }

        self._cache[session_id] = [summary_message] + to_keep

        logger.info(f"会话 {session_id} 历史已压缩：{len(history)} -> {len(self._cache[session_id])} 条消息")

    def _generate_summary(self, messages: List[Dict]) -> str:
        """
        生成对话摘要（简化版）

        Args:
            messages: 需要摘要的消息列表

        Returns:
            摘要文本
        """
        # 简化实现：提取关键信息
        summary_parts = []

        # 提取用户问题
        user_queries = [msg["content"] for msg in messages if msg["role"] == "user"]
        if user_queries:
            summary_parts.append(f"用户询问了 {len(user_queries)} 个问题，包括：")
            # 只列出前3个问题
            for i, query in enumerate(user_queries[:3], 1):
                # 截断过长的问题
                short_query = query[:50] + "..." if len(query) > 50 else query
                summary_parts.append(f"{i}. {short_query}")

        # 提取实验模块信息
        modules = set()
        for msg in messages:
            module = msg.get("metadata", {}).get("module")
            if module:
                modules.add(module)

        if modules:
            summary_parts.append(f"\n涉及实验模块：{', '.join(modules)}")

        return "\n".join(summary_parts) if summary_parts else "用户进行了多轮对话交互。"

    async def generate_llm_summary(
        self,
        messages: List[Dict],
        llm_client: Any
    ) -> str:
        """
        使用LLM生成对话摘要（高级版）

        Args:
            messages: 需要摘要的消息列表
            llm_client: LLM客户端实例

        Returns:
            摘要文本
        """
        # 构建摘要提示词
        conversation_text = "\n\n".join([
            f"{msg['role']}: {msg['content'][:200]}"
            for msg in messages
        ])

        summary_prompt = f"""请总结以下对话的核心内容，包括：
1. 用户主要询问了什么问题
2. 涉及哪些实验模块或算法
3. 关键的讨论点和结论

对话内容：
{conversation_text}

请用3-5句话简洁总结："""

        try:
            # 调用LLM生成摘要（具体实现取决于LLM客户端）
            summary = await llm_client.generate(summary_prompt, max_tokens=200)
            return summary
        except Exception as e:
            logger.error(f"LLM摘要生成失败: {e}")
            # 降级到简单摘要
            return self._generate_summary(messages)

    def extract_context(self, session_id: str) -> Dict[str, Any]:
        """
        从对话历史中提取上下文信息

        Args:
            session_id: 会话ID

        Returns:
            上下文字典，包含：
            - current_module: 当前实验模块
            - experiment_ids: 提到的实验ID列表
            - parameters: 提到的参数配置
            - topics: 讨论的主题
        """
        history = self.get_history(session_id)

        context = {
            "current_module": None,
            "experiment_ids": [],
            "parameters": {},
            "topics": set()
        }

        # 从最近的消息中提取模块信息
        for msg in reversed(history):
            module = msg.get("metadata", {}).get("module")
            if module:
                context["current_module"] = module
                break

        # 提取实验ID（简单的正则匹配）
        import re
        for msg in history:
            if msg["role"] == "user":
                # 匹配 "实验123" 或 "experiment_123" 等模式
                exp_ids = re.findall(r'实验[_\s]?(\d+)|experiment[_\s]?(\d+)', msg["content"], re.IGNORECASE)
                for match in exp_ids:
                    exp_id = match[0] or match[1]
                    if exp_id:
                        context["experiment_ids"].append(int(exp_id))

        # 提取主题关键词
        keywords = ["DQN", "PPO", "LSTM", "贝叶斯", "信号优化", "路径诱导", "车速控制", "CARLA", "SUMO"]
        for msg in history:
            content = msg["content"]
            for keyword in keywords:
                if keyword in content:
                    context["topics"].add(keyword)

        context["topics"] = list(context["topics"])

        return context

    def add_citation(
        self,
        session_id: str,
        source: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """
        添加引用来源

        Args:
            session_id: 会话ID
            source: 来源标识（文件路径、文档名等）
            content: 引用内容片段
            metadata: 额外元数据
        """
        if session_id not in self._citations:
            self._citations[session_id] = []

        citation = {
            "source": source,
            "content": content[:200],  # 只保留前200字符
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        self._citations[session_id].append(citation)

    def format_citations(self, session_id: str) -> str:
        """
        格式化引用来源为可读文本

        Args:
            session_id: 会话ID

        Returns:
            格式化的引用文本
        """
        citations = self.get_citations(session_id)

        if not citations:
            return ""

        # 去重（基于source）
        unique_sources = {}
        for citation in citations:
            source = citation["source"]
            if source not in unique_sources:
                unique_sources[source] = citation

        # 格式化输出
        lines = ["\n\n📚 参考来源："]
        for i, (source, citation) in enumerate(unique_sources.items(), 1):
            # 提取文件名
            file_name = Path(source).name if "/" in source or "\\" in source else source
            lines.append(f"{i}. {file_name}")

            # 添加章节信息（如果有）
            section = citation.get("metadata", {}).get("section")
            if section:
                lines.append(f"   章节：{section}")

        return "\n".join(lines)

    def export_conversation(
        self,
        session_id: str,
        format: str = "json"
    ) -> str:
        """
        导出对话记录

        Args:
            session_id: 会话ID
            format: 导出格式 (json/markdown/txt)

        Returns:
            导出的内容字符串
        """
        history = self.get_history(session_id)
        citations = self.get_citations(session_id)

        if format == "json":
            return json.dumps({
                "session_id": session_id,
                "messages": history,
                "citations": citations,
                "exported_at": datetime.now().isoformat()
            }, ensure_ascii=False, indent=2)

        elif format == "markdown":
            lines = [f"# 对话记录 - {session_id}\n"]
            lines.append(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            for msg in history:
                role_name = {"user": "👤 用户", "assistant": "🤖 助手", "system": "⚙️ 系统"}
                role = role_name.get(msg["role"], msg["role"])
                timestamp = msg.get("timestamp", "")
                lines.append(f"\n## {role} ({timestamp})\n")
                lines.append(msg["content"])

            if citations:
                lines.append("\n\n## 📚 引用来源\n")
                for i, citation in enumerate(citations, 1):
                    lines.append(f"{i}. {citation['source']}")

            return "\n".join(lines)

        elif format == "txt":
            lines = [f"对话记录 - {session_id}"]
            lines.append(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("=" * 60)

            for msg in history:
                role = msg["role"].upper()
                lines.append(f"\n[{role}]")
                lines.append(msg["content"])
                lines.append("-" * 60)

            return "\n".join(lines)

        else:
            raise ValueError(f"不支持的导出格式: {format}")

    def save_to_file(self, session_id: str):
        """
        保存对话到文件

        Args:
            session_id: 会话ID
        """
        file_path = self.storage_dir / f"{self._safe_session_id(session_id)}.json"

        try:
            data = {
                "session_id": session_id,
                "messages": self._cache.get(session_id, []),
                "citations": self._citations.get(session_id, []),
                "saved_at": datetime.now().isoformat()
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"对话已保存到文件: {file_path}")
        except Exception as e:
            logger.error(f"保存对话失败: {e}")

    def _load_from_file(self, session_id: str):
        """
        从文件加载对话

        Args:
            session_id: 会话ID
        """
        file_path = self.storage_dir / f"{self._safe_session_id(session_id)}.json"

        if not file_path.exists():
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._cache[session_id] = data.get("messages", [])
            self._citations[session_id] = data.get("citations", [])

            logger.info(f"对话已从文件加载: {file_path}")
        except Exception as e:
            logger.error(f"加载对话失败: {e}")

    def clear_session(self, session_id: str):
        """
        清除会话数据

        Args:
            session_id: 会话ID
        """
        if session_id in self._cache:
            del self._cache[session_id]
        if session_id in self._citations:
            del self._citations[session_id]

        logger.info(f"会话已清除: {session_id}")


# 全局实例
_conversation_manager = None


def get_conversation_manager() -> ConversationManager:
    """获取对话管理器单例"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
