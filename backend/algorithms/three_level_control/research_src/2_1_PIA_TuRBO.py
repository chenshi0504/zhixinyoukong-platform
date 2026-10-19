"""
TD-MPC + PIA-TuRBO 信号优化算法

框架升级：从传统 MPC 升级为 TD-MPC (Temporal Difference MPC)

核心创新：
1. 混合世界模型
   - 显式动态模型：状态转移方程（物理先验，始终可用）
   - 学习残差模型：在线学习修正项（数据驱动，逐渐增强）
   - z_{t+1} = f_explicit(z_t, a_t) + confidence × Δ(z_t, a_t)

2. 隐状态表示
   - 状态编码器：将原始观测编码为隐状态
   - 隐状态包含历史信息，决策更连贯

3. 价值函数引导
   - Q 网络提供终端价值估计
   - 加速 TuRBO 规划收敛

4. 物理先验融合（PIA-TuRBO）
   - 物理先验：按需求比例分配绿灯
   - 当前配时：上一轮优化结果
   - 历史最优：历史优化中表现最好的配时
   - 协同先验：基于路径流量的信号-路径协同

5. 在线学习
   - 冷启动：100% 显式模型
   - 过渡期：显式模型 + 小权重残差
   - 成熟期：显式模型 + 自适应残差

6. TuRBO 规划器
   - 在隐空间中搜索最优配时
   - 信任域方法，样本效率高

参考: TD-MPC2 (Hansen et al., 2024)
"""
import os
import numpy as np
import pandas as pd
import traci
import sumolib
import torch
from typing import Dict, List, Tuple, Optional
from turbo import Turbo1

# TD-MPC 组件
try:
    from tdmpc_components import TDMPCAgent, get_device
    TDMPC_AVAILABLE = True
except ImportError:
    TDMPC_AVAILABLE = False
    print("[Warning] TD-MPC components not available, using fallback mode")


