"""
对话管理器测试
"""
import pytest
import sys
from pathlib import Path

# 添加knowledge_base到路径
kb_path = Path(__file__).parent.parent / "knowledge_base"
sys.path.insert(0, str(kb_path))

from conversation_manager import ConversationManager


def test_add_message():
    """测试添加消息"""
    manager = ConversationManager()
    session_id = "test_session_1"

    manager.add_message(
        session_id=session_id,
        role="user",
        content="什么是DQN算法？",
        metadata={"module": "signal_optimization"}
    )

    history = manager.get_history(session_id)
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "什么是DQN算法？"
    assert history[0]["metadata"]["module"] == "signal_optimization"


def test_get_history_with_limit():
    """测试获取历史记录（带限制）"""
    manager = ConversationManager()
    session_id = "test_session_2"

    # 添加多条消息
    for i in range(15):
        manager.add_message(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"消息 {i}"
        )

    # 获取最近5条
    history = manager.get_history(session_id, limit=5)
    assert len(history) == 5
    assert history[-1]["content"] == "消息 14"


def test_history_compression():
    """测试历史压缩"""
    manager = ConversationManager(max_history=20)
    session_id = "test_session_3"

    # 添加超过最大限制的消息
    for i in range(25):
        manager.add_message(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"消息 {i}"
        )

    history = manager.get_history(session_id)
    # 应该被压缩到最大限制以内
    assert len(history) <= 20
    # 应该包含摘要消息
    has_summary = any(msg.get("metadata", {}).get("type") == "summary" for msg in history)
    assert has_summary


def test_add_citation():
    """测试添加引用来源"""
    manager = ConversationManager()
    session_id = "test_session_4"

    manager.add_citation(
        session_id=session_id,
        source="docs/教材/第3章_DQN算法.md",
        content="DQN是一种深度强化学习算法...",
        metadata={"section": "3.1 算法原理"}
    )

    citations = manager.get_citations(session_id)
    assert len(citations) == 1
    assert citations[0]["source"] == "docs/教材/第3章_DQN算法.md"
    assert "DQN" in citations[0]["content"]


def test_format_citations():
    """测试格式化引用来源"""
    manager = ConversationManager()
    session_id = "test_session_5"

    manager.add_citation(
        session_id=session_id,
        source="docs/教材/第3章_DQN算法.md",
        content="DQN算法内容",
        metadata={"section": "3.1 算法原理"}
    )

    manager.add_citation(
        session_id=session_id,
        source="backend/algorithms/signal_optimization/README.md",
        content="信号优化说明"
    )

    formatted = manager.format_citations(session_id)
    assert "📚 参考来源" in formatted
    assert "第3章_DQN算法.md" in formatted
    assert "README.md" in formatted


def test_extract_context():
    """测试提取上下文信息"""
    manager = ConversationManager()
    session_id = "test_session_6"

    # 添加包含实验信息的对话
    manager.add_message(
        session_id=session_id,
        role="user",
        content="我想查看实验123的结果",
        metadata={"module": "signal_optimization"}
    )

    manager.add_message(
        session_id=session_id,
        role="user",
        content="DQN算法的训练参数怎么设置？"
    )

    context = manager.extract_context(session_id)
    assert context["current_module"] == "signal_optimization"
    assert 123 in context["experiment_ids"]
    assert "DQN" in context["topics"]


def test_export_conversation_json():
    """测试导出对话（JSON格式）"""
    manager = ConversationManager()
    session_id = "test_session_7"

    manager.add_message(session_id, "user", "你好")
    manager.add_message(session_id, "assistant", "你好！有什么可以帮助你的？")

    exported = manager.export_conversation(session_id, format="json")
    assert "session_id" in exported
    assert "messages" in exported
    assert "test_session_7" in exported


def test_export_conversation_markdown():
    """测试导出对话（Markdown格式）"""
    manager = ConversationManager()
    session_id = "test_session_8"

    manager.add_message(session_id, "user", "什么是LSTM？")
    manager.add_message(session_id, "assistant", "LSTM是长短期记忆网络...")

    exported = manager.export_conversation(session_id, format="markdown")
    assert "# 对话记录" in exported
    assert "👤 用户" in exported
    assert "🤖 助手" in exported
    assert "LSTM" in exported


def test_export_conversation_txt():
    """测试导出对话（TXT格式）"""
    manager = ConversationManager()
    session_id = "test_session_9"

    manager.add_message(session_id, "user", "测试消息")

    exported = manager.export_conversation(session_id, format="txt")
    assert "对话记录" in exported
    assert "[USER]" in exported
    assert "测试消息" in exported


def test_save_and_load():
    """测试保存和加载对话"""
    manager = ConversationManager()
    session_id = "test_session_10"

    # 添加消息
    manager.add_message(session_id, "user", "保存测试")
    manager.add_message(session_id, "assistant", "收到")

    # 保存到文件
    manager.save_to_file(session_id)

    # 清除缓存
    manager.clear_session(session_id)

    # 重新加载
    history = manager.get_history(session_id)
    assert len(history) == 2
    assert history[0]["content"] == "保存测试"


def test_clear_session():
    """测试清除会话"""
    manager = ConversationManager()
    session_id = "test_session_11"

    manager.add_message(session_id, "user", "测试")
    assert len(manager.get_history(session_id)) == 1

    manager.clear_session(session_id)
    assert len(manager.get_history(session_id)) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
