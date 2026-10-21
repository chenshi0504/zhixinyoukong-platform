"""
A/B测试框架
用于对比不同检索策略的效果
"""

import random
import json
import os
from typing import Dict, List, Optional, Literal
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from .vector_store import HybridRetriever, ChromaVectorStore


class ABTestConfig:
    """A/B测试配置"""

    def __init__(self, name: str, description: str, config: Dict):
        """
        初始化测试配置

        Args:
            name: 配置名称（如 "baseline", "optimized"）
            description: 配置描述
            config: 配置参数字典
        """
        self.name = name
        self.description = description
        self.config = config


class ABTestManager:
    """A/B测试管理器"""

    def __init__(self, data_dir: str = "backend/data/ab_testing"):
        """
        初始化A/B测试管理器

        Args:
            data_dir: 测试数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # 测试配置
        self.configs: Dict[str, ABTestConfig] = {}

        # 用户分组（用户ID -> 配置名称）
        self.user_groups: Dict[int, str] = {}

        # 测试结果记录
        self.results: List[Dict] = []

        # 加载已有配置和分组
        self._load_state()

    def register_config(self, name: str, description: str, config: Dict):
        """
        注册测试配置

        Args:
            name: 配置名称
            description: 配置描述
            config: 配置参数
        """
        self.configs[name] = ABTestConfig(name, description, config)
        self._save_configs()

    def assign_user_to_group(self, user_id: int, group: Optional[str] = None) -> str:
        """
        分配用户到测试组

        Args:
            user_id: 用户ID
            group: 指定组名（可选，不指定则随机分配）

        Returns:
            分配的组名
        """
        if user_id in self.user_groups:
            return self.user_groups[user_id]

        if group is None:
            # 随机分配到某个配置组
            available_groups = list(self.configs.keys())
            if not available_groups:
                raise ValueError("没有可用的测试配置")
            group = random.choice(available_groups)

        self.user_groups[user_id] = group
        self._save_user_groups()

        return group

    def get_user_config(self, user_id: int) -> Optional[ABTestConfig]:
        """
        获取用户的测试配置

        Args:
            user_id: 用户ID

        Returns:
            用户的测试配置，如果未分配则返回None
        """
        group = self.user_groups.get(user_id)
        if group is None:
            return None

        return self.configs.get(group)

    def record_query(
        self,
        user_id: int,
        query: str,
        results: List[Dict],
        response_time: float,
        user_feedback: Optional[Dict] = None
    ):
        """
        记录查询结果

        Args:
            user_id: 用户ID
            query: 查询文本
            results: 检索结果
            response_time: 响应时间（毫秒）
            user_feedback: 用户反馈（可选）
        """
        group = self.user_groups.get(user_id)
        if group is None:
            return

        record = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'group': group,
            'query': query,
            'num_results': len(results),
            'response_time': response_time,
            'user_feedback': user_feedback
        }

        self.results.append(record)

        # 定期保存结果
        if len(self.results) % 10 == 0:
            self._save_results()

    def record_user_feedback(
        self,
        user_id: int,
        query: str,
        feedback_type: Literal['click', 'like', 'dislike', 'report'],
        result_rank: Optional[int] = None
    ):
        """
        记录用户反馈

        Args:
            user_id: 用户ID
            query: 查询文本
            feedback_type: 反馈类型
            result_rank: 点击的结果排名（可选）
        """
        feedback = {
            'type': feedback_type,
            'result_rank': result_rank,
            'timestamp': datetime.now().isoformat()
        }

        # 查找最近的查询记录并更新
        for record in reversed(self.results):
            if record['user_id'] == user_id and record['query'] == query:
                if record.get('user_feedback') is None:
                    record['user_feedback'] = []
                record['user_feedback'].append(feedback)
                self._save_results()
                break

    def get_statistics(self) -> Dict:
        """
        获取A/B测试统计数据

        Returns:
            统计数据字典
        """
        if not self.results:
            return {
                'total_queries': 0,
                'groups': {}
            }

        # 按组统计
        group_stats = defaultdict(lambda: {
            'query_count': 0,
            'total_response_time': 0,
            'click_count': 0,
            'like_count': 0,
            'dislike_count': 0,
            'first_click_ranks': []
        })

        for record in self.results:
            group = record['group']
            stats = group_stats[group]

            stats['query_count'] += 1
            stats['total_response_time'] += record['response_time']

            # 统计用户反馈
            feedback_list = record.get('user_feedback', [])
            if feedback_list:
                for feedback in feedback_list:
                    if feedback['type'] == 'click':
                        stats['click_count'] += 1
                        if feedback.get('result_rank'):
                            stats['first_click_ranks'].append(feedback['result_rank'])
                    elif feedback['type'] == 'like':
                        stats['like_count'] += 1
                    elif feedback['type'] == 'dislike':
                        stats['dislike_count'] += 1

        # 计算平均值和比率
        result = {
            'total_queries': len(self.results),
            'groups': {}
        }

        for group, stats in group_stats.items():
            count = stats['query_count']
            result['groups'][group] = {
                'query_count': count,
                'avg_response_time': stats['total_response_time'] / count if count > 0 else 0,
                'click_rate': stats['click_count'] / count if count > 0 else 0,
                'like_rate': stats['like_count'] / count if count > 0 else 0,
                'dislike_rate': stats['dislike_count'] / count if count > 0 else 0,
                'avg_first_click_rank': (
                    sum(stats['first_click_ranks']) / len(stats['first_click_ranks'])
                    if stats['first_click_ranks'] else 0
                )
            }

        return result

    def generate_report(self) -> str:
        """
        生成A/B测试报告

        Returns:
            Markdown格式的报告
        """
        stats = self.get_statistics()

        report = f"""# A/B测试报告