class TDMPCSignalOptimizer:
    """
    TD-MPC + PIA-TuRBO 信号优化器
    
    升级自 MPCSignalOptimizer，增加：
    - 隐状态编码
    - 残差动态学习
    - Q 函数价值估计
    - 在线学习能力
    """
    
    SATURATION_FLOW_PER_LANE = 1800  # 饱和流率 (veh/h/lane)
    MAX_SATURATION_DEGREE = 0.95
    SAMPLE_INTERVAL = 10  # 数据采集间隔（秒）
    MAX_SAMPLES = 30      # 最大样本数
    MIN_GREEN_TIME = 15   # 最小绿灯时间（秒）- 行人过街安全
    
    def __init__(self, net_file: str, config_dir: str = None):
        self.net_file = net_file
        self.config_dir = config_dir
        self.net = None
        
        # MPC参数
        self.predict_step = 3  # 多步预测，MPC核心优势
        self.optimization_interval = 300
        
        # 决策变量
        self.lb = None
        self.ub = None
        self.dim = 0
        
        # 交叉口信息
        self.intersections = {}
        
        # 路段信息
        self.internal_edges = []   # 内部路段（上游是信号灯交叉口）
        self.boundary_edges = []   # 边界路段（上游不是信号灯交叉口）
        self.saturation_flow = {}  # 饱和流率 {edge_id: S}
        self.demand_flow = {}      # 需求流量 {edge_id: D}
        self.edge_phase = {}       # 路段对应相位 {edge_id: phase_idx}
        self.edge_upstream = {}    # 上游路段 {edge_id: [(upstream_edge, direction), ...]}
        self.edge_downstream = {}  # 下游路段 {edge_id: downstream_edge}
        self.turn_ratios = {}      # 转向比 {edge_id: [left, straight, right]}
        
        # 状态
        self.queue_internal = None
        self.queue_boundary = None
        self.current_timing = None
        self.max_change = 15  # 放宽搜索范围，从10增加到15
        
        # 控制
        self.enabled = False
        self.initialized = False
        
        # ========== 诊断开关 ==========
        self.enable_prior_diagnostics = True   # 先验诊断日志
        self.enable_cooperative_prior = True   # 协同先验开关
        self.enable_tdmpc = True               # TD-MPC 开关
        self.enable_tdmpc_guidance = True      # TD-MPC 引导开关（残差和Q值引导）
        
        # ========== 消融模式 ==========
        # None = 完整PIA-TuRBO
        # 'physics_only' = 仅物理先验（无扰动、无协同、无历史）
        # 'physics_perturb' = 物理先验 + 扰动采样（无协同、无历史）
        self.ablation_mode = None
        
        # 输出
        self.green_time_records = []
        self.output_dir = None
        
        # ========== 内置数据采集 ==========
        self.queue_history = {}     # 排队历史 {edge_id: [samples]}
        self.flow_history = {}      # 流量历史 {edge_id: [samples]}
        self.snapshot_queue = {}    # 排队快照
        self.snapshot_flow = {}     # 流量快照
        self.last_sample_time = 0   # 上次采样时间
        
        # ========== 路径协同（双向耦合） ==========
        self.path_flow_data = None
        self.path_intersection_matrix = {}
        self.cooperative_prior_data = {}
        self.prior_initialized = False
        
        # ========== 自适应搜索区间 ==========
        self.phase_performance = {}
        self.adaptive_lb = None
        self.adaptive_ub = None
        self.enable_adaptive_bounds = True
        
        # ========== 历史经验学习 ==========
        self.optimization_history = []
        self.max_history_size = 50
        self.history_weight = 0.3
        
        # ========== TD-MPC 组件（新增） ==========
        self.tdmpc_agent = None         # TD-MPC 智能体
        self.obs_dim = 0                # 观测维度（初始化后设置）
        self.last_obs = None            # 上一次观测
        self.last_action = None         # 上一次动作
        self.last_reward = None         # 上一次奖励
        self.tdmpc_update_interval = 5  # 每 5 次优化更新一次网络
        self.optimization_count = 0     # 优化次数计数
    
    # ========== 初始化 ==========
    
    def auto_initialize(self, data_dir: str = None):
        """
        自动初始化
        
        流程：
        1. 如果data_dir下有signal_config.xml，从该文件加载
        2. 否则从路网提取
        3. 初始化 TD-MPC 组件
        """
        print("[TD-MPC + PIA-TuRBO] Initializing...")
        
        if data_dir:
            xml_file = os.path.join(data_dir, 'signal_config.xml')
            if os.path.exists(xml_file):
                self._load_from_xml_file(xml_file)
                self.initialized = True
                # 初始化 TD-MPC 组件
                self._init_tdmpc()
                return
        
        print("  Warning: signal_config.xml not found, extracting from network...")
        self._extract_from_network()
        self.initialized = True
        # 初始化 TD-MPC 组件
        self._init_tdmpc()
    
    def _init_tdmpc(self):
        """初始化 TD-MPC 组件"""
        if not self.enable_tdmpc or not TDMPC_AVAILABLE:
            print("  [TD-MPC] Disabled or not available, using pure MPC mode")
            return
        
        # 计算观测维度：每个交叉口的每个相位有 (queue, flow) 两个特征
        # 加上当前配时
        num_phases = self.dim
        self.obs_dim = num_phases * 2 + num_phases  # queue + flow + current_timing
        
        # 动作维度 = 配时变量数 × 预测步数
        action_dim = self.dim * self.predict_step
        
        # 隐状态维度
        latent_dim = min(64, max(32, self.dim * 2))
        
        try:
            self.tdmpc_agent = TDMPCAgent(
                obs_dim=self.obs_dim,
                action_dim=action_dim,
                latent_dim=latent_dim,
                hidden_dim=128,
                lr=3e-4,
                gamma=0.99
            )
            print(f"  [TD-MPC] Initialized: obs_dim={self.obs_dim}, action_dim={action_dim}, latent_dim={latent_dim}")
            print(f"  [TD-MPC] Device: {self.tdmpc_agent.device}")
        except Exception as e:
            print(f"  [TD-MPC] Init failed: {e}, using pure MPC mode")
            self.tdmpc_agent = None
            self.enable_tdmpc = False
    
    def _get_observation(self) -> np.ndarray:
        """
        构建观测向量
        
        观测包含：
        - 各相位排队长度
        - 各相位流量
        - 当前配时
        """
        obs = []
        
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            
            for p in range(num_phases):
                queue, flow = self._get_phase_data(tl_id, p)
                obs.append(queue / 50.0)  # 归一化
                obs.append(flow / 2000.0)  # 归一化
        
        # 当前配时
        if self.current_timing is not None:
            for g in self.current_timing:
                obs.append(g / 60.0)  # 归一化
        else:
            obs.extend([0.5] * self.dim)
        
        return np.array(obs, dtype=np.float32)
        
        if data_dir:
            # 从 data_dir/signal_config.xml 加载（由main_batch.py从net.xml生成）
            xml_file = os.path.join(data_dir, 'signal_config.xml')
            if os.path.exists(xml_file):
                self._load_from_xml_file(xml_file)
                self.initialized = True
                return
        
        # 回退：从路网提取（不应该走到这里）
        print("  Warning: signal_config.xml not found, extracting from network...")
        self._extract_from_network()
        self.initialized = True
    
    def _load_from_xml_file(self, xml_file: str):
        """从指定的XML文件加载配置"""
        import xml.etree.ElementTree as ET
        
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            lb_list = []
            ub_list = []
            
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
                    # 最小绿灯时间强制为15秒（行人过街安全）
                    min_green = max(self.MIN_GREEN_TIME, int(phase_elem.get('min_green', '15')))
                    max_green = int(phase_elem.get('max_green', '60'))
                    edge_id = phase_elem.get('edge', '')
                    
                    self.intersections[tl_id]['phases'].append(phase_idx)
                    if edge_id:
                        self.intersections[tl_id]['incoming_edges'].append(edge_id)
                        self.edge_phase[edge_id] = phase_idx
                    
                    lb_list.append(min_green)
                    ub_list.append(max_green)
            
            self.lb = np.array(lb_list)
            self.ub = np.array(ub_list)
            self.dim = len(lb_list)
            
            # 加载路网并提取结构
            self.net = sumolib.net.readNet(self.net_file)
            
            # 设置饱和流率
            for edge in self.net.getEdges():
                edge_id = edge.getID()
                if not edge_id.startswith(':'):
                    self.saturation_flow[edge_id] = edge.getLaneNumber() * self.SATURATION_FLOW_PER_LANE
            
            self._init_network_structure()
            
            print(f"  Loaded from: {xml_file}")
            print(f"  {self.dim} vars, {len(self.intersections)} intersections")
            
        except Exception as e:
            print(f"  Warning: XML load failed: {e}")
            self._extract_from_network()
            print(f"  Warning: XML load failed: {e}")
            self._extract_from_network()
    
    def _init_network_structure(self):
        """
        初始化路网结构（参考tianjin的MPC建模）
        
        区分：
        - 内部路段(nb): 上游是信号灯交叉口，流入来自上游路段转向
        - 边界路段(bj): 上游不是信号灯交叉口，流入来自外部需求
        """
        if self.net is None:
            self.net = sumolib.net.readNet(self.net_file)
        
        tl_set = set(self.intersections.keys())
        
        # 分类内部和边界路段
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            if edge_id.startswith(':'):
                continue
            
            from_node = edge.getFromNode().getID()
            to_node = edge.getToNode().getID()
            
            # 只考虑进入信号灯交叉口的路段
            if to_node in tl_set:
                if from_node in tl_set:
                    self.internal_edges.append(edge_id)  # 内部路段
                else:
                    self.boundary_edges.append(edge_id)  # 边界路段
        
        # 获取内部路段的上游路段及转向信息
        for edge_id in self.internal_edges:
            edge = self.net.getEdge(edge_id)
            junction = edge.getFromNode()
            self.edge_upstream[edge_id] = []
            
            for conn in junction.getConnections():
                if conn.getTo().getID() == edge_id:
                    from_edge = conn.getFrom().getID()
                    direction = conn.getDirection()  # 'l'=左转, 's'=直行, 'r'=右转
                    self.edge_upstream[edge_id].append((from_edge, direction))
        
        # 获取下游路段信息
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            if edge_id.startswith(':'):
                continue
            to_node = edge.getToNode()
            for conn in to_node.getConnections():
                if conn.getFrom().getID() == edge_id:
                    self.edge_downstream[edge_id] = conn.getTo().getID()
                    break
        
        # 设置默认转向比（如果没有从配置加载）
        all_edges = self.internal_edges + self.boundary_edges
        for edge_id in all_edges:
            if edge_id not in self.turn_ratios:
                self.turn_ratios[edge_id] = [0.2, 0.6, 0.2]  # 左转20%, 直行60%, 右转20%
        
        # 初始化排队状态
        self.queue_internal = np.zeros(len(self.internal_edges))
        self.queue_boundary = np.zeros(len(self.boundary_edges))
        
        print(f"  Network: {len(self.internal_edges)} internal, {len(self.boundary_edges)} boundary edges")
    
    def _extract_from_network(self):
        """从路网提取配置"""
        self.net = sumolib.net.readNet(self.net_file)
        
        tl_nodes = [n.getID() for n in self.net.getNodes() if n.getType() == 'traffic_light']
        print(f"  Found {len(tl_nodes)} traffic lights")
        
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
            
            for i in range(num_phases):
                lb_list.append(15)
                ub_list.append(60)
                if i < len(incoming_edges):
                    self.edge_phase[incoming_edges[i]] = i * 2
            
            var_index += num_phases
        
        self.lb = np.array(lb_list)
        self.ub = np.array(ub_list)
        self.dim = len(self.lb)
        
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            if not edge_id.startswith(':'):
                self.saturation_flow[edge_id] = edge.getLaneNumber() * self.SATURATION_FLOW_PER_LANE
        
        self._init_network_structure()
        print(f"  Extracted: {self.dim} variables")
    
    # ========== 内置数据采集（原2_2功能） ==========
    
    def collect_traffic_data(self, current_time: float):
        """采集交通数据（每10秒）"""
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
                flow = veh * 3600
                
                if eid not in self.queue_history:
                    self.queue_history[eid] = []
                self.queue_history[eid].append(queue)
                if len(self.queue_history[eid]) > self.MAX_SAMPLES:
                    self.queue_history[eid] = self.queue_history[eid][-self.MAX_SAMPLES:]
                
                if eid not in self.flow_history:
                    self.flow_history[eid] = []
                self.flow_history[eid].append(flow)
                if len(self.flow_history[eid]) > self.MAX_SAMPLES:
                    self.flow_history[eid] = self.flow_history[eid][-self.MAX_SAMPLES:]
            except:
                pass
    
    def create_snapshot(self):
        """创建数据快照"""
        self.snapshot_queue = {eid: np.mean(q) for eid, q in self.queue_history.items() if q}
        self.snapshot_flow = {eid: np.mean(f) for eid, f in self.flow_history.items() if f}
        
        if self.snapshot_queue:
            total = sum(self.snapshot_queue.values())
            print(f"  [DataCollector] Snapshot: total_queue={total:.0f}")
    
    def clear_history(self):
        """清空历史"""
        self.queue_history = {}
        self.flow_history = {}
    
    # ========== 数据获取 ==========
    
    def _get_phase_data(self, tl_id: str, phase_idx: int) -> Tuple[float, float]:
        """
        获取相位的排队和到达流量
        
        方案B：分离计算
        - queue: 当前停车线处的排队车辆数（用于计算初始排队消散时间）
        - arrival_flow: 上游路段流出量（真正的"新到达"，用于Webster延迟）
        
        Returns:
            (queue, arrival_flow_vph)
        """
        info = self.intersections.get(tl_id, {})
        incoming = info.get('incoming_edges', [])
        edge_id = incoming[phase_idx] if phase_idx < len(incoming) else None
        
        if not edge_id:
            return 0, 500
        
        # 1. 获取当前排队（停车线处）
        queue = self.snapshot_queue.get(edge_id, 0)
        if queue == 0:
            try:
                queue = traci.edge.getLastStepHaltingNumber(edge_id)
            except:
                queue = 0
        
        # 2. 计算上游流入量（真正的新到达）
        arrival_flow = self._compute_upstream_arrival_flow(edge_id)
        
        return queue, max(arrival_flow, 100)
    
    def _compute_upstream_arrival_flow(self, edge_id: str) -> float:
        """
        计算路段的上游到达流量（vph）
        
        上游到达 = Σ(上游路段流量 × 转向比)
        
        对于边界路段（无上游信号灯），使用需求流量
        对于内部路段，计算上游路段的流出量
        """
        # 边界路段：使用需求流量
        if edge_id in self.boundary_edges:
            return self.demand_flow.get(edge_id, 500)
        
        # 内部路段：计算上游流入
        upstream_list = self.edge_upstream.get(edge_id, [])
        if not upstream_list:
            # 无上游信息，回退到需求流量
            return self.demand_flow.get(edge_id, 500)
        
        total_arrival = 0.0
        for up_edge, direction in upstream_list:
            # 上游路段的流量
            up_flow = self.snapshot_flow.get(up_edge, 0)
            if up_flow == 0:
                up_flow = self.demand_flow.get(up_edge, 500)
            
            # 转向比
            turn_ratio = self.turn_ratios.get(up_edge, [0.2, 0.6, 0.2])
            if direction == 'l':
                ratio = turn_ratio[0]
            elif direction == 's':
                ratio = turn_ratio[1]
            else:
                ratio = turn_ratio[2]
            
            total_arrival += up_flow * ratio
        
        return total_arrival if total_arrival > 0 else self.demand_flow.get(edge_id, 500)
    
    def _get_saturation_flow(self, tl_id: str, phase_idx: int) -> float:
        """获取饱和流率"""
        info = self.intersections.get(tl_id, {})
        incoming = info.get('incoming_edges', [])
        edge_id = incoming[phase_idx] if phase_idx < len(incoming) else None
        return self.saturation_flow.get(edge_id, 3600) if edge_id else 3600
    
    def _get_edge_flow(self, edge_id: str) -> float:
        """获取路段流量（优先使用快照）"""
        # 优先从快照获取
        flow = self.snapshot_flow.get(edge_id, 0)
        if flow > 0:
            return flow
        # 回退：从demand_flow获取
        return self.demand_flow.get(edge_id, 500)
    
    def _get_edge_queue(self, edge_id: str) -> float:
        """获取路段排队（优先使用快照）"""
        return self.snapshot_queue.get(edge_id, 0)

    def _simple_objective(self, u: np.ndarray) -> float:
        """
        简单目标函数：与 TuRBO 相同的 Webster 延误模型
        
        用于公平对比，确保 PIA-TuRBO 的优势来自先验而非目标函数差异
        """
        total_delay = 0.0
        
        for tl_id, info in self.intersections.items():
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            incoming_edges = info.get('incoming_edges', [])
            
            for p in range(num_phases):
                g = u[begin + p] if begin + p < len(u) else 30
                g = max(g, self.MIN_GREEN_TIME)
                lambda_i = g / cycle
                
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                queue = self.snapshot_queue.get(edge_id, 0) if edge_id else 0
                flow = self.snapshot_flow.get(edge_id, 500) if edge_id else 500
                S = self.saturation_flow.get(edge_id, 3600) if edge_id else 3600
                
                capacity = S * lambda_i
                x = flow / capacity if capacity > 0 else 0.5
                x = min(x, 0.95)
                
                # Webster延误
                denom = 1 - lambda_i * x
                if denom > 0.01:
                    d_uniform = cycle * (1 - lambda_i)**2 / (2 * denom)
                else:
                    d_uniform = cycle * (1 - lambda_i) / 2
                
                if flow > 0 and x < 1:
                    q_per_sec = flow / 3600
                    d_random = x**2 / (2 * q_per_sec * max(1 - x, 0.01))
                    d_random = min(d_random, cycle * 0.5)
                else:
                    d_random = 0
                
                service_rate = (S / 3600) * lambda_i
                if service_rate > 0 and queue > 0:
                    queue_delay = queue * queue / (2 * service_rate)
                    queue_delay = min(queue_delay, queue * cycle)
                else:
                    queue_delay = 0
                
                arrivals = (flow / 3600) * 90
                arrivals = max(arrivals, 0.1)
                
                phase_delay = (d_uniform + d_random) * arrivals + queue_delay
                total_delay += phase_delay
        
        return total_delay
    
    # ========== 目标函数：MPC状态转移 + Webster延误 ==========
    
    def _get_green_and_cycle(self, edge_id: str, u: np.ndarray) -> Tuple[float, float]:
        """
        获取路段对应的绿灯时间和周期（参考tianjin的green_c方法）
        
        Args:
            edge_id: 路段ID
            u: 当前步的决策变量
        Returns:
            (green_time, cycle_time)
        """
        # 获取下游路段（用于确定相位）
        downstream = self.edge_downstream.get(edge_id, edge_id)
        
        # 获取相位索引
        phase = self.edge_phase.get(downstream, 0)
        
        # 找到对应的交叉口
        for tl_id, info in self.intersections.items():
            incoming = info.get('incoming_edges', [])
            if downstream in incoming or edge_id in incoming:
                begin = info['begin']
                var_idx = begin + int(phase / 2)
                if var_idx < len(u):
                    return u[var_idx], info['cycle']
                return 30, info['cycle']
        
        return 30, 90  # 默认值
    
    def _compute_upstream_inflow(self, edge_id: str, u: np.ndarray, T: float) -> float:
        """
        计算内部路段的上游流入量（参考tianjin的get_x_next方法）
        
        上游流入 = Σ(上游路段饱和流率 × 转向比 × 绿信比 × T)
        
        Args:
            edge_id: 内部路段ID
            u: 当前步的决策变量
            T: 控制周期（秒）
        Returns:
            上游流入车辆数
        """
        upstream_list = self.edge_upstream.get(edge_id, [])
        x_up = 0.0
        
        for up_edge, direction in upstream_list:
            green_up, cycle_up = self._get_green_and_cycle(up_edge, u)
            S_up = self.saturation_flow.get(up_edge, self.SATURATION_FLOW_PER_LANE * 2)
            turn_ratio = self.turn_ratios.get(up_edge, [0.2, 0.6, 0.2])
            
            # 根据转向方向选择转向比
            if direction == 'l':
                ratio = turn_ratio[0]  # 左转
            elif direction == 's':
                ratio = turn_ratio[1]  # 直行
            else:
                ratio = turn_ratio[2]  # 右转
            
            # 上游流出 = 饱和流率 × 转向比 × 绿信比 × T
            x_up += (S_up / 3600) * ratio * (green_up / cycle_up) * T
        
        return x_up
    
    def predict_travel_time(self, u: np.ndarray) -> float:
        """
        MPC目标函数：最小化总行程时间，公平性为软约束
        
        行程时间 = 排队消散时间 + 信号延迟（自由流时间为常数，优化时忽略）
        
        延迟计算模型：
        - 排队消散时间：queue² / (2 × service_rate)
        - 均匀延迟 d_uniform = C(1-λ)² / [2(1-λx)]
        - 随机延迟 d_random = x² / [2q(1-x)]
        - 溢出延迟 d_overflow = α·max(0, x-0.95)^β
        
        公平性软约束（基于平均延误，与流量大小无关）：
        - 单相位平均延误不能超过阈值
        - 交叉口内相位间平均延误差异不能过大
        - 交叉口间平均延误差异不能过大
        
        Args:
            u: 决策变量（绿灯时间，包含predict_step步）
        Returns:
            目标函数值（总行程时间 + 公平性惩罚）
        """
        step_dim = self.dim
        T = 90  # 控制周期（秒）
        INFEASIBLE_PENALTY = 1e10  # 不可行解的惩罚值
        
        # ========== 公平性约束参数 ==========
        MAX_PHASE_AVG_DELAY = 90.0      # 单相位平均延误上限（秒/车）
        MAX_PHASE_DELAY_DIFF = 45.0     # 交叉口内相位平均延误差异上限（秒）
        MAX_INTERSECTION_DELAY_RATIO = 3.0  # 交叉口间平均延误比值上限
        
        # 溢出延迟参数
        OVERFLOW_ALPHA = 0.5
        OVERFLOW_BETA = 2.0
        
        # 初始化排队状态
        X_bj = np.array([self._get_edge_queue(e) for e in self.boundary_edges]) if self.boundary_edges else np.zeros(0)
        X_nb = np.array([self._get_edge_queue(e) for e in self.internal_edges]) if self.internal_edges else np.zeros(0)
        
        # 记录每个交叉口的行程时间分量
        intersection_data = {}  # {tl_id: {'queue_time': x, 'signal_delay': x, 'flow': x, 'phase_avg_delays': []}}
        
        # 多步预测
        for step in range(self.predict_step):
            start_idx = step * step_dim
            end_idx = start_idx + step_dim
            u_step = u[start_idx:end_idx] if end_idx <= len(u) else u[:step_dim]
            
            # ========== 边界路段状态转移（计算排队时间） ==========
            for i, edge_bj in enumerate(self.boundary_edges):
                green_bj, cycle_bj = self._get_green_and_cycle(edge_bj, u_step)
                S_bj = self.saturation_flow.get(edge_bj, self.SATURATION_FLOW_PER_LANE * 2)
                D_bj = self._get_edge_flow(edge_bj)
                
                arrival = (D_bj / 3600) * T
                capacity = (S_bj / 3600) * (green_bj / cycle_bj) * T
                departure = min(capacity, X_bj[i] + arrival)
                X_bj[i] = max(0, X_bj[i] + arrival - departure)
            
            # ========== 内部路段状态转移 ==========
            for i, edge_nb in enumerate(self.internal_edges):
                green_nb, cycle_nb = self._get_green_and_cycle(edge_nb, u_step)
                S_nb = self.saturation_flow.get(edge_nb, self.SATURATION_FLOW_PER_LANE * 2)
                D_nb = self._get_edge_flow(edge_nb)
                
                arrival = (D_nb / 3600) * T
                x_up = self._compute_upstream_inflow(edge_nb, u_step, T)
                total_arrival = arrival + x_up
                
                capacity = (S_nb / 3600) * (green_nb / cycle_nb) * T
                departure = min(capacity, X_nb[i] + total_arrival)
                X_nb[i] = max(0, X_nb[i] + total_arrival - departure)
            
            # ========== 交叉口级别：计算行程时间分量 ==========
            for tl_id, info in self.intersections.items():
                cycle = info['cycle']
                begin, end = info['begin'], info['end']
                num_phases = end - begin + 1
                
                if tl_id not in intersection_data:
                    intersection_data[tl_id] = {
                        'queue_time': 0, 'signal_delay': 0, 'flow': 0,
                        'phase_avg_delays': [[] for _ in range(num_phases)]
                    }
                
                for p in range(num_phases):
                    g = u_step[begin + p] if begin + p < len(u_step) else 30
                    g = max(g, 1)
                    lambda_i = g / cycle  # 绿信比
                    
                    queue, arrival_flow = self._get_phase_data(tl_id, p)
                    S = self._get_saturation_flow(tl_id, p)
                    
                    # 到达车辆数（本周期，来自上游流入）
                    arrivals = (arrival_flow / 3600) * T
                    if arrivals < 0.1:
                        arrivals = 0.1  # 避免除零
                    
                    # ========== 1. 初始排队消散时间（车·秒） ==========
                    # 方案B：只计算初始排队的消散延迟，不与Webster重叠
                    # 
                    # 初始排队消散时间 = queue² / (2 × service_rate)
                    # 这是排队论中的平均等待时间公式
                    # 
                    # 单位分析：
                    #   queue: veh
                    #   service_rate: veh/s
                    #   queue_time: veh² / (veh/s) = veh·s（车·秒）
                    service_rate = (S / 3600) * lambda_i  # 服务率(veh/s)
                    if service_rate > 0 and queue > 0:
                        # 初始排队的总消散延迟（车·秒）
                        # 每辆排队车的平均等待 ≈ queue / (2 × service_rate)
                        queue_time = queue * queue / (2 * service_rate)
                        # 限制最大值，避免极端情况
                        queue_time = min(queue_time, queue * cycle)
                    else:
                        queue_time = 0
                    
                    # ========== 2. 新到达车辆的信号延迟（Webster模型，车·秒） ==========
                    # 方案B：只对新到达车辆（arrivals）计算Webster延迟
                    # 
                    # 单位分析：
                    #   d_uniform, d_random, d_overflow: 秒/车（单车平均延迟）
                    #   phase_signal_delay: 秒/车 × veh = 车·秒
                    
                    # 饱和度 x = 到达流率 / 通行能力
                    capacity_vph = S * lambda_i  # 通行能力(veh/h)
                    x = arrival_flow / capacity_vph if capacity_vph > 0 else 0.5
                    x = min(x, self.MAX_SATURATION_DEGREE)
                    
                    # 2.1 均匀延迟 d_uniform（秒/车）
                    denom = 1 - lambda_i * x
                    if denom > 0.01:
                        d_uniform = cycle * (1 - lambda_i)**2 / (2 * denom)
                    else:
                        d_uniform = cycle * (1 - lambda_i) / 2
                    
                    # 2.2 随机延迟 d_random（秒/车）
                    if arrival_flow > 0 and x < 1:
                        q_per_sec = arrival_flow / 3600
                        d_random = x**2 / (2 * q_per_sec * max(1 - x, 0.01))
                        d_random = min(d_random, cycle * 0.5)  # 限制最大值
                    else:
                        d_random = 0
                    
                    # 2.3 溢出延迟 d_overflow（秒/车）
                    if x > self.MAX_SATURATION_DEGREE:
                        d_overflow = OVERFLOW_ALPHA * (x - self.MAX_SATURATION_DEGREE)**OVERFLOW_BETA * 100
                    else:
                        d_overflow = 0
                    
                    # 单车平均信号延迟（秒/车）
                    avg_signal_delay = d_uniform + d_random + d_overflow
                    
                    # 该相位总信号延迟（车·秒）= 单车延迟 × 到达车辆数
                    phase_signal_delay = avg_signal_delay * arrivals
                    
                    # ========== 记录数据 ==========
                    intersection_data[tl_id]['queue_time'] += queue_time
                    intersection_data[tl_id]['signal_delay'] += phase_signal_delay
                    intersection_data[tl_id]['flow'] += arrivals
                    
                    # 记录该相位的平均延误（排队时间+信号延迟）/到达车辆
                    phase_total_delay = queue_time + phase_signal_delay
                    phase_avg_delay = phase_total_delay / arrivals if arrivals > 0 else 0
                    intersection_data[tl_id]['phase_avg_delays'][p].append(phase_avg_delay)
        
        # ========== 硬约束检查 ==========
        intersection_avg_delays = {}  # 各交叉口平均延误
        
        for tl_id, data in intersection_data.items():
            # 计算各相位的平均延误（多步预测的平均）
            phase_avg_delays = []
            for p_delays in data['phase_avg_delays']:
                if p_delays:
                    phase_avg_delays.append(sum(p_delays) / len(p_delays))
                else:
                    phase_avg_delays.append(0)
            
            # 约束1：单相位平均延误不能过高（软化：改为惩罚项而非硬约束）
            phase_penalty = 0
            for p_avg in phase_avg_delays:
                if p_avg > MAX_PHASE_AVG_DELAY:
                    # 软惩罚：超出部分的平方，但权重降低
                    phase_penalty += (p_avg - MAX_PHASE_AVG_DELAY) ** 2 * 0.1  # 权重 0.1
            
            # 约束2：交叉口内相位间平均延误差异不能过大（软化）
            if len(phase_avg_delays) > 1:
                max_p_delay = max(phase_avg_delays)
                min_p_delay = min(phase_avg_delays)
                delay_diff = max_p_delay - min_p_delay
                if delay_diff > MAX_PHASE_DELAY_DIFF:
                    # 软惩罚，权重降低
                    phase_penalty += (delay_diff - MAX_PHASE_DELAY_DIFF) ** 2 * 0.1
            
            # 记录该交叉口的惩罚
            intersection_data[tl_id]['phase_penalty'] = phase_penalty
            
            # 计算交叉口平均延误
            total_flow = data['flow']
            if total_flow > 0:
                intersection_avg_delays[tl_id] = (data['queue_time'] + data['signal_delay']) / total_flow
            else:
                intersection_avg_delays[tl_id] = 0
        
        # 约束3：交叉口间平均延误差异不能过大（软化）
        intersection_penalty = 0
        if len(intersection_avg_delays) > 1:
            valid_delays = [d for d in intersection_avg_delays.values() if d > 0]
            if len(valid_delays) > 1:
                max_int_delay = max(valid_delays)
                min_int_delay = min(valid_delays)
                if min_int_delay > 0:
                    ratio = max_int_delay / min_int_delay
                    if ratio > MAX_INTERSECTION_DELAY_RATIO:
                        # 软惩罚，权重降低
                        intersection_penalty = (ratio - MAX_INTERSECTION_DELAY_RATIO) ** 2 * 10  # 从100降到10
        
        # ========== 目标函数：总延误时间（车·秒） + 公平性惩罚 ==========
        # 单位说明：
        #   - queue_time: 车·秒（排队延迟总和）
        #   - signal_delay: 车·秒（信号延迟总和）
        #   - objective: 车·秒（总延误时间）
        # 
        # 物理意义：所有车辆因排队和信号控制产生的总等待时间
        # 例如：objective = 1000 表示所有车辆共等待了1000秒
        
        total_queue_time = sum(d['queue_time'] for d in intersection_data.values())
        total_signal_delay = sum(d['signal_delay'] for d in intersection_data.values())
        
        # 汇总公平性惩罚
        total_penalty = sum(d.get('phase_penalty', 0) for d in intersection_data.values()) + intersection_penalty
        
        # ========== 目标函数值 ==========
        # 
        # PIA-TuRBO 的核心优势：
        # 1. 多步预测（MPC）：考虑未来状态变化
        # 2. 物理先验：通过先验数据引导初始搜索
        # 3. 协同先验：引导配时向"均衡"方向优化
        # 
        # 协同先验的作用：
        # - 不是惩罚项，而是"软引导"
        # - 当配时不均衡时，给予小的惩罚，引导优化器探索更均衡的解
        # - 权重要足够小，不能主导优化方向
        
        base_objective = total_queue_time + total_signal_delay + total_penalty
        
        # 协同先验（软引导，权重很小）
        cooperative_prior = 0.0
        if hasattr(self, 'get_cooperative_prior_value') and self.enable_cooperative_prior:
            cooperative_prior = self.get_cooperative_prior_value(u)
            # 限制协同先验的影响：最多占基础目标的 5%
            max_prior_ratio = 0.05
            max_prior = base_objective * max_prior_ratio
            cooperative_prior = min(cooperative_prior, max_prior)
        
        # 诊断日志（每100次评估输出一次）
        if hasattr(self, 'enable_prior_diagnostics') and self.enable_prior_diagnostics:
            if cooperative_prior != 0:
                if not hasattr(self, '_prior_diag_count'):
                    self._prior_diag_count = 0
                self._prior_diag_count += 1
                
                if self._prior_diag_count % 100 == 1:
                    prior_ratio = cooperative_prior / max(base_objective, 1) * 100
                    print(f"    [Prior] base={base_objective:.0f}, prior={cooperative_prior:.1f} ({prior_ratio:.1f}%)")
        
        # 目标 = 基础目标 + 协同先验（软引导）
        objective = base_objective + cooperative_prior
        
        return objective
    
    # ========== 自适应搜索区间 ==========
    
    def record_phase_performance(self):
        """
        记录当前各相位的排队和延误表现
        在优化前调用，记录"优化前"的状态
        """
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            
            for p in range(num_phases):
                queue, flow = self._get_phase_data(tl_id, p)
                key = (tl_id, p)
                
                if key not in self.phase_performance:
                    self.phase_performance[key] = {
                        'queue_before': queue,
                        'queue_after': queue,
                        'flow': flow,
                        'var_idx': begin + p,
                        'trend': 0  # 趋势：正数表示排队增加，负数表示减少
                    }
                else:
                    # 更新：上一轮的after变成这一轮的before
                    self.phase_performance[key]['queue_before'] = self.phase_performance[key]['queue_after']
                    self.phase_performance[key]['queue_after'] = queue
                    self.phase_performance[key]['flow'] = flow
                    
                    # 计算趋势
                    before = self.phase_performance[key]['queue_before']
                    after = self.phase_performance[key]['queue_after']
                    if before > 0:
                        self.phase_performance[key]['trend'] = (after - before) / before
                    else:
                        self.phase_performance[key]['trend'] = 0 if after == 0 else 1
    
    def update_adaptive_bounds(self):
        """
        根据各相位的表现，自适应调整搜索边界
        
        策略：
        - 排队增加多的相位（trend > 0.2）：提高下界，给更多绿灯
        - 排队减少的相位（trend < -0.2）：可以降低上界，压缩绿灯
        - 同一交叉口内，保持周期约束
        """
        if not self.enable_adaptive_bounds:
            return
        
        if self.adaptive_lb is None:
            self.adaptive_lb = self.lb.copy()
        if self.adaptive_ub is None:
            self.adaptive_ub = self.ub.copy()
        
        TREND_THRESHOLD = 0.2  # 趋势阈值
        ADJUST_STEP = 5        # 每次调整步长（秒）
        
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            cycle = info['cycle']
            num_phases = end - begin + 1
            
            # 收集该交叉口各相位的趋势
            phase_trends = []
            for p in range(num_phases):
                key = (tl_id, p)
                if key in self.phase_performance:
                    trend = self.phase_performance[key]['trend']
                    phase_trends.append((p, trend))
                else:
                    phase_trends.append((p, 0))
            
            # 按趋势排序：排队增加最多的排前面
            phase_trends.sort(key=lambda x: x[1], reverse=True)
            
            # 调整边界
            for rank, (p, trend) in enumerate(phase_trends):
                var_idx = begin + p
                current_green = self.current_timing[var_idx] if self.current_timing is not None else (self.lb[var_idx] + self.ub[var_idx]) / 2
                
                if trend > TREND_THRESHOLD:
                    # 排队增加：提高下界，鼓励给更多绿灯
                    new_lb = min(current_green, self.adaptive_lb[var_idx] + ADJUST_STEP)
                    self.adaptive_lb[var_idx] = max(self.lb[var_idx], new_lb)
                    # 上界保持或略微提高
                    self.adaptive_ub[var_idx] = min(self.ub[var_idx], max(self.adaptive_ub[var_idx], current_green + self.max_change))
                    
                elif trend < -TREND_THRESHOLD:
                    # 排队减少：可以降低上界，允许压缩绿灯
                    new_ub = max(current_green, self.adaptive_ub[var_idx] - ADJUST_STEP)
                    self.adaptive_ub[var_idx] = min(self.ub[var_idx], new_ub)
                    # 下界可以适当降低
                    self.adaptive_lb[var_idx] = max(self.lb[var_idx], min(self.adaptive_lb[var_idx], current_green - self.max_change))
                
                else:
                    # 趋势平稳：逐渐恢复到原始边界
                    self.adaptive_lb[var_idx] = max(self.lb[var_idx], self.adaptive_lb[var_idx] - 1)
                    self.adaptive_ub[var_idx] = min(self.ub[var_idx], self.adaptive_ub[var_idx] + 1)
                
                # 确保边界有效
                if self.adaptive_lb[var_idx] >= self.adaptive_ub[var_idx]:
                    mid = (self.adaptive_lb[var_idx] + self.adaptive_ub[var_idx]) / 2
                    self.adaptive_lb[var_idx] = mid - 5
                    self.adaptive_ub[var_idx] = mid + 5
            
            # 收集需要调整的相位信息（用于汇总输出）
            for p in range(num_phases):
                var_idx = begin + p
                key = (tl_id, p)
                trend = self.phase_performance.get(key, {}).get('trend', 0)
                queue_before = self.phase_performance.get(key, {}).get('queue_before', 0)
                queue_after = self.phase_performance.get(key, {}).get('queue_after', 0)
                
                # 只记录有显著变化的相位
                if abs(trend) > TREND_THRESHOLD:
                    if not hasattr(self, '_adjustment_summary'):
                        self._adjustment_summary = []
                    self._adjustment_summary.append({
                        'tl_id': tl_id,
                        'phase': p,
                        'trend': trend,
                        'queue_before': queue_before,
                        'queue_after': queue_after,
                        'lb': self.adaptive_lb[var_idx],
                        'ub': self.adaptive_ub[var_idx]
                    })
    
    def print_adjustment_summary(self):
        """打印自适应边界调整的汇总信息（只显示排队增加最多的5个相位）"""
        if not hasattr(self, '_adjustment_summary') or not self._adjustment_summary:
            print("    No significant queue changes detected")
            return
        
        # 按趋势排序（排队增加最多的在前）
        sorted_adjustments = sorted(self._adjustment_summary, key=lambda x: x['trend'], reverse=True)
        
        # 只显示前5个排队增加的相位
        top_increases = [a for a in sorted_adjustments if a['trend'] > 0][:5]
        
        if top_increases:
            print("    Top queue increases (bounds raised):")
            for adj in top_increases:
                symbol = "↑" if adj['trend'] > 0.2 else "→"
                print(f"      {adj['tl_id']}-P{adj['phase']}: {adj['queue_before']:.0f}→{adj['queue_after']:.0f} ({adj['trend']:+.0%}) {symbol} [{adj['lb']:.0f}-{adj['ub']:.0f}]")
        else:
            print("    No phases with significant queue increase")
        
        # 清空汇总
        self._adjustment_summary = []
    
    def get_adaptive_bounds(self):
        """
        获取自适应边界
        
        Returns:
            (lb, ub): 自适应后的边界，如果未启用则返回原始边界
        """
        # 打印汇总信息
        self.print_adjustment_summary()
        
        if self.enable_adaptive_bounds and self.adaptive_lb is not None and self.adaptive_ub is not None:
            return self.adaptive_lb.copy(), self.adaptive_ub.copy()
        return self.lb.copy(), self.ub.copy()
    
    # ========== 物理先验 ==========
    
    def generate_physics_prior(self) -> np.ndarray:
        """
        物理先验：按需求比例分配绿灯时间
        g_i ∝ (queue_i × 40 + flow_i)
        """
        prior = np.zeros(self.dim)
        
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            cycle = info['cycle']
            num_phases = end - begin + 1
            
            demands = []
            for p in range(num_phases):
                queue, flow = self._get_phase_data(tl_id, p)
                demand = queue * 40 + flow  # 排队转换为等效流量
                demands.append(max(demand, 100))
            
            total = sum(demands)
            for i, d in enumerate(demands):
                green = (d / total) * cycle if total > 0 else cycle / num_phases
                prior[begin + i] = np.clip(green, self.lb[begin + i], self.ub[begin + i])
        
        return prior
    
    def generate_prior_data(self, n_samples: int = 10, lb_ext=None, ub_ext=None) -> Dict:
        """
        生成先验数据（包含物理先验、历史经验、协同先验）
        
        【PIA-TuRBO核心优势】
        先验数据引导TuRBO的初始搜索方向，使其从"好的起点"开始优化，
        而不是从随机点开始。这是PIA相比TuRBO的核心优势。
        
        先验来源：
        1. 物理先验：按需求比例分配绿灯（最重要）
        2. 当前配时：上一轮优化结果（保持连续性）
        3. 历史最优：历史优化中表现最好的配时
        4. 协同先验：基于路径流量的信号-路径协同
        5. 随机采样：探索新解（保持多样性）
        """
        if lb_ext is None:
            lb_ext = np.tile(self.lb, self.predict_step)
        if ub_ext is None:
            ub_ext = np.tile(self.ub, self.predict_step)
        
        prior_X, prior_fX = [], []
        prior_sources = []  # 记录先验来源（用于诊断）
        
        # ========== 消融模式控制 ==========
        # physics_only:   仅物理先验（1个点）+ 随机填充
        # physics_perturb: 物理先验 + 高斯扰动采样（无协同、无历史）
        # None (默认):    完整PIA-TuRBO（物理+当前+历史+协同+随机）
        
        # 1. 物理先验（按需求比例分配绿灯）- 最重要的先验
        physics = np.tile(self.generate_physics_prior(), self.predict_step)
        physics = np.clip(physics, lb_ext, ub_ext)
        physics_obj = self.predict_travel_time(physics)
        prior_X.append(physics)
        prior_fX.append([physics_obj])
        prior_sources.append(('physics', physics_obj))
        
        if self.ablation_mode == 'physics_only':
            # 仅物理先验，其余用随机采样填充
            remaining = n_samples - len(prior_X)
            for i in range(max(0, remaining)):
                x = np.array([np.random.uniform(l, u) for l, u in zip(lb_ext, ub_ext)])
                x_obj = self.predict_travel_time(x)
                prior_X.append(x)
                prior_fX.append([x_obj])
                prior_sources.append((f'random_{i}', x_obj))
        
        elif self.ablation_mode == 'physics_perturb':
            # 物理先验 + 高斯扰动采样（模拟perturbation exploration）
            n_perturb = min(5, n_samples - 1)
            for i in range(n_perturb):
                noise = np.random.normal(0, 0.05, len(physics)) * (ub_ext - lb_ext)
                perturbed = np.clip(physics + noise, lb_ext, ub_ext)
                perturbed_obj = self.predict_travel_time(perturbed)
                prior_X.append(perturbed)
                prior_fX.append([perturbed_obj])
                prior_sources.append((f'perturb_{i}', perturbed_obj))
            # 剩余用随机采样填充
            remaining = n_samples - len(prior_X)
            for i in range(max(0, remaining)):
                x = np.array([np.random.uniform(l, u) for l, u in zip(lb_ext, ub_ext)])
                x_obj = self.predict_travel_time(x)
                prior_X.append(x)
                prior_fX.append([x_obj])
                prior_sources.append((f'random_{i}', x_obj))
        
        else:
            # 完整PIA-TuRBO模式
            # 2. 当前配时（上一轮优化结果）
            if self.current_timing is not None:
                current = np.tile(self.current_timing, self.predict_step)
                current = np.clip(current, lb_ext, ub_ext)
                current_obj = self.predict_travel_time(current)
                prior_X.append(current)
                prior_fX.append([current_obj])
                prior_sources.append(('current', current_obj))
            
            # 3. 历史最优配时（从历史经验中选择）
            history_priors = self._get_history_priors(lb_ext, ub_ext, max_count=3)
            for i, (hist_timing, hist_obj) in enumerate(history_priors):
                hist_obj_new = self.predict_travel_time(hist_timing)
                prior_X.append(hist_timing)
                prior_fX.append([hist_obj_new])
                prior_sources.append((f'history_{i}', hist_obj_new))
            
            # 4. 协同先验（基于路径流量的信号-路径协同）
            if self.enable_cooperative_prior and self.path_flow_data is not None:
                coop_prior = self._generate_cooperative_prior()
                if coop_prior is not None:
                    coop_ext = np.tile(coop_prior, self.predict_step)
                    coop_ext = np.clip(coop_ext, lb_ext, ub_ext)
                    coop_obj = self.predict_travel_time(coop_ext)
                    prior_X.append(coop_ext)
                    prior_fX.append([coop_obj])
                    prior_sources.append(('cooperative', coop_obj))
            
            # 5. 随机采样（探索新解）- 保持多样性
            remaining = n_samples - len(prior_X)
            for i in range(max(0, remaining)):
                x = np.array([np.random.uniform(l, u) for l, u in zip(lb_ext, ub_ext)])
                x_obj = self.predict_travel_time(x)
                prior_X.append(x)
                prior_fX.append([x_obj])
                prior_sources.append((f'random_{i}', x_obj))
        
        # ========== 诊断输出 ==========
        if self.enable_prior_diagnostics:
            print(f"  [Prior Data] Generated {len(prior_X)} prior points:")
            # 按目标值排序
            sorted_sources = sorted(prior_sources, key=lambda x: x[1])
            for source, obj in sorted_sources[:5]:  # 只显示前5个
                print(f"    {source}: obj={obj:.0f}")
            
            # 找出最优先验
            best_source, best_obj = sorted_sources[0]
            print(f"  [Prior Data] Best prior: {best_source} (obj={best_obj:.0f})")
        
        return {'X': np.array(prior_X), 'fX': np.array(prior_fX)}
    
    def _get_history_priors(self, lb_ext, ub_ext, max_count=3) -> List[Tuple[np.ndarray, float]]:
        """
        从历史优化结果中获取先验
        
        策略：
        1. 选择目标函数值最小的历史配时
        2. 选择与当前交通状态最相似的历史配时
        """
        if not self.optimization_history:
            return []
        
        result = []
        
        # 按目标函数值排序，选择最优的
        sorted_history = sorted(self.optimization_history, key=lambda x: x[1])
        
        for timing, obj, state in sorted_history[:max_count]:
            timing_ext = np.tile(timing, self.predict_step)
            timing_ext = np.clip(timing_ext, lb_ext, ub_ext)
            result.append((timing_ext, obj))
        
        return result
    
    def _record_optimization_result(self, timing: np.ndarray, objective: float):
        """
        记录优化结果到历史
        
        Args:
            timing: 优化后的配时
            objective: 目标函数值
        """
        # 获取当前交通状态特征
        traffic_state = self._get_traffic_state_features()
        
        # 添加到历史
        self.optimization_history.append((timing.copy(), objective, traffic_state))
        
        # 限制历史大小
        if len(self.optimization_history) > self.max_history_size:
            # 保留目标函数值最小的记录
            self.optimization_history.sort(key=lambda x: x[1])
            self.optimization_history = self.optimization_history[:self.max_history_size]
    
    def _get_traffic_state_features(self) -> Dict:
        """获取当前交通状态特征（用于历史匹配）"""
        total_queue = sum(self.snapshot_queue.values()) if self.snapshot_queue else 0
        total_flow = sum(self.snapshot_flow.values()) if self.snapshot_flow else 0
        return {
            'total_queue': total_queue,
            'total_flow': total_flow,
            'timestamp': self.last_sample_time
        }
    
    def _generate_cooperative_prior(self) -> Optional[np.ndarray]:
        """
        生成协同先验（基于路径流量的信号-路径协同）
        
        原理：
        - 如果某条路径流量大，则该路径经过的交叉口相位应获得更多绿灯
        - 这实现了信号控制与路径诱导的协同优化
        
        Returns:
            协同先验配时，如果无法生成则返回None
        """
        if self.path_flow_data is None:
            return None
        
        prior = np.zeros(self.dim)
        
        # 计算每个相位的路径加权需求
        phase_path_demand = {}  # {(tl_id, phase): weighted_demand}
        
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            incoming = info.get('incoming_edges', [])
            
            for p in range(num_phases):
                edge_id = incoming[p] if p < len(incoming) else None
                if edge_id is None:
                    continue
                
                # 基础需求
                queue, flow = self._get_phase_data(tl_id, p)
                base_demand = queue * 40 + flow
                
                # 路径加权（如果该路段在高流量路径上，增加权重）
                path_weight = self._get_path_weight_for_edge(edge_id)
                weighted_demand = base_demand * (1 + path_weight * 0.5)
                
                phase_path_demand[(tl_id, p)] = weighted_demand
        
        # 按加权需求分配绿灯
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            cycle = info['cycle']
            num_phases = end - begin + 1
            
            demands = []
            for p in range(num_phases):
                demand = phase_path_demand.get((tl_id, p), 100)
                demands.append(max(demand, 100))
            
            total = sum(demands)
            for i, d in enumerate(demands):
                green = (d / total) * cycle if total > 0 else cycle / num_phases
                prior[begin + i] = np.clip(green, self.lb[begin + i], self.ub[begin + i])
        
        return prior
    
    def _get_path_weight_for_edge(self, edge_id: str) -> float:
        """
        获取路段的路径权重
        
        如果该路段在高流量路径上，返回较高权重
        """
        if not hasattr(self, 'edge_path_weights') or self.edge_path_weights is None:
            return 0.0
        return self.edge_path_weights.get(edge_id, 0.0)
    
    def update_path_flow_data(self, path_flows: Dict):
        """
        更新路径流量数据（由路径诱导模块调用）
        
        Args:
            path_flows: {path_id: flow_count}
        """
        self.path_flow_data = path_flows
        
        # 计算每条路段的路径权重
        self.edge_path_weights = {}
        total_flow = sum(path_flows.values()) if path_flows else 1
        
        for path_id, flow in path_flows.items():
            # 假设path_id包含路段信息，或者有路径-路段映射
            if hasattr(self, 'path_edge_mapping') and path_id in self.path_edge_mapping:
                for edge_id in self.path_edge_mapping[path_id]:
                    weight = flow / total_flow
                    self.edge_path_weights[edge_id] = self.edge_path_weights.get(edge_id, 0) + weight
    
    # ========== 优化 ==========
    
    def optimize(self, max_evals=200, n_init=30, batch_size=16) -> np.ndarray:
        """
        TD-MPC + TuRBO 优化
        
        流程：
        1. 获取当前观测，编码为隐状态
        2. 使用混合目标函数（显式模型 + 学习残差 + Q值引导）
        3. TuRBO 在隐空间中搜索最优配时
        4. 存储转移，在线更新网络
        
        参数说明：
        - max_evals: 最大评估次数
        - n_init: 初始采样点数（包含物理先验、历史经验等）
        - batch_size: 每批采样数
        
        Returns:
            最优绿灯时间配置
        """
        if self.dim == 0:
            return None
        
        if self.current_timing is None:
            self.current_timing = (self.lb + self.ub) / 2
        
        self.optimization_count += 1
        
        # ========== TD-MPC: 获取观测和隐状态 ==========
        current_obs = self._get_observation() if self.enable_tdmpc and self.tdmpc_agent else None
        latent_state = None
        
        if self.enable_tdmpc and self.tdmpc_agent is not None:
            try:
                latent_state = self.tdmpc_agent.encode(current_obs)
                confidence = self.tdmpc_agent.confidence
                print(f"  [TD-MPC] Latent state encoded, confidence={confidence:.2f}")
            except Exception as e:
                print(f"  [TD-MPC] Encoding failed: {e}")
                latent_state = None
        
        # ========== 自适应边界调整 ==========
        if self.enable_adaptive_bounds and self.phase_performance:
            print("  [Adaptive Bounds] Queue trend → Search range:")
            self.update_adaptive_bounds()
            adaptive_lb, adaptive_ub = self.get_adaptive_bounds()
        else:
            adaptive_lb, adaptive_ub = self.lb.copy(), self.ub.copy()
            if self.enable_adaptive_bounds:
                print("  [Adaptive Bounds] First optimization, using default bounds")
        
        # 动态边界
        dynamic_lb = np.maximum(adaptive_lb, self.current_timing - self.max_change)
        dynamic_ub = np.minimum(adaptive_ub, self.current_timing + self.max_change)
        
        # 确保 ub > lb
        min_gap = 2.0
        for i in range(len(dynamic_lb)):
            if dynamic_ub[i] <= dynamic_lb[i] + min_gap:
                center = self.current_timing[i]
                half_gap = min_gap / 2 + 0.5
                dynamic_lb[i] = max(self.lb[i], center - half_gap)
                dynamic_ub[i] = min(self.ub[i], center + half_gap)
                if dynamic_ub[i] <= dynamic_lb[i]:
                    dynamic_lb[i] = self.lb[i]
                    dynamic_ub[i] = max(self.lb[i] + min_gap, self.ub[i])
        
        lb_ext = np.tile(dynamic_lb, self.predict_step)
        ub_ext = np.tile(dynamic_ub, self.predict_step)
        
        # ========== 生成先验数据 ==========
        prior_data = self.generate_prior_data(15, lb_ext, ub_ext)
        
        # 评估当前配时
        current_ext = np.tile(self.current_timing, self.predict_step)
        current_ext = np.clip(current_ext, lb_ext, ub_ext)
        current_obj = self._compute_tdmpc_objective(current_ext, latent_state)
        
        # ========== TuRBO 优化（使用 TD-MPC 增强的目标函数） ==========
        if torch.cuda.is_available():
            device = "cuda"
            print(f"  [GPU] Using CUDA: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
        
        # 创建 TD-MPC 增强的目标函数
        def tdmpc_objective(u):
            return self._compute_tdmpc_objective(u, latent_state)
        
        turbo = Turbo1(
            f=tdmpc_objective,
            lb=lb_ext, ub=ub_ext,
            n_init=n_init, max_evals=max_evals, batch_size=batch_size,
            verbose=False, use_ard=True, device=device, dtype="float64",
            prior_data=prior_data
        )
        
        turbo.optimize()
        x_best, f_best = turbo.get_best()
        
        # ========== 绘制收敛曲线 ==========
        self._plot_convergence_curve(turbo, current_obj)
        
        # ========== 结果处理 ==========
        improvement = (current_obj - f_best) / current_obj * 100 if current_obj > 0 else 0
        
        if f_best >= current_obj * 1.1:
            print(f"  [TuRBO Result] ✗ Worse: {f_best:.0f} > {current_obj:.0f} (current)")
            physics = self.generate_physics_prior()
            physics_ext = np.tile(physics, self.predict_step)
            physics_ext = np.clip(physics_ext, lb_ext, ub_ext)
            physics_obj = self._compute_tdmpc_objective(physics_ext, latent_state)
            
            if physics_obj < current_obj:
                print(f"  [Fallback] Using physics prior (obj={physics_obj:.0f})")
                best_timing = physics
            else:
                print(f"  [Fallback] Keeping current timing (obj={current_obj:.0f})")
                best_timing = self.current_timing.copy()
        else:
            if improvement > 0:
                print(f"  [TuRBO Result] ✓ Improved: {current_obj:.0f} → {f_best:.0f} ({improvement:+.1f}%)")
            else:
                print(f"  [TuRBO Result] ~ Similar: {current_obj:.0f} → {f_best:.0f} ({improvement:+.1f}%)")
            best_timing = x_best[:self.dim]
        
        # ========== TD-MPC: 存储转移并在线学习 ==========
        if self.enable_tdmpc and self.tdmpc_agent is not None:
            self._tdmpc_store_and_learn(current_obs, x_best, f_best)
        
        # 记录优化结果
        self._record_optimization_result(best_timing, f_best)
        
        return best_timing
    
    def _compute_tdmpc_objective(self, u: np.ndarray, latent_state=None) -> float:
        """
        TD-MPC 增强的目标函数
        
        目标 = 显式模型预测 + 置信度加权的残差修正 + Q值引导
        
        【渐进式启用策略】
        - 冷启动（confidence < 0.3）：使用简单目标函数（与TuRBO相同）
        - 过渡期（0.3 <= confidence < 0.7）：MPC多步预测 + 小权重残差
        - 成熟期（confidence >= 0.7）：完整 TD-MPC
        
        【目标函数选择】
        - 冷启动时使用 _simple_objective（与TuRBO相同），避免复杂目标函数引入噪声
        - 成熟后使用 predict_travel_time（MPC多步预测），发挥预测优势
        
        Args:
            u: 动作序列（配时）
            latent_state: 隐状态（如果可用）
        
        Returns:
            目标函数值
        """
        # 获取置信度（如果 TD-MPC 可用）
        confidence = 0.0
        if self.enable_tdmpc and self.tdmpc_agent is not None:
            confidence = self.tdmpc_agent.confidence
        
        # 【冷启动阶段】使用简单目标函数，与 TuRBO 保持一致
        # 这样 PIA-TuRBO 的优势纯粹来自先验数据，而非目标函数差异
        if confidence < 0.3:
            # 对于多步预测，只取第一步的配时
            u_single = u[:self.dim] if len(u) > self.dim else u
            return self._simple_objective(u_single)
        
        # 【过渡期和成熟期】使用 MPC 多步预测目标函数
        base_obj = self.predict_travel_time(u)
        
        # 如果 TD-MPC 引导不可用，直接返回基础目标
        if not self.enable_tdmpc_guidance or self.tdmpc_agent is None or latent_state is None:
            return base_obj
        
        try:
            # 残差修正（置信度加权）
            action_tensor = torch.FloatTensor(u).unsqueeze(0).to(self.tdmpc_agent.device)
            
            # 预测残差
            residual = self.tdmpc_agent.predict_residual(latent_state, action_tensor)
            residual_value = residual.mean().item()
            
            # Q 值引导（终端价值估计）
            q_value = self.tdmpc_agent.estimate_q(latent_state, action_tensor)
            q_guidance = -q_value.item() * 0.1  # 负 Q 值作为惩罚，权重 0.1
            
            # 根据置信度调整权重
            # 过渡期：使用较小的权重
            if confidence < 0.7:
                weight = (confidence - 0.3) / 0.4  # 0 到 1 的线性插值
                residual_value *= weight * 0.5
                q_guidance *= weight * 0.5
            
            # 组合目标
            tdmpc_obj = base_obj + residual_value + q_guidance
            
            return tdmpc_obj
            
        except Exception as e:
            # 出错时回退到基础目标
            return base_obj
    
    def _tdmpc_store_and_learn(self, obs: np.ndarray, action: np.ndarray, reward: float):
        """
        TD-MPC: 存储转移并在线学习
        
        Args:
            obs: 当前观测
            action: 执行的动作
            reward: 获得的奖励（负延误）
        """
        if self.tdmpc_agent is None:
            return
        
        # 计算奖励（负延误，越小越好 → 负值越大越好）
        # 归一化到合理范围
        normalized_reward = -reward / 10000.0
        
        # 存储转移
        if self.last_obs is not None and self.last_action is not None:
            self.tdmpc_agent.store_transition(
                obs=self.last_obs,
                action=self.last_action,
                reward=self.last_reward if self.last_reward else 0,
                next_obs=obs,
                done=False
            )
        
        # 更新记录
        self.last_obs = obs.copy()
        self.last_action = action.copy()
        self.last_reward = normalized_reward
        
        # 定期更新网络
        if self.optimization_count % self.tdmpc_update_interval == 0:
            if self.tdmpc_agent.buffer.is_ready:
                losses = self.tdmpc_agent.update(batch_size=32)
                if losses:
                    print(f"  [TD-MPC] Update: q_loss={losses['q_loss']:.4f}, "
                          f"consistency={losses['consistency_loss']:.4f}, "
                          f"confidence={losses['confidence']:.2f}")
    
    def _plot_convergence_curve(self, turbo, current_obj: float):
        """
        绘制TuRBO优化的收敛曲线
        
        Args:
            turbo: TuRBO优化器实例
            current_obj: 当前配时的目标函数值（作为基准线）
        """
        try:
            import matplotlib.pyplot as plt
            
            # 获取所有评估的目标函数值
            if hasattr(turbo, 'fX') and turbo.fX is not None:
                fX = turbo.fX.flatten()
                n_evals = len(fX)
                
                # 计算累积最优值
                best_so_far = np.minimum.accumulate(fX)
                
                # 创建图形
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
                
                # 左图：所有评估点
                ax1.scatter(range(n_evals), fX, alpha=0.5, s=20, label='Evaluations')
                ax1.plot(range(n_evals), best_so_far, 'r-', linewidth=2, label='Best so far')
                ax1.axhline(y=current_obj, color='g', linestyle='--', label=f'Current: {current_obj:.0f}')
                ax1.set_xlabel('Evaluation Number')
                ax1.set_ylabel('Objective Value (vehicle·seconds)')
                ax1.set_title('TuRBO Optimization Progress')
                ax1.legend()
                ax1.grid(True, alpha=0.3)
                
                # 右图：收敛曲线（只显示最优值）
                ax2.plot(range(n_evals), best_so_far, 'b-', linewidth=2)
                ax2.axhline(y=current_obj, color='g', linestyle='--', label=f'Current: {current_obj:.0f}')
                ax2.fill_between(range(n_evals), best_so_far, current_obj, 
                                where=best_so_far < current_obj, alpha=0.3, color='green',
                                label='Improvement')
                ax2.set_xlabel('Evaluation Number')
                ax2.set_ylabel('Best Objective Value')
                ax2.set_title('Convergence Curve')
                ax2.legend()
                ax2.grid(True, alpha=0.3)
                
                plt.tight_layout()
                
                # 保存图片
                if self.output_dir:
                    import os
                    convergence_file = os.path.join(self.output_dir, 'turbo_convergence.png')
                    plt.savefig(convergence_file, dpi=150, bbox_inches='tight')
                    print(f"  [Convergence] Saved to: {convergence_file}")
                
                plt.close()
                
                # 输出统计信息
                improvement_pct = (current_obj - best_so_far[-1]) / current_obj * 100
                print(f"  [Convergence] Evals={n_evals}, Init={fX[0]:.0f}, Final={best_so_far[-1]:.0f}, Improvement={improvement_pct:.1f}%")
                
        except Exception as e:
            print(f"  [Convergence] Failed to plot: {e}")
    
    # ========== 应用配时 ==========
    
    def apply_timing(self, u: np.ndarray, current_time: float = 0) -> np.ndarray:
        """
        应用优化后的配时（带周期约束投影）
        
        Returns:
            调整后的配时数组（满足周期约束）
        """
        adjusted = u.copy()  # 用于存储调整后的配时
        
        for tl_id, info in self.intersections.items():
            try:
                programs = traci.trafficlight.getAllProgramLogics(tl_id)
                if not programs:
                    continue
                program = programs[0]
                
                begin, end = info['begin'], info['end']
                green_times = list(map(float, u[begin:end+1]))
                
                # 周期约束：按比例调整所有相位，而不是只调整第一个
                cycle = info['cycle']
                total_green = sum(green_times)
                if total_green > 0 and abs(total_green - cycle) > 0.1:
                    # 按比例缩放所有相位
                    scale = cycle / total_green
                    green_times = [g * scale for g in green_times]
                
                # 转为整数并确保在边界内
                green_times = [max(int(self.lb[begin + i]), min(int(self.ub[begin + i]), int(round(g)))) 
                               for i, g in enumerate(green_times)]
                
                # 微调确保总和等于周期
                diff = sum(green_times) - cycle
                if diff != 0:
                    # 找到可以调整的相位（优先调整绿灯时间最长的）
                    sorted_indices = sorted(range(len(green_times)), key=lambda i: green_times[i], reverse=True)
                    for idx in sorted_indices:
                        if diff > 0 and green_times[idx] > self.lb[begin + idx]:
                            adjust = min(diff, green_times[idx] - int(self.lb[begin + idx]))
                            green_times[idx] -= adjust
                            diff -= adjust
                        elif diff < 0 and green_times[idx] < self.ub[begin + idx]:
                            adjust = min(-diff, int(self.ub[begin + idx]) - green_times[idx])
                            green_times[idx] += adjust
                            diff += adjust
                        if diff == 0:
                            break
                
                # 更新调整后的配时数组
                for i, gt in enumerate(green_times):
                    adjusted[begin + i] = gt
                
                # 记录
                for idx, gt in enumerate(green_times):
                    self.green_time_records.append({
                        'time': current_time, 'tl_id': tl_id,
                        'phase_idx': idx * 2, 'green_time': gt
                    })
                
                # 更新相位
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
        
        # 更新当前配时为调整后的值
        self.current_timing = adjusted.copy()
        return adjusted

    
    # ========== 仿真步进 ==========
    
    def step(self, current_time: float):
        """仿真步进（每步调用）"""
        if not self.enabled:
            return
        
        # ========== 预热期参数 ==========
        WARMUP_TIME = 600  # 预热时间（秒），0-600s不进行优化
        
        # 数据采集（每10秒，预热期也采集）
        self.collect_traffic_data(current_time)
        
        # 排队采样（每10秒，预热期也采集）
        if current_time % 10 == 0:
            self._collect_queue_sample()
        
        # 预热期内不进行优化，但继续采集数据
        if current_time < WARMUP_TIME:
            return
        
        # ========== 第一次优化：在600s时，使用完整的0-600s数据 ==========
        if current_time == WARMUP_TIME:
            print(f"\n[Time {current_time}s] First signal optimization (using 0-{WARMUP_TIME}s warmup data)...")
            
            # 第一次优化使用完整的预热期数据（不清空）
            self.create_snapshot()
            
            self.record_phase_performance()
            self.pre_opt_avg_queue = self._get_avg_queue()
            self._update_queue_state()
            
            optimal = self.optimize()
            if optimal is not None:
                adjusted = self.apply_timing(optimal, current_time)
                self._print_intersection_10_timing(adjusted)
            
            # 第一次优化后清空历史，开始新的采集周期
            self.clear_history()
            return
        
        # 每60秒检查排队状态，如果恶化严重则提前优化
        if current_time % 60 == 0:
            if self._check_queue_deterioration():
                print(f"\n[Time {current_time}s] Queue deterioration detected, emergency optimization...")
                self._emergency_optimize(current_time)
                return
        
        # 常规优化时间点：预热后每300秒优化一次
        time_since_warmup = current_time - WARMUP_TIME
        if time_since_warmup > 0 and time_since_warmup % self.optimization_interval == 0:
            print(f"\n[Time {current_time}s] Signal optimization (using last {self.optimization_interval}s data)...")
            
            self.create_snapshot()
            
            # ========== 自适应边界：记录各相位表现 ==========
            self.record_phase_performance()
            self.pre_opt_avg_queue = self._get_avg_queue()
            self._update_queue_state()
            
            optimal = self.optimize()
            if optimal is not None:
                adjusted = self.apply_timing(optimal, current_time)
                self._print_intersection_10_timing(adjusted)
            
            self.clear_history()
    
    def _check_queue_deterioration(self) -> bool:
        """
        检查排队是否恶化（使用一段时间的平均值）
        如果近期平均排队比优化前增加超过50%，认为恶化
        """
        if not hasattr(self, 'pre_opt_avg_queue') or self.pre_opt_avg_queue == 0:
            return False
        
        # 使用快照数据
        if self.snapshot_queue:
            current_avg = sum(self.snapshot_queue.values())
        else:
            # 回退：使用历史记录的平均
            if not hasattr(self, 'queue_history_for_check'):
                return False
            if len(self.queue_history_for_check) < 3:
                return False
            current_avg = np.mean(self.queue_history_for_check[-6:])
        
        increase_ratio = (current_avg - self.pre_opt_avg_queue) / max(self.pre_opt_avg_queue, 1)
        
        if increase_ratio > 0.5:
            print(f"  Avg queue increased {increase_ratio*100:.0f}% ({self.pre_opt_avg_queue:.0f} -> {current_avg:.0f})")
            return True
        return False
    
    def _collect_queue_sample(self):
        """采集排队样本（每10秒调用）"""
        if not hasattr(self, 'queue_history_for_check'):
            self.queue_history_for_check = []
        
        total = 0
        for tl_id, info in self.intersections.items():
            num_phases = info['end'] - info['begin'] + 1
            for p in range(num_phases):
                incoming = info.get('incoming_edges', [])
                edge_id = incoming[p] if p < len(incoming) else None
                if edge_id:
                    try:
                        total += traci.edge.getLastStepHaltingNumber(edge_id)
                    except:
                        pass
        
        self.queue_history_for_check.append(total)
        # 保留最近30个样本（5分钟）
        if len(self.queue_history_for_check) > 30:
            self.queue_history_for_check = self.queue_history_for_check[-30:]
    
    def _get_avg_queue(self) -> float:
        """获取近期平均排队"""
        if hasattr(self, 'queue_history_for_check') and self.queue_history_for_check:
            return np.mean(self.queue_history_for_check[-6:])  # 最近60秒
        return 0
    
    def _emergency_optimize(self, current_time: float):
        """
        紧急优化：使用物理先验快速调整
        不运行完整TuRBO，直接用需求比例分配
        """
        self.create_snapshot()
        
        # 直接使用物理先验（按需求比例分配）
        physics_prior = self.generate_physics_prior()
        
        # 限制变化幅度
        if self.current_timing is not None:
            diff = physics_prior - self.current_timing
            diff = np.clip(diff, -self.max_change, self.max_change)
            adjusted = self.current_timing + diff
            adjusted = np.clip(adjusted, self.lb, self.ub)
        else:
            adjusted = physics_prior
        
        final_timing = self.apply_timing(adjusted, current_time)
        self.pre_opt_avg_queue = self._get_avg_queue()  # 更新基准（平均值）
        self._print_key_intersections_timing(final_timing, prefix="Emergency")
    
    def _print_key_intersections_timing(self, timing: np.ndarray, prefix: str = "Applied"):
        """
        显示关键交叉口的绿灯时长和排队情况
        
        关键交叉口：
        - 交叉口10: 5-leg典型交叉口 (var_index 0-4, cycle=150s)
        - 交叉口16: 4-leg交叉口 (var_index 13-16, cycle=120s)
        
        Args:
            timing: 绿灯时间配置数组（已满足周期约束）
            prefix: 输出前缀
        """
        key_intersections = ['10', '16']
        
        for tl_id in key_intersections:
            info = self.intersections.get(tl_id, {})
            if not info:
                continue
            
            begin = info.get('begin', 0)
            end = info.get('end', 0)
            cycle = info.get('cycle', 90)
            num_phases = end - begin + 1
            incoming = info.get('incoming_edges', [])
            
            if begin >= len(timing) or end >= len(timing):
                continue
            
            # 获取绿灯时长
            green_times = [int(timing[begin + i]) for i in range(num_phases)]
            total = sum(green_times)
            
            # 获取排队数据
            queue_data = []
            for i, edge in enumerate(incoming):
                q = self.snapshot_queue.get(edge, 0)
                queue_data.append(q)
            
            # 格式化输出：绿灯时间
            phase_parts = []
            for i, gt in enumerate(green_times):
                edge_name = incoming[i].split('_')[0] if i < len(incoming) else '?'
                phase_parts.append(f"P{i}({edge_name}):{gt}s")
            phase_str = " | ".join(phase_parts)
            
            # 检查周期约束
            cycle_check = "✓" if total == cycle else f"✗ expect {cycle}"
            leg_info = f"{num_phases}-leg" if num_phases >= 4 else f"{num_phases}p"
            
            print(f"  {prefix} [Int-{tl_id}, {leg_info}] {phase_str}  (total={total}s {cycle_check})")
            
            # 显示排队情况
            queue_parts = [f"Q{i}:{int(q)}" for i, q in enumerate(queue_data)]
            queue_str = " | ".join(queue_parts)
            total_queue = sum(queue_data)
            print(f"          Queue: {queue_str}  (total={int(total_queue)})")
        
        # 显示其他交叉口的汇总
        key_indices = set()
        for tl_id in key_intersections:
            info = self.intersections.get(tl_id, {})
            if info:
                for i in range(info.get('begin', 0), info.get('end', 0) + 1):
                    key_indices.add(i)
        
        other_timing = [int(t) for i, t in enumerate(timing[:self.dim]) if i not in key_indices]
        if other_timing:
            print(f"          [Others] range=[{min(other_timing)}-{max(other_timing)}]s, avg={np.mean(other_timing):.1f}s")
    
    # 保留旧方法名作为别名，保持兼容性
    def _print_intersection_10_timing(self, timing: np.ndarray, prefix: str = "Applied"):
        """别名，保持向后兼容"""
        self._print_key_intersections_timing(timing, prefix)
    
    def _update_queue_state(self):
        """
        从仿真中更新排队状态（参考tianjin的X_nb_net和X_bj_net）
        
        这是MPC的初始状态，用于多步预测
        """
        # 如果路段列表为空，重新初始化
        if not self.internal_edges and not self.boundary_edges:
            self._init_network_structure()
        
        # 确保数组大小正确
        if self.queue_internal is None or len(self.queue_internal) != len(self.internal_edges):
            self.queue_internal = np.zeros(len(self.internal_edges))
        if self.queue_boundary is None or len(self.queue_boundary) != len(self.boundary_edges):
            self.queue_boundary = np.zeros(len(self.boundary_edges))
        
        total_internal = 0
        total_boundary = 0
        
        # 更新内部路段排队
        for i, eid in enumerate(self.internal_edges):
            try:
                q = traci.edge.getLastStepHaltingNumber(eid)
                self.queue_internal[i] = q
                total_internal += q
            except:
                pass
        
        # 更新边界路段排队
        for i, eid in enumerate(self.boundary_edges):
            try:
                q = traci.edge.getLastStepHaltingNumber(eid)
                self.queue_boundary[i] = q
                total_boundary += q
            except:
                pass
        
        # 同时更新需求流量（从仿真获取实时数据）
        for eid in self.internal_edges + self.boundary_edges:
            try:
                veh_count = traci.edge.getLastStepVehicleNumber(eid)
                self.demand_flow[eid] = max(veh_count * 3600, 100)
            except:
                if eid not in self.demand_flow:
                    self.demand_flow[eid] = 500
        
        print(f"  Queue: internal={total_internal:.0f}, boundary={total_boundary:.0f}, total={total_internal+total_boundary:.0f}")
    
    # ========== 输出 ==========
    
    def set_output_dir(self, output_dir: str):
        """
        设置输出目录
        
        新目录结构：直接输出到实验配置目录
        - output/{config_name}/green_times.xlsx
        
        Args:
            output_dir: 实验配置目录（如 output/1_1_3_X/）
        """
        self.output_dir = output_dir
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def record_initial_green_times(self):
        """记录初始绿灯时长"""
        for tl_id, info in self.intersections.items():
            try:
                programs = traci.trafficlight.getAllProgramLogics(tl_id)
                if not programs:
                    continue
                program = programs[0]
                
                green_idx = 0
                for phase in program.phases:
                    if 'G' in phase.state or 'g' in phase.state:
                        self.green_time_records.append({
                            'time': 0, 'tl_id': tl_id,
                            'phase_idx': green_idx * 2,
                            'green_time': int(phase.duration)
                        })
                        green_idx += 1
            except:
                pass
        print(f"  Recorded initial green times")
    
    def save_green_times_to_excel(self, filename: str = None):
        """
        保存绿灯时长到Excel
        
        新目录结构：直接保存到实验配置目录
        - output/{config_name}/green_times.xlsx
        """
        if not self.green_time_records:
            return
        
        # 新目录结构：直接保存到output_dir（实验配置目录）
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
        
        print(f"  Saved: {output_path}")
    
    def get_predicted_green_changes(self):
        """
        获取预测的绿灯时间变化（用于传递给路径诱导的TD-MPC预测）
        
        基于MPC预测的未来配时变化，计算各路段的绿灯时间变化比例。
        路径诱导可以利用这些信息来预测未来的流量变化。
        
        Returns:
            dict: {edge_id: green_time_change_ratio}
                  正值表示绿灯增加，负值表示绿灯减少
        """
        green_changes = {}
        
        if self.current_timing is None:
            return green_changes
        
        # 获取上一次的配时（如果有）
        if not hasattr(self, 'previous_timing') or self.previous_timing is None:
            self.previous_timing = self.current_timing.copy()
            return green_changes
        
        # 计算各路段的绿灯时间变化比例
        for tl_id, info in self.intersections.items():
            begin, end = info['begin'], info['end']
            cycle = info.get('cycle', 90)
            incoming_edges = info.get('incoming_edges', [])
            num_phases = end - begin + 1
            
            for p in range(num_phases):
                var_idx = begin + p
                if var_idx >= len(self.current_timing) or var_idx >= len(self.previous_timing):
                    continue
                
                current_green = self.current_timing[var_idx]
                previous_green = self.previous_timing[var_idx]
                
                # 计算变化比例
                if previous_green > 0:
                    change_ratio = (current_green - previous_green) / previous_green
                else:
                    change_ratio = 0
                
                # 获取对应的路段
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                if edge_id:
                    green_changes[edge_id] = change_ratio
        
        # 更新上一次配时
        self.previous_timing = self.current_timing.copy()
        
        return green_changes


# ========== 辅助函数 ==========

def get_current_program(tl_id: str):
    """获取当前配时方案"""
    programs = traci.trafficlight.getAllProgramLogics(tl_id)
    return programs[0] if programs else None


def update_phase_durations(program, new_durations: List[float]):
    """更新相位时长"""
    green_phases = [p for p in program.phases if 'G' in p.state or 'g' in p.state]
    for i, phase in enumerate(green_phases):
        if i < len(new_durations):
            phase.duration = new_durations[i]
            phase.minDur = new_durations[i]
            phase.maxDur = new_durations[i]
    return program


def set_new_program(tl_id: str, program):
    """设置新配时方案"""
    traci.trafficlight.setProgramLogic(tl_id, program)


    # ==================== 交叉耦合接口方法 ====================
    
    def compute_edge_delays(self):
        """
        计算各路段的Webster延误预测（用于传递给路径诱导）
        
        对应论文公式(3)-(6)的Webster延误模型
        
        Returns:
            dict: {edge_id: predicted_delay_seconds}
        """
        edge_delays = {}
        
        for tl_id, info in self.intersections.items():
            cycle = info.get('cycle', 90)
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            incoming_edges = info.get('incoming_edges', [])
            
            for p in range(num_phases):
                # 获取该相位的绿灯时间
                if self.current_timing is not None and begin + p < len(self.current_timing):
                    green_time = self.current_timing[begin + p]
                else:
                    green_time = 30  # 默认值
                
                # 获取该相位控制的路段
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                if not edge_id:
                    continue
                
                # 获取到达流量
                arrival_flow = self.demand_flow.get(edge_id, 500)  # vph
                capacity_vph = self.saturation_flow.get(edge_id, 3600) * (green_time / cycle)
                
                # 饱和度
                x = arrival_flow / capacity_vph if capacity_vph > 0 else 0.5
                x = min(x, self.MAX_SATURATION_DEGREE)
                
                # 绿信比
                lambda_i = green_time / cycle
                
                # Webster延误公式
                if x < self.MAX_SATURATION_DEGREE:
                    # 均匀延误
                    denom = 1 - lambda_i * x
                    if denom > 0.01:
                        d_uniform = cycle * (1 - lambda_i)**2 / (2 * denom)
                    else:
                        d_uniform = cycle * (1 - lambda_i) / 2
                    
                    # 随机延误
                    if arrival_flow > 0 and x < 1:
                        q_per_sec = arrival_flow / 3600
                        d_random = x**2 / (2 * q_per_sec * max(1 - x, 0.01))
                        d_random = min(d_random, cycle * 0.5)
                    else:
                        d_random = 0
                    
                    total_delay = d_uniform + d_random
                else:
                    # 过饱和情况
                    total_delay = 120  # 设置较大延误值
                
                edge_delays[edge_id] = max(total_delay, 0)
        
        return edge_delays
    
    def update_cooperative_prior(self, path_flows=None, path_edges=None, edge_flows=None):
        """
        更新协同先验函数（用于PIA-TuRBO算法）
        
        对应论文中的协同先验函数 μ_route(f)
        
        Args:
            path_flows: 路径流量分布 {path_id: flow}
            path_edges: 路径-路段关系 {path_id: [edge_ids]}
            edge_flows: 路段流量 {edge_id: flow}
        """
        if not hasattr(self, 'cooperative_prior_data'):
            self.cooperative_prior_data = {}
        
        # 存储路径流量信息
        if path_flows:
            self.cooperative_prior_data['path_flows'] = path_flows
        if path_edges:
            self.cooperative_prior_data['path_edges'] = path_edges
        if edge_flows:
            self.cooperative_prior_data['edge_flows'] = edge_flows
        
        # 计算路径流量的均衡性指标（用于先验函数）
        if path_flows:
            flows = list(path_flows.values())
            if flows:
                flow_variance = np.var(flows)
                flow_mean = np.mean(flows)
                # 流量分布的变异系数（CV）
                cv = np.sqrt(flow_variance) / flow_mean if flow_mean > 0 else 0
                self.cooperative_prior_data['flow_cv'] = cv
        
        # 自动构建路径-交叉口关联矩阵
        if path_edges and not self.path_intersection_matrix:
            self._build_path_intersection_matrix(path_edges)
        
        self.prior_initialized = True
        print(f"  [协同先验] 更新路径流量数据: {len(path_flows or {})} 条路径")
    
    def _build_path_intersection_matrix(self, path_edges):
        """
        构建路径-交叉口关联矩阵 δ_ir
        
        对应论文公式(2): q_i = Σ f_r · δ_ir
        
        Args:
            path_edges: 路径-路段关系 {path_id: [edge_ids]}
        """
        self.path_intersection_matrix = {}
        
        if not self.intersections:
            return
        
        for path_id, edges in path_edges.items():
            for edge_id in edges:
                # 检查该路段是否进入某个信号交叉口
                for tl_id, info in self.intersections.items():
                    incoming_edges = info.get('incoming_edges', [])
                    if edge_id in incoming_edges:
                        self.path_intersection_matrix[(tl_id, path_id)] = 1
        
        if self.path_intersection_matrix:
            print(f"    [路径-交叉口矩阵] 构建完成: {len(self.path_intersection_matrix)} 个关联")
    
    def auto_init_cooperative_prior(self):
        """
        自动初始化协同先验数据（当没有路径诱导模块时使用）
        
        基于当前交通状态自动构建先验数据
        """
        if self.prior_initialized:
            return
        
        # 从当前流量数据构建edge_flows
        edge_flows = {}
        for tl_id, info in self.intersections.items():
            incoming_edges = info.get('incoming_edges', [])
            for edge_id in incoming_edges:
                if edge_id:
                    flow = self.demand_flow.get(edge_id, 500)
                    edge_flows[edge_id] = flow / 360  # 转换为车辆数
        
        # 构建简化的路径数据（每条进入路段视为一条路径）
        path_flows = {}
        path_edges = {}
        for i, (edge_id, flow) in enumerate(edge_flows.items()):
            path_id = f"auto_path_{i}"
            path_flows[path_id] = flow * 360  # 转换为vph
            path_edges[path_id] = [edge_id]
        
        # 更新协同先验数据
        self.cooperative_prior_data = {
            'edge_flows': edge_flows,
            'path_flows': path_flows,
            'path_edges': path_edges,
            'flow_cv': 0.3  # 默认CV值
        }
        
        # 构建路径-交叉口矩阵
        self._build_path_intersection_matrix(path_edges)
        
        self.prior_initialized = True
        print(f"  [协同先验] 自动初始化: {len(path_flows)} 条路径")
    
    def update_predicted_green_changes(self, predicted_changes):
        """
        接收来自协调层的预测配时变化（交叉耦合：协调层→信号优化）
        
        协调层基于路径流量变化预测信号优化器会如何调整配时。
        信号优化器可以利用这些预测来：
        1. 提前调整搜索方向
        2. 验证自身优化结果与预测的一致性
        3. 在目标函数中考虑预测的流量变化
        
        预测公式（来自协调层）：
        g'_i = g_i · (q_i^new / q_i^old)^α
        
        Args:
            predicted_changes: {tl_id: {phase: delta_green}} 预测的绿灯时间变化
        """
        if not hasattr(self, 'predicted_green_changes'):
            self.predicted_green_changes = {}
        
        self.predicted_green_changes = predicted_changes.copy() if predicted_changes else {}
        
        # 统计信息
        total_changes = sum(len(phases) for phases in predicted_changes.values()) if predicted_changes else 0
        if total_changes > 0:
            # 计算平均预测变化量
            all_deltas = []
            for tl_id, phases in predicted_changes.items():
                all_deltas.extend(phases.values())
            avg_delta = np.mean(all_deltas) if all_deltas else 0
            
            print(f"    [协调层→信号] 接收预测配时变化: {total_changes} 个相位, "
                  f"平均变化 {avg_delta:+.1f}s")
        
        # 可选：利用预测调整搜索边界
        if self.enable_adaptive_bounds and predicted_changes:
            self._adjust_bounds_from_prediction(predicted_changes)
    
    def _adjust_bounds_from_prediction(self, predicted_changes):
        """
        根据预测的配时变化调整搜索边界
        
        如果协调层预测某相位需要更多绿灯时间，
        可以适当提高该相位的搜索下界，加速收敛。
        
        Args:
            predicted_changes: 预测的配时变化
        """
        if self.adaptive_lb is None or self.adaptive_ub is None:
            return
        
        for tl_id, phase_changes in predicted_changes.items():
            if tl_id not in self.intersections:
                continue
            
            info = self.intersections[tl_id]
            begin = info.get('begin', 0)
            
            for phase, delta in phase_changes.items():
                var_idx = begin + phase
                if var_idx >= len(self.adaptive_lb):
                    continue
                
                # 根据预测方向微调边界
                if delta > 2:  # 预测需要增加绿灯
                    # 适当提高下界
                    self.adaptive_lb[var_idx] = min(
                        self.adaptive_lb[var_idx] + delta * 0.3,
                        self.adaptive_ub[var_idx] - 5
                    )
                elif delta < -2:  # 预测需要减少绿灯
                    # 适当降低上界
                    self.adaptive_ub[var_idx] = max(
                        self.adaptive_ub[var_idx] + delta * 0.3,
                        self.adaptive_lb[var_idx] + 5
                    )
    
    def get_cooperative_prior_value(self, green_times):
        """
        计算协同先验函数值（修复版 v2）
        
        【核心思想】
        协同先验应该是"软引导"，帮助优化器更快找到好的解，
        而不是"硬惩罚"干扰优化方向。
        
        【修复内容】
        1. 大幅降低权重，确保协同先验不会主导优化
        2. 使用相对值而非绝对值，避免在不同流量下表现差异过大
        3. 添加边界检查，避免极端值
        
        Args:
            green_times: 当前绿灯时间配置（numpy数组）
            
        Returns:
            float: 先验函数值（软引导项，越小越好）
        """
        # 检查是否需要自动初始化
        if not self.prior_initialized:
            self.auto_init_cooperative_prior()
        
        if not self.cooperative_prior_data:
            return 0.0
        
        # ========== 权重参数（大幅降低） ==========
        # 协同先验的作用是"微调"，不是"主导"
        alpha_balance = 0.01   # 均衡性引导权重（从0.1降到0.01）
        
        prior_balance = 0.0
        
        # ========== 均衡性引导 ==========
        # 思路：各相位的饱和度应该接近，否则说明配时不均衡
        # 但这只是"软引导"，不应该主导优化方向
        edge_flows = self.cooperative_prior_data.get('edge_flows', {})
        if edge_flows and isinstance(green_times, np.ndarray):
            saturation_degrees = []
            
            for tl_id, info in self.intersections.items():
                cycle = info.get('cycle', 90)
                begin, end = info['begin'], info['end']
                incoming_edges = info.get('incoming_edges', [])
                
                for p in range(end - begin + 1):
                    if begin + p >= len(green_times):
                        continue
                    g = green_times[begin + p]
                    edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                    if not edge_id:
                        continue
                    
                    # 获取需求流量
                    flow = edge_flows.get(edge_id, 0) * 360  # 转换为vph
                    if flow <= 0:
                        flow = self.demand_flow.get(edge_id, 500)
                    
                    # 计算饱和度 x = flow / capacity
                    capacity = 1800 * (g / cycle) if g > 0 else 1
                    x = flow / capacity if capacity > 0 else 0.5
                    x = min(x, 1.5)  # 限制最大值
                    saturation_degrees.append(x)
            
            # 计算饱和度的标准差（不用CV，避免分母问题）
            if len(saturation_degrees) > 1:
                x_std = np.std(saturation_degrees)
                # 标准差越大，说明配时越不均衡
                # 使用平方根来减缓惩罚增长速度
                prior_balance = np.sqrt(x_std) * 10  # 缩放因子从50降到10
        
        # ========== 组合协同先验 ==========
        total_prior = alpha_balance * prior_balance
        
        # 限制最大值（额外保护）
        total_prior = min(total_prior, 10.0)
        
        return total_prior


# ========== 兼容性别名 ==========
# 保持向后兼容，旧代码使用 MPCSignalOptimizer 仍然可以工作
MPCSignalOptimizer = TDMPCSignalOptimizer
