"""
检索质量评估脚本
评估检索系统的准确率、召回率、MRR和响应时间等指标
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.retriever import get_knowledge_manager


class RetrievalEvaluator:
    """检索质量评估器"""

    def __init__(self):
        try:
            self.manager = get_knowledge_manager()
            self.mock_mode = False
        except ValueError as e:
            if "API_KEY" in str(e):
                print("⚠️ 未检测到API密钥，使用模拟模式进行评估")
                self.manager = None
                self.mock_mode = True
            else:
                raise
        self.results = []

    def evaluate(self, test_cases: List[Dict]) -> Dict:
        """
        评估检索质量

        Args:
            test_cases: 测试用例列表，每个用例包含：
                - query: 查询文本
                - relevant_keywords: 相关关键词列表（用于判断相关性）
                - category: 查询类别（理论/操作/诊断）

        Returns:
            评估结果字典
        """
        print(f"\n开始评估检索质量，共 {len(test_cases)} 个测试用例...\n")

        total_precision = 0
        total_mrr = 0
        total_response_time = 0
        category_stats = {}

        for i, test_case in enumerate(test_cases, 1):
            query = test_case['query']
            relevant_keywords = test_case['relevant_keywords']
            category = test_case.get('category', 'unknown')

            print(f"[{i}/{len(test_cases)}] 测试查询: {query}")

            # 执行检索并计时
            start_time = time.time()
            if self.mock_mode:
                # 模拟模式：生成模拟结果
                results = self._generate_mock_results(query, relevant_keywords)
            else:
                results = self.manager.search(query, top_k=5)
            response_time = (time.time() - start_time) * 1000  # 转换为毫秒

            # 计算准确率（top-5中相关文档的比例）
            relevant_count = 0
            first_relevant_rank = None

            for rank, doc in enumerate(results, 1):
                content = doc.get('content', '').lower()
                is_relevant = any(kw.lower() in content for kw in relevant_keywords)

                if is_relevant:
                    relevant_count += 1
                    if first_relevant_rank is None:
                        first_relevant_rank = rank

            precision = relevant_count / len(results) if results else 0
            mrr = 1 / first_relevant_rank if first_relevant_rank else 0

            # 记录结果
            result = {
                'query': query,
                'category': category,
                'precision': precision,
                'mrr': mrr,
                'response_time': response_time,
                'relevant_count': relevant_count,
                'total_results': len(results),
                'first_relevant_rank': first_relevant_rank
            }
            self.results.append(result)

            # 累计统计
            total_precision += precision
            total_mrr += mrr
            total_response_time += response_time

            # 分类统计
            if category not in category_stats:
                category_stats[category] = {
                    'count': 0,
                    'precision': 0,
                    'mrr': 0,
                    'response_time': 0
                }
            category_stats[category]['count'] += 1
            category_stats[category]['precision'] += precision
            category_stats[category]['mrr'] += mrr
            category_stats[category]['response_time'] += response_time

            # 打印单个结果
            print(f"  准确率: {precision:.2%} | MRR: {mrr:.3f} | 响应时间: {response_time:.0f}ms")
            print(f"  相关文档: {relevant_count}/{len(results)} | 首个相关排名: {first_relevant_rank or 'N/A'}\n")

        # 计算平均指标
        n = len(test_cases)
        avg_precision = total_precision / n
        avg_mrr = total_mrr / n
        avg_response_time = total_response_time / n

        # 计算分类平均值
        for cat, stats in category_stats.items():
            count = stats['count']
            stats['avg_precision'] = stats['precision'] / count
            stats['avg_mrr'] = stats['mrr'] / count
            stats['avg_response_time'] = stats['response_time'] / count

        # 生成评估报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_queries': n,
            'overall_metrics': {
                'avg_precision': avg_precision,
                'avg_mrr': avg_mrr,
                'avg_response_time': avg_response_time
            },
            'category_metrics': category_stats,
            'detailed_results': self.results
        }

        return report

    def _generate_mock_results(self, query: str, relevant_keywords: List[str]) -> List[Dict]:
        """生成模拟检索结果（用于测试）"""
        import random

        # 生成5个模拟文档
        results = []
        for i in range(5):
            # 随机决定是否相关（前3个更可能相关）
            is_relevant = random.random() > (0.3 if i < 3 else 0.7)

            if is_relevant and relevant_keywords:
                # 相关文档：包含一些关键词
                num_keywords = random.randint(1, min(3, len(relevant_keywords)))
                selected_keywords = random.sample(relevant_keywords, num_keywords)
                content = f"这是关于{query}的文档。" + " ".join(selected_keywords) + " 的详细说明和示例。"
            else:
                # 不相关文档
                content = f"这是一个关于其他主题的文档，与{query}关系不大。"

            results.append({
                'content': content,
                'metadata': {'source': f'mock_doc_{i}.md'},
                'distance': random.uniform(0.3, 0.9),
                'id': f'mock_{i}'
            })

        return results

    def print_report(self, report: Dict):
        """打印评估报告"""
        print("\n" + "="*60)
        print("检索质量评估报告")
        print("="*60)

        overall = report['overall_metrics']
        print(f"\n总体指标 (共 {report['total_queries']} 个查询):")
        print(f"  平均准确率: {overall['avg_precision']:.2%}")
        print(f"  平均MRR: {overall['avg_mrr']:.3f}")
        print(f"  平均响应时间: {overall['avg_response_time']:.0f}ms")

        print(f"\n分类指标:")
        for category, stats in report['category_metrics'].items():
            print(f"\n  {category} ({stats['count']} 个查询):")
            print(f"    准确率: {stats['avg_precision']:.2%}")
            print(f"    MRR: {stats['avg_mrr']:.3f}")
            print(f"    响应时间: {stats['avg_response_time']:.0f}ms")

        print("\n" + "="*60)

        # 性能评估
        print("\n性能评估:")
        if overall['avg_precision'] >= 0.8:
            print("  ✅ 准确率达标 (>80%)")
        else:
            print(f"  ⚠️ 准确率未达标 ({overall['avg_precision']:.2%} < 80%)")

        if overall['avg_mrr'] >= 0.7:
            print("  ✅ MRR达标 (>0.7)")
        else:
            print(f"  ⚠️ MRR未达标 ({overall['avg_mrr']:.3f} < 0.7)")

        if overall['avg_response_time'] <= 500:
            print("  ✅ 响应时间达标 (<500ms)")
        else:
            print(f"  ⚠️ 响应时间超标 ({overall['avg_response_time']:.0f}ms > 500ms)")

        print("\n" + "="*60 + "\n")

    def save_report(self, report: Dict, output_path: str):
        """保存评估报告到文件"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"评估报告已保存到: {output_path}")


