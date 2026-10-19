"""
信号配时配置文件读写模块

使用XML格式存储信号优化配置，支持：
- 从路网自动提取并保存
- 从XML文件加载
- 仿真后更新配置
"""
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
import numpy as np
import sumolib
from typing import Dict, List, Tuple, Optional


# 默认参数
DEFAULT_MIN_GREEN = 10   # 最小绿灯时间
DEFAULT_MAX_GREEN = 60   # 最大绿灯时间
DEFAULT_PHASE_DURATION = 30  # 默认相位时长
DEFAULT_CYCLE = 90       # 默认周期
YELLOW_TIME = 0          # 黄灯时间（Siouxfalls路网无黄灯）


def prettify_xml(elem):
    """格式化XML输出"""
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def extract_and_save_config(net_file: str, output_dir: str) -> Dict:
    """
    从路网提取信号配置并保存为XML
    
    Args:
        net_file: SUMO路网文件路径
        output_dir: 输出目录
        
    Returns:
        提取的配置字典
    """
    net = sumolib.net.readNet(net_file)
    
    # 获取所有信号灯节点
    tl_nodes = []
    for node in net.getNodes():
        if node.getType() == 'traffic_light':
            tl_nodes.append(node.getID())
    
    print(f"Found {len(tl_nodes)} traffic lights")
    
    # ========== 1. 生成信号配置XML ==========
    root = ET.Element('signal_config')
    root.set('yellow_time', str(YELLOW_TIME))
    root.set('default_cycle', str(DEFAULT_CYCLE))
    root.set('min_green', str(DEFAULT_MIN_GREEN))
    root.set('max_green', str(DEFAULT_MAX_GREEN))
    
    var_index = 0
    intersections = {}
    decision_vars = []
    
    for tl_id in tl_nodes:
        node = net.getNode(tl_id)
        
        # 获取进口道
        incoming_edges = []
        for edge in net.getEdges():
            if edge.getToNode().getID() == tl_id and not edge.getID().startswith(':'):
                incoming_edges.append(edge.getID())
        
        # 估算相位数（简化：每个进口方向一个相位，最多4相位）
        num_phases = min(len(incoming_edges), 4)
        if num_phases == 0:
            continue
        
        # 创建交叉口元素
        tl_elem = ET.SubElement(root, 'intersection')
        tl_elem.set('id', tl_id)
        tl_elem.set('cycle', str(DEFAULT_CYCLE))
        tl_elem.set('num_phases', str(num_phases))
        tl_elem.set('var_start', str(var_index))
        tl_elem.set('var_end', str(var_index + num_phases - 1))
        
        # 记录交叉口信息
        intersections[tl_id] = {
            'cycle': DEFAULT_CYCLE,
            'begin': var_index,
            'end': var_index + num_phases - 1,
            'phases': [],
            'incoming_edges': incoming_edges
        }
        
        # 添加相位
        for i in range(num_phases):
            phase_elem = ET.SubElement(tl_elem, 'phase')
            phase_elem.set('index', str(i * 2))
            phase_elem.set('var_index', str(var_index + i))
            phase_elem.set('duration', str(DEFAULT_PHASE_DURATION))
            phase_elem.set('min_green', str(DEFAULT_MIN_GREEN))
            phase_elem.set('max_green', str(DEFAULT_MAX_GREEN))
            
            # 关联进口道
            if i < len(incoming_edges):
                phase_elem.set('edge', incoming_edges[i])
            
            intersections[tl_id]['phases'].append(i * 2)
            decision_vars.append({
                'intersection': tl_id,
                'phase': i * 2,
                'var_index': var_index + i,
                'min': DEFAULT_MIN_GREEN,
                'max': DEFAULT_MAX_GREEN
            })
        
        var_index += num_phases
    
    # 保存信号配置XML
    config_file = os.path.join(output_dir, 'signal_config.xml')
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(root))
    print(f"Saved: {config_file}")
    
    # ========== 2. 生成流量数据XML ==========
    flow_root = ET.Element('flow_data')
    
    edge_data = {}
    for edge in net.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(':'):
            continue
        
        lanes = edge.getLaneNumber()
        saturation_flow = lanes * 1800  # 每车道1800 veh/h
        
        edge_elem = ET.SubElement(flow_root, 'edge')
        edge_elem.set('id', edge_id)
        edge_elem.set('saturation_flow', str(saturation_flow))
        edge_elem.set('demand_flow', '0')  # 初始需求为0，仿真中更新
        edge_elem.set('lanes', str(lanes))
        edge_elem.set('length', f'{edge.getLength():.2f}')
        
        # 获取下游路段
        to_node = edge.getToNode()
        for conn in to_node.getConnections():
            if conn.getFrom().getID() == edge_id:
                edge_elem.set('downstream', conn.getTo().getID())
                break
        
        edge_data[edge_id] = {
            'saturation_flow': saturation_flow,
            'demand_flow': 0
        }
    
    flow_file = os.path.join(output_dir, 'flow_data.xml')
    with open(flow_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(flow_root))
    print(f"Saved: {flow_file}")
    
    # ========== 3. 生成转向比XML ==========
    turn_root = ET.Element('turn_ratios')
    
    turn_data = {}
    for edge in net.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(':'):
            continue
        
        turn_elem = ET.SubElement(turn_root, 'edge')
        turn_elem.set('id', edge_id)
        turn_elem.set('left', '0.2')
        turn_elem.set('straight', '0.6')
        turn_elem.set('right', '0.2')
        
        turn_data[edge_id] = [0.2, 0.6, 0.2]
    
    turn_file = os.path.join(output_dir, 'turn_ratios.xml')
    with open(turn_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(turn_root))
    print(f"Saved: {turn_file}")
    
    # ========== 4. 生成相位映射XML ==========
    phase_root = ET.Element('phase_mapping')
    
    phase_data = {}
    for tl_id, info in intersections.items():
        for i, edge_id in enumerate(info['incoming_edges']):
            if i < len(info['phases']):
                mapping_elem = ET.SubElement(phase_root, 'mapping')
                mapping_elem.set('edge', edge_id)
                mapping_elem.set('intersection', tl_id)
                mapping_elem.set('phase', str(info['phases'][i]))
                
                phase_data[edge_id] = info['phases'][i]
    
    phase_file = os.path.join(output_dir, 'phase_mapping.xml')
    with open(phase_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(phase_root))
    print(f"Saved: {phase_file}")
    
    return {
        'intersections': intersections,
        'decision_vars': decision_vars,
        'edge_data': edge_data,
        'turn_data': turn_data,
        'phase_data': phase_data,
        'dim': len(decision_vars)
    }


