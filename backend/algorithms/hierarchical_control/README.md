# 分层控制模块

## 模块简介
多层级交通控制系统，实现从宏观到微观的分层优化，包括区域协调、走廊控制、交叉口控制。

## 算法原理

### 分层架构
1. **宏观层**: 区域交通协调，OD需求管理
2. **中观层**: 走廊信号协调，绿波带优化
3. **微观层**: 单点信号控制，实时自适应

### 优化方法
- 分层优化算法
- 上下层信息交互
- 分布式决策

## 主要功能
- 区域信号协调
- 绿波带设计
- 多交叉口联动
- 分层性能评估

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| num_intersections | int | 5 | 交叉口数量 |
| coordination_mode | str | green_wave | 协调模式（green_wave/bandwidth） |
| optimization_level | str | all | 优化层级（macro/meso/micro/all） |

### 运行示例
```bash
cd backend/algorithms/hierarchical_control
python service.py --mode green_wave --intersections 5
```

## 输出结果
- **协调方案**: `output/coordination_plan_{timestamp}.xml`
- **性能评估**: `output/performance_{timestamp}.json`

## 性能指标
- **绿波带宽**: 双向绿波带宽度（秒）
- **停车次数**: 平均停车次数
- **协调度**: 信号协调效果评分

## 常见问题

### 1. 绿波带宽过窄
**解决方案**: 调整交叉口间距，优化周期时长，考虑单向绿波

### 2. 协调效果不稳定
**解决方案**: 增加协调交叉口数量，使用自适应协调算法

## 参考文献
1. 绿波协调: Little, J. D. C., "MAXBAND: A Program for Setting Signals", 1981
2. 分层控制: Papageorgiou, M., et al., "Hierarchical traffic control", 2003
