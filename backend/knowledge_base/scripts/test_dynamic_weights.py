"""
动态权重配置测试脚本
演示不同查询类型如何自动选择最佳权重配置
"""

import sys
import os
from pathlib import Path

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.dynamic_weights import get_weight_manager


def test_query_detection():
    """测试查询类型检测"""
    manager = get_weight_manager()

    test_queries = [
        # 理论知识
        ("DQN算法的原理是什么？", "theory"),
        ("贝叶斯融合算法和卡尔曼滤波的区别", "theory"),
        ("PPO算法的优势", "theory"),

        # 操作指导
        ("如何配置CARLA仿真环境？", "operation"),
        ("数据采集模块怎么使用？", "operation"),
        ("信号优化实验的参数如何设置？", "operation"),

        # 问题诊断
        ("为什么我的实验失败了？", "diagnosis"),
        ("SUMO连接超时怎么办？", "diagnosis"),
        ("训练不收敛的原因", "diagnosis"),

        # 个性化查询
        ("我的实验记录", "personalized"),
        ("班级完成情况", "personalized"),
        ("最近的实验结果", "personalized"),

        # 代码搜索
        ("查找DQN的训练函数", "code"),
        ("api接口定义", "code"),
    ]

    print("="*70)
    print("查询类型自动检测测试")
    print("="*70 + "\n")

    correct = 0
    total = len(test_queries)

    for query, expected_type in test_queries:
        detected_type = manager.detect_query_type(query)
        is_correct = detected_type == expected_type

        status = "✅" if is_correct else "❌"
        print(f"{status} 查询: {query}")
        print(f"   预期类型: {expected_type} | 检测类型: {detected_type}")

        if is_correct:
            correct += 1
        print()

    accuracy = correct / total
    print("="*70)
    print(f"检测准确率: {correct}/{total} = {accuracy:.2%}")
    print("="*70 + "\n")


def show_config_details():
    """显示所有配置的详细信息"""
    manager = get_weight_manager()

    print("="*70)
    print("权重配置详情")
    print("="*70 + "\n")

    for name, config in manager.list_configs().items():
        print(f"【{name}】")
        print(f"描述: {config.description}")
        print(f"混合检索权重: 向量={config.vector_weight:.1f}, 关键词={config.keyword_weight:.1f}")
        print(f"重排序权重:")
        for factor, weight in config.rerank_weights.items():
            print(f"  - {factor}: {weight:.2f}")
        print()


def compare_configs():
    """对比不同配置的权重差异"""
    manager = get_weight_manager()

    print("="*70)
    print("配置对比表")
    print("="*70 + "\n")

    configs = ['default', 'theory', 'operation', 'diagnosis', 'personalized', 'code']
    factors = ['semantic', 'keyword', 'recency', 'user_preference', 'quality']

    # 表头
    print(f"{'因子':<20} | " + " | ".join(f"{c:<12}" for c in configs))
    print("-" * 70)

    # 混合检索权重
    print(f"{'向量权重':<20} | " + " | ".join(
        f"{manager.get_config(c).vector_weight:>12.1f}" for c in configs
    ))
    print(f"{'关键词权重':<20} | " + " | ".join(
        f"{manager.get_config(c).keyword_weight:>12.1f}" for c in configs
    ))
    print("-" * 70)

    # 重排序权重
    for factor in factors:
        row = f"{factor:<20} | "
        for config_name in configs:
            config = manager.get_config(config_name)
            weight = config.rerank_weights.get(factor, 0)
            row += f"{weight:>12.2f} | "
        print(row)

    print("\n")


def test_auto_selection():
    """测试自动配置选择"""
    manager = get_weight_manager()

    print("="*70)
    print("自动配置选择测试")
    print("="*70 + "\n")

    test_queries = [
        "DQN算法的原理是什么？",
        "如何配置CARLA仿真环境？",
        "为什么我的实验失败了？",
        "我的实验记录",
        "查找训练函数的代码",
    ]

    for query in test_queries:
        config = manager.get_config_for_query(query)
        print(f"查询: {query}")
        print(f"  → 选择配置: {config.name}")
        print(f"  → 混合检索: 向量={config.vector_weight:.1f}, 关键词={config.keyword_weight:.1f}")
        print(f"  → 重排序权重: semantic={config.rerank_weights['semantic']:.2f}, "
              f"keyword={config.rerank_weights['keyword']:.2f}, "
              f"recency={config.rerank_weights['recency']:.2f}")
        print()


def generate_weight_report():
    """生成权重配置报告"""
    manager = get_weight_manager()

    report = """# 动态权重配置报告

## 一、配置概览

本系统支持6种预设权重配置，可根据查询类型自动选择最佳配置。

"""

    for name, config in manager.list_configs().items():
        report += f"""
### {name}

**描述**: {config.description}

**混合检索权重**:
- 向量检索: {config.vector_weight:.1f}
- 关键词检索: {config.keyword_weight:.1f}

**重排序权重**:
"""
        for factor, weight in config.rerank_weights.items():
            report += f"- {factor}: {weight:.2f}\n"

    report += """
---

## 二、查询类型检测规则

系统通过关键词匹配自动检测查询类型：

| 查询类型 | 关键词示例 | 配置名称 |
|---------|-----------|---------|
| 理论知识 | 原理、算法、理论、概念、是什么、区别 | theory |
| 操作指导 | 如何、怎么、配置、设置、使用、步骤 | operation |
| 问题诊断 | 为什么、失败、错误、问题、故障、原因 | diagnosis |
| 个性化查询 | 我的、班级、最近、历史、记录 | personalized |
| 代码搜索 | def、class、function、代码、函数、.py | code |
| 默认 | 其他 | default |

---

## 三、配置对比

不同配置的权重分配策略：

| 因子 | default | theory | operation | diagnosis | personalized | code |
|------|---------|--------|-----------|-----------|--------------|------|
"""

    configs = ['default', 'theory', 'operation', 'diagnosis', 'personalized', 'code']
    factors = ['semantic', 'keyword', 'recency', 'user_preference', 'quality']

    for factor in factors:
        row = f"| {factor} |"
        for config_name in configs:
            config = manager.get_config(config_name)
            weight = config.rerank_weights.get(factor, 0)
            row += f" {weight:.2f} |"
        report += row + "\n"

    report += """
---

## 四、使用建议

1. **理论知识查询**: 使用 `theory` 配置，强调语义理解
2. **操作指导查询**: 使用 `operation` 配置，强调文档质量和时间新鲜度
3. **问题诊断查询**: 使用 `diagnosis` 配置，强调用户偏好和最新信息
4. **个性化查询**: 使用 `personalized` 配置，强调用户历史记录
5. **代码搜索**: 使用 `code` 配置，强调关键词精确匹配

系统会自动检测查询类型并选择最佳配置，无需手动指定。

---

*报告由动态权重配置系统自动生成*
"""

    # 保存报告
    output_dir = project_root / '.RAG'
    output_path = output_dir / 'dynamic_weights_report.md'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"权重配置报告已保存到: {output_path}")


def main():
    """主函数"""
    print("\n")
    test_query_detection()
    print("\n")
    show_config_details()
    print("\n")
    compare_configs()
    print("\n")
    test_auto_selection()
    print("\n")
    generate_weight_report()


if __name__ == '__main__':
    main()