def load_config_from_xml(config_dir: str) -> Optional[Dict]:
    """
    从XML文件加载信号配置
    
    Args:
        config_dir: 配置文件目录
        
    Returns:
        配置字典，如果文件不存在返回None
    """
    signal_file = os.path.join(config_dir, 'signal_config.xml')
    flow_file = os.path.join(config_dir, 'flow_data.xml')
    turn_file = os.path.join(config_dir, 'turn_ratios.xml')
    phase_file = os.path.join(config_dir, 'phase_mapping.xml')
    
    # 检查主配置文件是否存在
    if not os.path.exists(signal_file):
        return None
    
    config = {
        'intersections': {},
        'decision_vars': [],
        'edge_data': {},
        'turn_data': {},
        'phase_data': {},
        'lb': [],
        'ub': []
    }
    
    # 加载信号配置
    tree = ET.parse(signal_file)
    root = tree.getroot()
    
    config['yellow_time'] = int(root.get('yellow_time', '0'))
    config['default_cycle'] = int(root.get('default_cycle', '90'))
    
    for tl_elem in root.findall('intersection'):
        tl_id = tl_elem.get('id')
        config['intersections'][tl_id] = {
            'cycle': int(tl_elem.get('cycle', '90')),
            'begin': int(tl_elem.get('var_start', '0')),
            'end': int(tl_elem.get('var_end', '0')),
            'phases': [],
            'incoming_edges': []  # 添加incoming_edges列表
        }
        
        for phase_elem in tl_elem.findall('phase'):
            phase_idx = int(phase_elem.get('index', '0'))
            var_idx = int(phase_elem.get('var_index', '0'))
            min_green = int(phase_elem.get('min_green', '10'))
            max_green = int(phase_elem.get('max_green', '60'))
            edge_id = phase_elem.get('edge', '')  # 获取关联的路段
            
            config['intersections'][tl_id]['phases'].append(phase_idx)
            if edge_id:
                config['intersections'][tl_id]['incoming_edges'].append(edge_id)
            config['decision_vars'].append({
                'intersection': tl_id,
                'phase': phase_idx,
                'var_index': var_idx,
                'min': min_green,
                'max': max_green
            })
            config['lb'].append(min_green)
            config['ub'].append(max_green)
    
    config['dim'] = len(config['decision_vars'])
    config['lb'] = np.array(config['lb'])
    config['ub'] = np.array(config['ub'])
    
    # 加载流量数据
    if os.path.exists(flow_file):
        tree = ET.parse(flow_file)
        for edge_elem in tree.getroot().findall('edge'):
            edge_id = edge_elem.get('id')
            config['edge_data'][edge_id] = {
                'saturation_flow': float(edge_elem.get('saturation_flow', '1800')),
                'demand_flow': float(edge_elem.get('demand_flow', '0')),
                'downstream': edge_elem.get('downstream', '')
            }
    
    # 加载转向比
    if os.path.exists(turn_file):
        tree = ET.parse(turn_file)
        for edge_elem in tree.getroot().findall('edge'):
            edge_id = edge_elem.get('id')
            config['turn_data'][edge_id] = [
                float(edge_elem.get('left', '0.2')),
                float(edge_elem.get('straight', '0.6')),
                float(edge_elem.get('right', '0.2'))
            ]
    
    # 加载相位映射
    if os.path.exists(phase_file):
        tree = ET.parse(phase_file)
        for mapping_elem in tree.getroot().findall('mapping'):
            edge_id = mapping_elem.get('edge')
            phase = int(mapping_elem.get('phase', '0'))
            config['phase_data'][edge_id] = phase
    
    print(f"Loaded config: {config['dim']} decision variables, "
          f"{len(config['intersections'])} intersections")
    
    return config


