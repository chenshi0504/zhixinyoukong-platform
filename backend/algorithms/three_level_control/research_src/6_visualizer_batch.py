"""
批次对比绘图脚本
接收命令行参数，一次性处理多个配置的对比图

用法: python 5_visualizer_batch.py <configs>
  configs: 用()分组的配置列表，每组生成一张对比图

示例1 - 单组:
  python 5_visualizer_batch.py "(0_1_X,0_2_X,2_1_20,2_1_40)"

示例2 - 多组（生成多张图）:
  python 5_visualizer_batch.py "(0_1_X,2_1_20,2_1_40),(0_3_X,2_3_20,2_3_40)"
"""
import os
import sys
import re

# 导入5_visualizer中的函数
from importlib import import_module

# 获取项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')

# 新目录结构
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
RESULTS_DIR = os.path.join(PROJECT_ROOT, 'results')

# 对比图目录结构：results/comparison/{type}/
COMPARISON_DIR = os.path.join(RESULTS_DIR, 'comparison')
COMPARISON_RUNNING_DIR = os.path.join(COMPARISON_DIR, 'running')
COMPARISON_WAITING_DIR = os.path.join(COMPARISON_DIR, 'waiting')
COMPARISON_ENDED_DIR = os.path.join(COMPARISON_DIR, 'ended_loaded')
COMPARISON_OCCUPANCY_DIR = os.path.join(COMPARISON_DIR, 'occupancy')
COMPARISON_SPEED_DIR = os.path.join(COMPARISON_DIR, 'speed_ratio')
COMPARISON_TABLE_DIR = os.path.join(COMPARISON_DIR, 'table')
COMPARISON_CHART_DIR = os.path.join(COMPARISON_DIR, 'chart')

# 旧目录结构（兼容性，后续可删除）
SUMO_OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output', 'sumo')
EXCEL_DIR = os.path.join(PROJECT_ROOT, 'output', '仿真结果')

# Module name for visualizer (updated from 5 to 6)
VISUALIZER_MODULE = '6_visualizer'


def get_experiment_output_dir(config_name):
    """
    获取实验配置对应的输出目录
    
    新目录结构: output/{config_name}/
    """
    return os.path.join(OUTPUT_DIR, config_name)


def get_experiment_results_dir(config_name):
    """
    获取实验配置对应的结果目录
    
    新目录结构: results/{config_name}/
    """
    exp_dir = os.path.join(RESULTS_DIR, config_name)
    if not os.path.exists(exp_dir):
        os.makedirs(exp_dir)
    return exp_dir


def get_comparison_output_path(configs, suffix):
    """
    获取对比结果的输出路径（直接放在results根目录）
    
    Args:
        configs: 配置列表
        suffix: 文件后缀（如 'running.png'）
    Returns:
        输出文件路径
    """
    prefix = 'comparison_' + '_vs_'.join(configs)
    return os.path.join(RESULTS_DIR, f'{prefix}_{suffix}')


def get_data_file_path(config_name, file_type):
    """
    获取数据文件路径（优先使用新目录结构，回退到旧目录结构）
    
    Args:
        config_name: 配置名称（如 '0_3_X', '1_1_3_X'）
        file_type: 文件类型（'summary', 'edgedata', 'excel'）
    Returns:
        文件路径
    """
    # 新目录结构
    new_dir = get_experiment_output_dir(config_name)
    
    if file_type == 'summary':
        new_path = os.path.join(new_dir, 'summary.xml')
        old_path = os.path.join(SUMO_OUTPUT_DIR, f'summary_{config_name}.xml')
    elif file_type == 'edgedata':
        new_path = os.path.join(new_dir, 'edgedata.xml')
        old_path = os.path.join(SUMO_OUTPUT_DIR, f'edgedata_{config_name}.xml')
    elif file_type == 'excel':
        # 优先查找results.xlsx，回退到仿真结果.xlsx
        new_path = os.path.join(new_dir, 'results.xlsx')
        new_path_alt = os.path.join(new_dir, '仿真结果.xlsx')
        old_path = os.path.join(EXCEL_DIR, f'仿真结果_{config_name}.xlsx')
        # 检查备选路径
        if not os.path.exists(new_path) and os.path.exists(new_path_alt):
            new_path = new_path_alt
    else:
        return None
    
    # 优先使用新目录结构
    if os.path.exists(new_path):
        return new_path
    elif os.path.exists(old_path):
        return old_path
    else:
        return new_path  # 返回新路径（即使不存在，用于错误提示）