**生成时间**: {datetime.now().isoformat()}
**总查询数**: {stats['total_queries']}

---

## 测试配置

"""

        for name, config in self.configs.items():
            report += f"""
### {name}

**描述**: {config.description}

**配置参数**:
```json
{json.dumps(config.config, ensure_ascii=False, indent=2)}
```

"""

        report += "\n---\n\n## 测试结果\n\n"

        if not stats['groups']:
            report += "暂无测试数据\n"
            return report

        # 对比表格
        report += "| 指标 | " + " | ".join(stats['groups'].keys()) + " |\n"
        report += "|------|" + "|".join(["------"] * len(stats['groups'])) + "|\n"

        metrics = [
            ('查询数', 'query_count', ''),
            ('平均响应时间', 'avg_response_time', 'ms'),
            ('点击率', 'click_rate', '%'),
            ('点赞率', 'like_rate', '%'),
            ('点踩率', 'dislike_rate', '%'),
            ('平均首次点击排名', 'avg_first_click_rank', '')
        ]

        for metric_name, metric_key, unit in metrics:
            row = f"| {metric_name} |"
            for group in stats['groups'].keys():
                value = stats['groups'][group][metric_key]
                if unit == '%':
                    row += f" {value:.2%} |"
                elif unit == 'ms':
                    row += f" {value:.0f}{unit} |"
                else:
                    row += f" {value:.2f}{unit} |"
            report += row + "\n"

        report += "\n---\n\n## 结论\n\n"

        # 自动生成结论
        if len(stats['groups']) >= 2:
            groups = list(stats['groups'].items())
            best_click_rate = max(groups, key=lambda x: x[1]['click_rate'])
            best_response_time = min(groups, key=lambda x: x[1]['avg_response_time'])

            report += f"- **点击率最高**: {best_click_rate[0]} ({best_click_rate[1]['click_rate']:.2%})\n"
            report += f"- **响应时间最快**: {best_response_time[0]} ({best_response_time[1]['avg_response_time']:.0f}ms)\n"

            # 综合评分（点击率60% + 响应时间20% + 点赞率20%）
            scores = {}
            for group, data in groups:
                score = (
                    data['click_rate'] * 0.6 +
                    (1 - min(data['avg_response_time'] / 1000, 1)) * 0.2 +
                    data['like_rate'] * 0.2
                )
                scores[group] = score

            best_overall = max(scores.items(), key=lambda x: x[1])
            report += f"\n**综合评分最高**: {best_overall[0]} (得分: {best_overall[1]:.3f})\n"

        report += "\n---\n\n*报告由A/B测试框架自动生成*\n"

        return report

    def _load_state(self):
        """加载测试状态"""
        self._load_configs()
        self._load_user_groups()
        self._load_results()

    def _load_configs(self):
        """加载测试配置"""
        config_file = os.path.join(self.data_dir, 'configs.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for name, item in data.items():
                        self.configs[name] = ABTestConfig(
                            name,
                            item['description'],
                            item['config']
                        )
            except Exception as e:
                print(f"加载配置失败: {e}")

    def _save_configs(self):
        """保存测试配置"""
        config_file = os.path.join(self.data_dir, 'configs.json')
        data = {
            name: {
                'description': config.description,
                'config': config.config
            }
            for name, config in self.configs.items()
        }

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_user_groups(self):
        """加载用户分组"""
        groups_file = os.path.join(self.data_dir, 'user_groups.json')
        if os.path.exists(groups_file):
            try:
                with open(groups_file, 'r', encoding='utf-8') as f:
                    # 将字符串键转换为整数
                    data = json.load(f)
                    self.user_groups = {int(k): v for k, v in data.items()}
            except Exception as e:
                print(f"加载用户分组失败: {e}")

    def _save_user_groups(self):
        """保存用户分组"""
        groups_file = os.path.join(self.data_dir, 'user_groups.json')
        with open(groups_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_groups, f, ensure_ascii=False, indent=2)

    def _load_results(self):
        """加载测试结果"""
        results_file = os.path.join(self.data_dir, 'results.jsonl')
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self.results.append(json.loads(line))
            except Exception as e:
                print(f"加载测试结果失败: {e}")

    def _save_results(self):
        """保存测试结果"""
        results_file = os.path.join(self.data_dir, 'results.jsonl')
        with open(results_file, 'w', encoding='utf-8') as f:
            for record in self.results:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')


# 全局实例
_ab_test_manager = None


def get_ab_test_manager() -> ABTestManager:
    """获取A/B测试管理器单例"""
    global _ab_test_manager
    if _ab_test_manager is None:
        _ab_test_manager = ABTestManager()
    return _ab_test_manager


def setup_default_ab_test():
    """设置默认的A/B测试配置"""
    manager = get_ab_test_manager()

    # A组：基线配置（纯向量检索）
    manager.register_config(
        name='baseline',
        description='基线配置：纯向量检索，无重排序',
        config={
            'use_hybrid': False,
            'use_rerank': False,
            'vector_weight': 1.0,
            'keyword_weight': 0.0
        }
    )

    # B组：优化配置（混合检索 + 智能重排序）
    manager.register_config(
        name='optimized',
        description='优化配置：混合检索 + 智能重排序 + 上下文感知',
        config={
            'use_hybrid': True,
            'use_rerank': True,
            'vector_weight': 0.7,
            'keyword_weight': 0.3,
            'rerank_weights': {
                'semantic': 0.4,
                'keyword': 0.2,
                'recency': 0.15,
                'user_preference': 0.15,
                'quality': 0.1
            }
        }
    )

    return manager
