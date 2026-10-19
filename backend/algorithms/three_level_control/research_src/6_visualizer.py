"""
路网流量可视化模块
基于SUMO的edgedata输出和路网数据，绘制路段流量强度分布图
"""
import os
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端，避免Tkinter错误
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
import sumolib


class NetworkFlowVisualizer:
    """路网流量可视化器"""
    
    def __init__(self, net_file, net_csv=None, node_csv=None):
        """
        初始化可视化器
        
        Args:
            net_file: SUMO路网文件(.net.xml)
            net_csv: 路网CSV文件（可选，用于补充信息）
            node_csv: 节点CSV文件（可选，用于补充信息）
        """
        self.net = sumolib.net.readNet(net_file)
        self.net_csv = net_csv
        self.node_csv = node_csv
        
        # 读取CSV数据（如果提供）
        self.df_net = None
        self.df_node = None
        if net_csv and os.path.exists(net_csv):
            self.df_net = pd.read_csv(net_csv)
        if node_csv and os.path.exists(node_csv):
            self.df_node = pd.read_csv(node_csv)
    
    def parse_edgedata(self, edgedata_file):
        """
        解析edgedata文件，提取路段流量信息
        
        Args:
            edgedata_file: edgedata.xml文件路径
            
        Returns:
            dict: {edge_id: {'flow': avg_flow, 'speed': avg_speed, 'occupancy': avg_occupancy}}
        """
        if not os.path.exists(edgedata_file):
            print(f"Warning: edgedata file not found: {edgedata_file}")
            return {}
        
        try:
            tree = ET.parse(edgedata_file)
            root = tree.getroot()
            
            # 存储每条边的所有时间步数据
            edge_data = {}
            
            for interval in root.findall('interval'):
                for edge in interval.findall('edge'):
                    edge_id = edge.get('id')
                    
                    if edge_id not in edge_data:
                        edge_data[edge_id] = {
                            'flows': [],
                            'speeds': [],
                            'occupancies': [],
                            'samples': []
                        }
                    
                    # 提取数据
                    departed = float(edge.get('departed', 0))
                    arrived = float(edge.get('arrived', 0))
                    entered = float(edge.get('entered', 0))
                    left = float(edge.get('left', 0))
                    speed = float(edge.get('speed', 0))
                    occupancy = float(edge.get('occupancy', 0))
                    samples = float(edge.get('sampledSeconds', 0))  # 修复：使用float而不是int
                    
                    # 计算流量（进入+出发）
                    flow = entered + departed
                    
                    edge_data[edge_id]['flows'].append(flow)
                    edge_data[edge_id]['speeds'].append(speed)
                    edge_data[edge_id]['occupancies'].append(occupancy)
                    edge_data[edge_id]['samples'].append(samples)
            
            # 计算平均值
            edge_stats = {}
            for edge_id, data in edge_data.items():
                edge_stats[edge_id] = {
                    'avg_flow': np.mean(data['flows']) if data['flows'] else 0,
                    'max_flow': np.max(data['flows']) if data['flows'] else 0,
                    'avg_speed': np.mean(data['speeds']) if data['speeds'] else 0,
                    'avg_occupancy': np.mean(data['occupancies']) if data['occupancies'] else 0,
                    'total_samples': sum(data['samples'])
                }
            
            print(f"Successfully parsed flow data for {len(edge_stats)} edges")
            return edge_stats
            
        except Exception as e:
            print(f"Error parsing edgedata file: {e}")
            return {}
    
    def plot_network_flow(self, edge_stats, output_file, metric='avg_flow', 
                         title='路网流量分布图', cmap='YlOrRd', figsize=(16, 12)):
        """
        绘制路网流量分布图（带方向偏移，区分正反方向）
        
        Args:
            edge_stats: 路段统计数据字典
            output_file: 输出图片文件路径
            metric: 要可视化的指标 ('avg_flow', 'max_flow', 'avg_speed', 'avg_occupancy')
            title: 图表标题
            cmap: 颜色映射
            figsize: 图片尺寸
        """
        if not edge_stats:
            print("No edge data available")
            return
        
        # 创建图形
        fig, ax = plt.subplots(figsize=figsize)
        
        # 收集所有路段的几何信息和流量值
        segments = []
        values = []
        
        # 偏移量（用于区分正反方向）
        offset_distance = 15  # 偏移距离（米）
        
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            
            # 跳过内部边
            if edge_id.startswith(':'):
                continue
            
            # 获取流量数据
            if edge_id in edge_stats:
                value = edge_stats[edge_id].get(metric, 0)
            else:
                value = 0
            
            # 获取边的形状（坐标序列）
            shape = edge.getShape()
            
            # 计算偏移后的形状（向右侧偏移）
            offset_shape = self._offset_shape(shape, offset_distance)
            
            # 将偏移后的形状转换为线段
            for i in range(len(offset_shape) - 1):
                segments.append([offset_shape[i], offset_shape[i+1]])
                values.append(value)
        
        # 归一化值用于颜色映射
        values = np.array(values)
        if values.max() > 0:
            norm_values = values / values.max()
        else:
            norm_values = values
        
        # 创建线集合
        lc = LineCollection(segments, cmap=cmap, linewidths=3)
        lc.set_array(norm_values)
        lc.set_clim(0, 1)
        
        # 添加到图中
        ax.add_collection(lc)
        
        # 设置坐标轴范围
        bounds = self.net.getBoundary()
        margin = 50  # 边距
        ax.set_xlim(bounds[0] - margin, bounds[2] + margin)
        ax.set_ylim(bounds[1] - margin, bounds[3] + margin)
        
        # 添加颜色条
        cbar = plt.colorbar(lc, ax=ax, fraction=0.046, pad=0.04)
        
        # 设置颜色条标签
        metric_labels = {
            'avg_flow': f'Average Flow (max: {values.max():.1f} veh/interval)',
            'max_flow': f'Maximum Flow (max: {values.max():.1f} veh/interval)',
            'avg_speed': f'Average Speed (max: {values.max():.1f} m/s)',
            'avg_occupancy': f'Average Occupancy (max: {values.max():.3f})'
        }
        cbar.set_label(metric_labels.get(metric, metric), fontsize=12)
        
        # 设置标题和标签
        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('X Coordinate (m)', fontsize=12)
        ax.set_ylabel('Y Coordinate (m)', fontsize=12)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        
        # 添加统计信息
        stats_text = f'Total Edges: {len(edge_stats)}\n'
        stats_text += f'Average: {values.mean():.2f}\n'
        stats_text += f'Maximum: {values.max():.2f}\n'
        stats_text += f'Minimum: {values.min():.2f}'
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # 保存图片
        plt.tight_layout()
        plt.savefig(output_file, format='svg', bbox_inches='tight')
        print(f"Flow distribution map saved to: {output_file}")
        plt.close()
    
    def _offset_shape(self, shape, distance):
        """
        将形状向右侧偏移指定距离
        
        Args:
            shape: 原始坐标序列 [(x1,y1), (x2,y2), ...]
            distance: 偏移距离
            
        Returns:
            偏移后的坐标序列
        """
        if len(shape) < 2:
            return shape
        
        offset_shape = []
        
        for i in range(len(shape)):
            if i == 0:
                # 第一个点：使用第一段的方向
                dx = shape[1][0] - shape[0][0]
                dy = shape[1][1] - shape[0][1]
            elif i == len(shape) - 1:
                # 最后一个点：使用最后一段的方向
                dx = shape[-1][0] - shape[-2][0]
                dy = shape[-1][1] - shape[-2][1]
            else:
                # 中间点：使用前后两段的平均方向
                dx = shape[i+1][0] - shape[i-1][0]
                dy = shape[i+1][1] - shape[i-1][1]
            
            # 计算单位法向量（向右侧）
            length = np.sqrt(dx*dx + dy*dy)
            if length > 0:
                # 右侧法向量：(dy, -dx) / length
                nx = dy / length
                ny = -dx / length
            else:
                nx, ny = 0, 0
            
            # 偏移点
            new_x = shape[i][0] + nx * distance
            new_y = shape[i][1] + ny * distance
            offset_shape.append((new_x, new_y))
        
        return offset_shape
    
    def plot_multiple_metrics(self, edge_stats, output_dir, prefix='flow_viz'):
        """
        绘制占有率分布图（仅保留occupancy）
        
        Args:
            edge_stats: 路段统计数据字典
            output_dir: 输出目录
            prefix: 文件名前缀
        """
        # 只绘制占有率图，使用绿色系
        output_file = os.path.join(output_dir, f'{prefix}_occupancy.svg')
        self.plot_network_flow(edge_stats, output_file, metric='avg_occupancy', 
                              title='Network Occupancy Distribution', cmap='Greens')
    
    def generate_flow_report(self, edge_stats, output_file):
        """
        生成流量统计报告
        
        Args:
            edge_stats: 路段统计数据字典
            output_file: 输出Excel文件路径
        """
        if not edge_stats:
            print("No edge data available")
            return
        
        # 准备数据
        data = []
        for edge_id, stats in edge_stats.items():
            edge = self.net.getEdge(edge_id)
            
            row = {
                'Edge ID': edge_id,
                'From Node': edge.getFromNode().getID(),
                'To Node': edge.getToNode().getID(),
                'Length(m)': edge.getLength(),
                'Lanes': edge.getLaneNumber(),
                'Avg Flow': stats['avg_flow'],
                'Max Flow': stats['max_flow'],
                'Avg Speed(m/s)': stats['avg_speed'],
                'Avg Occupancy': stats['avg_occupancy'],
                'Total Samples(s)': stats['total_samples']
            }
            
            # 如果有CSV数据，添加额外信息
            if self.df_net is not None:
                try:
                    # CSV文件使用A和B列表示起点和终点
                    net_info = self.df_net[self.df_net['A'] == int(edge.getFromNode().getID())]
                    if not net_info.empty:
                        row['Capacity(veh/h)'] = net_info.iloc[0].get('capacity', 'N/A')
                        row['Free flow time(s)'] = net_info.iloc[0].get('a0', 'N/A')
                except:
                    pass  # 如果CSV数据不可用，跳过
            
            data.append(row)
        
        # 创建DataFrame
        df = pd.DataFrame(data)
        
        # 按平均流量排序
        df = df.sort_values('Avg Flow', ascending=False)
        
        # 保存到Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Edge Flow Statistics', index=False)
            
            # 添加汇总统计
            summary_data = {
                'Metric': ['Total Edges', 'Avg Flow', 'Max Flow', 'Avg Speed', 'Avg Occupancy'],
                'Value': [
                    len(df),
                    df['Avg Flow'].mean(),
                    df['Max Flow'].max(),
                    df['Avg Speed(m/s)'].mean(),
                    df['Avg Occupancy'].mean()
                ]
            }
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
        
        print(f"Flow statistics report saved to: {output_file}")


