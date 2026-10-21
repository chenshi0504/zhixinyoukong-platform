# 车速控制模块

## 模块简介
智能网联车辆速度控制系统，基于模型预测控制（MPC）和强化学习，实现节能、安全、舒适的车速优化。

## 算法原理

### 模型预测控制（MPC）
- 预测未来状态轨迹
- 滚动优化控制序列
- 考虑约束条件（速度限制、加速度限制）

### 强化学习控制
- 基于PPO/SAC算法
- 学习最优控制策略
- 适应复杂交通场景

## 主要功能
- 单车速度优化
- 车队协同控制
- 节能驾驶
- 安全车距保持
- 舒适性优化

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| control_method | str | MPC | 控制方法（MPC/RL） |
| prediction_horizon | int | 10 | 预测时域（秒） |
| control_horizon | int | 5 | 控制时域（秒） |
| max_speed | float | 30.0 | 最大速度（m/s） |
| max_accel | float | 2.0 | 最大加速度（m/s²） |
| max_decel | float | -3.0 | 最大减速度（m/s²） |
| objective | str | fuel | 优化目标（fuel/time/comfort） |

### 运行示例
```bash
cd backend/algorithms/speed_control
python run_speed_control.py --method MPC --objective fuel
```

### API调用
```python
import requests

response = requests.post('http://localhost:5004/control', json={
    'current_speed': 15.0,
    'target_speed': 20.0,
    'distance_to_signal': 100.0,
    'signal_phase': 'green'
})
```

## 输出结果
- **控制轨迹**: `output/speed_trajectory_{timestamp}.json`
  - 时间序列、速度、加速度、位置
- **性能指标**: `output/performance_{timestamp}.json`
  - 燃油消耗、行程时间、舒适度评分
- **可视化图表**: `output/control_visualization_{timestamp}.png`

## 性能指标
- **燃油消耗**: 总燃油消耗量（升）
- **行程时间**: 完成行程所需时间（秒）
- **舒适度**: 基于加速度变化率的舒适度评分
- **安全性**: 最小车距、碰撞风险

## 依赖环境
- Python 3.10
- cvxpy (凸优化库，用于MPC)
- PyTorch (用于RL)
- SUMO 1.15+

## 常见问题

### 1. MPC求解失败
**问题**: 提示"优化问题无解"
**解决方案**:
- 放宽约束条件
- 减小预测时域
- 检查初始状态是否可行

### 2. 控制不平滑
**问题**: 速度曲线抖动明显
**解决方案**:
- 增加加速度变化率惩罚
- 调整控制时域
- 使用低通滤波器

### 3. 节能效果不明显
**问题**: 燃油消耗改善小于10%
**解决方案**:
- 调整目标函数权重
- 增加预测时域（更长远规划）
- 考虑信号灯信息（绿波控制）

## 技术细节

### MPC优化问题
```python
# 目标函数
minimize: Σ(fuel_cost + time_cost + comfort_cost)

# 约束条件
subject to:
    v_min ≤ v(t) ≤ v_max
    a_min ≤ a(t) ≤ a_max
    d(t) ≥ d_safe  # 安全车距
```

### 燃油消耗模型
```python
# VT-Micro模型
fuel_rate = exp(a0 + a1*v + a2*v^2 + a3*a + a4*a^2 + a5*v*a)
```

### 舒适度评价
```python
# 基于加速度变化率（jerk）
comfort_score = 1 / (1 + mean(|jerk|))
```

## 实验建议

### 基础实验
1. 使用MPC实现单车速度控制
2. 对比不同优化目标（节能vs快速）
3. 测试不同交通场景（自由流、跟驰、信号灯）

### 进阶实验
1. 实现车队协同控制
2. 对比MPC和RL的性能
3. 研究CAV渗透率对系统性能的影响
4. 设计绿波速度引导策略

## 参考文献
1. MPC: Camacho, E. F., & Alba, C. B., "Model predictive control", 2013
2. 燃油消耗模型: Rakha, H., et al., "VT-Micro model", 2004
3. 车队控制: Ploeg, J., et al., "Cooperative Adaptive Cruise Control", 2014
