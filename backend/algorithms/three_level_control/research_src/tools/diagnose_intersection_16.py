"""
诊断交叉口16的优化问题

检查：
1. incoming_edges是否正确加载
2. 排队数据是否正确采集
3. 目标函数是否正确使用排队数据
4. 优化结果是否合理
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'data', 'signal_config'))

import numpy as np
from signal_config_io import load_config_from_xml


def diagnose_config():
    """诊断配置加载"""
    print("=" * 70)
    print("1. 配置加载诊断")
    print("=" * 70)
    
    config_dir = os.path.join(PROJECT_ROOT, 'data', 'signal_config')
    config = load_config_from_xml(config_dir)
    
    if not config:
        print("[ERROR] 配置加载失败!")
        return None
    
    # 检查交叉口16
    int16 = config['intersections'].get('16', {})
    if not int16:
        print("[ERROR] 交叉口16不存在!")
        return None
    
    print(f"交叉口16配置:")
    print(f"  cycle: {int16.get('cycle')}")
    print(f"  begin: {int16.get('begin')}")
    print(f"  end: {int16.get('end')}")
    print(f"  phases: {int16.get('phases')}")
    print(f"  incoming_edges: {int16.get('incoming_edges')}")
    
    # 检查决策变量
    print(f"\n决策变量 (var_index {int16['begin']}-{int16['end']}):")
    for dv in config['decision_vars']:
        if dv['intersection'] == '16':
            print(f"  var_{dv['var_index']}: phase={dv['phase']}, bounds=[{dv['min']}, {dv['max']}]")
    
    return config


def diagnose_objective_function():
    """诊断目标函数中的数据使用"""
    print("\n" + "=" * 70)
    print("2. 目标函数数据流诊断")
    print("=" * 70)
    
    # 模拟优化器的数据结构
    config_dir = os.path.join(PROJECT_ROOT, 'data', 'signal_config')
    config = load_config_from_xml(config_dir)
    
    int16 = config['intersections']['16']
    incoming_edges = int16['incoming_edges']
    
    print(f"\n交叉口16的相位-路段映射:")
    for p, edge in enumerate(incoming_edges):
        print(f"  相位{p} (var_index={int16['begin']+p}): {edge}")
    
    # 模拟排队数据
    print(f"\n模拟排队数据 (假设相位0拥堵):")
    mock_queue = {
        '10_16': 25,  # 相位0: 高排队
        '17_16': 5,   # 相位1: 低排队
        '18_16': 3,   # 相位2: 低排队
        '8_16': 8,    # 相位3: 中等排队
    }
    
    for p, edge in enumerate(incoming_edges):
        queue = mock_queue.get(edge, 0)
        print(f"  相位{p} ({edge}): queue={queue}")
    
    # 检查_get_phase_data的逻辑
    print(f"\n_get_phase_data逻辑检查:")
    print(f"  incoming_edges列表: {incoming_edges}")
    print(f"  当phase_idx=0时, edge_id = incoming_edges[0] = {incoming_edges[0]}")
    print(f"  当phase_idx=1时, edge_id = incoming_edges[1] = {incoming_edges[1]}")
    
    # 检查目标函数中的循环
    print(f"\n目标函数中的循环:")
    print(f"  begin={int16['begin']}, end={int16['end']}")
    print(f"  num_phases = end - begin + 1 = {int16['end'] - int16['begin'] + 1}")
    print(f"  for p in range(num_phases): # p = 0, 1, 2, 3")
    print(f"    g = u[begin + p]  # 获取绿灯时间")
    print(f"    queue, flow = _get_phase_data(tl_id, p)  # 获取排队和流量")


def diagnose_optimization_logic():
    """诊断优化逻辑"""
    print("\n" + "=" * 70)
    print("3. 优化逻辑诊断")
    print("=" * 70)
    
    config_dir = os.path.join(PROJECT_ROOT, 'data', 'signal_config')
    config = load_config_from_xml(config_dir)
    
    int16 = config['intersections']['16']
    cycle = int16['cycle']
    num_phases = int16['end'] - int16['begin'] + 1
    
    print(f"\n周期约束分析:")
    print(f"  周期: {cycle}s")
    print(f"  相位数: {num_phases}")
    print(f"  每相位边界: [10, 60]s")
    print(f"  最小总绿灯: {num_phases * 10}s")
    print(f"  最大总绿灯: {num_phases * 60}s")
    
    # 模拟不同排队情况下的理想绿灯分配
    print(f"\n理想绿灯分配 (按排队比例):")
    mock_queue = [25, 5, 3, 8]  # 相位0拥堵
    total_queue = sum(mock_queue)
    
    if total_queue > 0:
        ideal_green = [cycle * q / total_queue for q in mock_queue]
        print(f"  排队: {mock_queue}")
        print(f"  理想绿灯 (按比例): {[f'{g:.1f}s' for g in ideal_green]}")
        
        # 应用边界约束
        bounded_green = [max(10, min(60, g)) for g in ideal_green]
        print(f"  边界约束后: {[f'{g:.1f}s' for g in bounded_green]}")
        
        # 缩放到周期
        total = sum(bounded_green)
        if total != cycle:
            scale = cycle / total
            scaled_green = [g * scale for g in bounded_green]
            print(f"  周期缩放后: {[f'{g:.1f}s' for g in scaled_green]}")
    
    print(f"\n问题分析:")
    print(f"  如果相位0排队高但绿灯时间没有增加，可能原因:")
    print(f"  1. 排队数据没有正确采集到snapshot_queue")
    print(f"  2. _get_phase_data返回的queue为0")
    print(f"  3. 目标函数中queue的权重太低")
    print(f"  4. TuRBO优化陷入局部最优")
    print(f"  5. 周期约束导致无法给更多绿灯")


def suggest_debug_code():
    """建议添加的调试代码"""
    print("\n" + "=" * 70)
    print("4. 建议添加的调试代码")
    print("=" * 70)
    
    print("""
在 2_1_mpc_turbo.py 的 predict_travel_time 方法中添加:

```python
# 在交叉口循环内，相位循环前添加:
if tl_id == '16':
    print(f"  [Debug Int-16] incoming_edges: {info.get('incoming_edges', [])}")

# 在相位循环内添加:
if tl_id == '16':
    print(f"    Phase {p}: edge={incoming[p] if p < len(incoming) else 'N/A'}, "
          f"queue={queue:.1f}, flow={arrival_flow:.1f}, g={g:.1f}s")
```

在 _print_key_intersections_timing 方法中添加排队信息:

```python
# 获取排队数据
queue_info = []
for i, edge in enumerate(incoming):
    q = self.snapshot_queue.get(edge, 0)
    queue_info.append(f"Q{i}:{q:.0f}")
queue_str = " ".join(queue_info)
print(f"          Queue: {queue_str}")
```
""")


if __name__ == "__main__":
    diagnose_config()
    diagnose_objective_function()
    diagnose_optimization_logic()
    suggest_debug_code()
