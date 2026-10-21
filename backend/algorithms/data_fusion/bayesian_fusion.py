import os
import json
import math
import numpy as np


# 关注以下类别（类别ID对应名称）。
# 注意：ID 必须与输入数据一致。这份数据的实际映射是 0/1/3/5/**7**，
# 早期写成 6 时 Truck 永远取不到 YOLO 结果、一直用缺省值 0.1，融合结论失真。
# 为防数据再次变动，process_fusion 里另有一层按 class_name 的兜底匹配。
CLASS_NAMES = {
    0: "Cyclist",
    1: "Car",
    3: "Pedestrian",
    5: "Bus",
    7: "Truck"
}


# 贝叶斯融合参数：先验概率和熵转换调节参数 lambda_val
#
# PRIOR 必须取 0.5（中性先验）。
# 输入的 P_yolo 是 YOLO 对"目标存在"的置信度，本身已经是后验概率；P_pc = exp(-λ·熵)
# 是点云的可靠性权重。两者都不是似然 P(证据|目标存在)。再乘一个非中性的先验，相当于
# 把先验计入两次：后验几率 = LR_yolo × LR_pc × 先验几率。
# 取 PRIOR = 0.1 时先验几率 = 1/9，融合概率要超过单源 YOLO 需要 LR_pc > 9，
# 即 entropy < 1.05；而真实熵值在 4.7~9.8 —— 于是融合概率恒低于单源、"提升"恒为负，
# 与"多源融合提升可靠性"的实验结论相反。
# 取 0.5（先验几率 = 1）后公式退化为两个独立后验概率的经典合并：
#   P = P_yolo·P_pc / (P_yolo·P_pc + (1-P_yolo)(1-P_pc))
# 此时点云熵越低（越确定）融合提升越大，点云不确定时融合结果向单源收敛。
PRIOR = 0.5
LAMBDA_VAL = {
    "Cyclist": 0.1,
    "Car": 0.1,
    "Pedestrian": 0.1,
    "Bus": 0.1,
    "Truck": 0.1
}

# YOLO 完全没有该类别检测结果时使用的低置信度（表示"基本没看到"）。
# 注意不要写成 PRIOR：先验是融合基准，和"本次观测的置信度"是两回事。
DEFAULT_YOLO_PROB = 0.1

# 点云熵值缺失时的兜底熵值，保留用于"确实有熵但异常大"的情形
DEFAULT_ENTROPY = 10.0

# 点云缺少该类别数据时按"中性证据"处理：P_pc = 0.5 等价于似然比 LR = 1，既不增强
# 也不惩罚。旧实现让缺失走 DEFAULT_ENTROPY=10.0，得到 P_pc = 0.368 < 0.5，等于让
# "没有数据"投反对票——Truck 有 96% 的帧点云无数据，融合值被压到单源的 7.8%。
NEUTRAL_PC_PROB = 0.5

#######################################
# 文件夹路径设置
#######################################
# 获取当前脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 输入数据目录
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
YOLO_VAL_FOLDER = os.path.join(INPUT_DIR, "yolo", "val")
YOLO_TEST_FOLDER = os.path.join(INPUT_DIR, "yolo", "test")
PC_VAL_FOLDER = os.path.join(INPUT_DIR, "pointcloud", "val")
PC_TEST_FOLDER = os.path.join(INPUT_DIR, "pointcloud", "test")

# 输出数据目录
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
FUSION_VAL_FOLDER = os.path.join(OUTPUT_DIR, "fusion", "val")
FUSION_TEST_FOLDER = os.path.join(OUTPUT_DIR, "fusion", "test")

# 确保输出文件夹存在
for folder in [FUSION_VAL_FOLDER, FUSION_TEST_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)


