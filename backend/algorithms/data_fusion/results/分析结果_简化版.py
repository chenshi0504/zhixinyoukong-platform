# -*- coding: utf-8 -*-
"""
分析结果_简化版 - 生成融合分析图表和实验报告
从 output/fusion 目录读取融合结果，生成可视化图表
"""
import os
import json
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)  # data_fusion 目录
FUSION_VAL = os.path.join(BASE_DIR, "output", "fusion", "val")
FUSION_TEST = os.path.join(BASE_DIR, "output", "fusion", "test")
CHARTS_DIR = os.path.join(SCRIPT_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

# 尝试导入matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("警告: 未安装matplotlib，将跳过图表生成")


def load_fusion_results(folder):
    """加载融合结果"""
    all_results = {}
    if not os.path.exists(folder):
        return all_results
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith('.json'):
            continue
        filepath = os.path.join(folder, fname)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            frame_id = os.path.splitext(fname)[0]
            all_results[frame_id] = data
        except Exception:
            continue
    return all_results


def aggregate_results(results):
    """聚合所有帧的融合结果"""
    class_stats = {}
    for frame_id, frame_data in results.items():
        for cls_name, info in frame_data.items():
            if cls_name not in class_stats:
                class_stats[cls_name] = {
                    'yolo_confs': [],
                    'pc_entropies': [],
                    'fused_probs': []
                }
            class_stats[cls_name]['yolo_confs'].append(info.get('yolo_mean_conf', 0))
            class_stats[cls_name]['pc_entropies'].append(info.get('pc_entropy', 0))
            class_stats[cls_name]['fused_probs'].append(info.get('fused_prob', 0))
    return class_stats


def generate_charts(val_stats, test_stats):
    """生成可视化图表（2张核心图表，全中文标注）"""
    if not HAS_MATPLOTLIB:
        print("跳过图表生成（matplotlib不可用）")
        return

    classes = sorted(set(list(val_stats.keys()) + list(test_stats.keys())))

    # 图1: 各类别融合效果对比（YOLO原始置信度 vs 贝叶斯融合概率）
    fig, ax = plt.subplots(figsize=(10, 6))
    x = range(len(classes))
    val_yolo = [sum(val_stats.get(c, {}).get('yolo_confs', [0])) / max(len(val_stats.get(c, {}).get('yolo_confs', [0])), 1) for c in classes]
    val_fused = [sum(val_stats.get(c, {}).get('fused_probs', [0])) / max(len(val_stats.get(c, {}).get('fused_probs', [0])), 1) for c in classes]
    width = 0.35
    bars1 = ax.bar([i - width/2 for i in x], val_yolo, width, label='YOLO原始置信度', color='#6c8ebf')
    bars2 = ax.bar([i + width/2 for i in x], val_fused, width, label='贝叶斯融合概率', color='#2C5AA0')
    ax.set_xlabel('目标类别', fontsize=12)
    ax.set_ylabel('概率值', fontsize=12)
    ax.set_title('融合前后置信度对比（验证集）', fontsize=14, fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(classes, fontsize=11)
    ax.legend(fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.grid(axis='y', alpha=0.3)
    # 在柱子上标注数值
    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.01, f'{h:.2f}', ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.01, f'{h:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, '融合前后对比.png'), dpi=150)
    plt.close()

    # 图2: 各类别验证集与测试集融合概率对比
    fig, ax = plt.subplots(figsize=(10, 6))
    val_means = [sum(val_stats.get(c, {}).get('fused_probs', [0])) / max(len(val_stats.get(c, {}).get('fused_probs', [0])), 1) for c in classes]
    test_means = [sum(test_stats.get(c, {}).get('fused_probs', [0])) / max(len(test_stats.get(c, {}).get('fused_probs', [0])), 1) for c in classes]
    bars1 = ax.bar([i - width/2 for i in x], val_means, width, label='验证集', color='#2C5AA0')
    bars2 = ax.bar([i + width/2 for i in x], test_means, width, label='测试集', color='#e07b54')
    ax.set_xlabel('目标类别', fontsize=12)
    ax.set_ylabel('平均融合概率', fontsize=12)
    ax.set_title('验证集与测试集融合概率对比', fontsize=14, fontweight='bold')
    ax.set_xticks(list(x))
    ax.set_xticklabels(classes, fontsize=11)
    ax.legend(fontsize=11)
    ax.set_ylim(0, 1.05)
    ax.grid(axis='y', alpha=0.3)
    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.01, f'{h:.2f}', ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.01, f'{h:.2f}', ha='center', va='bottom', fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, '验证集测试集对比.png'), dpi=150)
    plt.close()

    print(f"  图表已保存到: {CHARTS_DIR}")


def generate_report(val_stats, test_stats, val_count, test_count):
    """生成实验报告"""
    report_path = os.path.join(SCRIPT_DIR, '数据融合实验报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('多源数据融合实验报告\n')
        f.write('=' * 50 + '\n\n')
        f.write('一、实验概述\n')
        f.write('  算法: 贝叶斯决策级融合\n')
        f.write('  数据源: YOLO检测结果 + 点云熵值\n')
        f.write(f'  验证集帧数: {val_count}\n')
        f.write(f'  测试集帧数: {test_count}\n\n')
        f.write('二、融合结果统计\n')
        for dataset_name, stats in [('验证集', val_stats), ('测试集', test_stats)]:
            f.write(f'\n  {dataset_name}:\n')
            for cls_name in sorted(stats.keys()):
                info = stats[cls_name]
                avg_yolo = sum(info['yolo_confs']) / max(len(info['yolo_confs']), 1)
                avg_fused = sum(info['fused_probs']) / max(len(info['fused_probs']), 1)
                f.write(f'    {cls_name}: 平均YOLO置信度={avg_yolo:.4f}, '
                        f'平均融合概率={avg_fused:.4f}, 提升={avg_fused - avg_yolo:+.4f}\n')
        f.write('\n三、结论\n')
        f.write('  贝叶斯融合算法有效整合了YOLO检测和点云熵值信息，\n')
        f.write('  融合后的概率综合考虑了两种数据源的可靠性。\n')
    print(f"  报告已保存: {report_path}")


def main():
    print("=" * 60)
    print("融合分析结果 - 简化版")
    print("=" * 60)

    print("\n[1/4] 加载验证集融合结果...")
    val_results = load_fusion_results(FUSION_VAL)
    print(f"  加载了 {len(val_results)} 帧")

    print("\n[2/4] 加载测试集融合结果...")
    test_results = load_fusion_results(FUSION_TEST)
    print(f"  加载了 {len(test_results)} 帧")

    print("\n[3/4] 生成可视化图表...")
    val_stats = aggregate_results(val_results)
    test_stats = aggregate_results(test_results)
    generate_charts(val_stats, test_stats)

    print("\n[4/4] 生成实验报告...")
    generate_report(val_stats, test_stats, len(val_results), len(test_results))

    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