def ensure_dirs():
    """确保输出目录存在"""
    # 对比图分类目录
    for dir_path in [COMPARISON_RUNNING_DIR, COMPARISON_WAITING_DIR, COMPARISON_ENDED_DIR, 
                     COMPARISON_OCCUPANCY_DIR, COMPARISON_SPEED_DIR, COMPARISON_TABLE_DIR, 
                     COMPARISON_CHART_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)


def batch_comparison_plot(configs_str):
    """
    批次对比绘图
    
    Args:
        configs_str: 逗号分隔的配置字符串，如 "0_1_X,0_2_X,2_1_20"
    """
    # 导入可视化模块的函数
    visualizer_module = import_module(VISUALIZER_MODULE)
    parse_summary_data = visualizer_module.parse_summary_data
    plot_comparison_running_waiting = visualizer_module.plot_comparison_running_waiting
    plot_comparison_waiting = visualizer_module.plot_comparison_waiting
    plot_comparison_ended_loaded = visualizer_module.plot_comparison_ended_loaded
    plot_occupancy_comparison = visualizer_module.plot_occupancy_comparison
    plot_excel_comparison = visualizer_module.plot_excel_comparison
    plot_speed_ratio_comparison = visualizer_module.plot_speed_ratio_comparison
    NetworkFlowVisualizer = visualizer_module.NetworkFlowVisualizer
    
    # 解析配置列表
    configs = [c.strip() for c in configs_str.split(',') if c.strip()]
    
    if not configs:
        print("错误：未提供任何配置！")
        return
    
    print("=" * 60)
    print("Batch Comparison Plot Tool")
    print("=" * 60)
    print(f"\n共 {len(configs)} 个配置:")
    for i, config in enumerate(configs, 1):
        print(f"  [{i}] {config}")
    print()
    
    # 确保输出目录存在
    ensure_dirs()
    
    # ========== 数据加载检查阶段 ==========
    print("\n--- 数据加载检查 ---")
    configs_data = {}
    failed_configs = []
    
    for config in configs:
        # 使用新的路径获取函数
        summary_file = get_data_file_path(config, 'summary')
        
        data = parse_summary_data(summary_file)
        if data:
            configs_data[config] = data
            print(f"  [OK] {config} (from {os.path.dirname(summary_file)})")
        else:
            failed_configs.append(config)
            print(f"  [FAIL] {config} - 文件不存在或无法解析: {summary_file}")
    
    # ========== 加载结果汇总 ==========
    print("\n--- 加载结果汇总 ---")
    print(f"  成功: {len(configs_data)}/{len(configs)}")
    print(f"  失败: {len(failed_configs)}/{len(configs)}")
    
    if not configs_data:
        print("\n错误：没有成功加载任何配置数据！")
        return
    
    # ========== 如果有加载失败的配置，提示用户确认 ==========
    if failed_configs:
        print("\n" + "!" * 60)
        print("警告：以下配置加载失败:")
        for fc in failed_configs:
            print(f"  - {fc}")
        print("!" * 60)
        print("\n是否继续处理已成功加载的配置？")
        print(f"  将处理: {list(configs_data.keys())}")
        
        user_input = input("\n输入 'yes' 继续，其他任意键取消: ").strip().lower()
        if user_input != 'yes':
            print("\n已取消操作。")
            return
        print("\n继续处理...")
    
    # 根据配置数量决定输出目录和文件名格式
    is_single_config = len(configs_data) == 1
    
    # 使用成功加载的配置列表（保持原始顺序）
    loaded_configs = [c for c in configs if c in configs_data]
    
    if is_single_config:
        # 单配置：输出到 results/{config_name}/
        config_name = loaded_configs[0]
        output_base_dir = get_experiment_results_dir(config_name)
        prefix = ''  # 单配置不需要前缀
        print(f"\n开始绘制单配置图表: {config_name}")
        print(f"  输出目录: {output_base_dir}")
    else:
        # 多配置对比：输出到 results/comparison/{type}/ 分类目录
        output_base_dir = COMPARISON_DIR  # 设置基础目录
        # 使用原始顺序生成 prefix（如 0_6_X_vs_1_1_6_X_vs_2_1_6_40_vs_3_1_1_6_40）
        prefix = '_vs_'.join(loaded_configs)
        # 如果文件名太长，使用简化版本
        if len(prefix) > 100:
            prefix = f'{len(loaded_configs)}configs'
        print(f"\n开始绘制对比图 ({len(loaded_configs)} 个配置)...")
        print(f"  输出目录: {COMPARISON_DIR}/")
    
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    
    # 1. 绘制运行中车辆图
    print("\n[1/8] 生成运行中车辆对比图...")
    if is_single_config:
        output_file1 = os.path.join(output_base_dir, 'running.svg')
    else:
        output_file1 = os.path.join(COMPARISON_RUNNING_DIR, f'{prefix}.svg')
    plot_comparison_running_waiting(configs_data, output_file1)
    
    # 2. 绘制等待车辆图
    print("\n[2/8] 生成等待车辆对比图...")
    if is_single_config:
        output_file_waiting = os.path.join(output_base_dir, 'waiting.svg')
    else:
        output_file_waiting = os.path.join(COMPARISON_WAITING_DIR, f'{prefix}.svg')
    plot_comparison_waiting(configs_data, output_file_waiting)
    
    # 3. 绘制完成和加载车辆图
    print("\n[3/8] 生成完成车辆对比图...")
    if is_single_config:
        output_file2 = os.path.join(output_base_dir, 'ended_loaded.svg')
    else:
        output_file2 = os.path.join(COMPARISON_ENDED_DIR, f'{prefix}.svg')
    plot_comparison_ended_loaded(configs_data, output_file2)
    
    # 4. 生成占有率图
    print("\n[4/8] 生成路网占有率对比图...")
    if is_single_config:
        config_name = list(configs_data.keys())[0]
        edgedata_file = get_data_file_path(config_name, 'edgedata')
        if os.path.exists(edgedata_file):
            visualizer = NetworkFlowVisualizer(net_file)
            edge_stats = visualizer.parse_edgedata(edgedata_file)
            if edge_stats:
                visualizer.plot_multiple_metrics(edge_stats, output_base_dir, prefix='')
    else:
        # 多配置对比：输出到 comparison/occupancy/
        plot_occupancy_comparison_new(configs_data, net_file, COMPARISON_OCCUPANCY_DIR, prefix)
    
    # 5. 生成仿真结果合并表格
    print("\n[5/8] 生成仿真结果合并表格...")
    if is_single_config:
        table_output_dir = output_base_dir
        table_prefix = ''
    else:
        table_output_dir = COMPARISON_TABLE_DIR
        table_prefix = prefix
    plot_excel_comparison_new(configs, table_output_dir, table_prefix)
    
    # 6. 生成路段速度比对比图
    print("\n[6/8] 生成路段速度比对比图...")
    if is_single_config:
        speed_output_dir = output_base_dir
        speed_prefix = ''
    else:
        speed_output_dir = COMPARISON_SPEED_DIR
        speed_prefix = prefix
    plot_speed_ratio_comparison_new(configs, net_file, speed_output_dir, speed_prefix)
    
    # 7. 生成对比图（车均延误柱状图 + 总油耗折线图）
    print("\n[7/8] 生成对比图...")
    plot_penetration_comparison = visualizer_module.plot_penetration_comparison
    if is_single_config:
        excel_file = os.path.join(output_base_dir, '仿真结果.xlsx')
        comparison_output_dir = output_base_dir
        comparison_prefix = ''
    else:
        excel_file = os.path.join(COMPARISON_TABLE_DIR, f'{prefix}_合并结果.xlsx')
        comparison_output_dir = COMPARISON_CHART_DIR
        comparison_prefix = prefix
    if os.path.exists(excel_file):
        plot_penetration_comparison(excel_file, comparison_output_dir, comparison_prefix)
    else:
        print(f"  跳过（Excel文件不存在: {excel_file}）")
    
    # 8. 生成路由变更分析图
    print("\n[8/8] 生成路由变更分析图...")
    analyze_route_changes_batch = visualizer_module.analyze_route_changes_batch
    
    # 筛选出有路由变更记录的配置（模式2和3）
    route_configs = [c for c in configs if c.split('_')[0] in ['2', '2.0', '2.1', '2_0', '2_1', '3']]
    if route_configs:
        analyze_route_changes_batch_new(route_configs, output_base_dir)
    else:
        print("  跳过（无路径诱导配置）")
    
    route_analysis_dir = output_base_dir if is_single_config else os.path.join(RESULTS_DIR, 'route_analysis')
    
    print("\n" + "=" * 60)
    print("图表绘制完成！")
    print("=" * 60)
    print(f"\n输出目录: {output_base_dir}")
    if is_single_config:
        print(f"  所有图表保存在配置目录下")
    else:
        print(f"  对比图保存在results根目录")


