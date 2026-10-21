"""
PPO 信号优化算法（Proximal Policy Optimization）

文件编号: 2_5 (sig=5)
配置编码: 1_5_{flow}_X 表示使用 PPO 算法

来源：HAC3论文 "Hierarchical adaptive cross-coupled control of traffic signals and vehicle routes" (2025)

实现：
- PPO (Proximal Policy Optimization) 用于信号配时优化
- 多智能体架构：每个交叉口一个智能体
- 状态：各相位的排队长度、车辆数、当前相位
- 动作：选择下一个相位或延长当前相位
- 奖励：负的总延误 + 吞吐量奖励

支持 GPU 加速（自动检测 CUDA）
"""
import os
import random
import numpy as np
import pandas as pd
import traci
import sumolib
from collections import deque
from typing import Dict, List, Tuple, Optional

# 尝试导入PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.distributions import Categorical
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not available, PPO will use fixed timing")


def get_device():
    """自动检测并返回最佳设备"""
    if TORCH_AVAILABLE and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class ActorCritic(nn.Module):
    """
    Actor-Critic 网络
    
    Actor: 输出动作概率分布
    Critic: 输出状态价值
    """
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
        super(ActorCritic, self).__init__()
        
        # 共享特征提取层
        self.shared = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU()
        )
        
        # Actor头（输出动作概率）
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        )
        
        # Critic头（输出状态价值）
        self.critic = nn.Linear(hidden_dim, 1)
    
    def forward(self, x):
        features = self.shared(x)
        action_probs = self.actor(features)
        state_value = self.critic(features)
        return action_probs, state_value
    
    def act(self, state):
        """选择动作"""
        action_probs, _ = self.forward(state)
        dist = Categorical(action_probs)
        action = dist.sample()
        return action, dist.log_prob(action)
    
    def evaluate(self, state, action):
        """评估动作"""
        action_probs, state_value = self.forward(state)
        dist = Categorical(action_probs)
        action_log_prob = dist.log_prob(action)
        entropy = dist.entropy()
        return action_log_prob, state_value, entropy


class RolloutBuffer:
    """
    经验缓冲区（用于PPO的on-policy学习）
    """
    
    def __init__(self):
        self.states = []
        self.actions = []
        self.rewards = []
        self.log_probs = []
        self.dones = []
        self.values = []
    
    def add(self, state, action, reward, log_prob, done, value):
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.log_probs.append(log_prob)
        self.dones.append(done)
        self.values.append(value)
    
    def clear(self):
        self.states = []
        self.actions = []
        self.rewards = []
        self.log_probs = []
        self.dones = []
        self.values = []
    
    def __len__(self):
        return len(self.states)


