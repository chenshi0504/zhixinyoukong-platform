"""
用户反馈收集系统
收集和分析用户对检索结果和回答的反馈
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
import json
from pathlib import Path


class FeedbackType(Enum):
    """反馈类型"""
    THUMBS_UP = "thumbs_up"  # 点赞
    THUMBS_DOWN = "thumbs_down"  # 点踩
    RATING = "rating"  # 评分（1-5星）
    COMMENT = "comment"  # 文字评论
    REPORT = "report"  # 问题报告


class FeedbackCategory(Enum):
    """反馈分类"""
    ACCURACY = "accuracy"  # 准确性
    RELEVANCE = "relevance"  # 相关性
    COMPLETENESS = "completeness"  # 完整性
    CLARITY = "clarity"  # 清晰度
    TIMELINESS = "timeliness"  # 及时性
    OTHER = "other"  # 其他


@dataclass
class Feedback:
    """用户反馈"""
    feedback_id: str
    user_id: str
    query: str
    response: str
    feedback_type: FeedbackType
    timestamp: datetime = field(default_factory=datetime.now)

    # 可选字段
    rating: Optional[int] = None  # 1-5星评分
    comment: Optional[str] = None  # 文字评论
    category: Optional[FeedbackCategory] = None  # 反馈分类
    retrieved_docs: List[str] = field(default_factory=list)  # 检索到的文档ID
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'feedback_id': self.feedback_id,
            'user_id': self.user_id,
            'query': self.query,
            'response': self.response,
            'feedback_type': self.feedback_type.value,
            'timestamp': self.timestamp.isoformat(),
            'rating': self.rating,
            'comment': self.comment,
            'category': self.category.value if self.category else None,
            'retrieved_docs': self.retrieved_docs,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Feedback':
        """从字典创建"""
        return cls(
            feedback_id=data['feedback_id'],
            user_id=data['user_id'],
            query=data['query'],
            response=data['response'],
            feedback_type=FeedbackType(data['feedback_type']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            rating=data.get('rating'),
            comment=data.get('comment'),
            category=FeedbackCategory(data['category']) if data.get('category') else None,
            retrieved_docs=data.get('retrieved_docs', []),
            metadata=data.get('metadata', {})
        )


class FeedbackCollector:
    """反馈收集器"""

    def __init__(self, storage_path: Optional[Path] = None):
        """
        初始化反馈收集器

        Args:
            storage_path: 反馈数据存储路径
        """
        self.storage_path = storage_path or Path('.RAG/feedback_data.json')
        self.feedbacks: List[Feedback] = []
        self._load_feedbacks()

    def _load_feedbacks(self):
        """加载历史反馈"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.feedbacks = [Feedback.from_dict(item) for item in data]
            except Exception as e:
                print(f"加载反馈数据失败: {e}")
                self.feedbacks = []

    def _save_feedbacks(self):
        """保存反馈数据"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                data = [fb.to_dict() for fb in self.feedbacks]
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存反馈数据失败: {e}")

    def add_feedback(
        self,
        user_id: str,
        query: str,
        response: str,
        feedback_type: FeedbackType,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        category: Optional[FeedbackCategory] = None,
        retrieved_docs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Feedback:
        """
        添加反馈

        Args:
            user_id: 用户ID
            query: 查询内容
            response: 回答内容
            feedback_type: 反馈类型
            rating: 评分（1-5）
            comment: 评论
            category: 反馈分类
            retrieved_docs: 检索到的文档ID列表
            metadata: 额外元数据

        Returns:
            创建的反馈对象
        """
        # 生成反馈ID
        feedback_id = f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.feedbacks)}"

        # 创建反馈对象
        feedback = Feedback(
            feedback_id=feedback_id,
            user_id=user_id,
            query=query,
            response=response,
            feedback_type=feedback_type,
            rating=rating,
            comment=comment,
            category=category,
            retrieved_docs=retrieved_docs or [],
            metadata=metadata or {}
        )

        # 添加到列表
        self.feedbacks.append(feedback)

        # 保存
        self._save_feedbacks()

        return feedback

    def get_feedbacks(
        self,
        user_id: Optional[str] = None,
        feedback_type: Optional[FeedbackType] = None,
        category: Optional[FeedbackCategory] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Feedback]:
        """
        查询反馈

        Args:
            user_id: 用户ID过滤
            feedback_type: 反馈类型过滤
            category: 分类过滤
            min_rating: 最低评分
            max_rating: 最高评分
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            符合条件的反馈列表
        """
        results = self.feedbacks

        # 应用过滤条件
        if user_id:
            results = [fb for fb in results if fb.user_id == user_id]

        if feedback_type:
            results = [fb for fb in results if fb.feedback_type == feedback_type]

        if category:
            results = [fb for fb in results if fb.category == category]

        if min_rating is not None:
            results = [fb for fb in results if fb.rating and fb.rating >= min_rating]

        if max_rating is not None:
            results = [fb for fb in results if fb.rating and fb.rating <= max_rating]

        if start_time:
            results = [fb for fb in results if fb.timestamp >= start_time]

        if end_time:
            results = [fb for fb in results if fb.timestamp <= end_time]

        # 按时间倒序排序
        results.sort(key=lambda x: x.timestamp, reverse=True)

        # 应用数量限制
        if limit:
            results = results[:limit]

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取反馈统计信息

        Returns:
            统计信息字典
        """
        if not self.feedbacks:
            return {
                'total_feedbacks': 0,
                'feedback_type_distribution': {},
                'category_distribution': {},
                'average_rating': 0,
                'positive_rate': 0,
                'negative_rate': 0
            }

        # 统计反馈类型分布
        type_dist = {}
        for fb in self.feedbacks:
            type_name = fb.feedback_type.value
            type_dist[type_name] = type_dist.get(type_name, 0) + 1

        # 统计分类分布
        category_dist = {}
        for fb in self.feedbacks:
            if fb.category:
                cat_name = fb.category.value
                category_dist[cat_name] = category_dist.get(cat_name, 0) + 1

        # 计算平均评分
        ratings = [fb.rating for fb in self.feedbacks if fb.rating]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        # 计算正负反馈率
        positive = sum(1 for fb in self.feedbacks if fb.feedback_type == FeedbackType.THUMBS_UP)
        negative = sum(1 for fb in self.feedbacks if fb.feedback_type == FeedbackType.THUMBS_DOWN)
        total = len(self.feedbacks)

        return {
            'total_feedbacks': total,
            'feedback_type_distribution': type_dist,
            'category_distribution': category_dist,
            'average_rating': avg_rating,
            'positive_rate': positive / total if total > 0 else 0,
            'negative_rate': negative / total if total > 0 else 0,
            'rating_distribution': self._get_rating_distribution()
        }

    def _get_rating_distribution(self) -> Dict[int, int]:
        """获取评分分布"""
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for fb in self.feedbacks:
            if fb.rating and 1 <= fb.rating <= 5:
                dist[fb.rating] += 1
        return dist

    def get_negative_feedbacks(self, limit: int = 10) -> List[Feedback]:
        """
        获取负面反馈

        Args:
            limit: 返回数量限制

        Returns:
            负面反馈列表
        """
        negative = [
            fb for fb in self.feedbacks
            if fb.feedback_type == FeedbackType.THUMBS_DOWN or
               (fb.rating and fb.rating <= 2) or
               fb.feedback_type == FeedbackType.REPORT
        ]

        # 按时间倒序排序
        negative.sort(key=lambda x: x.timestamp, reverse=True)

        return negative[:limit]

    def get_user_feedback_summary(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户反馈摘要

        Args:
            user_id: 用户ID

        Returns:
            用户反馈摘要
        """
        user_feedbacks = self.get_feedbacks(user_id=user_id)

        if not user_feedbacks:
            return {
                'user_id': user_id,
                'total_feedbacks': 0,
                'positive_count': 0,
                'negative_count': 0,
                'average_rating': 0
            }

        positive = sum(1 for fb in user_feedbacks if fb.feedback_type == FeedbackType.THUMBS_UP)
        negative = sum(1 for fb in user_feedbacks if fb.feedback_type == FeedbackType.THUMBS_DOWN)
        ratings = [fb.rating for fb in user_feedbacks if fb.rating]

        return {
            'user_id': user_id,
            'total_feedbacks': len(user_feedbacks),
            'positive_count': positive,
            'negative_count': negative,
            'average_rating': sum(ratings) / len(ratings) if ratings else 0,
            'recent_feedbacks': [fb.to_dict() for fb in user_feedbacks[:5]]
        }


class FeedbackAnalyzer:
    """反馈分析器"""

    def __init__(self, collector: FeedbackCollector):
        """
        初始化分析器

        Args:
            collector: 反馈收集器
        """
        self.collector = collector

    def analyze_query_performance(self, query: str) -> Dict[str, Any]:
        """
        分析特定查询的表现

        Args:
            query: 查询内容

        Returns:
            查询表现分析
        """
        # 查找相关反馈
        related_feedbacks = [
            fb for fb in self.collector.feedbacks
            if fb.query.lower() == query.lower()
        ]

        if not related_feedbacks:
            return {
                'query': query,
                'feedback_count': 0,
                'average_rating': 0,
                'positive_rate': 0
            }

        positive = sum(1 for fb in related_feedbacks if fb.feedback_type == FeedbackType.THUMBS_UP)
        ratings = [fb.rating for fb in related_feedbacks if fb.rating]

        return {
            'query': query,
            'feedback_count': len(related_feedbacks),
            'average_rating': sum(ratings) / len(ratings) if ratings else 0,
            'positive_rate': positive / len(related_feedbacks),
            'recent_comments': [
                fb.comment for fb in related_feedbacks[-5:]
                if fb.comment
            ]
        }

    def identify_problem_areas(self) -> List[Dict[str, Any]]:
        """
        识别问题领域

        Returns:
            问题领域列表
        """
        # 获取负面反馈
        negative_feedbacks = self.collector.get_negative_feedbacks(limit=100)

        # 按分类统计
        category_issues = {}
        for fb in negative_feedbacks:
            if fb.category:
                cat = fb.category.value
                if cat not in category_issues:
                    category_issues[cat] = {
                        'category': cat,
                        'count': 0,
                        'examples': []
                    }
                category_issues[cat]['count'] += 1
                if len(category_issues[cat]['examples']) < 3:
                    category_issues[cat]['examples'].append({
                        'query': fb.query,
                        'comment': fb.comment
                    })

        # 按问题数量排序
        problem_areas = sorted(
            category_issues.values(),
            key=lambda x: x['count'],
            reverse=True
        )

        return problem_areas

    def get_improvement_suggestions(self) -> List[str]:
        """
        获取改进建议

        Returns:
            改进建议列表
        """
        suggestions = []

        stats = self.collector.get_statistics()

        # 基于统计数据生成建议
        if stats['negative_rate'] > 0.2:
            suggestions.append("负面反馈率较高（>20%），需要改进回答质量")

        if stats['average_rating'] < 3.5:
            suggestions.append(f"平均评分较低（{stats['average_rating']:.1f}/5），需要提升用户满意度")

        # 分析问题领域
        problem_areas = self.identify_problem_areas()
        if problem_areas:
            top_issue = problem_areas[0]
            suggestions.append(
                f"'{top_issue['category']}'方面问题最多（{top_issue['count']}次），需要重点改进"
            )

        # 分析负面反馈中的常见评论
        negative = self.collector.get_negative_feedbacks(limit=50)
        comments = [fb.comment for fb in negative if fb.comment]
        if comments:
            suggestions.append(f"收集到{len(comments)}条负面评论，建议详细分析")

        return suggestions


# 全局反馈收集器实例
feedback_collector = FeedbackCollector()
feedback_analyzer = FeedbackAnalyzer(feedback_collector)
