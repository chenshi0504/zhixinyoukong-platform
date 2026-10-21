"""
从net.xml重新生成signal_config.xml

确保相位-路段映射严格按照net.xml中的linkIndex顺序

用法：
  python regenerate_signal_config.py                    # 生成到默认位置 data/signal_config/
  python regenerate_signal_config.py output/3_1_1_3_40  # 生成到指定实验目录
"""
import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NET_FILE = os.path.join(PROJECT_ROOT, 'config', 'siouxfalls.net.xml')
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'signal_config')


def prettify_xml(elem):
    """格式化XML输出"""
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def extract_phase_edge_mapping(net_file: str) -> dict:
    """
    从net.xml提取正确的相位-路段映射
    
    原理：
    1. tlLogic定义了相位的state字符串
    2. state字符串中每个字符对应一个linkIndex
    3. connection定义了linkIndex与from_edge的对应关系
    4. 每个相位有一组连续的'G'/'g'，找到这组绿灯的起始位置对应的路段
    
    关键改进：
    - 不是找所有'G'中最小的linkIndex
    - 而是找每个相位中"主要绿灯组"的起始linkIndex
    - 主要绿灯组是连续的'G'/'g'序列
    """
    tree = ET.parse(net_file)
    root = tree.getroot()
    
    # 1. 提取tlLogic信息
    tl_info = {}
    for tl in root.findall('tlLogic'):
        tl_id = tl.get('id')
        phases = tl.findall('phase')
        tl_info[tl_id] = {
            'num_phases': len(phases),
            'phase_durations': [int(p.get('duration')) for p in phases],
            'phase_states': [p.get('state') for p in phases],
            'cycle': sum(int(p.get('duration')) for p in phases)
        }
    
    # 2. 提取connection信息
    tl_connections = defaultdict(dict)  # {tl_id: {linkIndex: from_edge}}
    for conn in root.findall('connection'):
        tl_id = conn.get('tl')
        if tl_id is None:
            continue
        link_idx = conn.get('linkIndex')
        if link_idx is None:
            continue
        from_edge = conn.get('from')
        tl_connections[tl_id][int(link_idx)] = from_edge
    
    # 3. 分析每个相位对应的主要进入路段
    result = {}
    for tl_id, info in tl_info.items():
        phase_edges = []
        num_phases = info['num_phases']
        state_len = len(info['phase_states'][0]) if info['phase_states'] else 0
        
        # 计算每个相位的绿灯组起始位置
        # 假设：每个相位控制一组连续的linkIndex
        # 通过比较相邻相位的state来确定每个相位的"专属"绿灯区域
        
        for phase_idx, state in enumerate(info['phase_states']):
            # 找到这个相位中"专属"的绿灯区域
            # 方法：找到只在这个相位是绿灯，而在其他相位是红灯的位置
            exclusive_greens = []
            for i, s in enumerate(state):
                if s in ['G', 'g']:
                    # 检查这个位置在其他相位是否是红灯
                    is_exclusive = True
                    for other_idx, other_state in enumerate(info['phase_states']):
                        if other_idx != phase_idx:
                            if i < len(other_state) and other_state[i] in ['G', 'g']:
                                is_exclusive = False
                                break
                    if is_exclusive:
                        exclusive_greens.append(i)
            
            # 选择专属绿灯中最小的linkIndex
            if exclusive_greens:
                min_link = min(exclusive_greens)
                main_edge = tl_connections[tl_id].get(min_link, 'unknown')
            else:
                # 回退：找所有绿灯中最小的
                all_greens = [i for i, s in enumerate(state) if s in ['G', 'g']]
                if all_greens:
                    min_link = min(all_greens)
                    main_edge = tl_connections[tl_id].get(min_link, 'unknown')
                else:
                    main_edge = 'unknown'
            
            phase_edges.append(main_edge)
        
        result[tl_id] = {
            'num_phases': info['num_phases'],
            'cycle': info['cycle'],
            'phase_edges': phase_edges
        }
    
    return result


