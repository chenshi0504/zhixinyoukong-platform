# -*- coding: utf-8 -*-
"""
图像熵结果输出 - 处理YOLO检测数据，计算图像熵
从 input/yolo 目录读取JSON数据，输出到 output/初步output/image_entropy
"""
import os
import json
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "初步output", "image_entropy")

YOLO_VAL = os.path.join(INPUT_DIR, "yolo", "val")
YOLO_TEST = os.path.join(INPUT_DIR, "yolo", "test")


def compute_image_entropy(yolo_data):
    """根据YOLO检测结果计算图像信息熵"""
    results = {}
    total_objects = 0

    for cls_id, info in yolo_data.items():
        count = info.get("count", 0)
        total_objects += count

    if total_objects == 0:
        return results

    for cls_id, info in yolo_data.items():
        cls_name = info.get("class_name", f"class_{cls_id}")
        count = info.get("count", 0)
        mean_conf = info.get("mean_conf", 0)

        if count > 0:
            p = count / total_objects
            entropy = -p * math.log2(p) if p > 0 else 0
        else:
            entropy = 0

        results[cls_name] = {
            "count": count,
            "mean_conf": round(mean_conf, 4),
            "proportion": round(count / total_objects, 4) if total_objects > 0 else 0,
            "entropy_contribution": round(entropy, 4)
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
                yolo_data = json.load(f)
            entropy_result = compute_image_entropy(yolo_data)
            output_path = os.path.join(output_folder, fname)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(entropy_result, f, indent=2, ensure_ascii=False)
            count += 1
        except Exception as e:
            print(f"  处理失败 {fname}: {e}")

    return count


def main():
    print("=" * 60)
    print("图像熵结果输出")
    print("=" * 60)

    val_output = os.path.join(OUTPUT_DIR, "val")
    test_output = os.path.join(OUTPUT_DIR, "test")

    print("\n处理验证集...")
    val_count = process_folder(YOLO_VAL, val_output)
    print(f"  处理了 {val_count} 个文件")

    print("\n处理测试集...")
    test_count = process_folder(YOLO_TEST, test_output)
    print(f"  处理了 {test_count} 个文件")

    print(f"\n完成！共处理 {val_count + test_count} 个文件")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
