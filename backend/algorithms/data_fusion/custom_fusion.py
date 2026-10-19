# -*- coding: utf-8 -*-
"""
自定义融合实验 - 贝叶斯融合（调参版）
=====================================
通过修改先验概率 PRIOR 和熵转换参数 LAMBDA_VAL，
观察不同参数对融合结果的影响。
"""
import os, sys, json, math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ============ 可修改区域 ============
# 先验概率：目标存在的先验信念，越大越倾向于认为目标存在。
# 注意：P_yolo 与 P_pc 本身都已是后验概率/可靠性权重，不是似然，所以中性先验是 0.5。
# 取 0.1 会把先验计入两次，融合值恒低于单源 YOLO，"提升"列恒为负。
PRIOR = 0.5          # 试试 0.2, 0.3, 0.5, 0.7

# 熵转换参数 lambda：控制点云熵值对融合的影响强度
# lambda 越大，熵值对结果影响越大
LAMBDA_VAL = {
    "Cyclist": 0.1,      # 试试 0.05, 0.1, 0.2, 0.5
    "Car": 0.1,
    "Pedestrian": 0.1,
    "Bus": 0.1,
    "Truck": 0.1
}
# ====================================

# 类别 ID 必须与输入数据一致：这份数据是 0/1/3/5/7，Truck 是 7 而不是 6
CLASS_NAMES = {0: "Cyclist", 1: "Car", 3: "Pedestrian", 5: "Bus", 7: "Truck"}

# YOLO 没有该类别检测结果时的低置信度（表示"基本没看到"）。
# 不要写成 PRIOR：先验是融合公式的基准，和"本次观测的置信度"是两回事。
# 写成 PRIOR 的话，调大先验会让"没检测到"变成 0.5 的中性观测，结论就失真了。
DEFAULT_YOLO_PROB = 0.1

# 点云熵值缺失时的兜底熵值
DEFAULT_ENTROPY = 10.0

# 点云缺少该类别数据时按中性证据处理（P_pc = 0.5 等价于 LR = 1），不增强也不惩罚
NEUTRAL_PC_PROB = 0.5

INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "custom")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_frames(folder):
    results = {}
    if not os.path.exists(folder):
        return results
    for f in os.listdir(folder):
        if f.endswith('.json'):
            with open(os.path.join(folder, f), 'r', encoding='utf-8') as fp:
                results[os.path.splitext(f)[0]] = json.load(fp)
    return results

def entropy_to_prob(entropy, cls):
    lam = LAMBDA_VAL.get(cls, 0.1)
    return math.exp(-lam * entropy)

def bayesian_fusion(p_yolo, entropy, cls, pc_missing=False):
    p_pc = NEUTRAL_PC_PROB if pc_missing else entropy_to_prob(entropy, cls)
    num = p_yolo * p_pc * PRIOR
    den = num + (1 - p_yolo) * (1 - p_pc) * (1 - PRIOR)
    return num / den if den > 0 else 0

print("=" * 60)
print("  自定义贝叶斯融合实验")
print(f"  PRIOR={PRIOR}, LAMBDA={list(LAMBDA_VAL.values())[0]}")
print("=" * 60)

yolo_val = load_frames(os.path.join(INPUT_DIR, "yolo", "val"))
pc_val = load_frames(os.path.join(INPUT_DIR, "pointcloud", "val"))
print(f"\n加载验证集: YOLO {len(yolo_val)} 帧, 点云 {len(pc_val)} 帧")

all_ids = sorted(set(yolo_val.keys()) | set(pc_val.keys()))
class_results = {c: [] for c in CLASS_NAMES.values()}

for fid in all_ids:
    yd = yolo_val.get(fid, {})
    pd = pc_val.get(fid, {})
    for cid, cname in CLASS_NAMES.items():
        yolo_entry = yd.get(str(cid))
        if yolo_entry is None:
            yolo_entry = next((item for item in yd.values()
                               if isinstance(item, dict) and item.get("class_name") == cname), None)
        p_yolo = yolo_entry.get("mean_conf", DEFAULT_YOLO_PROB) if yolo_entry else DEFAULT_YOLO_PROB
        pc_missing = cname not in pd
        ent = DEFAULT_ENTROPY if pc_missing else pd[cname].get("entropy", DEFAULT_ENTROPY)
        fused = bayesian_fusion(p_yolo, ent, cname, pc_missing=pc_missing)
        class_results[cname].append((p_yolo, ent, fused))

print("\n" + "=" * 60)
print(f"{'类别':<12} {'YOLO均值':<10} {'熵均值':<10} {'融合均值':<10} {'提升':<8}")
print("-" * 60)
for cname, vals in class_results.items():
    if vals:
        avg_y = np.mean([v[0] for v in vals])
        avg_e = np.mean([v[1] for v in vals])
        avg_f = np.mean([v[2] for v in vals])
        diff = avg_f - avg_y
        print(f"{cname:<12} {avg_y:<10.4f} {avg_e:<10.4f} {avg_f:<10.4f} {diff:+.4f}")
print("=" * 60)
print("\n实验完成！")