def parse_summary_data(summary_file):
    """
    解析summary.xml文件，提取时间序列数据
    
    Args:
        summary_file: summary.xml文件路径
        
    Returns:
        dict: 包含时间序列数据的字典
    """
    if not os.path.exists(summary_file):
        print(f"Warning: summary file not found: {summary_file}")
        return None
    
    try:
        tree = ET.parse(summary_file)
        root = tree.getroot()
        
        times = []
        running = []
        waiting = []
        ended = []
        loaded = []
        
        for step in root.findall('step'):
            times.append(float(step.get('time', 0)))
            running.append(int(step.get('running', 0)))
            waiting.append(int(step.get('waiting', 0)))
            ended.append(int(step.get('ended', 0)))
            loaded.append(int(step.get('loaded', 0)))
        
        return {
            'times': times,
            'running': running,
            'waiting': waiting,
            'ended': ended,
            'loaded': loaded
        }
    except Exception as e:
        print(f"Error parsing summary file: {e}")
        return None


def plot_time_series(summary_file, output_file):
    """
    绘制时间序列图表（车辆数随时间变化）- 保留原有功能用于兼容
    
    Args:
        summary_file: summary.xml文件路径
        output_file: 输出图片路径
    """
    data = parse_summary_data(summary_file)
    if data is None:
        return
    
    try:
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # 子图1：运行中和等待中的车辆
        ax1.plot(data['times'], data['running'], label='Running Vehicles', linewidth=2, color='#1d9bf7')
        ax1.plot(data['times'], data['waiting'], label='Waiting Vehicles', linewidth=2, color='#fe5357')
        ax1.set_xlabel('Simulation Time (s)', fontsize=12)
        ax1.set_ylabel('Number of Vehicles', fontsize=12)
        ax1.set_title('Vehicle Status Over Time', fontsize=14, fontweight='bold', pad=40)
        ax1.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=2, framealpha=0.9)
        ax1.grid(True, alpha=0.3)
        
        # 子图2：累计完成和加载的车辆
        ax2.plot(data['times'], data['ended'], label='Completed Trips', linewidth=2, color='#8386fc')
        ax2.plot(data['times'], data['loaded'], label='Loaded Vehicles', linewidth=2, color='#dd7c1a')
        ax2.set_xlabel('Simulation Time (s)', fontsize=12)
        ax2.set_ylabel('Cumulative Count', fontsize=12)
        ax2.set_title('Cumulative Vehicle Statistics', fontsize=14, fontweight='bold', pad=40)
        ax2.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=2, framealpha=0.9)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, format='svg', bbox_inches='tight')
        print(f"Time series plot saved to: {output_file}")
        plt.close()
        
    except Exception as e:
        print(f"Error generating time series plot: {e}")


def plot_comparison_running_waiting(configs_data, output_file, baseline_config=None):
    """
    绘制多个配置的运行中车辆对比图（仅Running，不含Waiting）
    上图：全时段概览；下图：600s到仿真结束的详细图
    在图例中标注相对基准的平均变化百分比
    
    Args:
        configs_data: 字典，格式为 {config_name: data_dict}
        output_file: 输出图片路径
        baseline_config: 基准配置名称（默认为第一个以'0_'开头的配置或第一个配置）
    """
    if not configs_data:
        print("No data to plot")
        return
    
    print(f"  Plotting {len(configs_data)} configurations: {list(configs_data.keys())}")
    
    try:
        # 确定基准配置
        if baseline_config is None:
            # 优先选择以'0_'开头的配置作为基准
            for name in configs_data.keys():
                if name.startswith('0_'):
                    baseline_config = name
                    break
            if baseline_config is None:
                baseline_config = list(configs_data.keys())[0]
        
        baseline_data = configs_data.get(baseline_config)
        
        # 创建上下两个子图
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[1, 1])
        
        # 定义颜色方案（统一配色：暖色、冷色、暗色对比）
        colors = ['#fe5357', '#1d9bf7', '#8386fc', '#dd7c1a', '#ffbd15', '#0ddbf5', '#303cf9', '#388E3C']
        
        # 找到仿真结束时间
        max_time = 0
        for config_name, data in configs_data.items():
            if data['times']:
                max_time = max(max_time, max(data['times']))
        
        # 详细图的时间范围：600s 到 3600s
        detail_start = 600
        detail_end = 3600
        
        # 计算基准的平均running值（用于百分比计算）
        baseline_avg = np.mean(baseline_data['running']) if baseline_data else 0
        
        # 绘制两个子图
        idx = 0
        for config_name, data in configs_data.items():
            color = colors[idx % len(colors)]
            
            # 计算相对基准的变化百分比
            avg_running = np.mean(data['running'])
            if baseline_avg > 0 and config_name != baseline_config:
                pct_change = (avg_running - baseline_avg) / baseline_avg * 100
                pct_str = f' ({pct_change:+.1f}%)' if pct_change != 0 else ''
                # 根据变化方向设置标签颜色提示
                label_suffix = pct_str
            else:
                label_suffix = ' (Baseline)' if config_name == baseline_config else ''
            
            label = f'{config_name}{label_suffix}'
            print(f"    Drawing {config_name}: {len(data['times'])} data points, color={color}")
            
            # 上图：全时段
            ax1.plot(data['times'], data['running'], label=label, 
                    linewidth=2, color=color, linestyle='-')
            
            # 下图：600s到结束的详细图
            ax2.plot(data['times'], data['running'], label=label, 
                    linewidth=2, color=color, linestyle='-')
            idx += 1
        
        # 上图设置
        ax1.set_xlabel('Simulation Time (s)', fontsize=12)
        ax1.set_ylabel('Number of Running Vehicles', fontsize=12)
        ax1.set_title('(a) Running Vehicles - Full Time Range', fontsize=13, fontweight='bold', pad=40)
        ax1.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, 1.12), 
                  ncol=min(len(configs_data), 3), framealpha=0.9)
        ax1.grid(True, alpha=0.3)
        
        # 在上图标记详细图区域
        ax1.axvspan(detail_start, detail_end, alpha=0.15, color='#1d9bf7', label='Detail region')
        ax1.axvline(x=detail_start, color='#1d9bf7', linestyle='--', linewidth=1.5, alpha=0.7)
        
        # 下图设置
        ax2.set_xlim(detail_start, detail_end)
        ax2.set_xlabel('Simulation Time (s)', fontsize=12)
        ax2.set_ylabel('Number of Running Vehicles', fontsize=12)
        ax2.set_title(f'(b) Running Vehicles - Detail View ({detail_start}s ~ {int(detail_end)}s)', 
                     fontsize=13, fontweight='bold', pad=40)
        ax2.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, 1.12),
                  ncol=min(len(configs_data), 3), framealpha=0.9)
        ax2.grid(True, alpha=0.3)
        
        # 自动调整下图Y轴范围
        detail_running_values = []
        for config_name, data in configs_data.items():
            for t, r in zip(data['times'], data['running']):
                if detail_start <= t <= detail_end:
                    detail_running_values.append(r)
        
        if detail_running_values:
            y_min = min(detail_running_values) * 0.95
            y_max = max(detail_running_values) * 1.05
            ax2.set_ylim(y_min, y_max)
        
        plt.tight_layout()
        plt.savefig(output_file, format='svg', bbox_inches='tight', facecolor='white')
        print(f"Comparison plot (Running) saved to: {output_file}")
        plt.close()
        
    except Exception as e:
        print(f"Error generating comparison plot: {e}")
        import traceback
        traceback.print_exc()


