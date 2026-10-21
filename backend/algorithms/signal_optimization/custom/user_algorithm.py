# Webster公式信号配时优化
# 基于经典Webster公式计算最优周期和绿信比

import numpy as np

def optimize_signal(flow_data, saturation_flow=1800):
    """
    Webster公式配时优化
    flow_data: dict, 各相位流量 {phase_id: flow_rate}
    saturation_flow: 饱和流率(pcu/h)
    """
    # 计算各相位流量比
    y_values = []
    for phase_id, flow in flow_data.items():
        y = flow / saturation_flow
        y_values.append(y)
    
    Y = sum(y_values)  # 总流量比
    L = len(y_values) * 4  # 总损失时间(每相位4s)
    
    # Webster最优周期
    C0 = (1.5 * L + 5) / (1 - Y)
    C0 = max(40, min(C0, 180))  # 限制在40-180s
    
    # 各相位有效绿灯时间
    green_times = []
    for y in y_values:
        g = (y / Y) * (C0 - L)
        g = max(10, round(g))  # 最小绿灯10s
        green_times.append(g)
    
    return {
        "cycle": round(C0),
        "green_times": green_times,
        "Y": round(Y, 3)
    }

# 示例调用
flow_data = {0: 600, 1: 450, 2: 500, 3: 380}
result = optimize_signal(flow_data)
print(f"最优周期: {result['cycle']}s")
print(f"绿灯时长: {result['green_times']}")