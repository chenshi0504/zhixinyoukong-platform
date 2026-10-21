"""
动态权重配置系统
根据查询类型和场景自动调整检索权重
"""

from typing import Dict, Optional, Literal
import re


class WeightConfig:
    """权重配置"""

    def __init__(
        self,
        name: str,
        description: str,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        rerank_weights: Optional[Dict[str, float]] = None
    ):
        """
        初始化权重配置

        Args:
            name: 配置名称
            description: 配置描述
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            rerank_weights: 重排序权重字典
        """
        self.name = name
        self.description = description
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight

        if rerank_weights is None:
            rerank_weights = {
                'semantic': 0.4,
                'keyword': 0.2,
                'recency': 0.15,
                'user_preference': 0.15,
                'quality': 0.1
            }
        self.rerank_weights = rerank_weights

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'name': self.name,
            'description': self.description,
            'vector_weight': self.vector_weight,
            'keyword_weight': self.keyword_weight,
            'rerank_weights': self.rerank_weights
        }


class DynamicWeightManager:
    """动态权重管理器"""

    def __init__(self):
        """初始化管理器"""
        self.configs: Dict[str, WeightConfig] = {}
        self._setup_default_configs()

    def _setup_default_configs(self):
        """设置默认配置"""

        # 默认配置（平衡型）
        self.register_config(WeightConfig(
            name='default',
            description='默认配置：平衡各项指标',
            vector_weight=0.7,
            keyword_weight=0.3,
            rerank_weights={
                'semantic': 0.4,
                'keyword': 0.2,
                'recency': 0.15,
                'user_preference': 0.15,
                'quality': 0.1
            }
        ))

        # 理论知识查询配置
        self.register_config(WeightConfig(
            name='theory',
            description='理论知识查询：强调语义理解，降低时间权重',
            vector_weight=0.8,
            keyword_weight=0.2,
            rerank_weights={
                'semantic': 0.5,      # 提高语义权重
                'keyword': 0.25,      # 提高关键词权重
                'recency': 0.05,      # 降低时间权重（理论不常变）
                'user_preference': 0.1,
                'quality': 0.1
            }
        ))

        # 操作指导查询配置
        self.register_config(WeightConfig(
            name='operation',
            description='操作指导查询：强调文档质量和时间新鲜度',
            vector_weight=0.6,
            keyword_weight=0.4,
            rerank_weights={
                'semantic': 0.3,
                'keyword': 0.2,
                'recency': 0.25,      # 提高时间权重（最新操作步骤）
                'user_preference': 0.1,
                'quality': 0.15       # 提高质量权重（偏好有代码示例）
            }
        ))

        # 问题诊断查询配置
        self.register_config(WeightConfig(
            name='diagnosis',
            description='问题诊断查询：强调用户偏好和时间新鲜度',
            vector_weight=0.65,
            keyword_weight=0.35,
            rerank_weights={
                'semantic': 0.3,
                'keyword': 0.2,
                'recency': 0.2,       # 提高时间权重（最新错误日志）
                'user_preference': 0.2,  # 提高用户偏好（相似问题）
                'quality': 0.1
            }
        ))

        # 个性化查询配置
        self.register_config(WeightConfig(
            name='personalized',
            description='个性化查询：强调用户偏好和历史记录',
            vector_weight=0.6,
            keyword_weight=0.4,
            rerank_weights={
                'semantic': 0.25,
                'keyword': 0.15,
                'recency': 0.15,
                'user_preference': 0.35,  # 大幅提高用户偏好权重
                'quality': 0.1
            }
        ))

        # 代码搜索配置
        self.register_config(WeightConfig(
            name='code',
            description='代码搜索：强调关键词匹配和文档质量',
            vector_weight=0.5,
            keyword_weight=0.5,   # 提高关键词权重（代码精确匹配重要）
            rerank_weights={
                'semantic': 0.25,
                'keyword': 0.35,      # 提高关键词权重
                'recency': 0.1,
                'user_preference': 0.1,
                'quality': 0.2        # 提高质量权重（代码示例）
            }
        ))

    def register_config(self, config: WeightConfig):
        """注册权重配置"""
        self.configs[config.name] = config

    def get_config(self, name: str) -> Optional[WeightConfig]:
        """获取配置"""
        return self.configs.get(name)

    def detect_query_type(self, query: str) -> str:
        """
        自动检测查询类型

        Args:
            query: 查询文本

        Returns:
            配置名称
        """
        query_lower = query.lower()

        # 理论知识关键词
        theory_keywords = [
            '原理', '算法', '理论', '概念', '定义', '是什么', '什么是',
            '区别', '对比', '优势', '缺点', '特点', 'principle', 'algorithm'
        ]

        # 操作指导关键词
        operation_keywords = [
            '如何', '怎么', '怎样', '配置', '设置', '使用', '操作', '步骤',
            '启动', '运行', '安装', '部署', 'how to', 'how do'
        ]

        # 问题诊断关键词
        diagnosis_keywords = [
            '为什么', '失败', '错误', '问题', '故障', '异常', '超时',
            '不工作', '无法', '不能', '原因', 'why', 'error', 'fail'
        ]

        # 个性化查询关键词
        personalized_keywords = [
            '我的', '我们的', '班级', '最近', '历史', '记录'
        ]

        # 代码搜索关键词
        code_keywords = [
            'def ', 'class ', 'function', 'import', '代码', '函数', '类',
            '.py', '.js', 'api'
        ]

        # 按优先级检测
        if any(kw in query_lower for kw in personalized_keywords):
            return 'personalized'
        elif any(kw in query_lower for kw in diagnosis_keywords):
            return 'diagnosis'
        elif any(kw in query_lower for kw in operation_keywords):
            return 'operation'
        elif any(kw in query_lower for kw in code_keywords):
            return 'code'
        elif any(kw in query_lower for kw in theory_keywords):
            return 'theory'
        else:
            return 'default'

    def get_config_for_query(self, query: str, context: Optional[Dict] = None) -> WeightConfig:
        """
        根据查询自动选择最佳配置

        Args:
            query: 查询文本
            context: 上下文信息（可选）

        Returns:
            权重配置
        """
        # 如果上下文中指定了配置，直接使用
        if context and 'weight_config' in context:
            config_name = context['weight_config']
            config = self.get_config(config_name)
            if config:
                return config

        # 自动检测查询类型
        query_type = self.detect_query_type(query)
        config = self.get_config(query_type)

        return config or self.configs['default']

    def list_configs(self) -> Dict[str, WeightConfig]:
        """列出所有配置"""
        return self.configs

    def optimize_weights(
        self,
        config_name: str,
        performance_data: Dict[str, float]
    ) -> WeightConfig:
        """
        基于性能数据优化权重

        Args:
            config_name: 配置名称
            performance_data: 性能数据，包含各项指标的得分

        Returns:
            优化后的配置
        """
        config = self.get_config(config_name)
        if not config:
            raise ValueError(f"配置不存在: {config_name}")

        # 简单的优化策略：根据性能数据调整权重
        # 这里可以实现更复杂的优化算法（如梯度下降、贝叶斯优化等）

        new_rerank_weights = config.rerank_weights.copy()

        # 如果某项指标表现不佳，降低其权重
        for factor, score in performance_data.items():
            if factor in new_rerank_weights:
                if score < 0.5:  # 表现不佳
                    new_rerank_weights[factor] *= 0.9
                elif score > 0.8:  # 表现优秀
                    new_rerank_weights[factor] *= 1.1

        # 归一化权重
        total = sum(new_rerank_weights.values())
        new_rerank_weights = {k: v / total for k, v in new_rerank_weights.items()}

        # 创建新配置
        optimized_config = WeightConfig(
            name=f"{config_name}_optimized",
            description=f"{config.description} (优化版)",
            vector_weight=config.vector_weight,
            keyword_weight=config.keyword_weight,
            rerank_weights=new_rerank_weights
        )

        return optimized_config


# 全局实例
_weight_manager = None


def get_weight_manager() -> DynamicWeightManager:
    """获取权重管理器单例"""
    global _weight_manager
    if _weight_manager is None:
        _weight_manager = DynamicWeightManager()
    return _weight_manager
