"""实时监控对比实验进度"""

import json
import time
from pathlib import Path


def monitor_experiments():
    """监控实验进度"""
    output_dir = Path(__file__).parent / "output"

    print("=" * 60)
    print("多层级协调对比实验 - 实时监控")
    print("=" * 60)
    print()

    modes = ["none", "local", "full"]
    mode_names = {
        "none": "无协调模式",
        "local": "局部协调模式",
        "full": "全局协调模式",
    }

    last_status = {}

    try:
        while True:
            print("\033[2J\033[H")  # 清屏
            print("=" * 60)
            print("实验进度监控")
            print("=" * 60)
            print()

            # 检查各模式的输出文件
            for mode in modes:
                pattern = f"metrics_{mode}_*.json"
                files = list(output_dir.glob(pattern))

                if files:
                    # 使用最新的文件
                    latest_file = sorted(files)[-1]

                    try:
                        with open(latest_file, "r", encoding="utf-8") as f:
                            metrics = json.load(f)

                        if metrics:
                            last_metric = metrics[-1]
                            step = last_metric.get("step", 0)
                            total_vehicles = last_metric.get("total_vehicles", 0)
                            avg_speed = last_metric.get("avg_speed", 0)
                            waiting_count = last_metric.get("waiting_count", 0)

                            status = f"[运行中] 步数: {step}/500"
                            print(f"{mode_names[mode]:12s}: {status}")
                            print(f"  车辆数: {total_vehicles:3d} | 平均速度: {avg_speed:5.2f} m/s | 等待车辆: {waiting_count:3d}")

                            last_status[mode] = step
                        else:
                            print(f"{mode_names[mode]:12s}: [准备中] 等待数据...")

                    except Exception as e:
                        print(f"{mode_names[mode]:12s}: [读取错误] {e}")
                else:
                    if mode in last_status and last_status[mode] >= 500:
                        print(f"{mode_names[mode]:12s}: [已完成] ✓")
                    else:
                        print(f"{mode_names[mode]:12s}: [等待中] 未开始")

                print()

            # 检查是否全部完成
            all_completed = all(
                last_status.get(mode, 0) >= 500 for mode in modes
            )

            if all_completed:
                print("=" * 60)
                print("所有实验已完成！")
                print("=" * 60)
                break

            print("按 Ctrl+C 退出监控...")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n监控已停止")


if __name__ == "__main__":
    monitor_experiments()
