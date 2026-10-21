"""评估指标计算和可视化工具"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)


class MetricsEvaluator:
    """性能指标评估器"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_metrics(self, metrics_file: Path) -> List[Dict[str, Any]]:
        """加载指标数据"""
        with open(metrics_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def calculate_summary(self, metrics: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算汇总指标"""
        if not metrics:
            return {}

        # 提取时间序列数据
        avg_speeds = [m["avg_speed"] for m in metrics]
        waiting_counts = [m["waiting_count"] for m in metrics]
        total_vehicles = [m["total_vehicles"] for m in metrics]

        return {
            "avg_speed_mean": np.mean(avg_speeds),
            "avg_speed_std": np.std(avg_speeds),
            "waiting_count_mean": np.mean(waiting_counts),
            "waiting_count_std": np.std(waiting_counts),
            "total_vehicles_mean": np.mean(total_vehicles),
            "throughput": sum(total_vehicles) / len(metrics),  # 车辆/步
        }

    def compare_modes(
        self,
        metrics_files: Dict[str, Path],
    ) -> Dict[str, Dict[str, float]]:
        """对比不同协调模式的性能

        Args:
            metrics_files: {mode_name: metrics_file_path}

        Returns:
            Dict: {mode_name: summary_metrics}
        """
        results = {}

        for mode_name, metrics_file in metrics_files.items():
            metrics = self.load_metrics(metrics_file)
            summary = self.calculate_summary(metrics)
            results[mode_name] = summary

            logger.info(f"Mode: {mode_name}")
            logger.info(f"  Avg Speed: {summary['avg_speed_mean']:.2f} ± {summary['avg_speed_std']:.2f} m/s")
            logger.info(f"  Waiting Count: {summary['waiting_count_mean']:.1f} ± {summary['waiting_count_std']:.1f}")
            logger.info(f"  Throughput: {summary['throughput']:.2f} vehicles/step")

        return results

    def plot_comparison(
        self,
        metrics_files: Dict[str, Path],
        output_file: Path = None,
    ) -> None:
        """绘制对比图表

        Args:
            metrics_files: {mode_name: metrics_file_path}
            output_file: 输出文件路径
        """
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("Multi-Level Coordination Performance Comparison", fontsize=16)

        # 加载所有数据
        all_metrics = {}
        for mode_name, metrics_file in metrics_files.items():
            all_metrics[mode_name] = self.load_metrics(metrics_file)

        # 1. 平均速度时间序列
        ax = axes[0, 0]
        for mode_name, metrics in all_metrics.items():
            steps = [m["step"] for m in metrics]
            speeds = [m["avg_speed"] for m in metrics]
            ax.plot(steps, speeds, label=mode_name, linewidth=2)
        ax.set_xlabel("Simulation Step")
        ax.set_ylabel("Average Speed (m/s)")
        ax.set_title("Average Speed Over Time")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 2. 等待车辆数时间序列
        ax = axes[0, 1]
        for mode_name, metrics in all_metrics.items():
            steps = [m["step"] for m in metrics]
            waiting = [m["waiting_count"] for m in metrics]
            ax.plot(steps, waiting, label=mode_name, linewidth=2)
        ax.set_xlabel("Simulation Step")
        ax.set_ylabel("Waiting Vehicles")
        ax.set_title("Waiting Vehicles Over Time")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 3. 平均速度对比（柱状图）
        ax = axes[1, 0]
        mode_names = list(all_metrics.keys())
        avg_speeds = []
        speed_stds = []
        for mode_name in mode_names:
            metrics = all_metrics[mode_name]
            speeds = [m["avg_speed"] for m in metrics]
            avg_speeds.append(np.mean(speeds))
            speed_stds.append(np.std(speeds))

        x = np.arange(len(mode_names))
        ax.bar(x, avg_speeds, yerr=speed_stds, capsize=5, alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(mode_names)
        ax.set_ylabel("Average Speed (m/s)")
        ax.set_title("Average Speed Comparison")
        ax.grid(True, alpha=0.3, axis='y')

        # 4. 等待车辆数对比（柱状图）
        ax = axes[1, 1]
        avg_waiting = []
        waiting_stds = []
        for mode_name in mode_names:
            metrics = all_metrics[mode_name]
            waiting = [m["waiting_count"] for m in metrics]
            avg_waiting.append(np.mean(waiting))
            waiting_stds.append(np.std(waiting))

        ax.bar(x, avg_waiting, yerr=waiting_stds, capsize=5, alpha=0.7, color='orange')
        ax.set_xticks(x)
        ax.set_xticklabels(mode_names)
        ax.set_ylabel("Waiting Vehicles")
        ax.set_title("Waiting Vehicles Comparison")
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        # 保存图表
        if output_file is None:
            output_file = self.output_dir / "comparison.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        logger.info(f"Comparison plot saved to: {output_file}")

        plt.close()

    def generate_report(
        self,
        metrics_files: Dict[str, Path],
        output_file: Path = None,
    ) -> None:
        """生成实验报告

        Args:
            metrics_files: {mode_name: metrics_file_path}
            output_file: 输出文件路径
        """
        if output_file is None:
            output_file = self.output_dir / "report.txt"

        # 计算对比结果
        results = self.compare_modes(metrics_files)

        # 生成报告
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("Multi-Level Coordination Performance Report\n")
            f.write("=" * 80 + "\n\n")

            # 各模式详细指标
            for mode_name, summary in results.items():
                f.write(f"Mode: {mode_name}\n")
                f.write("-" * 40 + "\n")
                f.write(f"  Average Speed:    {summary['avg_speed_mean']:.2f} ± {summary['avg_speed_std']:.2f} m/s\n")
                f.write(f"  Waiting Vehicles: {summary['waiting_count_mean']:.1f} ± {summary['waiting_count_std']:.1f}\n")
                f.write(f"  Throughput:       {summary['throughput']:.2f} vehicles/step\n")
                f.write("\n")

            # 对比分析
            if "none" in results and "full" in results:
                f.write("=" * 80 + "\n")
                f.write("Improvement Analysis (Full vs None)\n")
                f.write("=" * 80 + "\n\n")

                none_speed = results["none"]["avg_speed_mean"]
                full_speed = results["full"]["avg_speed_mean"]
                speed_improvement = (full_speed - none_speed) / none_speed * 100

                none_waiting = results["none"]["waiting_count_mean"]
                full_waiting = results["full"]["waiting_count_mean"]
                waiting_reduction = (none_waiting - full_waiting) / none_waiting * 100

                f.write(f"  Speed Improvement:    {speed_improvement:+.1f}%\n")
                f.write(f"  Waiting Reduction:    {waiting_reduction:+.1f}%\n")
                f.write("\n")

        logger.info(f"Report saved to: {output_file}")


def main():
    """示例：评估和可视化"""
    import argparse

    parser = argparse.ArgumentParser(description="评估多层级协调性能")
    parser.add_argument(
        "--metrics-dir",
        type=Path,
        default=Path(__file__).parent / "output",
        help="指标文件目录",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "output" / "evaluation",
        help="输出目录",
    )

    args = parser.parse_args()

    # 查找指标文件
    metrics_files = {}
    for mode in ["none", "local", "full"]:
        pattern = f"metrics_{mode}_*.json"
        files = list(args.metrics_dir.glob(pattern))
        if files:
            # 使用最新的文件
            metrics_files[mode] = sorted(files)[-1]

    if not metrics_files:
        logger.error(f"No metrics files found in {args.metrics_dir}")
        return

    logger.info(f"Found {len(metrics_files)} metrics files")

    # 创建评估器
    evaluator = MetricsEvaluator(args.output_dir)

    # 生成对比图表
    evaluator.plot_comparison(metrics_files)

    # 生成报告
    evaluator.generate_report(metrics_files)


if __name__ == "__main__":
    main()
