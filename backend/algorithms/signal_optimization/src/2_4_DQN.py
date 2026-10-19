"""
DQN 信号优化算法（Deep Q-Network）

文件编号: 2_4 (sig=4)
配置编码: 1_4_{flow}_X 表示使用 DQN 算法

实现：
- DQN (Deep Q-Network) 用于信号配时优化
- 状态：各相位的排队长度、车辆数
- 动作：离散化的绿灯时间调整 (-5, 0, +5 秒)
- 奖励：负的总延误

支持 GPU 加速（自动检测 CUDA）
"""
import os
import random
import numpy as np
import pandas as pd
import traci
import sumolib
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
from typing import Dict, List, Tuple, Optional


def get_device():
    """自动检测并返回最佳设备"""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class DQN(nn.Module):
    """Deep Q-Network 神经网络"""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
        super(DQN, self).__init__()
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, action_dim)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.fc3(x)


class ReplayBuffer:
    """经验回放缓冲区"""
    
    def __init__(self, capacity: int = 50000):
        self.buffer = deque(maxlen=capacity)
    
    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))
    
    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (np.array(states), np.array(actions), np.array(rewards),
                np.array(next_states), np.array(dones))
    
    def __len__(self):
        return len(self.buffer)


class RLOptimizer:
    """RL信号优化器（DQN实现，支持GPU加速）"""
    
    SATURATION_FLOW_PER_LANE = 1800
    MIN_GREEN = 15
    MAX_GREEN = 60
    SAMPLE_INTERVAL = 10
    MAX_SAMPLES = 30
    
    # DQN 超参数（优化版 - 更稳定的学习）
    GAMMA = 0.95              # 降低折扣因子，更关注短期奖励
    EPSILON_START = 0.3       # 降低初始探索率，利用先验知识
    EPSILON_END = 0.05
    EPSILON_DECAY = 0.995     # 更慢的衰减，保持探索
    LEARNING_RATE = 5e-5      # 进一步降低学习率，更稳定
    BATCH_SIZE = 128          # 增大batch size，减少方差
    TARGET_UPDATE = 50        # 更慢的目标网络更新，提高稳定性
    REPLAY_BUFFER_SIZE = 50000  # 增大经验池
    MIN_REPLAY_SIZE = 256     # 开始训练前的最小经验数（必须大于BATCH_SIZE）
    # 简化动作空间：保守调整
    ACTION_ADJUSTMENTS = [-3, -1, 0, 1, 3]  # 更小的调整幅度，避免剧烈变化
    
    def __init__(self, net_file: str, config_dir: str = None):
        self.net_file = net_file
        self.config_dir = config_dir
        self.net = None
        self.device = get_device()
        self.use_gpu = (self.device.type == "cuda")
        self.optimization_interval = 300
        self.lb = None
        self.ub = None
        self.dim = 0
        self.intersections = {}
        self.edge_phase = {}
        self.saturation_flow = {}
        self.current_timing = None
        self.enabled = False
        self.initialized = False
        self.green_time_records = []
        self.output_dir = None
        self.queue_history = {}
        self.flow_history = {}
        self.snapshot_queue = {}
        self.snapshot_flow = {}
        self.last_sample_time = 0
        self.policy_net = None
        self.target_net = None
        self.optimizer = None
        self.replay_buffer = ReplayBuffer()
        self.epsilon = self.EPSILON_START
        self.state_dim = 0
        self.action_dim = 0
        self.optimization_count = 0
        self.training_steps = 0
        self.episode_rewards = []
        self.last_state = None
        self.last_action = None
        self.last_timing = None
        self.last_reward = 0.0
        self.last_loss = None

    def auto_initialize(self, data_dir: str = None):
        """自动初始化"""
        print("[RL-DQN] Initializing...")
        print(f"  Device: {self.device} {'(GPU accelerated)' if self.use_gpu else '(CPU)'}")
        if data_dir:
            xml_file = os.path.join(data_dir, 'signal_config.xml')
            if os.path.exists(xml_file):
                self._load_from_xml_file(xml_file)
                self._init_dqn()
                self.initialized = True
                return
        self._extract_from_network()
        self._init_dqn()
        self.initialized = True

    def _init_dqn(self):
        """初始化DQN网络"""
        # 状态：每个相位的排队和车辆数
        self.state_dim = self.dim * 2
        # 动作：每个相位5种调整幅度，简化为选择调整方向
        # 使用分层动作：先选择交叉口，再选择调整幅度
        self.num_intersections = len(self.intersections)
        self.action_dim = self.num_intersections * len(self.ACTION_ADJUSTMENTS)
        
        self.policy_net = DQN(self.state_dim, self.action_dim, hidden_dim=256).to(self.device)
        self.target_net = DQN(self.state_dim, self.action_dim, hidden_dim=256).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=self.LEARNING_RATE)
        # 初始配时将在 record_initial_green_times() 中从SUMO读取
        self.current_timing = np.ones(self.dim) * 30
        print(f"  DQN initialized: state_dim={self.state_dim}, action_dim={self.action_dim}")
        print(f"  Action space: {self.num_intersections} intersections × {len(self.ACTION_ADJUSTMENTS)} adjustments")
        print(f"  Network parameters: {sum(p.numel() for p in self.policy_net.parameters())}")

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
                for phase_elem in tl_elem.findall('phase'):
                    phase_idx = int(phase_elem.get('index', '0'))
                    min_green = max(self.MIN_GREEN, int(phase_elem.get('min_green', '15')))
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
                'cycle': 90, 'begin': var_index, 'end': var_index + num_phases - 1,
                'incoming_edges': incoming_edges
            }
            for i in range(num_phases):
                lb_list.append(self.MIN_GREEN)
                ub_list.append(self.MAX_GREEN)
            var_index += num_phases
        self.lb = np.array(lb_list, dtype=np.float64)
        self.ub = np.array(ub_list, dtype=np.float64)
        self.dim = len(self.lb)
        print(f"  Extracted: {self.dim} variables")

    def collect_traffic_data(self, current_time: float):
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
        self.snapshot_queue = {eid: np.mean(q) for eid, q in self.queue_history.items() if q}
        self.snapshot_flow = {eid: np.mean(f) for eid, f in self.flow_history.items() if f}

    def clear_history(self):
        self.queue_history = {}
        self.flow_history = {}

    def get_state(self) -> np.ndarray:
        state = []
        for tl_id, info in self.intersections.items():
            incoming_edges = info.get('incoming_edges', [])
            num_phases = info['end'] - info['begin'] + 1
            for p in range(num_phases):
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                if edge_id:
                    queue = self.snapshot_queue.get(edge_id, 0)
                    veh = self.snapshot_flow.get(edge_id, 0)
                else:
                    queue, veh = 0, 0
                state.append(queue / 50.0)
                state.append(veh / 30.0)
        return np.array(state, dtype=np.float32)

    def select_action(self, state: np.ndarray) -> int:
        if random.random() < self.epsilon:
            return random.randrange(self.action_dim)
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)
            return q_values.argmax().item()

    def decode_action(self, action: int) -> Tuple[int, int]:
        """
        解码动作为交叉口索引和调整幅度
        
        Returns:
            (intersection_idx, adjustment_value)
        """
        num_adj = len(self.ACTION_ADJUSTMENTS)
        intersection_idx = action // num_adj
        adjustment_idx = action % num_adj
        adjustment = self.ACTION_ADJUSTMENTS[adjustment_idx]
        return intersection_idx, adjustment

    def apply_adjustment(self, intersection_idx: int, adjustment: int) -> np.ndarray:
        """
        应用调整到指定交叉口的所有相位
        
        策略：根据排队情况智能分配调整
        - 排队多的相位增加绿灯
        - 排队少的相位减少绿灯
        """
        new_timing = self.current_timing.copy()
        
        # 获取交叉口信息
        tl_ids = list(self.intersections.keys())
        if intersection_idx >= len(tl_ids):
            return new_timing
        
        tl_id = tl_ids[intersection_idx]
        info = self.intersections[tl_id]
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
        
        total_queue = sum(queues) + 0.1  # 避免除零
        
        # 根据排队比例分配调整
        for p in range(num_phases):
            # 排队多的相位获得更多正调整
            weight = queues[p] / total_queue
            phase_adj = adjustment * (weight * 2)  # 权重放大
            new_timing[begin + p] = np.clip(
                new_timing[begin + p] + phase_adj,
                self.lb[begin + p],
                self.ub[begin + p]
            )
        
        # 周期约束
        greens = new_timing[begin:end+1]
        total = sum(greens)
        if total > 0 and abs(total - cycle) > 0.1:
            scale = cycle / total
            for i in range(num_phases):
                new_timing[begin + i] = np.clip(
                    greens[i] * scale,
                    self.MIN_GREEN,
                    self.MAX_GREEN
                )
        
        return new_timing

    def compute_reward(self) -> float:
        """
        计算奖励（优化版 - 更密集的奖励信号）
        
        奖励 = -总延误 + 吞吐量奖励 - 配时变化惩罚 + 改善奖励
        """
        total_delay = 0.0
        total_throughput = 0.0
        total_queue = 0.0
        
        for tl_id, info in self.intersections.items():
            incoming_edges = info.get('incoming_edges', [])
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            
            for i, edge_id in enumerate(incoming_edges):
                if edge_id:
                    queue = self.snapshot_queue.get(edge_id, 0)
                    veh = self.snapshot_flow.get(edge_id, 0)
                    
                    # 获取绿灯时间
                    green = self.current_timing[begin + i] if begin + i < len(self.current_timing) else 30
                    green_ratio = green / cycle
                    
                    # 延误估计：排队 / 绿信比
                    if green_ratio > 0:
                        delay = queue / green_ratio
                    else:
                        delay = queue * 10
                    
                    total_delay += delay
                    total_throughput += veh
                    total_queue += queue
        
        # 配时变化惩罚（鼓励稳定，但不要太强）
        timing_change_penalty = 0.0
        if self.last_timing is not None:
            timing_change_penalty = np.sum(np.abs(self.current_timing - self.last_timing)) * 0.005
        
        # 排队改善奖励（与上一步比较）
        improvement_bonus = 0.0
        if hasattr(self, 'last_total_queue'):
            if total_queue < self.last_total_queue:
                improvement_bonus = (self.last_total_queue - total_queue) * 0.1
        self.last_total_queue = total_queue
        
        # 综合奖励：更平衡的权重
        reward = -total_delay / 100.0 + total_throughput / 200.0 - timing_change_penalty + improvement_bonus
        
        # 奖励裁剪，避免极端值
        reward = np.clip(reward, -10, 10)
        
        return reward

    def train_step(self):
        if len(self.replay_buffer) < self.MIN_REPLAY_SIZE:
            return
        states, actions, rewards, next_states, dones = self.replay_buffer.sample(self.BATCH_SIZE)
        states = torch.FloatTensor(states).to(self.device)
        actions = torch.LongTensor(actions).to(self.device)
        rewards = torch.FloatTensor(rewards).to(self.device)
        next_states = torch.FloatTensor(next_states).to(self.device)
        dones = torch.FloatTensor(dones).to(self.device)
        current_q = self.policy_net(states).gather(1, actions.unsqueeze(1))
        with torch.no_grad():
            # Double DQN: 用policy网络选动作，用target网络评估
            next_actions = self.policy_net(next_states).argmax(1)
            next_q = self.target_net(next_states).gather(1, next_actions.unsqueeze(1)).squeeze()
            target_q = rewards + self.GAMMA * next_q * (1 - dones)
        loss = nn.SmoothL1Loss()(current_q.squeeze(), target_q)  # Huber loss更稳定
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)  # 梯度裁剪
        self.optimizer.step()
        self.training_steps += 1
        self.last_loss = loss.item()
        if self.training_steps % self.TARGET_UPDATE == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
        return loss.item()

    def optimize(self) -> np.ndarray:
        if self.dim == 0 or self.policy_net is None:
            return None
        
        state = self.get_state()
        action = self.select_action(state)
        
        # 解码动作
        intersection_idx, adjustment = self.decode_action(action)
        
        # 应用调整
        new_timing = self.apply_adjustment(intersection_idx, adjustment)
        
        # 计算奖励并存储经验（推理模式下跳过训练）
        reward = self.compute_reward()
        inference_only = getattr(self, 'inference_only', False)
        if self.last_state is not None and not inference_only:
            self.replay_buffer.push(self.last_state, self.last_action, reward, state, False)
            self.episode_rewards.append(reward)
            # 在线训练：每次决策后立即训练
            self.train_step()
        
        self.last_state = state
        self.last_action = action
        self.last_reward = reward
        self.last_timing = self.current_timing.copy()
        self.current_timing = new_timing
        
        # 推理模式下不衰减探索率
        if not inference_only:
            self.epsilon = max(self.EPSILON_END, self.epsilon * self.EPSILON_DECAY)
        return new_timing

    def apply_timing(self, u: np.ndarray, current_time: float = 0):
        self.current_timing = u.copy()
        for tl_id, info in self.intersections.items():
            try:
                programs = traci.trafficlight.getAllProgramLogics(tl_id)
                if not programs:
                    continue
                program = programs[0]
                begin, end = info['begin'], info['end']
                green_times = list(map(float, u[begin:end+1]))
                cycle = info['cycle']
                total_green = sum(green_times)
                if total_green > 0 and abs(total_green - cycle) > 0.1:
                    scale = cycle / total_green
                    green_times = [g * scale for g in green_times]
                green_times = [max(int(self.MIN_GREEN), min(int(self.MAX_GREEN), int(round(g)))) for g in green_times]
                for idx, gt in enumerate(green_times):
                    self.green_time_records.append({'time': current_time, 'tl_id': tl_id, 'phase_idx': idx * 2, 'green_time': gt})
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
                print(f"Warning: {tl_id}: {e}")

    def step(self, current_time: float):
        """
        RL在线学习步进
        
        与TuRBO不同，RL采用在线学习：
        - 预热时间600秒（与其他算法一致）
        - 决策间隔60秒（比TuRBO的300秒更频繁）
        - 每次动作后立即收集奖励并训练
        - 探索率逐渐衰减
        """
        if not self.enabled:
            return
        
        WARMUP_TIME = 600  # 预热时间600秒（与其他算法一致）
        DECISION_INTERVAL = 60  # 决策间隔60秒（比TuRBO更频繁）
        LOG_INTERVAL = 300  # 详细日志输出间隔300秒
        
        # 持续采集数据
        self.collect_traffic_data(current_time)
        
        # 预热期不优化
        if current_time < WARMUP_TIME:
            return
        
        # 第一次决策（详细输出）
        if current_time == WARMUP_TIME:
            self.optimization_count = 1
            self._run_optimization(current_time, is_first=True, verbose=True)
            return
        
        # 常规决策间隔（60秒）
        time_since_warmup = current_time - WARMUP_TIME
        if time_since_warmup > 0 and time_since_warmup % DECISION_INTERVAL == 0:
            self.optimization_count += 1
            
            # 每300秒输出详细日志，其他时间简洁输出
            verbose = (time_since_warmup % LOG_INTERVAL == 0)
            self._run_optimization(current_time, is_first=False, verbose=verbose)

    def _run_optimization(self, current_time: float, is_first: bool = False, verbose: bool = True):
        """执行一次RL决策"""
        self.create_snapshot()
        optimal = self.optimize()
        
        if optimal is None:
            return
        
        self.apply_timing(optimal, current_time)
        
        # 详细输出（首次或每300秒）
        if verbose:
            print(f"\n{'='*60}")
            print(f"[RL-DQN] Decision #{self.optimization_count} at t={current_time}s")
            print(f"{'='*60}")
            
            if is_first:
                print(f"  Algorithm: DQN (Deep Q-Network) - Online Learning")
                print(f"  Device: {self.device} {'(GPU accelerated)' if self.use_gpu else '(CPU)'}")
                print(f"  State dim: {self.state_dim}, Action dim: {self.action_dim}")
                print(f"  Decision interval: 60s (vs TuRBO 300s)")
                print(f"  Learning: Online (train after each decision)")
                print(f"{'='*60}")
            
            self._print_intersection_status(['10', '16'])
            self._print_optimized_timing(['10', '16'], optimal)
            
            # RL特有的训练统计
            print(f"\n  [RL Training Status]")
            print(f"    Decisions: {self.optimization_count}")
            print(f"    Training steps: {self.training_steps}")
            buf_size = len(self.replay_buffer)
            buf_max = self.replay_buffer.buffer.maxlen
            if buf_size == 0:
                print(f"    Replay buffer: {buf_size}/{buf_max} (exploration phase, no training yet)")
            elif buf_size < self.BATCH_SIZE:
                print(f"    Replay buffer: {buf_size}/{buf_max} (collecting experiences, need {self.BATCH_SIZE} to start training)")
            else:
                print(f"    Replay buffer: {buf_size}/{buf_max}")
            print(f"    Epsilon (exploration): {self.epsilon:.3f} ({'exploring' if self.epsilon > 0.5 else 'exploiting'})")
            print(f"    Last reward: {self.last_reward:.2f}")
            if self.last_loss is not None:
                print(f"    Last loss: {self.last_loss:.4f}")
            if len(self.episode_rewards) >= 10:
                recent_rewards = self.episode_rewards[-10:]
                print(f"    Avg reward (last 10): {np.mean(recent_rewards):.2f}")
        else:
            # 简洁输出（每60秒）
            buf_info = f"buf={len(self.replay_buffer)}"
            if self.training_steps > 0:
                buf_info += f", train={self.training_steps}"
            print(f"  [RL] t={current_time}s: #{self.optimization_count}, ε={self.epsilon:.2f}, {buf_info}, r={self.last_reward:.1f}")
        
        self.clear_history()

    def _print_intersection_status(self, tl_ids: List[str]):
        print(f"\n  [Intersection Status]")
        for tl_id in tl_ids:
            if tl_id not in self.intersections:
                continue
            info = self.intersections[tl_id]
            incoming_edges = info.get('incoming_edges', [])
            num_phases = info['end'] - info['begin'] + 1
            queues, vehicles = [], []
            for p in range(num_phases):
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                q, v = 0, 0
                if edge_id:
                    try:
                        q = traci.edge.getLastStepHaltingNumber(edge_id)
                        v = traci.edge.getLastStepVehicleNumber(edge_id)
                    except:
                        q = int(self.snapshot_queue.get(edge_id, 0))
                queues.append(int(q))
                vehicles.append(int(v))
            print(f"  Intersection {tl_id}: queue={queues}, vehicles={vehicles}")

    def _print_optimized_timing(self, tl_ids: List[str], optimal: np.ndarray):
        print(f"\n  [Applied Timing]")
        for tl_id in tl_ids:
            if tl_id not in self.intersections:
                continue
            info = self.intersections[tl_id]
            begin, end = info['begin'], info['end']
            greens = [int(optimal[begin + p]) for p in range(end - begin + 1)]
            print(f"  Intersection {tl_id}: greens={greens}")

    def set_output_dir(self, output_dir: str):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def record_initial_green_times(self):
        """从SUMO读取初始绿灯时长并初始化current_timing"""
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
                            'time': 0, 'tl_id': tl_id, 
                            'phase_idx': green_idx * 2, 
                            'green_time': green_time
                        })
                        # 更新current_timing
                        if self.current_timing is not None and begin + green_idx < len(self.current_timing):
                            self.current_timing[begin + green_idx] = green_time
                        green_idx += 1
            except Exception as e:
                print(f"    Warning: {tl_id}: {e}")
        
        # 输出初始配时
        if self.current_timing is not None:
            print(f"  Initial timing loaded: {len(self.green_time_records)} phases")
            print(f"  Sample greens (first 8): {[int(g) for g in self.current_timing[:8]]}")

    def save_green_times_to_excel(self, filename: str = None):
        if not self.green_time_records:
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
                df_rewards = pd.DataFrame({'Episode': range(len(self.episode_rewards)), 'Reward': self.episode_rewards})
                df_rewards.to_excel(writer, sheet_name='训练奖励', index=False)
        print(f"\n[RL-DQN] Summary: {self.optimization_count} optimizations, {self.training_steps} training steps")
        print(f"  Green times saved: {output_path}")

    def save_model(self, filepath: str = None):
        """
        保存训练好的模型
        
        Args:
            filepath: 模型保存路径，默认保存到output_dir/dqn_model.pth
        """
        if self.policy_net is None:
            print("[RL-DQN] No model to save")
            return
        
        if filepath is None:
            if self.output_dir:
                filepath = os.path.join(self.output_dir, 'dqn_model.pth')
            else:
                filepath = 'dqn_model.pth'
        
        # 保存模型和相关信息
        checkpoint = {
            'policy_net_state_dict': self.policy_net.state_dict(),
            'target_net_state_dict': self.target_net.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'state_dim': self.state_dim,
            'action_dim': self.action_dim,
            'epsilon': self.epsilon,
            'training_steps': self.training_steps,
            'dim': self.dim,
            'intersections': dict(self.intersections),
        }
        
        torch.save(checkpoint, filepath)
        print(f"[RL-DQN] Model saved to: {filepath}")
        print(f"  Training steps: {self.training_steps}, Epsilon: {self.epsilon:.3f}")
    
    def load_model(self, filepath: str):
        """
        加载预训练模型
        
        Args:
            filepath: 模型文件路径
            
        Returns:
            bool: 是否加载成功
        """
        if not os.path.exists(filepath):
            print(f"[RL-DQN] Model file not found: {filepath}")
            return False
        
        try:
            checkpoint = torch.load(filepath, map_location=self.device)
            
            # 验证维度匹配
            if checkpoint['state_dim'] != self.state_dim or checkpoint['action_dim'] != self.action_dim:
                print(f"[RL-DQN] Dimension mismatch: model({checkpoint['state_dim']}, {checkpoint['action_dim']}) vs current({self.state_dim}, {self.action_dim})")
                return False
            
            # 加载网络权重
            self.policy_net.load_state_dict(checkpoint['policy_net_state_dict'])
            self.target_net.load_state_dict(checkpoint['target_net_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            
            # 加载训练状态
            self.epsilon = checkpoint.get('epsilon', self.EPSILON_END)  # 使用较低的探索率
            self.training_steps = checkpoint.get('training_steps', 0)
            
            print(f"[RL-DQN] Model loaded from: {filepath}")
            print(f"  Training steps: {self.training_steps}, Epsilon: {self.epsilon:.3f}")
            return True
            
        except Exception as e:
            print(f"[RL-DQN] Failed to load model: {e}")
            return False
    
    def set_inference_mode(self, inference_only: bool = True):
        """
        设置推理模式（不进行在线学习）
        
        Args:
            inference_only: True表示只推理不学习
        """
        self.inference_only = inference_only
        if inference_only:
            self.epsilon = 0.0  # 不探索，只利用
            print("[RL-DQN] Inference mode enabled (no exploration, no training)")
        else:
            print("[RL-DQN] Training mode enabled")