def generate_signal_config(mapping: dict, output_dir: str) -> str:
    """
    生成signal_config.xml到指定目录的signal_config子目录
    
    Returns:
        生成的文件路径
    """
    # 确保输出目录存在
    config_dir = os.path.join(output_dir, 'signal_config')
    os.makedirs(config_dir, exist_ok=True)
    output_file = os.path.join(config_dir, 'signal_config.xml')
    
    return _write_signal_config(mapping, output_file)


def generate_signal_config_file(mapping: dict, output_dir: str) -> str:
    """
    直接生成signal_config.xml到指定目录（不创建子目录）
    
    Returns:
        生成的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'signal_config.xml')
    
    return _write_signal_config(mapping, output_file)


def _write_signal_config(mapping: dict, output_file: str) -> str:
    """
    写入signal_config.xml文件
    
    Returns:
        生成的文件路径
    """
    # 按交叉口ID排序（数字排序）
    sorted_tl_ids = sorted(mapping.keys(), key=lambda x: int(x) if x.isdigit() else x)
    
    # 创建根元素
    root = ET.Element('signal_config')
    root.set('yellow_time', '0')
    root.set('default_cycle', '120')
    root.set('min_green', '10')
    root.set('max_green', '60')
    
    var_index = 0
    
    for tl_id in sorted_tl_ids:
        info = mapping[tl_id]
        num_phases = info['num_phases']
        cycle = info['cycle']
        phase_edges = info['phase_edges']
        
        # 创建交叉口元素
        tl_elem = ET.SubElement(root, 'intersection')
        tl_elem.set('id', tl_id)
        tl_elem.set('cycle', str(cycle))
        tl_elem.set('num_phases', str(num_phases))
        tl_elem.set('var_start', str(var_index))
        tl_elem.set('var_end', str(var_index + num_phases - 1))
        
        # 添加相位
        for p in range(num_phases):
            phase_elem = ET.SubElement(tl_elem, 'phase')
            phase_elem.set('index', str(p * 2))
            phase_elem.set('var_index', str(var_index + p))
            phase_elem.set('duration', '30')
            phase_elem.set('min_green', '10')
            phase_elem.set('max_green', '60')
            phase_elem.set('edge', phase_edges[p])
        
        var_index += num_phases
    
    # 保存
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(prettify_xml(root))
    
    return output_file


def main():
    print("=" * 70)
    print("从net.xml重新生成signal_config.xml")
    print("=" * 70)
    
    # 确定输出目录
    if len(sys.argv) > 1:
        # 命令行指定输出目录
        output_dir = sys.argv[1]
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(PROJECT_ROOT, output_dir)
    else:
        output_dir = DEFAULT_OUTPUT_DIR
    
    print(f"Input:  {NET_FILE}")
    print(f"Output: {output_dir}")
    print()
    
    # 提取映射
    mapping = extract_phase_edge_mapping(NET_FILE)
    
    # 显示关键交叉口的映射
    print("关键交叉口的相位-路段映射（按linkIndex顺序）:")
    for tl_id in ['10', '16']:
        if tl_id in mapping:
            info = mapping[tl_id]
            print(f"\n交叉口 {tl_id}: {info['num_phases']}相位, cycle={info['cycle']}s")
            for p, edge in enumerate(info['phase_edges']):
                print(f"  相位{p}: {edge}")
    
    print()
    
    # 生成配置文件
    output_file = generate_signal_config(mapping, output_dir)
    
    # 统计
    total_vars = sum(info['num_phases'] for info in mapping.values())
    print(f"Generated: {output_file}")
    print(f"Total decision variables: {total_vars}")
    print(f"Total intersections: {len(mapping)}")
    
    print()
    print("=" * 70)
    print("完成！")
    print("=" * 70)
    
    return output_file


if __name__ == "__main__":
    main()
