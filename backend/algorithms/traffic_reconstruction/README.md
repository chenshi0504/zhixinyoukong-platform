# 交通流重构模块

## 模块简介
基于DTALite的交通流重构系统，根据观测数据反推路网交通流分布，用于交通状态估计和预测。

## 算法原理

### 动态交通分配（DTA）
- 基于用户均衡原理
- 考虑时变交通需求
- 路径选择和流量分配

### DTALite引擎
- 轻量级DTA求解器
- 快速收敛算法
- 支持大规模路网

## 主要功能
- OD矩阵估计
- 路段流量重构
- 交通状态估计
- 历史数据分析

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| network_file | str | - | 路网文件路径 |
| demand_file | str | - | 需求文件路径 |
| iterations | int | 100 | 迭代次数 |

### 运行示例
```bash
cd backend/algorithms/traffic_reconstruction
python run_dtalite.py --network data/network.csv --demand data/demand.csv
```

## 输出结果
- **重构流量**: `output/reconstructed_flow_{timestamp}.csv`
- **OD矩阵**: `output/od_matrix_{timestamp}.csv`

## 常见问题

### 1. 收敛速度慢
**解决方案**: 增加迭代次数，调整收敛阈值

### 2. 重构精度不足
**解决方案**: 增加观测点数量，使用更精确的初始OD矩阵

## 参考文献
1. DTALite: Zhou, X., & Taylor, J., "DTALite: A queue-based mesoscopic traffic simulator", 2014