def plot_occupancy_comparison_new(configs_data, net_file, output_dir, prefix):
    """
    生成占有率对比图（新目录结构，支持差值图模式）
    第一张是基准模型绝对值，后续是与基准的差值图
    """
    visualizer_module = import_module(VISUALIZER_MODULE)
    NetworkFlowVisualizer = visualizer_module.NetworkFlowVisualizer
    plot_occupancy_comparison = visualizer_module.plot_occupancy_comparison
    
    config_list = list(configs_data.keys())
    
    if len(config_list) == 1:
        # 单配置：生成绝对值图
        config = config_list[0]
        edgedata_file = get_data_file_path(config, 'edgedata')
        if os.path.exists(edgedata_file):
            visualizer = NetworkFlowVisualizer(net_file)
            edge_stats = visualizer.parse_edgedata(edgedata_file)
            if edge_stats:
                config_prefix = f'{prefix}_{config}' if prefix else config
                visualizer.plot_multiple_metrics(edge_stats, output_dir, prefix=config_prefix)
    else:
        # 多配置：使用差值图模式
        # 构建临时目录映射（兼容原有函数接口）
        import tempfile
        import shutil
        
        # 创建临时目录存放edgedata文件的符号链接
        temp_dir = tempfile.mkdtemp()
        try:
            for config in config_list:
                src_file = get_data_file_path(config, 'edgedata')
                if os.path.exists(src_file):
                    dst_file = os.path.join(temp_dir, f'edgedata_{config}.xml')
                    shutil.copy2(src_file, dst_file)
            
            # 调用带差值图模式的函数
            plot_occupancy_comparison(configs_data, temp_dir, net_file, output_dir, prefix, 
                                     diff_mode=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def plot_excel_comparison_new(configs, output_dir, prefix):
    """
    生成仿真结果合并表格（新目录结构）
    
    将多个配置的results.xlsx合并为一个表格，格式为：
    指标 | config1 | config2 | ...
    """
    import pandas as pd
    
    # 指标名称映射（英文→中文）
    metric_map = {
        'Average Delay (s)': '车均延误(秒)',
        'Total Travel Time (s)': '总行程时间(秒)',
        'Total Fuel (L)': '总油耗(升)',
        'Throughput': '通过量(辆)',
        'Vehicle Count': '车辆数',
        'CAV Count': 'CAV数量',
        'CAV Percent': 'CAV比例',
        'Flow Level': '流量等级',
        'Runtime (s)': 'Runtime (s)'
    }
    
    # 收集所有配置的数据
    config_data = {}
    for config in configs:
        excel_file = get_data_file_path(config, 'excel')
        if os.path.exists(excel_file):
            try:
                df = pd.read_excel(excel_file)
                # 转换为字典 {Metric: Value}
                data_dict = dict(zip(df['Metric'], df['Value']))
                config_data[config] = data_dict
                print(f"    加载: {config}")
            except Exception as e:
                print(f"    警告: 无法加载 {config}: {e}")
    
    if not config_data:
        print("    警告: 没有成功加载任何配置数据")
        return
    
    # 构建合并表格
    # 选择关键指标（包含 Runtime）
    key_metrics = ['Average Delay (s)', 'Total Travel Time (s)', 'Total Fuel (L)', 
                   'Throughput', 'Vehicle Count', 'Runtime (s)']
    
    rows = []
    for metric in key_metrics:
        row = {'指标': metric_map.get(metric, metric)}
        for config, data in config_data.items():
            row[config] = data.get(metric, '')
        rows.append(row)
    
    merged_df = pd.DataFrame(rows)
    
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    if prefix:
        output_file = os.path.join(output_dir, f'{prefix}_合并结果.xlsx')
    else:
        output_file = os.path.join(output_dir, '合并结果.xlsx')
    merged_df.to_excel(output_file, index=False)
    print(f"    保存: {output_file}")


def plot_speed_ratio_comparison_new(configs, net_file, output_dir, prefix):
    """
    生成路段速度比对比图（新目录结构，支持差值图模式）
    第一张是基准模型绝对值，后续是与基准的差值图
    """
    import tempfile
    import shutil
    
    visualizer_module = import_module(VISUALIZER_MODULE)
    if hasattr(visualizer_module, 'plot_speed_ratio_comparison'):
        # 构建edgedata文件列表
        edgedata_files = {}
        for config in configs:
            edgedata_file = get_data_file_path(config, 'edgedata')
            if os.path.exists(edgedata_file):
                edgedata_files[config] = edgedata_file
        
        if edgedata_files:
            # 创建临时目录存放edgedata文件
            temp_dir = tempfile.mkdtemp()
            try:
                for config, src_file in edgedata_files.items():
                    dst_file = os.path.join(temp_dir, f'edgedata_{config}.xml')
                    shutil.copy2(src_file, dst_file)
                
                # 调用带差值图模式的函数
                visualizer_module.plot_speed_ratio_comparison(
                    list(edgedata_files.keys()), 
                    temp_dir,
                    net_file, 
                    output_dir, 
                    prefix,
                    diff_mode=True  # 启用差值图模式
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)


def analyze_route_changes_batch_new(configs, output_dir):
    """
    分析路由变更（新目录结构）
    """
    visualizer_module = import_module(VISUALIZER_MODULE)
    if hasattr(visualizer_module, 'analyze_route_changes_batch'):
        # 新目录结构：route_changes.xml 在各配置目录下
        for config in configs:
            config_dir = get_experiment_output_dir(config)
            route_file = os.path.join(config_dir, 'route_changes.xml')
            if os.path.exists(route_file):
                print(f"    分析: {config}")
                # 调用单配置分析
                try:
                    visualizer_module.analyze_route_changes_batch([config], config_dir, output_dir)
                except Exception as e:
                    print(f"    警告: {config} 分析失败: {e}")


def parse_groups(input_str):
    """
    解析分组输入
    
    Args:
        input_str: 输入字符串，如 "(0_1_X,2_1_20),(0_3_X,2_3_40)"
        
    Returns:
        list: 分组列表，每组是配置字符串
    """
    # 使用正则表达式匹配括号内的内容
    pattern = r'\(([^)]+)\)'
    matches = re.findall(pattern, input_str)
    
    if matches:
        return matches
    else:
        # 如果没有括号，当作单组处理（兼容旧格式）
        return [input_str]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python 5_visualizer_batch.py <configs>")
        print()
        print("示例1 - 单组对比:")
        print('  python 5_visualizer_batch.py "(0_1_X,0_2_X,2_1_20,2_1_40)"')
        print()
        print("示例2 - 多组对比（生成多张图）:")
        print('  python 5_visualizer_batch.py "(0_1_X,2_1_20),(0_3_X,2_3_40),(0_5_X,2_5_60)"')
        sys.exit(1)
    
    # 合并所有参数（处理空格问题）
    input_str = ''.join(sys.argv[1:])
    
    # 解析分组
    groups = parse_groups(input_str)
    
    print("=" * 60)
    print(f"检测到 {len(groups)} 组对比任务")
    print("=" * 60)
    
    for i, group in enumerate(groups, 1):
        print(f"\n第 {i}/{len(groups)} 组: {group}")
        print("-" * 60)
        batch_comparison_plot(group)
    
    print("\n" + "=" * 60)
    print(f"全部 {len(groups)} 组对比图生成完成！")
    print("=" * 60)