def update_flow_data(config_dir: str, flow_updates: Dict[str, float]):
    """
    更新流量数据XML文件
    
    Args:
        config_dir: 配置文件目录
        flow_updates: {edge_id: demand_flow}
    """
    flow_file = os.path.join(config_dir, 'flow_data.xml')
    if not os.path.exists(flow_file):
        return
    
    tree = ET.parse(flow_file)
    root = tree.getroot()
    
    for edge_elem in root.findall('edge'):
        edge_id = edge_elem.get('id')
        if edge_id in flow_updates:
            edge_elem.set('demand_flow', str(flow_updates[edge_id]))
    
    with open(flow_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(root))


def save_optimized_timing(config_dir: str, optimal_timing: np.ndarray, 
                          intersections: Dict):
    """
    保存优化后的配时方案
    
    Args:
        config_dir: 配置文件目录
        optimal_timing: 优化后的绿灯时间数组
        intersections: 交叉口信息字典
    """
    output_file = os.path.join(config_dir, 'optimized_timing.xml')
    
    root = ET.Element('optimized_timing')
    
    for tl_id, info in intersections.items():
        tl_elem = ET.SubElement(root, 'intersection')
        tl_elem.set('id', tl_id)
        
        begin = info['begin']
        end = info['end']
        green_times = optimal_timing[begin:end+1]
        
        for i, green in enumerate(green_times):
            phase_elem = ET.SubElement(tl_elem, 'phase')
            phase_elem.set('index', str(i))
            phase_elem.set('green_time', str(int(green)))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(root))
    
    print(f"Saved optimized timing to: {output_file}")


# ============== 命令行接口 ==============

if __name__ == "__main__":
    import sys
    
    # 默认路径
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    NET_FILE = os.path.join(PROJECT_ROOT, 'config', 'siouxfalls.net.xml')
    OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
    
    print("="*60)
    print("Signal Config XML Generator")
    print("="*60)
    print(f"Network file: {NET_FILE}")
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    
    # 提取并保存配置
    config = extract_and_save_config(NET_FILE, OUTPUT_DIR)
    
    print()
    print("="*60)
    print("Generation Summary")
    print("="*60)
    print(f"  Decision variables: {config['dim']}")
    print(f"  Intersections: {len(config['intersections'])}")
    print(f"  Edges with flow data: {len(config['edge_data'])}")
    print(f"  Edges with turn ratios: {len(config['turn_data'])}")
    print("="*60)