#######################################
# 工具函数：加载按帧分割的结果 JSON
#######################################
def load_per_frame_results(folder):
    """
    从指定文件夹中读取每帧的 JSON 结果，以
    {frame_id: json_data} 的字典形式返回
    """
    results = {}
    if not os.path.exists(folder):
        print(f"警告: 文件夹不存在 - {folder}")
        return results
    
    for fname in os.listdir(folder):
        if fname.endswith('.json'):
            frame_id = os.path.splitext(fname)[0]
            filepath = os.path.join(folder, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results[frame_id] = data
            except Exception as e:
                print(f"读取文件失败 {filepath}: {e}")
    return results


# 工具函数：将点云熵转换为概率
def entropy_to_probability(entropy, cls_name):
    """
    根据类别使用不同的熵转换参数 LAMBDA_VAL。
    """
    lambda_val = LAMBDA_VAL.get(cls_name, 0.2)  # 默认为 0.2
    return math.exp(-lambda_val * entropy)


# 贝叶斯融合函数
def bayesian_fusion(P_yolo, entropy, cls_name, prior=PRIOR, pc_missing=False):
    """
    贝叶斯融合函数
    P_yolo: YOLO检测置信度（本身已是后验概率）
    entropy: 点云熵值
    cls_name: 类别名称（用于获取对应的lambda值）
    prior: 先验概率；中性先验取 0.5 时公式退化为两个后验概率的经典合并
    pc_missing: 点云缺少该类别数据。为 True 时按中性证据处理（P_pc = 0.5，LR = 1），
                既不增强也不惩罚，避免"没有数据"被当成反对票。
    """
    P_pc = NEUTRAL_PC_PROB if pc_missing else entropy_to_probability(entropy, cls_name)
    num = P_yolo * P_pc * prior
    den = num + ((1 - P_yolo) * (1 - P_pc) * (1 - prior))
    if den == 0:
        return 0
    return num / den


# 主融合处理函数：对每帧进行贝叶斯决策级融合
def process_fusion(yolo_results, pc_results, output_folder):
    """
    对每帧进行贝叶斯决策级融合
    """
    # 遍历所有帧，使用各数据源的文件名集合的并集
    all_frame_ids = set(yolo_results.keys()) | set(pc_results.keys())
    
    if not all_frame_ids:
        print("警告: 没有找到任何帧数据")
        return

    processed_count = 0
    for frame_id in sorted(all_frame_ids):
        # 获取当前帧的 YOLO 与 PC 结果（若无则为空字典）
        yolo_data = yolo_results.get(frame_id, {})
        pc_data = pc_results.get(frame_id, {})

        fusion_frame = {}
        # 对关注的每个类别
        for cls_id, cls_name in CLASS_NAMES.items():
            # 从 YOLO 数据获取检测结果（若不存在则使用默认）
            yolo_entry = yolo_data.get(str(cls_id))
            if yolo_entry is None:
                # 类别 ID 映射与数据不一致时按 class_name 兜底匹配，
                # 避免某一类的 YOLO 结果被静默丢弃、整类退化成缺省值。
                yolo_entry = next(
                    (item for item in yolo_data.values()
                     if isinstance(item, dict) and item.get("class_name") == cls_name),
                    None,
                )
            P_yolo = yolo_entry.get("mean_conf", DEFAULT_YOLO_PROB) if yolo_entry else DEFAULT_YOLO_PROB
            
            # 从 PC 数据获取熵信息（键通常为类别名称）
            pc_missing = cls_name not in pc_data
            if pc_missing:
                entropy = DEFAULT_ENTROPY
            else:
                entropy = pc_data[cls_name].get("entropy", DEFAULT_ENTROPY)

            # 计算融合后概率；点云无数据时按中性证据处理
            fused_prob = bayesian_fusion(P_yolo, entropy, cls_name, prior=PRIOR,
                                         pc_missing=pc_missing)

            fusion_frame[cls_name] = {
                "yolo_mean_conf": round(P_yolo, 4),
                "pc_entropy": round(entropy, 4),
                "fused_prob": round(fused_prob, 4)
            }

        # 保存当前帧融合结果
        output_path = os.path.join(output_folder, f"{frame_id}.json")
        try:
            with open(output_path, "w", encoding="utf-8") as out_f:
                json.dump(fusion_frame, out_f, indent=2, ensure_ascii=False)
            processed_count += 1
        except Exception as e:
            print(f"保存文件失败 {output_path}: {e}")
    
    print(f"贝叶斯决策级融合完成: 处理了 {processed_count} 帧")
    print(f"结果已保存到: {output_folder}")


def main():
    print("=" * 70)
    print("贝叶斯决策级融合 - 多源数据融合")
    print("=" * 70)
    print(f"\n输入目录: {INPUT_DIR}")
    print(f"输出目录: {OUTPUT_DIR}\n")
    
    # 加载验证集和测试集的 YOLO 与 PC 结果
    print("[1/6] 加载验证集 YOLO 结果...")
    yolo_val = load_per_frame_results(YOLO_VAL_FOLDER)
    print(f"      加载了 {len(yolo_val)} 个验证集 YOLO 文件")
    
    print("\n[2/6] 加载验证集 点云熵结果...")
    pc_val = load_per_frame_results(PC_VAL_FOLDER)
    print(f"      加载了 {len(pc_val)} 个验证集点云文件")
    
    print("\n[3/6] 开始对验证集进行贝叶斯决策级融合...")
    process_fusion(yolo_val, pc_val, FUSION_VAL_FOLDER)

    print("\n[4/6] 加载测试集 YOLO 结果...")
    yolo_test = load_per_frame_results(YOLO_TEST_FOLDER)
    print(f"      加载了 {len(yolo_test)} 个测试集 YOLO 文件")
    
    print("\n[5/6] 加载测试集 点云熵结果...")
    pc_test = load_per_frame_results(PC_TEST_FOLDER)
    print(f"      加载了 {len(pc_test)} 个测试集点云文件")
    
    print("\n[6/6] 开始对测试集进行贝叶斯决策级融合...")
    process_fusion(yolo_test, pc_test, FUSION_TEST_FOLDER)
    
    print("\n" + "=" * 70)
    print("所有融合任务完成！")
    print("=" * 70)
    print(f"\n请查看输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
