#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OD需求缩放器
根据流量等级生成缩放后的OD文件，供模式0和模式2共同使用
确保两种模式的车辆数量完全一致
"""

import pandas as pd
import os


# 流量等级映射（流量等级 = 百分比）
# 例如：流量等级3 = 3%的OD需求
FLOW_LEVELS = {
    1: 0.01,  # 1% - 低流量
    2: 0.02,  # 2% - 中低流量
    3: 0.03,  # 3% - 中流量
    4: 0.04,  # 4% - 中高流量
    5: 0.05,  # 5% - 高流量
    6: 0.06,  # 6% - 极高流量（可能严重拥堵）
}


def generate_scaled_od(flow_level, data_dir=None, experiment_id=None, output_dir=None):
    """
    根据流量等级生成缩放后的OD文件
    
    Args:
        flow_level: 流量等级（1-6）
        data_dir: 数据目录路径（默认为当前脚本所在目录）
        experiment_id: 实验唯一标识（用于并行实验避免冲突，如 "0_1_X"）
        output_dir: 输出目录（如果提供，则保存到该目录；否则保存到data_dir）
        
    Returns:
        output_file: 生成的OD文件路径
        total_trips: 总行程数
        
    Note:
        - 如果指定output_dir，文件保存到output_dir/SiouxFalls_od_scaled.csv
        - 如果指定experiment_id，文件保存到data_dir/SiouxFalls_od_scaled_{experiment_id}.csv
        - 否则按流量等级命名：data_dir/SiouxFalls_od_scaled_flow{N}.csv（避免覆盖）
    """
    if data_dir is None:
        data_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 获取缩放比例
    if flow_level not in FLOW_LEVELS:
        print(f"Error: Invalid flow level {flow_level}, must be 1-6")
        return None, 0
    
    scale_factor = FLOW_LEVELS[flow_level]
    
    # 读取原始OD文件
    original_od_file = os.path.join(data_dir, "SiouxFalls_od.csv")
    if not os.path.exists(original_od_file):
        print(f"Error: Original OD file not found: {original_od_file}")
        return None, 0
    
    df = pd.read_csv(original_od_file)
    
    # 缩放需求（每个OD对至少1辆车）
    df['Trips'] = df['Ton'].apply(lambda x: max(1, int(x * scale_factor)))
    
    # 计算总行程数
    total_trips = df['Trips'].sum()
    
    # 确定输出目录和文件名
    if output_dir is not None:
        # 指定了输出目录，保存到该目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file = os.path.join(output_dir, "SiouxFalls_od_scaled.csv")
    elif experiment_id is not None:
        # 指定了实验ID（用于并行实验）
        output_file = os.path.join(data_dir, f"SiouxFalls_od_scaled_{experiment_id}.csv")
    else:
        # 按流量等级命名，避免覆盖
        output_file = os.path.join(data_dir, f"SiouxFalls_od_scaled_flow{flow_level}.csv")
    
    # 保存缩放后的OD（保留原始Ton列，添加Trips列）
    df.to_csv(output_file, index=False)
    
    print(f"=" * 50)
    print(f"OD需求缩放完成")
    print(f"=" * 50)
    print(f"  流量等级: {flow_level} ({scale_factor*100:.0f}%)")
    print(f"  原始OD对数: {len(df)}")
    print(f"  总行程数: {total_trips:,} 辆")
    print(f"  输出文件: {os.path.basename(output_file)}")
    print(f"=" * 50)
    
    return output_file, total_trips


def get_scaled_od_path(data_dir=None, flow_level=None, experiment_id=None, output_dir=None):
    """
    获取缩放后OD文件的路径
    
    Args:
        data_dir: 数据目录
        flow_level: 流量等级（用于按流量命名的文件）
        experiment_id: 实验ID（用于并行实验）
        output_dir: 输出目录（如果指定，返回该目录下的文件路径）
    """
    if data_dir is None:
        data_dir = os.path.dirname(os.path.abspath(__file__))
    
    if output_dir is not None:
        return os.path.join(output_dir, "SiouxFalls_od_scaled.csv")
    elif experiment_id is not None:
        return os.path.join(data_dir, f"SiouxFalls_od_scaled_{experiment_id}.csv")
    elif flow_level is not None:
        return os.path.join(data_dir, f"SiouxFalls_od_scaled_flow{flow_level}.csv")
    else:
        # 兼容旧代码
        return os.path.join(data_dir, "SiouxFalls_od_scaled.csv")


def load_scaled_od(data_dir=None):
    """
    加载缩放后的OD需求
    
    Returns:
        df: DataFrame with columns [O, D, Ton, Trips]
        total_trips: 总行程数
    """
    scaled_od_file = get_scaled_od_path(data_dir)
    
    if not os.path.exists(scaled_od_file):
        print(f"Error: Scaled OD file not found: {scaled_od_file}")
        print("Please run generate_scaled_od() first")
        return None, 0
    
    df = pd.read_csv(scaled_od_file)
    total_trips = df['Trips'].sum()
    
    return df, total_trips


def main():
    """独立运行时的交互式界面"""
    print("=" * 50)
    print("SiouxFalls OD需求缩放器")
    print("=" * 50)
    
    print("\n请选择流量等级：")
    for level, scale in FLOW_LEVELS.items():
        print(f"  [{level}] {scale*100:.1f}% OD需求")
    
    while True:
        try:
            flow_input = input("\n请输入流量等级 [1-6]: ").strip()
            flow_level = int(flow_input)
            if flow_level in FLOW_LEVELS:
                break
            else:
                print("❌ 无效输入，请输入 1-6")
        except ValueError:
            print("❌ 无效输入，请输入数字")
        except KeyboardInterrupt:
            print("\n\n用户取消操作")
            return
    
    generate_scaled_od(flow_level)


if __name__ == "__main__":
    main()