def plot_comparison_ended_loaded(configs_data, output_file, baseline_config=None):
    """
    绘制多个配置的完成和加载车辆对比图
    在图例中标注相对基准的最终完成数变化百分比
    
    Args:
        configs_data: 字典，格式为 {config_name: data_dict}
        output_file: 输出图片路径
        baseline_config: 基准配置名称（默认为第一个以'0_'开头的配置或第一个配置）
    """
    if not configs_data:
        print("No data to plot")
        return
    
    try:
        # 确定基准配置
        if baseline_config is None:
            for name in configs_data.keys():
                if name.startswith('0_'):
                    baseline_config = name
                    break
            if baseline_config is None:
                baseline_config = list(configs_data.keys())[0]
        
        baseline_data = configs_data.get(baseline_config)
        baseline_ended = baseline_data['ended'][-1] if baseline_data and baseline_data['ended'] else 0
        
        fig, ax = plt.subplots(figsize=(14, 8))
        
        # 定义颜色方案（统一配色：暖色、冷色、暗色对比）
        colors = ['#fe5357', '#1d9bf7', '#8386fc', '#dd7c1a', '#ffbd15', '#0ddbf5', '#303cf9', '#388E3C']
        
        idx = 0
        for config_name, data in configs_data.items():
            color = colors[idx % len(colors)]
            
            # 计算相对基准的变化百分比（基于最终完成数）
            final_ended = data['ended'][-1] if data['ended'] else 0
            if baseline_ended > 0 and config_name != baseline_config:
                pct_change = (final_ended - baseline_ended) / baseline_ended * 100
                pct_str = f' ({pct_change:+.1f}%)'
            else:
                pct_str = ' (Baseline)' if config_name == baseline_config else ''
            
            ax.plot(data['times'], data['ended'], label=f'{config_name} - Completed{pct_str}', 
                   linewidth=2, color=color, linestyle='-')
            ax.plot(data['times'], data['loaded'], label=f'{config_name} - Loaded', 
                   linewidth=2, color=color, linestyle='--', alpha=0.7)
            idx += 1
        
        ax.set_xlabel('Simulation Time (s)', fontsize=12)
        ax.set_ylabel('Cumulative Count', fontsize=12)
        ax.set_title('Cumulative Vehicle Statistics Comparison (Completed & Loaded)', fontsize=14, fontweight='bold', pad=45)
        ax.legend(fontsize=9, loc='upper center', bbox_to_anchor=(0.5, 1.12),
                 ncol=min(len(configs_data), 3), framealpha=0.9)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, format='svg', bbox_inches='tight')
        print(f"Comparison plot (Completed & Loaded) saved to: {output_file}")
        plt.close()
        
    except Exception as e:
        print(f"Error generating comparison plot: {e}")


def plot_comparison_waiting(configs_data, output_file, baseline_config=None):
    """
    绘制多个配置的等待车辆数对比图
    上图：全时段概览；下图：600s到仿真结束的详细图
    在图例中标注相对基准的平均变化百分比
    
    Args:
        configs_data: 字典，格式为 {config_name: data_dict}
        output_file: 输出图片路径
        baseline_config: 基准配置名称（默认为第一个以'0_'开头的配置或第一个配置）
    """
    if not configs_data:
        print("No data to plot")
        return
    
    print(f"  Plotting waiting vehicles for {len(configs_data)} configurations: {list(configs_data.keys())}")
    
    try:
        # 确定基准配置
        if baseline_config is None:
            for name in configs_data.keys():
                if name.startswith('0_'):
                    baseline_config = name
                    break
            if baseline_config is None:
                baseline_config = list(configs_data.keys())[0]
        
        baseline_data = configs_data.get(baseline_config)
        
        # 创建上下两个子图
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[1, 1])
        
        # 定义颜色方案（统一配色：暖色、冷色、暗色对比）
        colors = ['#fe5357', '#1d9bf7', '#8386fc', '#dd7c1a', '#ffbd15', '#0ddbf5', '#303cf9', '#388E3C']
        
        # 找到仿真结束时间
        max_time = 0
        for config_name, data in configs_data.items():
            if data['times']:
                max_time = max(max_time, max(data['times']))
        
        # 详细图的时间范围：600s 到 3600s
        detail_start = 600
        detail_end = 3600
        
        # 计算基准的平均waiting值（用于百分比计算）
        baseline_avg = np.mean(baseline_data['waiting']) if baseline_data else 0
        
        # 绘制两个子图
        idx = 0
        for config_name, data in configs_data.items():
            color = colors[idx % len(colors)]
            
            # 计算相对基准的变化百分比
            avg_waiting = np.mean(data['waiting'])
            if baseline_avg > 0 and config_name != baseline_config:
                pct_change = (avg_waiting - baseline_avg) / baseline_avg * 100
                pct_str = f' ({pct_change:+.1f}%)' if pct_change != 0 else ''
                label_suffix = pct_str
            else:
                label_suffix = ' (Baseline)' if config_name == baseline_config else ''
            
            label = f'{config_name}{label_suffix}'
            print(f"    Drawing {config_name}: {len(data['times'])} data points, color={color}")
            
            # 上图：全时段
            ax1.plot(data['times'], data['waiting'], label=label, 
                    linewidth=2, color=color, linestyle='-')
            
            # 下图：600s到结束的详细图
            ax2.plot(data['times'], data['waiting'], label=label, 
                    linewidth=2, color=color, linestyle='-')
            idx += 1
        
        # 上图设置
        ax1.set_xlabel('Simulation Time (s)', fontsize=12)
        ax1.set_ylabel('Number of Waiting Vehicles', fontsize=12)
        ax1.set_title('(a) Waiting Vehicles - Full Time Range', fontsize=13, fontweight='bold', pad=40)
        ax1.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, 1.12),
                  ncol=min(len(configs_data), 3), framealpha=0.9)
        ax1.grid(True, alpha=0.3)
        
        # 在上图标记详细图区域
        ax1.axvspan(detail_start, detail_end, alpha=0.15, color='#fe5357', label='Detail region')
        ax1.axvline(x=detail_start, color='#fe5357', linestyle='--', linewidth=1.5, alpha=0.7)
        
        # 下图设置
        ax2.set_xlim(detail_start, detail_end)
        ax2.set_xlabel('Simulation Time (s)', fontsize=12)
        ax2.set_ylabel('Number of Waiting Vehicles', fontsize=12)
        ax2.set_title(f'(b) Waiting Vehicles - Detail View ({detail_start}s ~ {int(detail_end)}s)', 
                     fontsize=13, fontweight='bold', pad=40)
        ax2.legend(fontsize=10, loc='upper center', bbox_to_anchor=(0.5, 1.12),
                  ncol=min(len(configs_data), 3), framealpha=0.9)
        ax2.grid(True, alpha=0.3)
        
        # 自动调整下图Y轴范围
        detail_waiting_values = []
        for config_name, data in configs_data.items():
            for t, w in zip(data['times'], data['waiting']):
                if detail_start <= t <= detail_end:
                    detail_waiting_values.append(w)
        
        if detail_waiting_values:
            y_min = min(detail_waiting_values) * 0.95
            y_max = max(detail_waiting_values) * 1.05
            ax2.set_ylim(y_min, y_max)
        
        plt.tight_layout()
        plt.savefig(output_file, format='svg', bbox_inches='tight', facecolor='white')
        print(f"Comparison plot (Waiting) saved to: {output_file}")
        plt.close()
        
    except Exception as e:
        print(f"Error generating waiting comparison plot: {e}")
        import traceback
        traceback.print_exc()