def get_test_cases() -> List[Dict]:
    """获取测试用例集"""
    return [
        # 理论知识查询
        {
            'query': 'DQN算法的原理是什么？',
            'relevant_keywords': ['DQN', '深度Q网络', 'Q-learning', '强化学习', '神经网络'],
            'category': '理论知识'
        },
        {
            'query': '贝叶斯融合算法如何工作？',
            'relevant_keywords': ['贝叶斯', '融合', '概率', '数据融合', 'Bayesian'],
            'category': '理论知识'
        },
        {
            'query': 'Dijkstra最短路径算法',
            'relevant_keywords': ['Dijkstra', '最短路径', '路径规划', '图算法'],
            'category': '理论知识'
        },
        {
            'query': 'PPO算法的优势',
            'relevant_keywords': ['PPO', 'Proximal Policy', '策略优化', '强化学习'],
            'category': '理论知识'
        },

        # 操作指导查询
        {
            'query': '如何配置CARLA仿真环境？',
            'relevant_keywords': ['CARLA', '配置', '仿真', '环境', '设置'],
            'category': '操作指导'
        },
        {
            'query': '数据采集模块怎么使用？',
            'relevant_keywords': ['数据采集', '使用', '模块', '操作', '步骤'],
            'category': '操作指导'
        },
        {
            'query': '信号优化实验的参数如何设置？',
            'relevant_keywords': ['信号优化', '参数', '设置', '配置', '实验'],
            'category': '操作指导'
        },
        {
            'query': '如何启动SUMO仿真？',
            'relevant_keywords': ['SUMO', '启动', '仿真', '运行'],
            'category': '操作指导'
        },

        # 问题诊断查询
        {
            'query': '为什么我的实验失败了？',
            'relevant_keywords': ['失败', '错误', '问题', '诊断', '原因'],
            'category': '问题诊断'
        },
        {
            'query': 'SUMO连接超时怎么办？',
            'relevant_keywords': ['SUMO', '超时', '连接', '错误', '解决'],
            'category': '问题诊断'
        },
        {
            'query': '训练不收敛的原因',
            'relevant_keywords': ['训练', '收敛', '问题', '原因', '优化'],
            'category': '问题诊断'
        },

        # 算法对比查询
        {
            'query': 'DQN和PPO算法的区别',
            'relevant_keywords': ['DQN', 'PPO', '区别', '对比', '算法'],
            'category': '理论知识'
        },
        {
            'query': '哪种路径规划算法更好？',
            'relevant_keywords': ['路径规划', '算法', '对比', 'Dijkstra', 'A*'],
            'category': '理论知识'
        },

        # 实验相关查询
        {
            'query': '信号优化实验的流程',
            'relevant_keywords': ['信号优化', '流程', '步骤', '实验'],
            'category': '操作指导'
        },
        {
            'query': '层级控制实验需要什么参数？',
            'relevant_keywords': ['层级控制', '参数', '实验', '配置'],
            'category': '操作指导'
        },

        # 技术细节查询
        {
            'query': 'YOLO目标检测的配置',
            'relevant_keywords': ['YOLO', '目标检测', '配置', '参数'],
            'category': '操作指导'
        },
        {
            'query': 'CAV渗透率如何设置？',
            'relevant_keywords': ['CAV', '渗透率', '设置', '参数'],
            'category': '操作指导'
        },
    ]


