# -*- coding: utf-8 -*-
"""
点云熵结果输出 - 处理点云数据，计算点云熵
从 input/pointcloud 目录读取JSON数据，输出到 output/初步output/pointcloud_entropy
"""
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "初步output", "pointcloud_entropy")

PC_VAL = os.path.join(INPUT_DIR, "pointcloud", "val")
PC_TEST = os.path.join(INPUT_DIR, "pointcloud", "test")


def process_pointcloud_entropy(pc_data):
    """处理点云数据，提取熵值信息"""
    results = {}
    for cls_name, info in pc_data.items():
        entropy = info.get("entropy", 0)
        count = info.get("count", 0)
        results[cls_name] = {
            "entropy": round(entropy, 4),
            "count": count,
            "processed": True
        }
    return results


def process_folder(input_folder, output_folder):
    """处理一个文件夹中的所有JSON文件"""
    os.makedirs(output_folder, exist_ok=True)
    count = 0

    if not os.path.exists(input_folder):
        print(f"  警告: 输入目录不存在 - {input_folder}")
        return count

    for fname in sorted(os.listdir(input_folder)):
        if not fname.endswith('.json'):
            continue
        filepath = os.path.join(input_folder, fname)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                pc_data = json.load(f)
            result = process_pointcloud_entropy(pc_data)
            output_path = os.path.join(output_folder, fname)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            count += 1
        except Exception as e:
            print(f"  处理失败 {fname}: {e}")

    return count


def main():
    print("=" * 60)
    print("点云熵结果输出")
    print("=" * 60)

    val_output = os.path.join(OUTPUT_DIR, "val")
    test_output = os.path.join(OUTPUT_DIR, "test")

    print("\n处理验证集...")
    val_count = process_folder(PC_VAL, val_output)
    print(f"  处理了 {val_count} 个文件")

    print("\n处理测试集...")
    test_count = process_folder(PC_TEST, test_output)
    print(f"  处理了 {test_count} 个文件")

    print(f"\n完成！共处理 {val_count + test_count} 个文件")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