def plot_excel_comparison(configs, excel_dir, chart_dir, prefix):
    """
    读取多个Excel仿真结果并合并为一个Excel表格
    
    Args:
        configs: 配置列表 ['0_1_X', '2_1_10', '2_0_2_40', ...]
        excel_dir: Excel文件目录 (output/仿真结果/)
        chart_dir: 输出目录 (results/chart/)
        prefix: 文件名前缀
    """
    # 要排除的系统相关指标
    exclude_metrics = ['OS', 'CPU', 'Python', 'CPU Cores', 'RAM', 'GPU']
    
    # 读取所有配置的Excel数据
    all_data = {}
    for config in configs:
        parts = config.split('_')
        # 支持3段格式（0_1_X）和4段格式（2_0_2_40）
        if len(parts) < 3:
            continue
        
        # 直接使用config构建文件名
        excel_file = os.path.join(excel_dir, f'仿真结果_{config}.xlsx')
        
        if not os.path.exists(excel_file):
            print(f"  警告：Excel文件不存在: {excel_file}")
            continue
        
        try:
            df = pd.read_excel(excel_file)
            # 转换为字典格式
            data_dict = dict(zip(df['指标'], df['数值']))
            # 过滤掉系统相关指标
            data_dict = {k: v for k, v in data_dict.items() if k not in exclude_metrics}
            all_data[config] = data_dict
            print(f"  成功加载Excel: {config}")
        except Exception as e:
            print(f"  警告：读取Excel失败 {config}: {e}")
    
    if not all_data:
        print("  没有成功加载任何Excel数据")
        return
    
    # 获取所有指标（保持顺序）
    all_metrics = []
    for config in configs:
        if config in all_data:
            for metric in all_data[config].keys():
                if metric not in all_metrics:
                    all_metrics.append(metric)
    
    # 构建合并的DataFrame
    # 第一列是指标名称，后续列是各配置的值
    merged_data = {'指标': all_metrics}
    for config in configs:
        if config in all_data:
            values = [all_data[config].get(metric, 'N/A') for metric in all_metrics]
            merged_data[config] = values
    
    df_merged = pd.DataFrame(merged_data)
    
    # 保存合并后的Excel
    output_file = os.path.join(chart_dir, f'{prefix}_合并结果.xlsx')
    df_merged.to_excel(output_file, index=False)
    print(f"  合并结果已保存到: {output_file}")


