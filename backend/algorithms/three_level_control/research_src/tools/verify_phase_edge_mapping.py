"""
验证相位-路段映射的一致性

从 net.xml 提取真实的相位-路段对应关系，与 signal_config.xml 对比验证。

数据流程：
1. net.xml (基础): tlLogic定义相位，connection定义linkIndex
2. signal_config.xml: 优化器使用的配置
3. 2_1_mpc_turbo.py: apply_timing应用配时

验证目标：确保三者的相位-路段映射完全一致
"""
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NET_FILE = os.path.join(PROJECT_ROOT, 'config', 'siouxfalls.net.xml')
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'data', 'signal_config', 'signal_config.xml')


def extract_from_net_xml(net_file: str) -> dict:
    """
    从net.xml提取相位-路段映射
    
    Returns:
        {tl_id: {
            'num_phases': int,
            'phase_edges': [edge_id, ...],  # 按相位顺序
            'phase_durations': [duration, ...],
            'cycle': int
        }}
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
    
    # 2. 提取connection信息，建立linkIndex -> from_edge映射
    # linkIndex对应state字符串中的位置
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
    # 相位state中'G'或'g'的位置对应linkIndex
    result = {}
    for tl_id, info in tl_info.items():
        phase_edges = []
        
        for phase_idx, state in enumerate(info['phase_states']):
            # 找到这个相位中绿灯的linkIndex
            green_links = []
            for i, s in enumerate(state):
                if s in ['G', 'g']:
                    green_links.append(i)
            
            # 找到对应的进入路段（去重）
            edges_in_phase = set()
            for link_idx in green_links:
                if link_idx in tl_connections[tl_id]:
                    edges_in_phase.add(tl_connections[tl_id][link_idx])
            
            # 通常一个相位对应一个主要进入路段
            # 选择linkIndex最小的那个作为主要路段
            if green_links and tl_connections[tl_id]:
                min_link = min(green_links)
                main_edge = tl_connections[tl_id].get(min_link, 'unknown')
            else:
                main_edge = 'unknown'
            
            phase_edges.append({
                'main_edge': main_edge,
                'all_edges': sorted(edges_in_phase),
                'green_links': green_links
            })
        
        result[tl_id] = {
            'num_phases': info['num_phases'],
            'cycle': info['cycle'],
            'phase_durations': info['phase_durations'],
            'phase_edges': phase_edges
        }
    
    return result


def extract_from_signal_config(config_file: str) -> dict:
    """
    从signal_config.xml提取配置
    
    Returns:
        {tl_id: {
            'num_phases': int,
            'cycle': int,
            'phase_edges': [edge_id, ...]
        }}
    """
    tree = ET.parse(config_file)
    root = tree.getroot()
    
    result = {}
    for intersection in root.findall('intersection'):
        tl_id = intersection.get('id')
        cycle = int(intersection.get('cycle', 90))
        
        phases = intersection.findall('phase')
        phase_edges = []
        for phase in phases:
            edge = phase.get('edge', 'unknown')
            phase_edges.append(edge)
        
        result[tl_id] = {
            'num_phases': len(phases),
            'cycle': cycle,
            'phase_edges': phase_edges
        }
    
    return result


def verify_mapping():
    """验证映射一致性"""
    print("=" * 70)
    print("相位-路段映射验证")
    print("=" * 70)
    print(f"net.xml: {NET_FILE}")
    print(f"signal_config.xml: {CONFIG_FILE}")
    print()
    
    # 提取数据
    net_data = extract_from_net_xml(NET_FILE)
    config_data = extract_from_signal_config(CONFIG_FILE)
    
    print(f"net.xml中的信号灯: {len(net_data)}")
    print(f"signal_config.xml中的交叉口: {len(config_data)}")
    print()
    
    # 逐个交叉口验证
    all_match = True
    mismatch_details = []
    
    for tl_id in sorted(config_data.keys(), key=lambda x: int(x) if x.isdigit() else x):
        if tl_id not in net_data:
            print(f"[ERROR] 交叉口 {tl_id} 在net.xml中不存在!")
            all_match = False
            continue
        
        net_info = net_data[tl_id]
        config_info = config_data[tl_id]
        
        # 检查相位数
        if net_info['num_phases'] != config_info['num_phases']:
            print(f"[ERROR] 交叉口 {tl_id}: 相位数不匹配!")
            print(f"        net.xml: {net_info['num_phases']}, config: {config_info['num_phases']}")
            all_match = False
            continue
        
        # 检查周期
        if net_info['cycle'] != config_info['cycle']:
            print(f"[WARN] 交叉口 {tl_id}: 周期不匹配 (net={net_info['cycle']}, config={config_info['cycle']})")
        
        # 检查每个相位的路段映射
        phase_match = True
        for p_idx in range(config_info['num_phases']):
            config_edge = config_info['phase_edges'][p_idx]
            net_phase = net_info['phase_edges'][p_idx]
            net_main_edge = net_phase['main_edge']
            net_all_edges = net_phase['all_edges']
            
            if config_edge != net_main_edge and config_edge not in net_all_edges:
                phase_match = False
                mismatch_details.append({
                    'tl_id': tl_id,
                    'phase': p_idx,
                    'config_edge': config_edge,
                    'net_main_edge': net_main_edge,
                    'net_all_edges': net_all_edges
                })
        
        if phase_match:
            # 简洁输出匹配的交叉口
            edges_str = ", ".join(config_info['phase_edges'])
            print(f"[OK] Int-{tl_id}: {config_info['num_phases']}相位, cycle={config_info['cycle']}s")
            print(f"     路段: {edges_str}")
        else:
            all_match = False
            print(f"[ERROR] Int-{tl_id}: 相位-路段映射不匹配!")
    
    print()
    print("=" * 70)
    
    if mismatch_details:
        print("不匹配详情:")
        print("-" * 70)
        for m in mismatch_details:
            print(f"交叉口 {m['tl_id']}, 相位 {m['phase']}:")
            print(f"  signal_config.xml: {m['config_edge']}")
            print(f"  net.xml主路段: {m['net_main_edge']}")
            print(f"  net.xml所有路段: {m['net_all_edges']}")
            print()
    
    if all_match:
        print("✓ 所有交叉口的相位-路段映射验证通过!")
    else:
        print("✗ 存在映射不一致，需要修复signal_config.xml")
    
    print("=" * 70)
    
    return all_match, mismatch_details, net_data, config_data


if __name__ == "__main__":
    verify_mapping()