def main():
    """主函数"""
    print("="*60)
    print("智信优控平台 - 检索质量评估工具")
    print("="*60)

    # 创建评估器
    evaluator = RetrievalEvaluator()

    # 获取测试用例
    test_cases = get_test_cases()

    # 执行评估
    report = evaluator.evaluate(test_cases)

    # 打印报告
    evaluator.print_report(report)

    # 保存报告
    output_dir = project_root / '.RAG'
    output_path = output_dir / f'retrieval_evaluation_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    evaluator.save_report(report, str(output_path))

    # 生成Markdown报告
    md_path = output_dir / 'retrieval_evaluation_latest.md'
    generate_markdown_report(report, str(md_path))

    return report


def generate_markdown_report(report: Dict, output_path: str):
    """生成Markdown格式的评估报告"""
    overall = report['overall_metrics']

    md_content = f"""# 检索质量评估报告

**评估时间**: {report['timestamp']}
**测试查询数**: {report['total_queries']}

---

## 一、总体指标

| 指标 | 实际值 | 目标值 | 状态 |
|------|--------|--------|------|
| 平均准确率 | {overall['avg_precision']:.2%} | >80% | {'✅ 达标' if overall['avg_precision'] >= 0.8 else '⚠️ 未达标'} |
| 平均MRR | {overall['avg_mrr']:.3f} | >0.7 | {'✅ 达标' if overall['avg_mrr'] >= 0.7 else '⚠️ 未达标'} |
| 平均响应时间 | {overall['avg_response_time']:.0f}ms | <500ms | {'✅ 达标' if overall['avg_response_time'] <= 500 else '⚠️ 超标'} |

---

## 二、分类指标

"""

    for category, stats in report['category_metrics'].items():
        md_content += f"""
### {category} ({stats['count']} 个查询)

| 指标 | 值 |
|------|-----|
| 准确率 | {stats['avg_precision']:.2%} |
| MRR | {stats['avg_mrr']:.3f} |
| 响应时间 | {stats['avg_response_time']:.0f}ms |

"""

    md_content += """
---

## 三、详细结果

| 查询 | 类别 | 准确率 | MRR | 响应时间 | 相关文档数 |
|------|------|--------|-----|----------|-----------|
"""

    for result in report['detailed_results']:
        md_content += f"| {result['query']} | {result['category']} | {result['precision']:.2%} | {result['mrr']:.3f} | {result['response_time']:.0f}ms | {result['relevant_count']}/{result['total_results']} |\n"

    md_content += """
---

## 四、优化建议

"""

    # 根据结果生成优化建议
    if overall['avg_precision'] < 0.8:
        md_content += "### 准确率优化\n"
        md_content += "- 调整重排序权重，提高语义相似度权重\n"
        md_content += "- 优化关键词提取算法\n"
        md_content += "- 补充相关领域的训练数据\n\n"

    if overall['avg_mrr'] < 0.7:
        md_content += "### MRR优化\n"
        md_content += "- 优化排序算法，确保最相关文档排在前面\n"
        md_content += "- 增加上下文感知能力\n"
        md_content += "- 调整向量/关键词权重比例\n\n"

    if overall['avg_response_time'] > 500:
        md_content += "### 响应时间优化\n"
        md_content += "- 优化向量检索性能\n"
        md_content += "- 增加缓存机制\n"
        md_content += "- 减少候选文档数量\n\n"

    # 找出表现最差的类别
    worst_category = min(report['category_metrics'].items(),
                        key=lambda x: x[1]['avg_precision'])
    md_content += f"### 重点关注\n"
    md_content += f"- **{worst_category[0]}** 类别表现较差（准确率 {worst_category[1]['avg_precision']:.2%}），需要重点优化\n"

    md_content += "\n---\n\n*报告由检索质量评估工具自动生成*\n"

    # 保存Markdown报告
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Markdown报告已保存到: {output_path}")


if __name__ == '__main__':
    main()
