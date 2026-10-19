# 多层级协调控制系统

基于 Claw-AI-Lab 的多智能体协调模式，实现车路云一体化的三层级交通协调控制。

## 架构设计

### 三层级协调架构

```
云端协调层 (RegionOrchestrator)
    ↓ 全局策略
路侧协调层 (IntersectionAgent × N)
    ↓ 局部优化
车辆执行层 (VehicleAgent × M)
```

### 核心组件

#### 1. BaseAgent (基础智能体)
- 统一的执行接口 `execute(context) -> AgentStepResult`
- 状态追踪：LLM 调用次数、token 使用量
- 结果封装：success, data, error

#### 2. IntersectionAgent (路口智能体)
- 职责：单路口信号优化、车辆引导
- 输入：路口车流状态、相邻路口信息
- 输出：信号配时方案、速度建议
- 协调：与相邻路口协商绿波带

#### 3. VehicleAgent (车辆智能体)
- 职责：路径选择、速度控制
- 输入：当前位置、目的地、路网状态
- 输出：路径决策、速度调整
- 协调：接收路口引导信号

#### 4. RegionOrchestrator (区域协调器)
- 职责：多路口协调、全局优化
- 工作流：
  1. 收集各路口状态 (Collect Phase)
  2. 计算全局最优策略 (Optimize Phase)
  3. 分发协调指令 (Dispatch Phase)
  4. 验证执行效果 (Validate Phase)
- 迭代：支持多轮优化，最大迭代次数可配置

### 协调机制

#### 数据流

```python
# 上行数据流（车辆 → 路口 → 区域）
VehicleState → IntersectionAgent.collect()
IntersectionState → RegionOrchestrator.collect()

# 下行数据流（区域 → 路口 → 车辆）
RegionStrategy → IntersectionAgent.apply_strategy()
IntersectionGuidance → VehicleAgent.apply_guidance()
```

#### 协调协议

**路口间协调**：
- 绿波协调：相邻路口信号相位差优化
- 流量均衡：拥堵路口向空闲路口分流
- 优先级协商：紧急车辆优先通行

**车辆协调**：
- 路径诱导：避开拥堵路段
- 速度引导：匹配绿波速度
- 队列管理：CAV 车辆编队通行

### 对比实验

#### 场景设置
- 路网：4 路口区域网络（2×2 网格）
- 车流：低/中/高三种流量等级
- CAV 渗透率：0%, 20%, 40%, 60%, 80%

#### 对比模式
1. **无协调模式**：各路口独立固定配时
2. **路口协调模式**：相邻路口绿波协调
3. **全局协调模式**：区域级多层级协调

#### 评估指标
- 平均延误时间（秒）
- 平均排队长度（辆）
- 路网通行效率（辆/小时）
- 停车次数
- 燃油消耗

## 技术实现

### 依赖 Claw-AI-Lab 模式
- `BaseAgent` 和 `AgentOrchestrator` 基类
- `AgentStepResult` 统一结果格式
- 迭代验证机制（Acquire → Validate 循环）

### SUMO 集成
- TraCI 实时控制接口
- 信号灯动态调整
- 车辆速度/路径控制
- 检测器数据采集

### 可视化
- 实时路网状态图
- 协调决策流程图
- 性能对比曲线图
- 协调消息序列图

## 使用方式

### 启动实验
```python
python run_multi_level_coordination.py \
    --scenario grid_4x4 \
    --traffic_level medium \
    --cav_penetration 0.6 \
    --coordination_mode full
```

### 参数说明
- `--scenario`: 场景名称（grid_4x4, arterial, etc.）
- `--traffic_level`: 流量等级（low, medium, high）
- `--cav_penetration`: CAV 渗透率（0.0-1.0）
- `--coordination_mode`: 协调模式（none, local, full）
- `--max_iterations`: 最大迭代次数（默认 3）

## 文件结构

```
multi_level_coordination/
├── README.md                    # 本文件
├── agents/
│   ├── __init__.py
│   ├── base.py                  # BaseAgent, AgentOrchestrator
│   ├── vehicle_agent.py         # VehicleAgent
│   ├── intersection_agent.py    # IntersectionAgent
│   └── region_orchestrator.py   # RegionOrchestrator
├── scenarios/
│   ├── grid_4x4.net.xml         # 4路口网格路网
│   ├── grid_4x4.rou.xml         # 车流配置
│   └── grid_4x4.sumocfg         # SUMO 配置
├── coordination/
│   ├── __init__.py
│   ├── protocols.py             # 协调协议定义
│   └── strategies.py            # 协调策略实现
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py               # 评估指标计算
│   └── visualizer.py            # 可视化工具
├── run_multi_level_coordination.py  # 主入口
└── output/                      # 实验结果输出
    ├── logs/
    ├── figures/
    └── data/
```

## 实验流程

1. **初始化阶段**
   - 加载 SUMO 场景
   - 创建 Agent 实例
   - 建立通信连接

2. **运行阶段**（每个仿真步）
   - 车辆 Agent 上报状态
   - 路口 Agent 收集数据
   - 区域协调器计算策略
   - 下发控制指令
   - 执行控制动作

3. **评估阶段**
   - 收集性能指标
   - 生成对比图表
   - 输出实验报告

## 预期效果

- 全局协调模式相比无协调模式：
  - 平均延误降低 25-40%
  - 排队长度减少 30-50%
  - 通行效率提升 20-35%
  
- CAV 渗透率越高，协调效果越显著
- 高流量场景下协调收益最大
