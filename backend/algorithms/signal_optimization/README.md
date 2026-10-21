# 信号优化模块

## 模块简介
基于强化学习的交叉口信号配时优化系统，支持DQN、PPO等多种算法，实现自适应信号控制。

## 算法原理

### 强化学习框架
- **状态空间**: 各进口道排队长度、等待时间、相位状态
- **动作空间**: 信号相位切换决策
- **奖励函数**: 基于延误、排队长度、通行效率的综合奖励

### 支持的算法
1. **DQN (Deep Q-Network)**: 深度Q学习，适合离散动作空间
2. **PPO (Proximal Policy Optimization)**: 近端策略优化，训练稳定
3. **TuRBO**: 贝叶斯优化，适合参数调优

## 主要功能
- 单交叉口信号优化
- 多交叉口协调控制
- 实时自适应信号控制
- 离线训练和在线部署
- 性能评估和可视化

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| algorithm | str | DQN | 优化算法（DQN/PPO/TuRBO） |
| episodes | int | 200 | 训练轮数 |
| learning_rate | float | 0.001 | 学习率 |
| batch_size | int | 32 | 批次大小 |
| gamma | float | 0.99 | 折扣因子 |
| epsilon_start | float | 1.0 | 初始探索率 |
| epsilon_end | float | 0.01 | 最终探索率 |
| traffic_level | int | 4 | 流量等级（2/4/6对应低/中/高） |

### 运行示例

**通过Web界面运行**:
1. 在实验平台选择"信号优化"模块
2. 选择优化算法和配置参数
3. 点击"开始训练"按钮
4. 查看训练过程和优化结果

**通过命令行运行**:
```bash
cd backend/algorithms/signal_optimization
python run_signal_opt.py --algorithm DQN --episodes 200 --traffic_level 4
```

### API调用
```python
import requests

# 启动信号优化
response = requests.post('http://localhost:5002/optimize', json={
    'algorithm': 'DQN',
    'episodes': 200,
    'traffic_level': 4
})

# 获取优化结果
results = requests.get('http://localhost:5002/results')
```

## 输出结果
- **训练曲线**: `output/training_curve_{timestamp}.png`
  - 奖励曲线、损失曲线、延误变化
- **优化结果JSON**: `output/optimization_result_{timestamp}.json`
  - 最优配时方案、性能指标、收敛信息
- **SUMO仿真视频**: `output/sumo_simulation_{timestamp}.mp4`
  - 优化前后的交通仿真对比
- **模型文件**: `output/model_{timestamp}.pth`
  - 训练好的神经网络模型

## 性能指标
- **平均延误**: 车辆平均等待时间（秒）
- **排队长度**: 各进口道平均排队车辆数
- **通行能力**: 单位时间通过交叉口的车辆数
- **优化提升**: 相比固定配时的改善百分比

## 依赖环境
- Python 3.10
- PyTorch 2.0+
- SUMO 1.15+
- numpy, pandas
- matplotlib

## 常见问题

### 1. SUMO连接失败
**问题**: 提示"无法连接到SUMO服务器"
**解决方案**:
- 确认SUMO已正确安装并配置环境变量
- 检查端口8813是否被占用
- 尝试手动启动SUMO: `sumo-gui -c config.sumocfg`

### 2. 训练不收敛
**问题**: 奖励曲线波动大，不收敛
**解决方案**:
- 降低学习率（如0.0001）
- 增加训练轮数（如500轮）
- 调整奖励函数权重
- 使用PPO算法（更稳定）

### 3. 优化效果不明显
**问题**: 优化后延误改善小于5%
**解决方案**:
- 检查流量等级设置是否合理
- 增加状态空间维度（更多交通信息）
- 调整动作空间粒度
- 使用预训练模型作为初始化

### 4. 内存不足
**问题**: 训练过程中内存溢出
**解决方案**:
- 减小batch_size（如16）
- 减小经验回放缓冲区大小
- 使用更小的神经网络结构

## 技术细节

### DQN网络结构
```
输入层: 状态维度（如12维）
隐藏层1: 128个神经元 + ReLU
隐藏层2: 64个神经元 + ReLU
输出层: 动作维度（如4个相位）
```

### 奖励函数设计
```python
reward = -w1 * avg_delay - w2 * queue_length + w3 * throughput
```
- w1=1.0: 延误权重
- w2=0.5: 排队权重
- w3=0.1: 通行能力权重

### SUMO仿真配置
- 仿真步长: 1秒
- 仿真时长: 3600秒（1小时）
- 路网: 单交叉口4进口道
- 车辆生成: 泊松分布

## 实验建议

### 初学者
1. 使用默认参数运行DQN算法
2. 观察训练过程和收敛情况
3. 对比优化前后的性能指标

### 进阶用户
1. 尝试不同算法（DQN vs PPO）
2. 调整超参数进行对比实验
3. 修改奖励函数优化目标
4. 扩展到多交叉口协调控制

## 参考文献
1. DQN: Mnih et al., "Human-level control through deep reinforcement learning", Nature 2015
2. PPO: Schulman et al., "Proximal Policy Optimization Algorithms", arXiv 2017
3. SUMO: https://www.eclipse.org/sumo/
