"""
用户查询历史管理器
用于记录和分析用户的查询历史，支持个性化检索
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import json
import os


class UserHistoryManager:
    """用户查询历史管理器"""

    def __init__(self, history_dir: str = "backend/data/user_history"):
        """
        初始化历史管理器

        Args:
            history_dir: 历史记录存储目录
        """
        self.history_dir = history_dir
        os.makedirs(history_dir, exist_ok=True)

        # 内存缓存（用户ID -> 查询列表）
        self._cache: Dict[int, List[Dict]] = defaultdict(list)
        self._cache_time: Dict[int, datetime] = {}
        self._cache_ttl = timedelta(minutes=30)  # 缓存30分钟

    def add_query(self, user_id: int, query: str, module: Optional[str] = None):
        """
        记录用户查询

        Args:
            user_id: 用户ID
            query: 查询内容
            module: 实验模块（可选）
        """
        record = {
            'query': query,
            'module': module,
            'timestamp': datetime.now().isoformat()
        }

        # 更新内存缓存
        self._cache[user_id].append(record)
        self._cache_time[user_id] = datetime.now()

        # 持久化到文件（异步写入，避免阻塞）
        self._save_to_file(user_id, record)

    def get_recent_queries(
        self,
        user_id: int,
        limit: int = 10,
        days: int = 30
    ) -> List[str]:
        """
        获取用户最近的查询记录

        Args:
            user_id: 用户ID
            limit: 返回数量限制
            days: 时间范围（天）

        Returns:
            查询字符串列表
        """
        # 检查缓存
        if user_id in self._cache:
            cache_time = self._cache_time.get(user_id)
            if cache_time and datetime.now() - cache_time < self._cache_ttl:
                # 缓存有效，直接返回
                queries = [r['query'] for r in self._cache[user_id]]
                return queries[-limit:]

        # 从文件加载
        history = self._load_from_file(user_id)

        # 过滤时间范围
        cutoff_time = datetime.now() - timedelta(days=days)
        recent = []

        for record in history:
            try:
                record_time = datetime.fromisoformat(record['timestamp'])
                if record_time >= cutoff_time:
                    recent.append(record['query'])
            except Exception:
                continue

        # 更新缓存
        self._cache[user_id] = history
        self._cache_time[user_id] = datetime.now()

        return recent[-limit:]

    def get_user_interests(self, user_id: int) -> Dict[str, int]:
        """
        分析用户兴趣（基于查询历史中的模块分布）

        Args:
            user_id: 用户ID

        Returns:
            模块 -> 查询次数的字典
        """
        history = self._load_from_file(user_id)

        module_counts = defaultdict(int)
        for record in history:
            module = record.get('module')
            if module:
                module_counts[module] += 1

        return dict(module_counts)

    def _save_to_file(self, user_id: int, record: Dict):
        """保存单条记录到文件"""
        file_path = os.path.join(self.history_dir, f"user_{user_id}.jsonl")

        try:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"保存用户历史失败: {e}")

    def _load_from_file(self, user_id: int) -> List[Dict]:
        """从文件加载用户历史"""
        file_path = os.path.join(self.history_dir, f"user_{user_id}.jsonl")

        if not os.path.exists(file_path):
            return []

        history = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        history.append(json.loads(line))
        except Exception as e:
            print(f"加载用户历史失败: {e}")

        return history

    def clear_cache(self):
        """清空内存缓存"""
        self._cache.clear()
        self._cache_time.clear()


# 全局实例
_history_manager = None


def get_history_manager() -> UserHistoryManager:
    """获取历史管理器单例"""
    global _history_manager
    if _history_manager is None:
        _history_manager = UserHistoryManager()
    return _history_manager
