# 数据融合模块

## 模块简介
多源交通数据融合系统，整合视频检测、雷达、GPS等多种传感器数据，提高目标检测和跟踪的准确性。

## 算法原理

### 贝叶斯融合
- 基于贝叶斯理论的概率融合
- 考虑各传感器的置信度和不确定性
- 动态权重分配

### 卡尔曼滤波
- 状态预测和更新
- 处理传感器噪声
- 平滑轨迹数据

## 主要功能
- 多传感器数据融合
- 目标状态估计
- 轨迹平滑和预测
- 融合结果可视化

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| fusion_method | str | bayesian | 融合方法（bayesian/kalman/custom） |
| sensor_weights | dict | auto | 各传感器权重 |
| update_rate | int | 10 | 更新频率（Hz） |

### 运行示例
```bash
cd backend/algorithms/data_fusion
python service.py --method bayesian
```

## 输出结果
- **融合结果JSON**: `output/fusion_result_{timestamp}.json`
- **轨迹对比图**: `output/trajectory_comparison_{timestamp}.png`

## 常见问题

### 1. 传感器数据不同步
**解决方案**: 使用时间戳对齐，设置合理的时间窗口

### 2. 融合精度不高
**解决方案**: 调整传感器权重，增加卡尔曼滤波的过程噪声协方差

## 参考文献
1. Kalman Filter: Kalman, R. E., "A New Approach to Linear Filtering and Prediction Problems", 1960
2. Bayesian Fusion: Murphy, K. P., "Machine Learning: A Probabilistic Perspective", 2012
