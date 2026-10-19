"""
Embedding模型性能测试工具
对比不同embedding模型的性能、准确率、速度和成本
"""

import sys
import os
import time
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


class EmbeddingModelTester:
    """Embedding模型测试器"""

    def __init__(self):
        """初始化测试器"""
        self.test_texts = self._get_test_texts()
        self.results = []

    def _get_test_texts(self) -> List[str]:
        """获取测试文本集"""
        return [
            # 短文本
            "DQN算法",
            "信号优化",
            "路径规划",

            # 中等文本
            "DQN算法是一种深度强化学习算法，结合了Q-learning和深度神经网络。",
            "信号优化实验通过调整交通信号灯配时方案，提高路口通行效率。",
            "路径规划算法用于计算车辆从起点到终点的最优路径。",

            # 长文本
            """深度Q网络（DQN）是DeepMind在2015年提出的一种深度强化学习算法。
            它将Q-learning与深度神经网络相结合，能够直接从高维输入（如图像）中学习策略。
            DQN的核心创新包括经验回放（Experience Replay）和目标网络（Target Network），
            这两个技术有效解决了深度强化学习中的不稳定性问题。""",

            """交通信号优化是智能交通系统的重要组成部分。传统的信号配时方案通常基于历史数据和经验，
            难以适应实时变化的交通流量。现代信号优化方法采用自适应控制策略，能够根据实时检测到的
            交通流量动态调整信号配时，从而提高路口通行效率，减少车辆等待时间和尾气排放。""",

            """路径规划是自动驾驶和智能导航系统的核心技术之一。常用的路径规划算法包括Dijkstra算法、
            A*算法和RRT算法等。这些算法各有特点：Dijkstra算法保证找到最短路径但计算量大；
            A*算法通过启发式函数加速搜索；RRT算法适合高维空间的路径规划。在实际应用中，
            需要根据具体场景选择合适的算法。"""
        ]

    def test_model(
        self,
        model_name: str,
        model_config: Dict,
        embedding_func
    ) -> Dict:
        """
        测试单个模型

        Args:
            model_name: 模型名称
            model_config: 模型配置
            embedding_func: 嵌入生成函数

        Returns:
            测试结果字典
        """
        print(f"\n测试模型: {model_name}")
        print(f"配置: {model_config}")

        results = {
            'model_name': model_name,
            'config': model_config,
            'embedding_times': [],
            'embedding_dimensions': None,
            'total_time': 0,
            'avg_time': 0,
            'tokens_per_second': 0,
            'success': True,
            'error': None
        }

        try:
            all_embeddings = []

            # 测试每个文本
            for i, text in enumerate(self.test_texts, 1):
                start_time = time.time()

                # 生成嵌入
                embedding = embedding_func(text)

                elapsed = time.time() - start_time
                results['embedding_times'].append(elapsed)

                # 记录维度
                if results['embedding_dimensions'] is None:
                    results['embedding_dimensions'] = len(embedding)

                all_embeddings.append(embedding)

                print(f"  [{i}/{len(self.test_texts)}] {len(text)}字符 -> {elapsed*1000:.0f}ms")

            # 计算统计信息
            results['total_time'] = sum(results['embedding_times'])
            results['avg_time'] = results['total_time'] / len(results['embedding_times'])

            # 估算tokens/秒（假设1个字符≈1个token）
            total_chars = sum(len(text) for text in self.test_texts)
            results['tokens_per_second'] = total_chars / results['total_time']

            print(f"\n✅ 测试完成")
            print(f"   总耗时: {results['total_time']:.2f}秒")
            print(f"   平均耗时: {results['avg_time']*1000:.0f}ms")
            print(f"   嵌入维度: {results['embedding_dimensions']}")
            print(f"   处理速度: {results['tokens_per_second']:.0f} tokens/秒")

        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
            print(f"\n❌ 测试失败: {e}")

        return results

    def test_openai_embedding(self):
        """测试OpenAI embedding模型"""
        try:
            from backend.knowledge_base.embeddings import OpenAIEmbedding

            model_configs = [
                {
                    'name': 'text-embedding-3-small',
                    'dimensions': 1536,
                    'cost_per_1m_tokens': 0.02
                },
                {
                    'name': 'text-embedding-3-large',
                    'dimensions': 3072,
                    'cost_per_1m_tokens': 0.13
                }
            ]

            for config in model_configs:
                embedding_model = OpenAIEmbedding(model=config['name'])

                result = self.test_model(
                    model_name=f"OpenAI {config['name']}",
                    model_config=config,
                    embedding_func=embedding_model.embed_query
                )

                # 计算成本
                total_chars = sum(len(text) for text in self.test_texts)
                cost = (total_chars / 1_000_000) * config['cost_per_1m_tokens']
                result['estimated_cost'] = cost

                self.results.append(result)

        except Exception as e:
            print(f"\n⚠️ 无法测试OpenAI模型: {e}")
            print("   请确保已配置OPENAI_API_KEY环境变量")

    def test_mock_embedding(self):
        """测试模拟embedding（用于演示）"""
        import random

        def mock_embed(text: str) -> List[float]:
            """生成模拟嵌入向量"""
            # 简单的基于文本长度和内容的模拟
            dimension = 768
            seed = hash(text) % 10000
            random.seed(seed)
            return [random.random() for _ in range(dimension)]

        config = {
            'name': 'mock-embedding',
            'dimensions': 768,
            'cost_per_1m_tokens': 0.0
        }

        result = self.test_model(
            model_name="Mock Embedding (本地模拟)",
            model_config=config,
            embedding_func=mock_embed
        )

        result['estimated_cost'] = 0.0
        self.results.append(result)

    def generate_comparison_report(self) -> str:
        """生成对比报告"""
        if not self.results:
            return "没有测试结果"

        report = f"""# Embedding模型性能对比报告

**测试时间**: {datetime.now().isoformat()}
**测试文本数**: {len(self.test_texts)}

---

## 一、测试结果

"""

        # 对比表格
        report += "| 模型 | 维度 | 平均耗时 | 处理速度 | 估算成本 | 状态 |\n"
        report += "|------|------|----------|----------|----------|------|\n"

        for result in self.results:
            model_name = result['model_name']
            dimensions = result.get('embedding_dimensions', 'N/A')
            avg_time = result.get('avg_time', 0) * 1000
            speed = result.get('tokens_per_second', 0)
            cost = result.get('estimated_cost', 0)
            status = "✅" if result['success'] else "❌"

            report += f"| {model_name} | {dimensions} | {avg_time:.0f}ms | {speed:.0f} tokens/s | ${cost:.6f} | {status} |\n"

        report += "\n---\n\n## 二、详细分析\n\n"

        for result in self.results:
            if not result['success']:
                continue

            report += f"### {result['model_name']}\n\n"
            report += f"**配置**:\n"
            for key, value in result['config'].items():
                report += f"- {key}: {value}\n"

            report += f"\n**性能指标**:\n"
            report += f"- 总耗时: {result['total_time']:.2f}秒\n"
            report += f"- 平均耗时: {result['avg_time']*1000:.0f}ms\n"
            report += f"- 嵌入维度: {result['embedding_dimensions']}\n"
            report += f"- 处理速度: {result['tokens_per_second']:.0f} tokens/秒\n"

            if 'estimated_cost' in result:
                report += f"- 估算成本: ${result['estimated_cost']:.6f}\n"

            report += "\n"

        report += "---\n\n## 三、推荐建议\n\n"

        # 找出最快的模型
        fastest = min(
            [r for r in self.results if r['success']],
            key=lambda x: x['avg_time']
        )
        report += f"**速度最快**: {fastest['model_name']} ({fastest['avg_time']*1000:.0f}ms)\n\n"

        # 找出成本最低的模型
        cheapest = min(
            [r for r in self.results if r['success'] and 'estimated_cost' in r],
            key=lambda x: x['estimated_cost'],
            default=None
        )
        if cheapest:
            report += f"**成本最低**: {cheapest['model_name']} (${cheapest['estimated_cost']:.6f})\n\n"

        report += """
### 选择建议

1. **开发测试环境**: 使用Mock Embedding或本地模型，成本为零
2. **生产环境（预算充足）**: 使用OpenAI text-embedding-3-large，准确率最高
3. **生产环境（预算有限）**: 使用OpenAI text-embedding-3-small，性价比最高
4. **离线部署**: 考虑使用开源模型（如sentence-transformers）

---

## 四、成本估算

基于100万tokens的月度使用量：

"""

        for result in self.results:
            if not result['success'] or 'estimated_cost' not in result:
                continue

            config = result['config']
            if 'cost_per_1m_tokens' in config:
                monthly_cost = config['cost_per_1m_tokens']
                report += f"- {result['model_name']}: ${monthly_cost:.2f}/月\n"

        report += "\n---\n\n*报告由Embedding模型性能测试工具自动生成*\n"

        return report

    def save_report(self, report: str, output_path: str):
        """保存报告"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {output_path}")


def main():
    """主函数"""
    print("="*70)
    print("Embedding模型性能测试")
    print("="*70)

    tester = EmbeddingModelTester()

    # 测试模拟模型（总是可用）
    print("\n" + "="*70)
    print("测试1: 模拟Embedding模型")
    print("="*70)
    tester.test_mock_embedding()

    # 尝试测试OpenAI模型
    print("\n" + "="*70)
    print("测试2: OpenAI Embedding模型")
    print("="*70)
    tester.test_openai_embedding()

    # 生成报告
    print("\n" + "="*70)
    print("生成对比报告")
    print("="*70)

    report = tester.generate_comparison_report()
    print(report)

    # 保存报告
    output_dir = project_root / '.RAG'
    output_path = output_dir / 'embedding_model_comparison.md'
    tester.save_report(report, str(output_path))


if __name__ == '__main__':
    main()