def plot_speed_ratio_comparison(configs, sumo_output_dir, net_file, speed_ratio_dir, prefix,
                                diff_mode=True, baseline_config=None):
    """
    绘制多配置的路段平均速度对比图
    支持差值图模式：第一张是基准绝对值，后续是与基准的差值图
    
    Args:
        configs: 配置列表
        sumo_output_dir: SUMO输出目录
        net_file: 路网文件路径
        speed_ratio_dir: 速度图输出目录
        prefix: 文件名前缀
        diff_mode: 是否使用差值图模式（默认True）
        baseline_config: 基准配置名称（默认为第一个以'0_'开头的配置）
    """
    import math
    from matplotlib.colors import LinearSegmentedColormap
    
    # 创建深绿-黄-橙色系的颜色映射（绿色=快，橙色=慢）
    colors_list = ['#FF8C00', '#FFA500', '#FFD700', '#ADFF2F', '#228B22']  # 橙-黄-绿
    cmap_speed = LinearSegmentedColormap.from_list('avg_speed', colors_list)
    
    # 差值图颜色映射（深绿-绿-黄-橙色系：绿=改善，橙=恶化）
    # 负值（恶化）→ 橙色，正值（改善）→ 深绿色
    diff_colors = ['#FF6600', '#FFA500', '#FFD700', '#90EE90', '#228B22']  # 橙-浅橙-黄-浅绿-深绿
    diff_cmap = LinearSegmentedColormap.from_list('diff_speed', diff_colors)
    
    # 支持3段格式（2_3_20）和4段格式（2_0_2_40）
    config_names = [c for c in configs if '_' in c and len(c.split('_')) >= 3]
    n_configs = len(config_names)
    
    if n_configs == 0:
        print("  No valid configurations")
        return
    
    # 确定基准配置
    if baseline_config is None:
        for name in config_names:
            if name.startswith('0_'):
                baseline_config = name
                break
        if baseline_config is None:
            baseline_config = config_names[0]
    
    # 计算子图布局
    n_cols = min(2, n_configs)
    n_rows = math.ceil(n_configs / n_cols)
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(8*n_cols, 6*n_rows))
    if n_configs == 1:
        axes = [axes]
    elif n_configs > 1:
        axes = axes.flatten()
    else:
        axes = [axes]
    
    visualizer = NetworkFlowVisualizer(net_file)
    
    # 首先加载基准配置的数据
    baseline_edge_stats = None
    if diff_mode:
        baseline_edgedata = os.path.join(sumo_output_dir, f'edgedata_{baseline_config}.xml')
        if os.path.exists(baseline_edgedata):
            baseline_edge_stats = visualizer.parse_edgedata(baseline_edgedata)
    
    # 收集所有配置的速度数据，找到全局最大值用于统一颜色映射
    all_speeds = []
    for config_name in config_names:
        edgedata_file = os.path.join(sumo_output_dir, f'edgedata_{config_name}.xml')
        if os.path.exists(edgedata_file):
            edge_stats = visualizer.parse_edgedata(edgedata_file)
            for edge_id, stats in edge_stats.items():
                all_speeds.append(stats.get('avg_speed', 0))
    
    max_speed = max(all_speeds) if all_speeds else 20  # 默认最大速度20 m/s
    
    for idx, config_name in enumerate(config_names):
        edgedata_file = os.path.join(sumo_output_dir, f'edgedata_{config_name}.xml')
        
        if not os.path.exists(edgedata_file):
            print(f"  Warning: edgedata file not found for {config_name}")
            continue
        
        edge_stats = visualizer.parse_edgedata(edgedata_file)
        if not edge_stats:
            continue
        
        ax = axes[idx]
        
        # 收集路段数据
        segments = []
        values = []
        offset_distance = 15
        
        is_baseline = (config_name == baseline_config)
        use_diff = diff_mode and not is_baseline and baseline_edge_stats is not None
        
        for edge in visualizer.net.getEdges():
            edge_id = edge.getID()
            if edge_id.startswith(':'):
                continue
            
            current_speed = edge_stats.get(edge_id, {}).get('avg_speed', 0)
            
            if use_diff:
                # 差值模式：计算与基准的差值
                baseline_speed = baseline_edge_stats.get(edge_id, {}).get('avg_speed', 0)
                value = current_speed - baseline_speed  # 正值=改善（速度增加），负值=恶化
            else:
                value = current_speed
            
            shape = edge.getShape()
            offset_shape = visualizer._offset_shape(shape, offset_distance)
            
            for i in range(len(offset_shape) - 1):
                segments.append([offset_shape[i], offset_shape[i+1]])
                values.append(value)
        
        values = np.array(values)
        
        if use_diff:
            # 差值图：使用发散色图
            max_abs = max(abs(values.min()), abs(values.max()), 0.1)
            lc = LineCollection(segments, cmap=diff_cmap, linewidths=3)
            lc.set_array(values)
            lc.set_clim(-max_abs, max_abs)
            ax.add_collection(lc)
            
            cbar = plt.colorbar(lc, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label(f'Δ Speed (m/s) (Green=Faster, Red=Slower)', fontsize=9)
            
            # 计算平均改善
            avg_diff = values.mean()
            title_suffix = f'\nAvg: {avg_diff:+.2f} m/s'
        else:
            # 绝对值图
            lc = LineCollection(segments, cmap=cmap_speed, linewidths=3)
            lc.set_array(values)
            lc.set_clim(0, max_speed)
            ax.add_collection(lc)
            
            cbar = plt.colorbar(lc, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label(f'Avg Speed (m/s), mean: {values.mean():.1f}', fontsize=10)
            title_suffix = ' (Baseline)' if is_baseline else ''
        
        bounds = visualizer.net.getBoundary()
        ax.set_xlim(bounds[0] - 50, bounds[2] + 50)
        ax.set_ylim(bounds[1] - 50, bounds[3] + 50)
        ax.set_aspect('equal')
        ax.set_title(f'{config_name}{title_suffix}', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
    
    # 隐藏多余的子图
    for idx in range(n_configs, len(axes)):
        axes[idx].set_visible(False)
    
    suptitle = 'Average Speed Comparison'
    if diff_mode:
        suptitle += ' (Difference from Baseline: Green=Faster, Red=Slower)'
    else:
        suptitle += ' (Green=Fast, Orange=Slow)'
    plt.suptitle(suptitle, fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    output_file = os.path.join(speed_ratio_dir, f'{prefix}_speed_ratio.svg')
    plt.savefig(output_file, format='svg', bbox_inches='tight', facecolor='white')
    print(f"  Average speed comparison plot saved to: {output_file}")
    plt.close()


def plot_occupancy_comparison(configs_data, sumo_output_dir, net_file, plots_dir, prefix, 
                              diff_mode=True, baseline_config=None):
    """
    绘制多配置的路网占有率对比图（子图形式）
    支持差值图模式：第一张是基准绝对值，后续是与基准的差值图
    
    Args:
        configs_data: 配置数据字典
        sumo_output_dir: SUMO输出目录
        net_file: 路网文件路径
        plots_dir: 图表输出目录
        prefix: 文件名前缀
        diff_mode: 是否使用差值图模式（默认True）
        baseline_config: 基准配置名称（默认为第一个以'0_'开头的配置）
    """
    import math
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
    
    config_names = list(configs_data.keys())
    n_configs = len(config_names)
    
    # 确定基准配置
    if baseline_config is None:
        for name in config_names:
            if name.startswith('0_'):
                baseline_config = name
                break
        if baseline_config is None:
            baseline_config = config_names[0]
    
    # 计算子图布局
    n_cols = min(2, n_configs)
    n_rows = math.ceil(n_configs / n_cols)
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(8*n_cols, 6*n_rows))
    if n_configs == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if n_configs > 1 else [axes]
    
    visualizer = NetworkFlowVisualizer(net_file)
    
    # 首先加载基准配置的数据
    baseline_edge_stats = None
    if diff_mode:
        baseline_edgedata = os.path.join(sumo_output_dir, f'edgedata_{baseline_config}.xml')
        if os.path.exists(baseline_edgedata):
            baseline_edge_stats = visualizer.parse_edgedata(baseline_edgedata)
    
    # 创建差值图的颜色映射（深绿-绿-黄-橙色系：绿=改善/减少，橙=恶化/增加）
    # 负值（占有率减少=改善）→ 深绿色，正值（占有率增加=恶化）→ 橙色
    diff_colors = ['#228B22', '#90EE90', '#FFD700', '#FFA500', '#FF6600']  # 深绿-浅绿-黄-浅橙-橙
    diff_cmap = LinearSegmentedColormap.from_list('diff_occupancy', diff_colors)
    
    for idx, config_name in enumerate(config_names):
        edgedata_file = os.path.join(sumo_output_dir, f'edgedata_{config_name}.xml')
        
        if not os.path.exists(edgedata_file):
            print(f"  Warning: edgedata file not found for {config_name}")
            continue
        
        edge_stats = visualizer.parse_edgedata(edgedata_file)
        if not edge_stats:
            continue
        
        ax = axes[idx]
        
        # 收集路段数据
        segments = []
        values = []
        offset_distance = 15
        
        is_baseline = (config_name == baseline_config)
        use_diff = diff_mode and not is_baseline and baseline_edge_stats is not None
        
        for edge in visualizer.net.getEdges():
            edge_id = edge.getID()
            if edge_id.startswith(':'):
                continue
            
            current_occ = edge_stats.get(edge_id, {}).get('avg_occupancy', 0)
            
            if use_diff:
                # 差值模式：计算与基准的差值
                baseline_occ = baseline_edge_stats.get(edge_id, {}).get('avg_occupancy', 0)
                value = current_occ - baseline_occ  # 正值=恶化，负值=改善
            else:
                value = current_occ
            
            shape = edge.getShape()
            offset_shape = visualizer._offset_shape(shape, offset_distance)
            
            for i in range(len(offset_shape) - 1):
                segments.append([offset_shape[i], offset_shape[i+1]])
                values.append(value)
        
        values = np.array(values)
        
        if use_diff:
            # 差值图：使用发散色图
            max_abs = max(abs(values.min()), abs(values.max()), 0.001)
            lc = LineCollection(segments, cmap=diff_cmap, linewidths=3)
            lc.set_array(values)
            lc.set_clim(-max_abs, max_abs)
            ax.add_collection(lc)
            
            # 颜色条标签
            cbar = plt.colorbar(lc, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label(f'Δ Occupancy (Green=Better, Red=Worse)', fontsize=9)
            
            # 计算平均改善
            avg_diff = values.mean()
            diff_pct = f'Avg: {avg_diff:+.4f}'
            title_suffix = f'\n{diff_pct}'
        else:
            # 绝对值图
            norm_values = values / values.max() if values.max() > 0 else values
            lc = LineCollection(segments, cmap='Greens', linewidths=3)
            lc.set_array(norm_values)
            lc.set_clim(0, 1)
            ax.add_collection(lc)
            
            cbar = plt.colorbar(lc, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label(f'Occupancy (max: {values.max():.3f})', fontsize=9)
            title_suffix = ' (Baseline)' if is_baseline else ''
        
        bounds = visualizer.net.getBoundary()
        ax.set_xlim(bounds[0] - 50, bounds[2] + 50)
        ax.set_ylim(bounds[1] - 50, bounds[3] + 50)
        ax.set_aspect('equal')
        ax.set_title(f'{config_name}{title_suffix}', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
    
    # 隐藏多余的子图
    for idx in range(n_configs, len(axes)):
        axes[idx].set_visible(False)
    
    suptitle = 'Network Occupancy Comparison'
    if diff_mode:
        suptitle += ' (Difference from Baseline)'
    plt.suptitle(suptitle, fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    output_file = os.path.join(plots_dir, f'{prefix}_occupancy.svg')
    plt.savefig(output_file, format='svg', bbox_inches='tight')
    print(f"Occupancy comparison plot saved to: {output_file}")
    plt.close()


def visualize_simulation_results(mode, flow, pr, config_dir, sumo_output_dir, 
                                 running_dir, ended_dir, occupancy_dir):
    """
    可视化仿真结果的便捷函数
    
    Args:
        mode: 实验模式
        flow: 流量比例
        pr: 渗透率
        config_dir: 配置文件目录
        sumo_output_dir: SUMO输出文件目录 (output/sumo/)
        running_dir: 运行中车辆图目录 (output/running/)
        ended_dir: 完成和加载车辆图目录 (output/ended_loaded/)
        occupancy_dir: 路网占有率图目录 (output/occupancy/)
    """
    # 文件路径
    net_file = os.path.join(config_dir, 'siouxfalls.net.xml')
    net_csv = os.path.join(os.path.dirname(config_dir), 'data', 'SiouxFalls_net.csv')
    node_csv = os.path.join(os.path.dirname(config_dir), 'data', 'SiouxFalls_node.csv')
    edgedata_file = os.path.join(sumo_output_dir, f'edgedata_{mode}_{flow}_{pr}.xml')
    summary_file = os.path.join(sumo_output_dir, f'summary_{mode}_{flow}_{pr}.xml')
    
    prefix = f'mode{mode}_flow{flow}_pr{pr}'
    
    # 1. 绘制路网占有率分布图
    visualizer = NetworkFlowVisualizer(net_file, net_csv, node_csv)
    edge_stats = visualizer.parse_edgedata(edgedata_file)
    
    if edge_stats:
        visualizer.plot_multiple_metrics(edge_stats, occupancy_dir, prefix=prefix)
    else:
        print("Unable to generate network visualization")
    
    # 2. 绘制时间序列图（分开输出到不同目录）
    data = parse_summary_data(summary_file)
    if data:
        # 创建单配置的数据字典用于对比函数
        single_config_data = {prefix: data}
        
        # 绘制运行中车辆图
        output_file1 = os.path.join(running_dir, f'{prefix}.svg')
        plot_comparison_running_waiting(single_config_data, output_file1)
        
        # 绘制完成和加载车辆图
        output_file2 = os.path.join(ended_dir, f'{prefix}.svg')
        plot_comparison_ended_loaded(single_config_data, output_file2)


def interactive_comparison_plot():
    """
    交互式对比绘图功能
    用户可以输入多个配置进行对比
    """
    print("=" * 60)
    print("Interactive Simulation Result Comparison Plot Tool")
    print("=" * 60)
    print("\nEnter configurations to compare (format: mode_flow_pr, e.g., 2_1_5)")
    print("Enter one configuration per line, type 'OK' when done\n")
    print("Example:")
    print("  2_1_5  (mode 2, flow 1, penetration 5)")
    print("  0_1_X  (mode 0, flow 1, no penetration)")
    print("\n")
    
    configs = []
    config_num = 1
    while True:
        try:
            prompt = f"Config #{config_num} (or 'OK' to start): "
            config = input(prompt).strip()
            
            if config.upper() == 'OK':
                break
            
            if config:
                configs.append(config)
                print(f"  >> Added: {config}")
                config_num += 1
        except EOFError:
            print("\n\nInput ended. Processing configurations...")
            break
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            return
    
    if not configs:
        print("\n错误：未输入任何配置！")
        return
    
    print(f"\n共输入 {len(configs)} 个配置，开始处理...")
    
    # 设置路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sumo_output_dir = os.path.join(project_root, 'output', 'sumo')
    running_dir = os.path.join(project_root, 'results', 'running')
    ended_dir = os.path.join(project_root, 'results', 'ended_loaded')
    occupancy_dir = os.path.join(project_root, 'results', 'occupancy')
    config_dir = os.path.join(project_root, 'config')
    
    # 确保输出目录存在
    for dir_path in [running_dir, ended_dir, occupancy_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    # 解析所有配置的数据
    configs_data = {}
    for config in configs:
        parts = config.split('_')
        if len(parts) != 3:
            print(f"警告：配置格式错误，跳过: {config}")
            continue
        
        mode, flow, pr = parts
        summary_file = os.path.join(sumo_output_dir, f'summary_{mode}_{flow}_{pr}.xml')
        
        data = parse_summary_data(summary_file)
        if data:
            configs_data[config] = data
            print(f"  成功加载配置: {config}")
        else:
            print(f"  警告：无法加载配置数据: {config}")
    
    if not configs_data:
        print("\n错误：没有成功加载任何配置数据！")
        return
    
    # 根据配置数量决定文件名格式
    if len(configs_data) == 1:
        # 单配置：使用 mode{mode}_flow{flow}_pr{pr} 格式
        config_name = list(configs_data.keys())[0]
        parts = config_name.split('_')
        prefix = f'mode{parts[0]}_flow{parts[1]}_pr{parts[2]}'
        print(f"\n开始绘制单配置图表: {config_name}")
    else:
        # 多配置对比：使用 comparison_xxx_vs_yyy 格式
        prefix = 'comparison_' + '_vs_'.join(configs_data.keys())
        print(f"\n开始绘制对比图 ({len(configs_data)} 个配置)...")
    
    # 绘制运行中车辆图
    output_file1 = os.path.join(running_dir, f'{prefix}.svg')
    plot_comparison_running_waiting(configs_data, output_file1)
    
    # 绘制完成和加载车辆图
    output_file2 = os.path.join(ended_dir, f'{prefix}.svg')
    plot_comparison_ended_loaded(configs_data, output_file2)
    
    # 生成占有率图（单配置生成单图，多配置生成对比图）
    net_file = os.path.join(config_dir, 'siouxfalls.net.xml')
    
    if len(configs_data) == 1:
        # 单配置：生成单个占有率图
        config_name = list(configs_data.keys())[0]
        parts = config_name.split('_')
        mode, flow, pr = parts
        
        edgedata_file = os.path.join(sumo_output_dir, f'edgedata_{mode}_{flow}_{pr}.xml')
        if os.path.exists(edgedata_file):
            print(f"\n生成路网占有率图...")
            visualizer = NetworkFlowVisualizer(net_file)
            edge_stats = visualizer.parse_edgedata(edgedata_file)
            if edge_stats:
                visualizer.plot_multiple_metrics(edge_stats, occupancy_dir, prefix=prefix)
    else:
        # 多配置：生成对比占有率图（子图形式）
        print(f"\n生成路网占有率对比图...")
        plot_occupancy_comparison(configs_data, sumo_output_dir, net_file, occupancy_dir, prefix)
    
    # 生成仿真结果合并表格
    excel_dir = os.path.join(project_root, 'output', '仿真结果')
    table_dir = os.path.join(project_root, 'results', 'table')
    if not os.path.exists(table_dir):
        os.makedirs(table_dir)
    
    print(f"\n生成仿真结果合并表格...")
    plot_excel_comparison(configs, excel_dir, table_dir, prefix)
    
    # 生成路段速度比对比图（深绿-黄-橙色系）
    speed_ratio_dir = os.path.join(project_root, 'results', 'speed_ratio')
    if not os.path.exists(speed_ratio_dir):
        os.makedirs(speed_ratio_dir)
    
    print(f"\n生成路段速度比对比图...")
    plot_speed_ratio_comparison(configs, sumo_output_dir, net_file, speed_ratio_dir, prefix)
    
    print("\n" + "=" * 60)
    print("图表绘制完成！")
    print("=" * 60)


def plot_penetration_comparison(excel_file, output_dir, prefix):
    """
    Plot comparison chart: Average Delay (bar) and Total Fuel (line) in one figure
    Supports both penetration rate comparison and mode/flow comparison
    
    Args:
        excel_file: Merged result Excel file path
        output_dir: Output directory
        prefix: File name prefix
    """
    if not os.path.exists(excel_file):
        print(f"  Warning: Excel file not found: {excel_file}")
        return
    
    try:
        df = pd.read_excel(excel_file)
        
        # Get config columns (except "指标" column)
        config_cols = [col for col in df.columns if col != '指标']
        
        if len(config_cols) < 2:
            print("  Warning: Need at least 2 configs for comparison")
            return
        
        # Analyze config pattern to determine X-axis type
        # Check if configs vary by penetration rate, mode, or flow
        modes = set()
        flows = set()
        prs = set()
        
        for col in config_cols:
            parts = col.split('_')
            if len(parts) == 3:
                # 3段格式：mode_flow_pr
                modes.add(parts[0])
                flows.add(parts[1])
                prs.add(parts[2])
            elif len(parts) == 4:
                # 4段格式：mode_submode_flow_pr
                modes.add(f"{parts[0]}_{parts[1]}")
                flows.add(parts[2])
                prs.add(parts[3])
        
        # X轴标签统一使用 "Mode {config}" 格式
        x_type = 'general'
        x_labels = [f'Mode {col}' for col in config_cols]
        x_label_text = 'Configuration'
        
        # 根据配置特征确定标题
        if len(prs) > 1 and len(modes) == 1 and len(flows) == 1:
            title_text = 'Average Delay and Total Fuel vs CAV Penetration Rate'
        elif len(modes) > 1 and len(flows) == 1:
            title_text = f'Average Delay and Total Fuel by Mode (Flow {list(flows)[0]})'
        elif len(flows) > 1 and len(modes) == 1:
            title_text = f'Average Delay and Total Fuel by Flow Level'
        else:
            title_text = 'Average Delay and Total Fuel Comparison'
        
        # Extract average delay, total fuel, and runtime data
        delay_row = df[df['指标'] == '车均延误(秒)']
        fuel_row = df[df['指标'] == '总油耗(升)']
        runtime_row = df[df['指标'].isin(['Runtime (s)', '运行时间(秒)'])]
        
        if delay_row.empty or fuel_row.empty:
            print("  Warning: Cannot find delay or fuel data")
            return
        
        delays = [float(delay_row[col].values[0]) for col in config_cols]
        fuels = [float(fuel_row[col].values[0]) for col in config_cols]
        
        # Runtime data (optional)
        runtimes = []
        if not runtime_row.empty:
            for col in config_cols:
                try:
                    runtimes.append(float(runtime_row[col].values[0]))
                except:
                    runtimes.append(None)
        else:
            runtimes = [None] * len(config_cols)
        
        # Create figure with dual Y-axis
        fig, ax1 = plt.subplots(figsize=(max(10, len(config_cols) * 1.5), 7))
        
        # 统一配色方案（冷色系）
        bar_color = '#1d9bf7'  # 天蓝色（冷色）
        line_color = '#dd7c1a'  # 橙色（暖色）
        
        # Bar chart: Average Delay
        x = np.arange(len(config_cols))
        width = 0.5
        bars = ax1.bar(x, delays, width, color=bar_color, alpha=0.85, 
                      label='Average Delay', edgecolor='white', linewidth=1)
        ax1.set_xlabel(x_label_text, fontsize=13, fontweight='medium')
        ax1.set_ylabel('Average Delay (s)', fontsize=13, color=bar_color, fontweight='medium')
        ax1.tick_params(axis='y', labelcolor=bar_color, labelsize=11)
        ax1.tick_params(axis='x', labelsize=10, rotation=45 if len(x_labels[0]) > 10 else 0)
        ax1.set_xticks(x)
        ax1.set_xticklabels(x_labels, ha='right' if len(x_labels[0]) > 10 else 'center')
        ax1.set_ylim(bottom=0)
        ax1.spines['top'].set_visible(False)
        
        # 在每个柱状图下方添加 Runtime 标注（使用 transform 确保位置正确）
        has_runtime = any(r is not None for r in runtimes)
        if has_runtime:
            # 获取当前 Y 轴下限
            y_min, y_max = ax1.get_ylim()
            for i, runtime in enumerate(runtimes):
                if runtime is not None:
                    # 格式化 runtime：如果超过60秒显示为 Xm Ys，否则显示为 Xs
                    if runtime >= 60:
                        mins = int(runtime // 60)
                        secs = int(runtime % 60)
                        runtime_str = f'{mins}m{secs}s'
                    else:
                        runtime_str = f'{runtime:.0f}s'
                    # 在 X 轴下方显示 Runtime
                    ax1.text(x[i], y_min - (y_max - y_min) * 0.12, runtime_str,
                            ha='center', va='top', fontsize=8,
                            color='#555555', style='italic')
        
        # 添加百分比标注（相对于第一个配置/基准）
        baseline_delay = delays[0]
        baseline_fuel = fuels[0]
        
        for i, (bar, delay) in enumerate(zip(bars, delays)):
            if i == 0:
                # 基准配置标注"Baseline"
                ax1.annotate('Baseline', xy=(bar.get_x() + bar.get_width()/2, delay),
                           xytext=(0, 5), textcoords='offset points',
                           ha='center', va='bottom', fontsize=9, fontweight='bold',
                           color='#666666')
            else:
                # 其他配置标注百分比变化
                pct_change = (delay - baseline_delay) / baseline_delay * 100
                # 使用深色：深绿=减小(好), 深红=增加(差)，避免与蓝色冲突
                color = '#006400' if pct_change < 0 else '#B22222'
                sign = '' if pct_change < 0 else '+'
                ax1.annotate(f'{sign}{pct_change:.1f}%', 
                           xy=(bar.get_x() + bar.get_width()/2, delay),
                           xytext=(0, 5), textcoords='offset points',
                           ha='center', va='bottom', fontsize=9, fontweight='bold',
                           color=color)
        
        # Line chart: Total Fuel (second Y-axis)
        ax2 = ax1.twinx()
        ax2.plot(x, fuels, 's-', color=line_color, linewidth=2.5, markersize=9, 
                label='Total Fuel', markerfacecolor='white', markeredgewidth=2)
        ax2.set_ylabel('Total Fuel (L)', fontsize=13, color=line_color, fontweight='medium')
        ax2.tick_params(axis='y', labelcolor=line_color, labelsize=11)
        ax2.set_ylim(bottom=0)
        ax2.spines['top'].set_visible(False)
        
        # 在折线图数据点上添加百分比标注
        for i, fuel in enumerate(fuels):
            if i == 0:
                continue  # 跳过基准
            pct_change = (fuel - baseline_fuel) / baseline_fuel * 100
            # 使用深色：深绿=减小(好), 深红=增加(差)
            color = '#006400' if pct_change < 0 else '#B22222'
            sign = '' if pct_change < 0 else '+'
            ax2.annotate(f'{sign}{pct_change:.1f}%', 
                        xy=(x[i], fuel),
                        xytext=(0, -15), textcoords='offset points',
                        ha='center', va='top', fontsize=8, fontweight='bold',
                        color=color)
        
        # Title
        plt.title(title_text, fontsize=15, fontweight='bold', pad=45)
        
        # Merge legends - 放在标题下方
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper center', 
                  bbox_to_anchor=(0.5, 1.15), ncol=2, fontsize=11, framealpha=0.9)
        
        # Add subtle grid
        ax1.grid(axis='y', alpha=0.3, linestyle='--')
        
        plt.tight_layout()
        
        # Save figure as SVG
        output_file = os.path.join(output_dir, f'{prefix}_comparison.svg')
        plt.savefig(output_file, format='svg', bbox_inches='tight', facecolor='white')
        print(f"  Comparison plot saved to: {output_file}")
        plt.close()
        
    except Exception as e:
        print(f"  Failed to plot comparison: {e}")
        import traceback
        traceback.print_exc()


def analyze_route_changes(route_changes_file, output_dir):
    """
    分析路由变更记录，生成统计图表
    
    Args:
        route_changes_file: route_changes XML文件路径
        output_dir: 输出目录
        
    Returns:
        dict: 分析结果统计
    """
    if not os.path.exists(route_changes_file):
        print(f"  Warning: Route changes file not found: {route_changes_file}")
        return None
    
    try:
        tree = ET.parse(route_changes_file)
        root = tree.getroot()
        
        # 提取基本信息
        mode = root.get('mode', 'N/A')
        flow = root.get('flow', 'N/A')
        pr = root.get('pr', 'N/A')
        total_attempts = int(root.get('total_reroute_attempts', 0))
        total_changes = int(root.get('total_route_changes', 0))
        
        # 解析所有变更记录
        changes = []
        for change in root.findall('change'):
            time = int(change.get('time', 0))
            vehicle = change.get('vehicle', '')
            current_edge = change.get('current_edge', '')
            old_route = change.get('old_route', '')
            new_route = change.get('new_route', '')
            
            # 解析路径
            old_edges = [e.strip() for e in old_route.split('->')]
            new_edges = [e.strip() for e in new_route.split('->')]
            
            changes.append({
                'time': time,
                'vehicle': vehicle,
                'current_edge': current_edge,
                'old_route': old_route,
                'new_route': new_route,
                'old_edges': old_edges,
                'new_edges': new_edges,
                'old_length': len(old_edges),
                'new_length': len(new_edges),
                'length_diff': len(new_edges) - len(old_edges)
            })
        
        if not changes:
            print("  No route changes found in file")
            return None
        
        # 创建DataFrame
        df = pd.DataFrame(changes)
        
        # ========== 统计分析 ==========
        stats = {
            'mode': mode,
            'flow': flow,
            'pr': pr,
            'total_attempts': total_attempts,
            'total_changes': total_changes,
            'change_rate': total_changes / total_attempts * 100 if total_attempts > 0 else 0,
            'unique_vehicles': df['vehicle'].nunique(),
            'avg_changes_per_vehicle': len(df) / df['vehicle'].nunique() if df['vehicle'].nunique() > 0 else 0,
            'avg_length_diff': df['length_diff'].mean(),
            'path_shortened': (df['length_diff'] < 0).sum(),
            'path_lengthened': (df['length_diff'] > 0).sum(),
            'path_same_length': (df['length_diff'] == 0).sum()
        }
        
        # ========== 生成图表 ==========
        prefix = f"route_changes_{mode}_{flow}_{pr}"
        
        # 创建输出目录
        route_analysis_dir = os.path.join(output_dir, 'route_analysis')
        if not os.path.exists(route_analysis_dir):
            os.makedirs(route_analysis_dir)
        
        # 图1: 综合分析图（2x2子图）
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 子图1: 时间分布（柱状图）
        ax1 = axes[0, 0]
        time_counts = df.groupby('time').size()
        ax1.bar(time_counts.index, time_counts.values, width=40, color='#3498db', alpha=0.8)
        ax1.set_xlabel('Simulation Time (s)', fontsize=11)
        ax1.set_ylabel('Number of Route Changes', fontsize=11)
        ax1.set_title('(a) Route Changes Over Time', fontsize=12, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)
        
        # 子图2: 车辆变更次数分布（直方图）
        ax2 = axes[0, 1]
        vehicle_counts = df.groupby('vehicle').size()
        ax2.hist(vehicle_counts.values, bins=range(1, vehicle_counts.max() + 2), 
                color='#2ecc71', alpha=0.8, edgecolor='white')
        ax2.set_xlabel('Number of Route Changes per Vehicle', fontsize=11)
        ax2.set_ylabel('Number of Vehicles', fontsize=11)
        ax2.set_title('(b) Distribution of Changes per Vehicle', fontsize=12, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)
        
        # 子图3: 路径长度变化分布
        ax3 = axes[1, 0]
        length_diff_counts = df['length_diff'].value_counts().sort_index()
        colors = ['#e74c3c' if x < 0 else '#2ecc71' if x > 0 else '#95a5a6' 
                 for x in length_diff_counts.index]
        ax3.bar(length_diff_counts.index, length_diff_counts.values, color=colors, alpha=0.8)
        ax3.axvline(x=0, color='black', linestyle='--', linewidth=1)
        ax3.set_xlabel('Path Length Change (edges)', fontsize=11)
        ax3.set_ylabel('Number of Changes', fontsize=11)
        ax3.set_title('(c) Path Length Change Distribution', fontsize=12, fontweight='bold', pad=35)
        ax3.grid(axis='y', alpha=0.3)
        # 添加图例 - 放在标题下方
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor='#e74c3c', label='Shortened'),
                         Patch(facecolor='#2ecc71', label='Lengthened'),
                         Patch(facecolor='#95a5a6', label='Same Length')]
        ax3.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, 1.12),
                  ncol=3, fontsize=9, framealpha=0.9)
        
        # 子图4: 统计摘要（文本）
        ax4 = axes[1, 1]
        ax4.axis('off')
        summary_text = f"""
Route Change Analysis Summary
{'='*40}

Configuration: Mode={mode}, Flow={flow}, PR={pr}%

Basic Statistics:
  • Total Reroute Attempts: {total_attempts:,}
  • Actual Route Changes: {total_changes:,}
  • Change Rate: {stats['change_rate']:.1f}%

Vehicle Statistics:
  • Unique Vehicles Changed: {stats['unique_vehicles']:,}
  • Avg Changes per Vehicle: {stats['avg_changes_per_vehicle']:.2f}

Path Length Analysis:
  • Path Shortened: {stats['path_shortened']:,} ({stats['path_shortened']/len(df)*100:.1f}%)
  • Path Lengthened: {stats['path_lengthened']:,} ({stats['path_lengthened']/len(df)*100:.1f}%)
  • Same Length: {stats['path_same_length']:,} ({stats['path_same_length']/len(df)*100:.1f}%)
  • Avg Length Change: {stats['avg_length_diff']:+.2f} edges
"""
        ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, fontsize=11,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        ax4.set_title('(d) Summary Statistics', fontsize=12, fontweight='bold')
        
        plt.suptitle(f'Route Change Analysis - Config: {mode}_{flow}_{pr}', 
                    fontsize=14, fontweight='bold', y=1.02)
        plt.tight_layout()
        
        output_file = os.path.join(route_analysis_dir, f'{prefix}_analysis.svg')
        plt.savefig(output_file, format='svg', bbox_inches='tight', facecolor='white')
        print(f"  Route change analysis saved to: {output_file}")
        plt.close()
        
        return stats
        
    except Exception as e:
        print(f"  Error analyzing route changes: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_route_changes_batch(configs, route_changes_dir, output_dir):
    """
    批量分析多个配置的路由变更（仅生成单独的分析图，不生成对比图）
    
    Args:
        configs: 配置列表 ['2_3_20', '2_3_40', '2_0_2_40', ...]
        route_changes_dir: route_changes目录
        output_dir: 输出目录
    """
    for config in configs:
        parts = config.split('_')
        if len(parts) < 3:
            continue
        
        # 支持3段格式（2_3_20）和4段格式（2_0_2_40）
        if len(parts) == 3:
            # 3段格式：mode_flow_pr
            route_file = os.path.join(route_changes_dir, f'route_changes_{config}.xml')
        elif len(parts) == 4:
            # 4段格式：mode_submode_flow_pr
            route_file = os.path.join(route_changes_dir, f'route_changes_{config}.xml')
        else:
            continue
        
        if os.path.exists(route_file):
            print(f"  Analyzing route changes for: {config}")
            analyze_route_changes(route_file, output_dir)
        else:
            print(f"  Warning: Route changes file not found: {route_file}")


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  1. Single visualization: python 5_visualizer.py <mode> <flow> <pr>")
        print("     Example: python 5_visualizer.py 2 3 80")
        print("  2. Interactive comparison: python 5_visualizer.py --compare")
        print("  3. Route change analysis: python 5_visualizer.py --route-analysis <config>")
        print("     Example: python 5_visualizer.py --route-analysis 2_3_40")
        sys.exit(1)
    
    if sys.argv[1] == '--compare':
        # 交互式对比模式
        interactive_comparison_plot()
    elif sys.argv[1] == '--route-analysis':
        # 路由变更分析模式
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        route_changes_dir = os.path.join(project_root, 'output', 'route_changes')
        results_dir = os.path.join(project_root, 'results')
        
        if len(sys.argv) >= 3:
            config = sys.argv[2]
            parts = config.split('_')
            if len(parts) == 3:
                mode, flow, pr = parts
                route_file = os.path.join(route_changes_dir, f'route_changes_{mode}_{flow}_{pr}.xml')
                analyze_route_changes(route_file, results_dir)
            else:
                print("Error: Invalid config format. Use mode_flow_pr (e.g., 2_3_40)")
        else:
            # 分析所有可用的route_changes文件
            if os.path.exists(route_changes_dir):
                files = [f for f in os.listdir(route_changes_dir) if f.endswith('.xml')]
                for f in files:
                    print(f"\nAnalyzing: {f}")
                    analyze_route_changes(os.path.join(route_changes_dir, f), results_dir)
    else:
        # 单个配置可视化模式
        if len(sys.argv) < 4:
            print("Error: Not enough arguments for single visualization")
            print("Usage: python 5_visualizer.py <mode> <flow> <pr>")
            sys.exit(1)
        
        mode = sys.argv[1]
        flow = sys.argv[2]
        pr = sys.argv[3]
        
        # 设置路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_dir = os.path.join(project_root, 'config')
        output_dir = os.path.join(project_root, 'output')
        results_dir = os.path.join(project_root, 'results')
        
        # 执行可视化
        visualize_simulation_results(mode, flow, pr, config_dir, output_dir, results_dir)