class PPOOptimizer:
    """
    PPO信号优化器
    
    基于HAC3论文的多智能体PPO实现
    每个交叉口独立决策，但共享网络参数
    """
    
    # 常量
    SATURATION_FLOW_PER_LANE = 1800
    MIN_GREEN = 10
    MAX_GREEN = 60
    SAMPLE_INTERVAL = 10
    MAX_SAMPLES = 30
    
    # PPO超参数（优化版 - 更稳定的策略学习）
    GAMMA = 0.95           # 降低折扣因子，更关注短期效果
    GAE_LAMBDA = 0.90      # 降低GAE参数，减少方差
    CLIP_EPSILON = 0.1     # 减小裁剪范围，更保守的更新
    ENTROPY_COEF = 0.01    # 降低熵正则化，减少随机性
    VALUE_COEF = 0.5       # 价值损失系数
    LEARNING_RATE = 1e-4   # 降低学习率，更稳定
    PPO_EPOCHS = 5         # 减少epoch数，避免过拟合
    BATCH_SIZE = 32        # 减小batch size，更频繁更新
    MIN_BUFFER_SIZE = 64   # 开始训练前的最小经验数
    # 动作空间：保守调整
    ACTION_ADJUSTMENTS = [-3, -1, 0, 1, 3]  # 更小的调整幅度
    
    def __init__(self, net_file: str, config_dir: str = None):
        self.net_file = net_file
        self.config_dir = config_dir
        self.net = None
        self.device = get_device()
        self.use_gpu = TORCH_AVAILABLE and (self.device.type == "cuda")
        
        # 优化间隔
        self.optimization_interval = 60  # 每60秒决策一次
        
        # 交叉口信息
        self.intersections = {}
        self.edge_phase = {}
        self.saturation_flow = {}
        
        # 状态维度和动作维度
        self.state_dim = 0
        self.action_dim = 4  # 假设每个交叉口4个相位
        
        # PPO网络
        self.policy = None
        self.optimizer = None
        self.buffer = RolloutBuffer()
        
        # 当前状态
        self.current_timing = None
        self.current_phases = {}  # {tls_id: current_phase_index}
        self.dim = 0
        self.lb = None
        self.ub = None
        
        # 控制标志
        self.enabled = False
        self.initialized = False
        
        # 记录
        self.green_time_records = []
        self.output_dir = None
        self.optimization_count = 0
        self.training_steps = 0
        self.episode_rewards = []
        
        # 数据采集
        self.queue_history = {}
        self.flow_history = {}
        self.snapshot_queue = {}
        self.snapshot_flow = {}
        self.last_sample_time = 0
        
        # 上一步状态
        self.last_state = None
        self.last_action = None
        self.last_log_prob = None
        self.last_value = None
        self.last_reward = 0.0

    def auto_initialize(self, data_dir: str = None):
        """自动初始化"""
        print("[PPO] Initializing...")
        print(f"  Device: {self.device} {'(GPU accelerated)' if self.use_gpu else '(CPU)'}")
        
        if data_dir:
            xml_file = os.path.join(data_dir, 'signal_config.xml')
            if os.path.exists(xml_file):
                self._load_from_xml_file(xml_file)
                self._init_ppo()
                self.initialized = True
                return
        
        self._extract_from_network()
        self._init_ppo()
        self.initialized = True

    def _init_ppo(self):
        """初始化PPO网络"""
        if not TORCH_AVAILABLE:
            print("  Warning: PyTorch not available, using fixed timing")
            return
        
        # 状态维度：每个相位的排队、车辆数、绿灯比例、压力
        self.state_dim = self.dim * 4
        
        # 动作维度：全局调整策略（5种调整幅度）
        # 改进：不再是单交叉口决策，而是全局调整策略
        self.num_intersections = len(self.intersections)
        self.action_dim = len(self.ACTION_ADJUSTMENTS)  # 简化为5种全局调整策略
        
        self.policy = ActorCritic(self.state_dim, self.action_dim, hidden_dim=256).to(self.device)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=self.LEARNING_RATE)
        
        # 初始化配时
        self.current_timing = np.ones(self.dim) * 30
        
        print(f"  PPO initialized: state_dim={self.state_dim}, action_dim={self.action_dim}")
        print(f"  Action space: {len(self.ACTION_ADJUSTMENTS)} global adjustment strategies")
        print(f"  Intersections: {self.num_intersections} (all adjusted simultaneously)")
        print(f"  Network parameters: {sum(p.numel() for p in self.policy.parameters())}")

    def _load_from_xml_file(self, xml_file: str):
        """从XML文件加载配置"""
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            lb_list, ub_list = [], []
            
            for tl_elem in root.findall('intersection'):
                tl_id = tl_elem.get('id')
                self.intersections[tl_id] = {
                    'cycle': int(tl_elem.get('cycle', '90')),
                    'begin': int(tl_elem.get('var_start', '0')),
                    'end': int(tl_elem.get('var_end', '0')),
                    'phases': [],
                    'incoming_edges': []
                }
                self.current_phases[tl_id] = 0
                
                for phase_elem in tl_elem.findall('phase'):
                    phase_idx = int(phase_elem.get('index', '0'))
                    min_green = max(self.MIN_GREEN, int(phase_elem.get('min_green', '10')))
                    max_green = int(phase_elem.get('max_green', '60'))
                    edge_id = phase_elem.get('edge', '')
                    
                    self.intersections[tl_id]['phases'].append(phase_idx)
                    if edge_id:
                        self.intersections[tl_id]['incoming_edges'].append(edge_id)
                        self.edge_phase[edge_id] = phase_idx
                    
                    lb_list.append(min_green)
                    ub_list.append(max_green)
            
            self.lb = np.array(lb_list, dtype=np.float64)
            self.ub = np.array(ub_list, dtype=np.float64)
            self.dim = len(lb_list)
            
            self.net = sumolib.net.readNet(self.net_file)
            for edge in self.net.getEdges():
                edge_id = edge.getID()
                if not edge_id.startswith(':'):
                    self.saturation_flow[edge_id] = edge.getLaneNumber() * self.SATURATION_FLOW_PER_LANE
            
            print(f"  Loaded: {self.dim} vars, {len(self.intersections)} intersections")
        except Exception as e:
            print(f"  Warning: XML load failed: {e}")
            self._extract_from_network()

    def _extract_from_network(self):
        """从路网提取配置"""
        self.net = sumolib.net.readNet(self.net_file)
        tl_nodes = [n.getID() for n in self.net.getNodes() if n.getType() == 'traffic_light']
        
        var_index = 0
        lb_list, ub_list = [], []
        
        for tl_id in tl_nodes:
            incoming_edges = [e.getID() for e in self.net.getEdges() 
                            if e.getToNode().getID() == tl_id and not e.getID().startswith(':')]
            num_phases = min(len(incoming_edges), 4)
            if num_phases == 0:
                continue
            
            self.intersections[tl_id] = {
                'cycle': 90,
                'begin': var_index,
                'end': var_index + num_phases - 1,
                'incoming_edges': incoming_edges
            }
            self.current_phases[tl_id] = 0
            
            for i in range(num_phases):
                lb_list.append(self.MIN_GREEN)
                ub_list.append(self.MAX_GREEN)
            var_index += num_phases
        
        self.lb = np.array(lb_list, dtype=np.float64)
        self.ub = np.array(ub_list, dtype=np.float64)
        self.dim = len(self.lb)
        print(f"  Extracted: {self.dim} variables")

    def collect_traffic_data(self, current_time: float):
        """采集交通数据"""
        if current_time - self.last_sample_time < self.SAMPLE_INTERVAL:
            return
        self.last_sample_time = current_time
        
        all_edges = set()
        for info in self.intersections.values():
            all_edges.update(info.get('incoming_edges', []))
        
        for eid in all_edges:
            if not eid:
                continue
            try:
                queue = traci.edge.getLastStepHaltingNumber(eid)
                veh = traci.edge.getLastStepVehicleNumber(eid)
                
                if eid not in self.queue_history:
                    self.queue_history[eid] = []
                self.queue_history[eid].append(queue)
                if len(self.queue_history[eid]) > self.MAX_SAMPLES:
                    self.queue_history[eid] = self.queue_history[eid][-self.MAX_SAMPLES:]
                
                if eid not in self.flow_history:
                    self.flow_history[eid] = []
                self.flow_history[eid].append(veh)
                if len(self.flow_history[eid]) > self.MAX_SAMPLES:
                    self.flow_history[eid] = self.flow_history[eid][-self.MAX_SAMPLES:]
            except:
                pass

    def create_snapshot(self):
        """创建数据快照"""
        self.snapshot_queue = {eid: np.mean(q) for eid, q in self.queue_history.items() if q}
        self.snapshot_flow = {eid: np.mean(f) for eid, f in self.flow_history.items() if f}

    def clear_history(self):
        """清空历史数据"""
        self.queue_history = {}
        self.flow_history = {}

    def get_state(self) -> np.ndarray:
        """
        获取全局状态向量（改进版，参考HAC3论文）
        
        状态包括：
        - 各相位排队长度（归一化）
        - 各相位车辆数（归一化）
        - 当前绿灯时间比例
        - 压力指标
        """
        state = []
        
        for tl_id, info in self.intersections.items():
            incoming_edges = info.get('incoming_edges', [])
            num_phases = info['end'] - info['begin'] + 1
            cycle = info['cycle']
            begin = info['begin']
            
            for p in range(num_phases):
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                if edge_id:
                    queue = self.snapshot_queue.get(edge_id, 0)
                    veh = self.snapshot_flow.get(edge_id, 0)
                else:
                    queue, veh = 0, 0
                
                # 当前绿灯时间
                green = self.current_timing[begin + p] if self.current_timing is not None and begin + p < len(self.current_timing) else 30
                green_ratio = green / cycle
                
                # 压力指标
                pressure = queue / max(green_ratio, 0.1)
                
                state.append(queue / 50.0)       # 排队归一化
                state.append(veh / 30.0)         # 车辆数归一化
                state.append(green_ratio)        # 绿灯比例
                state.append(pressure / 100.0)   # 压力归一化
        
        return np.array(state, dtype=np.float32)

    def compute_reward(self) -> float:
        """
        计算奖励（优化版 - 更密集且稳定的奖励信号）
        
        奖励 = -总压力 + 吞吐量奖励 - 排队惩罚 + 改善奖励
        """
        total_pressure = 0.0
        total_throughput = 0.0
        total_queue = 0.0
        
        for tl_id, info in self.intersections.items():
            incoming_edges = info.get('incoming_edges', [])
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            
            intersection_pressure = 0.0
            
            for i, edge_id in enumerate(incoming_edges):
                if edge_id:
                    queue = self.snapshot_queue.get(edge_id, 0)
                    flow = self.snapshot_flow.get(edge_id, 0)
                    
                    green = self.current_timing[begin + i] if begin + i < len(self.current_timing) else 30
                    green_ratio = green / cycle
                    
                    if green_ratio > 0:
                        pressure = queue / green_ratio
                    else:
                        pressure = queue * 10
                    
                    intersection_pressure += pressure
                    total_queue += queue
                    total_throughput += flow
            
            total_pressure += intersection_pressure
        
        # 排队改善奖励
        improvement_bonus = 0.0
        if hasattr(self, 'last_total_queue_ppo'):
            if total_queue < self.last_total_queue_ppo:
                improvement_bonus = (self.last_total_queue_ppo - total_queue) * 0.05
        self.last_total_queue_ppo = total_queue
        
        # 综合奖励：更平衡的权重
        reward = -total_pressure / 200.0 + total_throughput / 400.0 - total_queue / 100.0 + improvement_bonus
        
        # 奖励裁剪
        reward = np.clip(reward, -5, 5)
        
        return reward

    def select_action(self, state: np.ndarray) -> Tuple[int, float, float]:
        """选择动作"""
        if not TORCH_AVAILABLE or self.policy is None:
            return 0, 0.0, 0.0
        
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            action, log_prob = self.policy.act(state_tensor)
            _, value = self.policy(state_tensor)
            
        return action.item(), log_prob.item(), value.item()

    def apply_action(self, action: int, current_time: float):
        """
        应用动作（改进版 - 同时调整所有交叉口）
        
        动作解码：action = adjustment_idx (0-4)
        根据各交叉口的排队情况，按比例分配调整
        所有交叉口同时调整，避免单点调整导致的连锁拥堵
        """
        adjustment = self.ACTION_ADJUSTMENTS[action]
        
        for tl_id, info in self.intersections.items():
            try:
                programs = traci.trafficlight.getAllProgramLogics(tl_id)
                if not programs:
                    continue
                
                program = programs[0]
                begin, end = info['begin'], info['end']
                cycle = info['cycle']
                incoming_edges = info.get('incoming_edges', [])
                num_phases = end - begin + 1
                
                # 获取各相位排队
                queues = []
                for p in range(num_phases):
                    edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                    q = self.snapshot_queue.get(edge_id, 0) if edge_id else 0
                    queues.append(q)
                
                total_queue = sum(queues) + 0.1
                
                # 根据排队比例分配调整（所有交叉口同时调整）
                green_times = list(self.current_timing[begin:end+1])
                for p in range(num_phases):
                    weight = queues[p] / total_queue
                    # 排队多的相位获得更多绿灯时间
                    phase_adj = adjustment * (weight * 2)
                    green_times[p] = np.clip(
                        green_times[p] + phase_adj,
                        self.MIN_GREEN,
                        self.MAX_GREEN
                    )
                
                # 周期约束
                total = sum(green_times)
                if total > 0 and abs(total - cycle) > 0.1:
                    scale = cycle / total
                    green_times = [np.clip(g * scale, self.MIN_GREEN, self.MAX_GREEN) for g in green_times]
                
                green_times = [int(g) for g in green_times]
                
                # 更新配时
                for i, gt in enumerate(green_times):
                    self.current_timing[begin + i] = gt
                    self.green_time_records.append({
                        'time': current_time,
                        'tl_id': tl_id,
                        'phase_idx': i * 2,
                        'green_time': gt
                    })
                
                # 应用到SUMO
                green_idx = 0
                for phase in program.phases:
                    if 'G' in phase.state or 'g' in phase.state:
                        if green_idx < len(green_times):
                            phase.duration = float(green_times[green_idx])
                            phase.minDur = float(green_times[green_idx])
                            phase.maxDur = float(green_times[green_idx])
                            green_idx += 1
                
                traci.trafficlight.setProgramLogic(tl_id, program)
                
            except Exception as e:
                pass  # 静默处理错误，避免日志过多

    def update_policy(self):
        """PPO策略更新（优化版）"""
        if not TORCH_AVAILABLE or self.policy is None:
            return
        
        if len(self.buffer) < self.MIN_BUFFER_SIZE:
            return
        
        # 计算优势函数
        states = torch.FloatTensor(np.array(self.buffer.states)).to(self.device)
        actions = torch.LongTensor(self.buffer.actions).to(self.device)
        old_log_probs = torch.FloatTensor(self.buffer.log_probs).to(self.device)
        rewards = self.buffer.rewards
        dones = self.buffer.dones
        values = self.buffer.values
        
        # GAE计算
        advantages = []
        gae = 0
        for i in reversed(range(len(rewards))):
            if i == len(rewards) - 1:
                next_value = 0
            else:
                next_value = values[i + 1]
            
            delta = rewards[i] + self.GAMMA * next_value * (1 - dones[i]) - values[i]
            gae = delta + self.GAMMA * self.GAE_LAMBDA * (1 - dones[i]) * gae
            advantages.insert(0, gae)
        
        advantages = torch.FloatTensor(advantages).to(self.device)
        returns = advantages + torch.FloatTensor(values).to(self.device)
        
        # 归一化优势
        if len(advantages) > 1:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # PPO更新
        for _ in range(self.PPO_EPOCHS):
            log_probs, state_values, entropy = self.policy.evaluate(states, actions)
            
            # 计算比率
            ratios = torch.exp(log_probs - old_log_probs)
            
            # 裁剪目标
            surr1 = ratios * advantages
            surr2 = torch.clamp(ratios, 1 - self.CLIP_EPSILON, 1 + self.CLIP_EPSILON) * advantages
            
            # 损失
            actor_loss = -torch.min(surr1, surr2).mean()
            critic_loss = nn.SmoothL1Loss()(state_values.squeeze(), returns)  # Huber loss更稳定
            entropy_loss = -entropy.mean()
            
            loss = actor_loss + self.VALUE_COEF * critic_loss + self.ENTROPY_COEF * entropy_loss
            
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.policy.parameters(), 0.5)
            self.optimizer.step()
            
            self.training_steps += 1
        
        self.buffer.clear()

    def step(self, current_time: float):
        """PPO步进"""
        if not self.enabled:
            return
        
        WARMUP_TIME = 600
        DECISION_INTERVAL = 60
        LOG_INTERVAL = 300
        
        # 持续采集数据
        self.collect_traffic_data(current_time)
        
        # 预热期不优化
        if current_time < WARMUP_TIME:
            return
        
        # 决策间隔
        time_since_warmup = current_time - WARMUP_TIME
        if time_since_warmup > 0 and time_since_warmup % DECISION_INTERVAL == 0:
            self.optimization_count += 1
            self._run_optimization(current_time, verbose=(time_since_warmup % LOG_INTERVAL == 0))

    def _run_optimization(self, current_time: float, verbose: bool = True):
        """执行一次PPO决策"""
        self.create_snapshot()
        
        # 获取状态
        state = self.get_state()
        
        # 存储上一步经验
        if self.last_state is not None:
            reward = self.compute_reward()
            inference_only = getattr(self, 'inference_only', False)
            if not inference_only:
                self.buffer.add(
                    self.last_state,
                    self.last_action,
                    reward,
                    self.last_log_prob,
                    False,
                    self.last_value
                )
            self.episode_rewards.append(reward)
            self.last_reward = reward
        
        # 选择动作
        action, log_prob, value = self.select_action(state)
        
        # 应用动作
        self.apply_action(action, current_time)
        
        # 保存当前状态
        self.last_state = state
        self.last_action = action
        self.last_log_prob = log_prob
        self.last_value = value
        
        # 更新策略（推理模式下跳过）
        inference_only = getattr(self, 'inference_only', False)
        if not inference_only and len(self.buffer) >= self.BATCH_SIZE:
            self.update_policy()
        
        # 输出
        if verbose:
            print(f"\n{'='*60}")
            print(f"[PPO] Decision #{self.optimization_count} at t={current_time}s")
            print(f"{'='*60}")
            print(f"  Algorithm: PPO (Proximal Policy Optimization)")
            print(f"  Device: {self.device}")
            print(f"  Action: {action}, Reward: {self.last_reward:.2f}")
            print(f"  Buffer size: {len(self.buffer)}")
            print(f"  Training steps: {self.training_steps}")
        else:
            print(f"  [PPO] t={current_time}s: #{self.optimization_count}, action={action}, r={self.last_reward:.1f}")
        
        self.clear_history()

    def set_output_dir(self, output_dir: str):
        """设置输出目录"""
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def record_initial_green_times(self):
        """记录初始绿灯时长"""
        print(f"  Reading initial green times from SUMO...")
        for tl_id, info in self.intersections.items():
            try:
                programs = traci.trafficlight.getAllProgramLogics(tl_id)
                if not programs:
                    continue
                program = programs[0]
                green_idx = 0
                begin = info['begin']
                for phase in program.phases:
                    if 'G' in phase.state or 'g' in phase.state:
                        green_time = int(phase.duration)
                        self.green_time_records.append({
                            'time': 0,
                            'tl_id': tl_id,
                            'phase_idx': green_idx * 2,
                            'green_time': green_time
                        })
                        if self.current_timing is not None and begin + green_idx < len(self.current_timing):
                            self.current_timing[begin + green_idx] = green_time
                        green_idx += 1
            except Exception as e:
                print(f"    Warning: {tl_id}: {e}")

    def save_green_times_to_excel(self, filename: str = None):
        """保存绿灯时长到Excel"""
        if not self.green_time_records or not self.output_dir:
            return
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        if filename is None:
            filename = 'green_times.xlsx'
        
        output_path = os.path.join(self.output_dir, filename)
        df = pd.DataFrame(self.green_time_records)
        df['tl_phase'] = df['tl_id'].astype(str) + '_P' + df['phase_idx'].astype(str)
        
        pivot = df.pivot_table(index='time', columns='tl_phase', values='green_time', aggfunc='first')
        pivot = pivot.reset_index()
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            pivot.to_excel(writer, sheet_name='绿灯时长汇总', index=False)
            df_raw = pd.DataFrame(self.green_time_records)
            df_raw.columns = ['时间(s)', '交叉口ID', '相位编号', '绿灯时长(s)']
            df_raw.to_excel(writer, sheet_name='原始记录', index=False)
            
            if self.episode_rewards:
                df_rewards = pd.DataFrame({
                    'Episode': range(len(self.episode_rewards)),
                    'Reward': self.episode_rewards
                })
                df_rewards.to_excel(writer, sheet_name='训练奖励', index=False)
        
        print(f"\n[PPO] Summary: {self.optimization_count} optimizations, {self.training_steps} training steps")
        print(f"  Green times saved: {output_path}")

    def save_model(self, filepath: str = None):
        """
        保存训练好的模型
        
        Args:
            filepath: 模型保存路径，默认保存到output_dir/ppo_model.pth
        """
        if not TORCH_AVAILABLE or self.policy is None:
            print("[PPO] No model to save")
            return
        
        if filepath is None:
            if self.output_dir:
                filepath = os.path.join(self.output_dir, 'ppo_model.pth')
            else:
                filepath = 'ppo_model.pth'
        
        # 保存模型和相关信息
        checkpoint = {
            'policy_state_dict': self.policy.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'state_dim': self.state_dim,
            'action_dim': self.action_dim,
            'training_steps': self.training_steps,
            'dim': self.dim,
            'intersections': dict(self.intersections),
        }
        
        torch.save(checkpoint, filepath)
        print(f"[PPO] Model saved to: {filepath}")
        print(f"  Training steps: {self.training_steps}")
    
    def load_model(self, filepath: str):
        """
        加载预训练模型
        
        Args:
            filepath: 模型文件路径
            
        Returns:
            bool: 是否加载成功
        """
        if not TORCH_AVAILABLE:
            print("[PPO] PyTorch not available")
            return False
        
        if not os.path.exists(filepath):
            print(f"[PPO] Model file not found: {filepath}")
            return False
        
        try:
            checkpoint = torch.load(filepath, map_location=self.device)
            
            # 验证维度匹配
            if checkpoint['state_dim'] != self.state_dim or checkpoint['action_dim'] != self.action_dim:
                print(f"[PPO] Dimension mismatch: model({checkpoint['state_dim']}, {checkpoint['action_dim']}) vs current({self.state_dim}, {self.action_dim})")
                return False
            
            # 加载网络权重
            self.policy.load_state_dict(checkpoint['policy_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            
            # 加载训练状态
            self.training_steps = checkpoint.get('training_steps', 0)
            
            print(f"[PPO] Model loaded from: {filepath}")
            print(f"  Training steps: {self.training_steps}")
            return True
            
        except Exception as e:
            print(f"[PPO] Failed to load model: {e}")
            return False
    
    def set_inference_mode(self, inference_only: bool = True):
        """
        设置推理模式（不进行在线学习）
        
        Args:
            inference_only: True表示只推理不学习
        """
        self.inference_only = inference_only
        if inference_only:
            print("[PPO] Inference mode enabled (no training)")
        else:
            print("[PPO] Training mode enabled")
