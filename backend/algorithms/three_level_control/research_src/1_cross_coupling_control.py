"""
Cross-Coupling Control Module (交叉耦合控制模块)

双层协同优化控制器，协调：
- 模块2: 信号优化 (MPC-TuRBO)
- 模块3: 路径诱导 (CAV动态重路由)

核心机制：预测式双向耦合
==========================
信号层和路径层的交互核心是：考虑对方改变后的影响并进行预测

1. 信号→路径预测（正向预测）：
   - 输入：当前信号配时方案 g 和延误预测 d
   - 预测：路径诱导响应后的流量重分布 f'(g)
   - 方法：基于MSA（Method of Successive Averages）增量模型
   - 公式：f_e^{new} = f_e + λ·(f_e^{target} - f_e)
   - 其中 f_e^{target} = F_total × (1/d_e) / Σ(1/d_s)

2. 路径→信号预测（反向预测）：
   - 输入：当前路径流量分布 f
   - 预测：信号优化响应后的配时调整 g'(f)
   - 方法：基于Webster最优周期公式，预测信号配时变化
   - 公式：g'_i(f) = g_i · (q_i(f) / q_i^old)^α

3. 协调策略：
   - 根据预测结果调整耦合强度
   - 高预测偏差时增强协调频率

时序安排（避免冲突）：
- 信号优化：600s开始，每300s优化一次（600, 900, 1200, ...）
- 路径诱导：610s开始，每50s更新一次（610, 660, 710, ...）
- 协调控制：620s开始，每60s协调一次（620, 680, 740, ...）
"""

import traci
import numpy as np
from abc import ABC, abstractmethod


class CrossCouplingController:
    """
    双层协同控制器
    
    协调信号优化（上层）和路径诱导（下层）的交互
    实现信息双向传递和协调策略
    """
    
    # 预热时间（与信号优化一致）
    WARMUP_TIME = 620  # 比信号优化晚20s开始，确保信号已完成首次优化
    
    def __init__(self, signal_optimizer=None, route_guidance=None, coupling_mode='dynamic'):
        """
        初始化协同控制器
        
        Args:
            signal_optimizer: 信号优化模块实例 (MPCSignalOptimizer)
            route_guidance: 路径诱导模块实例 (RouteGuidance)
            coupling_mode: 耦合模式
                - 'dynamic': 动态耦合（默认，权重随拥堵变化）
                - 'fixed_high': 固定高耦合 (0.7/0.3)
                - 'fixed_medium': 固定中耦合 (0.5/0.5)
                - 'fixed_low': 固定低耦合 (0.4/0.6)
                - 'independent': 独立运行（无耦合，仅信息传递）
        """
        self.signal_optimizer = signal_optimizer
        self.route_guidance = route_guidance
        self.enabled = False
        self.update_interval = 60  # 协调更新间隔（秒）
        self.last_update_time = 0
        
        # 耦合模式
        self.coupling_mode = coupling_mode
        
        # 耦合参数（根据模式初始化）
        self._init_coupling_params(coupling_mode)
        
        # 状态变量
        self.signal_state = {}   # 当前信号配时状态
        self.route_state = {}    # 当前路径分布状态
        self.traffic_state = {}  # 当前交通状态
        
        # 协调记录
        self.coordination_history = []
        
        # 拥堵检测阈值
        self.congestion_threshold = 0.5  # 占有率阈值
        self.queue_threshold = 10        # 排队阈值（辆）
        
        # ========== 预测机制参数 ==========
        self.prediction_enabled = True
        self.msa_step_size = 0.4         # MSA步长λ（0.3-0.5）
        self.msa_iteration = 1           # MSA迭代计数（用于递减步长）
        self.webster_alpha = 0.5         # Webster调整指数α
        self.prediction_horizon = 300    # 预测时域（秒）
        
        # 预测历史（用于验证和自适应调整）
        self.signal_predictions = []     # 信号→路径预测记录
        self.route_predictions = []      # 路径→信号预测记录
        self.prediction_errors = []      # 预测误差记录
        
        # 上一时刻状态（用于计算变化量）
        self.last_edge_flows = {}
        self.last_green_times = {}
        self.last_edge_delays = {}
    
    def _init_coupling_params(self, mode):
        """
        根据耦合模式初始化参数
        
        Args:
            mode: 耦合模式
        """
        if mode == 'fixed_high':
            self.coupling_strength = 0.8
            self.signal_weight = 0.7
            self.route_weight = 0.3
        elif mode == 'fixed_medium':
            self.coupling_strength = 0.5
            self.signal_weight = 0.5
            self.route_weight = 0.5
        elif mode == 'fixed_low':
            self.coupling_strength = 0.3
            self.signal_weight = 0.4
            self.route_weight = 0.6
        elif mode == 'independent':
            # 独立模式：权重为0，不进行协调调整
            self.coupling_strength = 0.0
            self.signal_weight = 0.0
            self.route_weight = 0.0
        else:  # 'dynamic' 或其他
            self.coupling_strength = 0.5
            self.signal_weight = 0.6
            self.route_weight = 0.4
        
    def initialize(self):
        """初始化控制器"""
        self.enabled = True
        mode_desc = {
            'dynamic': '动态耦合',
            'fixed_high': '固定高耦合(信号优先)',
            'fixed_medium': '固定中耦合(均衡)',
            'fixed_low': '固定低耦合(路径优先)',
            'independent': '独立运行(无耦合)'
        }
        print("  Cross-coupling controller initialized")
        print(f"    Mode: {self.coupling_mode} ({mode_desc.get(self.coupling_mode, '未知')})")
        print(f"    Coordination interval: {self.update_interval}s")
        if self.coupling_mode != 'independent':
            print(f"    Initial weights: signal={self.signal_weight:.0%}, route={self.route_weight:.0%}")
        
    def set_signal_optimizer(self, signal_optimizer):
        """设置信号优化模块"""
        self.signal_optimizer = signal_optimizer
        
    def set_route_guidance(self, route_guidance):
        """设置路径诱导模块"""
        self.route_guidance = route_guidance

    def collect_traffic_state(self):
        """
        采集当前交通状态
        
        Returns:
            dict: 交通状态（排队、速度、占有率等）
        """
        traffic_state = {
            'edge_queues': {},      # 路段排队
            'edge_speeds': {},      # 路段速度
            'edge_densities': {},   # 路段占有率
            'edge_flows': {},       # 路段流量
            'total_queue': 0,
            'avg_speed': 0,
            'avg_density': 0,
            'congested_edges': []   # 拥堵路段列表
        }
        
        try:
            edge_count = 0
            total_speed = 0
            total_density = 0
            
            for edge_id in traci.edge.getIDList():
                if edge_id.startswith(':'):
                    continue
                
                queue = traci.edge.getLastStepHaltingNumber(edge_id)
                speed = traci.edge.getLastStepMeanSpeed(edge_id)
                density = traci.edge.getLastStepOccupancy(edge_id)
                flow = traci.edge.getLastStepVehicleNumber(edge_id)
                
                traffic_state['edge_queues'][edge_id] = queue
                traffic_state['edge_speeds'][edge_id] = speed
                traffic_state['edge_densities'][edge_id] = density
                traffic_state['edge_flows'][edge_id] = flow
                traffic_state['total_queue'] += queue
                
                total_speed += speed
                total_density += density
                edge_count += 1
                
                # 检测拥堵路段
                if density > self.congestion_threshold or queue > self.queue_threshold:
                    traffic_state['congested_edges'].append(edge_id)
            
            if edge_count > 0:
                traffic_state['avg_speed'] = total_speed / edge_count
                traffic_state['avg_density'] = total_density / edge_count
                
        except Exception as e:
            print(f"  Warning: Error collecting traffic state: {e}")
            
        self.traffic_state = traffic_state
        return traffic_state
    
    def get_signal_feedback(self):
        """
        获取信号配时反馈（传递给路径诱导）
        
        Returns:
            dict: 信号配时信息
        """
        signal_feedback = {
            'green_times': {},       # 各相位绿灯时间
            'cycle_times': {},       # 各交叉口周期
            'current_phases': {},    # 当前相位
            'next_switch_times': {}, # 下次切换时间
            'phase_queues': {}       # 各相位排队
        }
        
        try:
            # 从信号优化器获取配时信息
            if self.signal_optimizer and hasattr(self.signal_optimizer, 'intersections'):
                for tl_id, info in self.signal_optimizer.intersections.items():
                    signal_feedback['cycle_times'][tl_id] = info.get('cycle', 90)
                    
                    # 获取当前配时
                    if self.signal_optimizer.current_timing is not None:
                        begin, end = info['begin'], info['end']
                        signal_feedback['green_times'][tl_id] = list(
                            self.signal_optimizer.current_timing[begin:end+1]
                        )
            
            # 从SUMO获取实时相位信息
            for tl_id in traci.trafficlight.getIDList():
                signal_feedback['current_phases'][tl_id] = traci.trafficlight.getPhase(tl_id)
                signal_feedback['next_switch_times'][tl_id] = traci.trafficlight.getNextSwitch(tl_id)
                
        except Exception as e:
            print(f"  Warning: Error getting signal feedback: {e}")
            
        self.signal_state = signal_feedback
        return signal_feedback
    
    def get_route_feedback(self):
        """
        获取路径分布反馈（传递给信号优化）
        
        Returns:
            dict: 路径流量分布信息
        """
        route_feedback = {
            'edge_flows': {},        # 路段流量
            'cav_counts': {},        # CAV数量
            'cav_ratios': {},        # CAV比例
            'path_flows': {},        # 路径流量
            'reroute_count': 0       # 重路由次数
        }
        
        try:
            # 从路径诱导器获取统计信息
            if self.route_guidance:
                stats = self.route_guidance.get_statistics()
                route_feedback['reroute_count'] = stats.get('total_route_changes', 0)
                
                # 获取路径流量数据（包括路径-路段关系）
                if hasattr(self.route_guidance, 'get_path_flow_data'):
                    path_flows, path_edges = self.route_guidance.get_path_flow_data()
                    route_feedback['path_flows'] = path_flows
                    route_feedback['path_edges'] = path_edges  # 添加路径-路段关系
            
            # 从SUMO获取实时流量
            for edge_id in traci.edge.getIDList():
                if edge_id.startswith(':'):
                    continue
                    
                total_veh = traci.edge.getLastStepVehicleNumber(edge_id)
                route_feedback['edge_flows'][edge_id] = total_veh
                
                # 统计CAV数量
                cav_count = 0
                for veh_id in traci.edge.getLastStepVehicleIDs(edge_id):
                    if traci.vehicle.getTypeID(veh_id) == 'CAV':
                        cav_count += 1
                
                route_feedback['cav_counts'][edge_id] = cav_count
                route_feedback['cav_ratios'][edge_id] = cav_count / total_veh if total_veh > 0 else 0
                
        except Exception as e:
            print(f"  Warning: Error getting route feedback: {e}")
            
        self.route_state = route_feedback
        return route_feedback

    # ==================== 预测机制核心方法 ====================
    
    def predict_route_response(self, new_delays, current_flows):
        """
        预测路径诱导对信号变化的响应（正向预测：信号→路径）
        
        当信号配时改变导致延误变化时，预测CAV会如何重新选择路径。
        基于MSA（Method of Successive Averages）增量模型：
        
        f_e^{new} = f_e + λ · (f_e^{target} - f_e)
        
        其中：
        - λ: MSA步长（0.3-0.5，或1/k递减）
        - f_e^{target}: 基于延误的目标流量分布
        
        目标流量基于延误倒数分配：
        f_e^{target} = F_total · (1/d_e) / Σ(1/d_s)
        
        物理意义：流量逐步向"延误更低的路段"转移，而非一步到位
        
        Args:
            new_delays: 新的路段延误预测 {edge_id: delay}
            current_flows: 当前路段流量 {edge_id: flow}
            
        Returns:
            dict: 预测的流量变化 {edge_id: predicted_flow_change}
        """
        if not self.prediction_enabled:
            return {}
        
        predicted_changes = {}
        lambda_msa = self.msa_step_size
        
        # 计算总流量（用于归一化）
        total_flow = sum(current_flows.values()) if current_flows else 0
        if total_flow <= 0:
            return {}
        
        # 计算延误倒数之和（用于目标分布）
        delay_inv_sum = 0
        valid_edges = []
        for edge_id, delay in new_delays.items():
            if delay > 0.1 and edge_id in current_flows:
                delay_inv_sum += 1.0 / delay
                valid_edges.append(edge_id)
        
        if delay_inv_sum <= 0 or not valid_edges:
            return {}
        
        # 计算每条路段的目标流量和流量变化
        for edge_id in valid_edges:
            current_flow = current_flows.get(edge_id, 0)
            new_delay = new_delays.get(edge_id, 1)
            
            if current_flow <= 0 or new_delay <= 0.1:
                continue
            
            # 目标流量：基于延误倒数的比例分配
            # f_target = F_total × (1/d_e) / Σ(1/d_s)
            target_flow = total_flow * (1.0 / new_delay) / delay_inv_sum
            
            # MSA增量：f_new = f + λ·(f_target - f)
            # 流量变化：Δf = λ·(f_target - f)
            flow_change = lambda_msa * (target_flow - current_flow)
            
            # 限制变化幅度（每次最多变化30%）
            max_change = 0.3 * current_flow
            flow_change = np.clip(flow_change, -max_change, max_change)
            
            if abs(flow_change) > 0.1:
                predicted_changes[edge_id] = flow_change
        
        # 更新MSA迭代计数（可选：使用递减步长 λ = 1/k）
        self.msa_iteration += 1
        
        # 记录预测
        self.signal_predictions.append({
            'time': self.last_update_time,
            'delay_changes': {e: new_delays.get(e, 0) - self.last_edge_delays.get(e, 0) 
                             for e in new_delays},
            'predicted_flow_changes': predicted_changes.copy(),
            'msa_step': lambda_msa
        })
        
        return predicted_changes
    
    def predict_signal_response(self, new_flows, current_green_times):
        """
        预测信号优化对路径变化的响应（反向预测：路径→信号）
        
        当路径流量分布改变时，预测信号优化器会如何调整配时。
        基于Webster最优绿灯时间公式的简化版：
        
        g'_i = g_i · (q_i^new / q_i^old)^α
        
        其中：
        - α: 调整指数（0.5表示平方根关系）
        - q_i: 相位i的到达流量
        
        物理含义：流量增加的相位需要更多绿灯时间
        
        Args:
            new_flows: 新的路段流量 {edge_id: flow}
            current_green_times: 当前绿灯时间 {tl_id: [green_times]}
            
        Returns:
            dict: 预测的绿灯时间变化 {tl_id: {phase: delta_green}}
        """
        if not self.prediction_enabled or not self.signal_optimizer:
            return {}
        
        predicted_changes = {}
        alpha = self.webster_alpha
        
        if not hasattr(self.signal_optimizer, 'intersections'):
            return {}
        
        for tl_id, info in self.signal_optimizer.intersections.items():
            incoming_edges = info.get('incoming_edges', [])
            cycle = info.get('cycle', 90)
            begin, end = info.get('begin', 0), info.get('end', 0)
            
            tl_changes = {}
            
            for p, edge_id in enumerate(incoming_edges):
                if edge_id not in new_flows:
                    continue
                
                new_flow = new_flows.get(edge_id, 0)
                old_flow = self.last_edge_flows.get(edge_id, new_flow)
                
                if old_flow <= 0:
                    old_flow = 1  # 避免除零
                
                # 流量变化比例
                flow_ratio = new_flow / old_flow
                
                if abs(flow_ratio - 1.0) < 0.05:  # 变化太小，忽略
                    continue
                
                # 获取当前绿灯时间
                current_green = 30  # 默认值
                if tl_id in current_green_times and p < len(current_green_times[tl_id]):
                    current_green = current_green_times[tl_id][p]
                
                # Webster公式预测新绿灯时间
                predicted_green = current_green * (flow_ratio ** alpha)
                
                # 限制在合理范围内
                predicted_green = np.clip(predicted_green, 15, 60)
                
                delta_green = predicted_green - current_green
                
                # 限制单次变化幅度
                delta_green = np.clip(delta_green, -10, 10)
                
                if abs(delta_green) > 1:
                    tl_changes[p] = delta_green
            
            if tl_changes:
                predicted_changes[tl_id] = tl_changes
        
        # 记录预测
        self.route_predictions.append({
            'time': self.last_update_time,
            'flow_changes': {e: new_flows.get(e, 0) - self.last_edge_flows.get(e, 0) 
                            for e in new_flows if e in self.last_edge_flows},
            'predicted_green_changes': predicted_changes.copy()
        })
        
        return predicted_changes
    
    def validate_predictions(self, actual_flows, actual_green_times):
        """
        验证预测准确性并自适应调整参数
        
        比较上一轮的预测与实际观测，计算预测误差，
        并根据误差自适应调整MSA步长参数。
        
        Args:
            actual_flows: 实际观测的流量
            actual_green_times: 实际观测的绿灯时间
        """
        if len(self.signal_predictions) < 2:
            return
        
        # 获取上一轮预测
        last_prediction = self.signal_predictions[-2] if len(self.signal_predictions) >= 2 else None
        
        if not last_prediction:
            return
        
        # 计算流量预测误差
        flow_errors = []
        predicted_changes = last_prediction.get('predicted_flow_changes', {})
        
        for edge_id, predicted_change in predicted_changes.items():
            if edge_id in actual_flows and edge_id in self.last_edge_flows:
                actual_change = actual_flows[edge_id] - self.last_edge_flows.get(edge_id, 0)
                if abs(predicted_change) > 0.1:
                    error = abs(actual_change - predicted_change) / max(abs(predicted_change), 1)
                    flow_errors.append(error)
        
        if flow_errors:
            avg_error = np.mean(flow_errors)
            self.prediction_errors.append({
                'time': self.last_update_time,
                'type': 'flow',
                'avg_error': avg_error
            })
            
            # 自适应调整MSA步长参数
            if avg_error > 0.5:  # 误差过大，减小步长（更保守）
                self.msa_step_size *= 0.9
            elif avg_error < 0.2:  # 误差较小，可以增大步长（更激进）
                self.msa_step_size *= 1.05
            
            # 限制步长在合理范围 [0.2, 0.6]
            self.msa_step_size = np.clip(self.msa_step_size, 0.2, 0.6)
    
    def compute_predicted_equilibrium(self, signal_feedback, route_feedback):
        """
        计算预测均衡状态
        
        通过迭代预测，估计信号和路径达到均衡时的状态。
        这是双向耦合的核心：考虑对方响应后的最终状态。
        
        迭代过程：
        1. 信号变化 → 预测路径响应 → 新流量分布
        2. 新流量分布 → 预测信号响应 → 新配时方案
        3. 重复直到收敛或达到最大迭代次数
        
        Args:
            signal_feedback: 当前信号状态
            route_feedback: 当前路径状态
            
        Returns:
            dict: 预测的均衡状态
        """
        max_iterations = 3
        convergence_threshold = 0.05
        
        # 初始状态
        current_flows = route_feedback.get('edge_flows', {}).copy()
        current_green_times = signal_feedback.get('green_times', {}).copy()
        
        # 计算当前延误
        current_delays = {}
        if self.signal_optimizer and hasattr(self.signal_optimizer, 'compute_edge_delays'):
            current_delays = self.signal_optimizer.compute_edge_delays()
        
        equilibrium_flows = current_flows.copy()
        equilibrium_green = current_green_times.copy()
        
        for iteration in range(max_iterations):
            # Step 1: 预测路径响应
            flow_changes = self.predict_route_response(current_delays, equilibrium_flows)
            
            # 更新流量
            new_flows = equilibrium_flows.copy()
            for edge_id, change in flow_changes.items():
                if edge_id in new_flows:
                    new_flows[edge_id] = max(0, new_flows[edge_id] + change)
            
            # Step 2: 预测信号响应
            green_changes = self.predict_signal_response(new_flows, equilibrium_green)
            
            # 更新绿灯时间
            new_green = equilibrium_green.copy()
            for tl_id, phase_changes in green_changes.items():
                if tl_id in new_green:
                    for p, delta in phase_changes.items():
                        if p < len(new_green[tl_id]):
                            new_green[tl_id][p] = np.clip(
                                new_green[tl_id][p] + delta, 15, 60
                            )
            
            # 检查收敛
            flow_diff = sum(abs(new_flows.get(e, 0) - equilibrium_flows.get(e, 0)) 
                          for e in set(new_flows) | set(equilibrium_flows))
            
            if flow_diff < convergence_threshold * sum(equilibrium_flows.values()):
                break
            
            equilibrium_flows = new_flows
            equilibrium_green = new_green
        
        return {
            'equilibrium_flows': equilibrium_flows,
            'equilibrium_green': equilibrium_green,
            'iterations': iteration + 1,
            'converged': iteration < max_iterations - 1
        }
    
    # ==================== 原有方法（增强版） ====================
    
    def pass_signal_to_route(self, signal_feedback):
        """
        将信号配时信息传递给路径诱导模块（正向耦合：信号→路径）
        
        增强功能：
        1. 传递当前配时信息
        2. 计算并传递Webster延误预测
        3. 【新增】预测路径诱导的响应，提前通知预期流量变化
        
        Args:
            signal_feedback: 信号配时反馈
        """
        if not self.route_guidance:
            return
        
        # 1. 更新信号管理器的配时信息
        if hasattr(self.route_guidance, 'router') and self.route_guidance.router:
            router = self.route_guidance.router
            if hasattr(router, 'signal_manager'):
                signal_manager = router.signal_manager
                for tl_id, green_times in signal_feedback.get('green_times', {}).items():
                    cycle = signal_feedback.get('cycle_times', {}).get(tl_id, 90)
                    if hasattr(signal_manager, 'update_timing'):
                        signal_manager.update_timing(tl_id, green_times, cycle)
        
        # 2. 计算并传递Webster延误预测
        predicted_delays = {}
        if self.signal_optimizer and hasattr(self.signal_optimizer, 'compute_edge_delays'):
            predicted_delays = self.signal_optimizer.compute_edge_delays()
            
            # 将预测延误传递给路径诱导
            if hasattr(self.route_guidance, 'update_signal_delays'):
                self.route_guidance.update_signal_delays(predicted_delays, self.last_update_time)
        
        # 3. 【新增】预测路径诱导的响应
        current_flows = self.traffic_state.get('edge_flows', {})
        predicted_flow_changes = self.predict_route_response(predicted_delays, current_flows)
        
        # 将预测的流量变化传递给路径诱导（用于提前规划）
        if hasattr(self.route_guidance, 'update_predicted_flow_changes'):
            self.route_guidance.update_predicted_flow_changes(predicted_flow_changes)
        
        # 记录传递的信息
        self.signal_to_route_data = {
            'predicted_delays': predicted_delays,
            'predicted_flow_changes': predicted_flow_changes,
            'timestamp': self.last_update_time
        }
        
        # 更新历史记录
        self.last_edge_delays = predicted_delays.copy()
    
    def pass_route_to_signal(self, route_feedback):
        """
        将路径流量信息传递给信号优化模块（反向耦合：路径→信号）
        
        增强功能：
        1. 传递实时流量（用于更新需求预测）
        2. 传递路径流量分布（用于协同先验函数）
        3. 传递路径-交叉口关联信息（用于流量映射）
        4. 【新增】预测信号优化的响应，提前通知预期配时变化
        
        Args:
            route_feedback: 路径流量反馈
        """
        if not self.signal_optimizer:
            return
        
        edge_flows = route_feedback.get('edge_flows', {})
        
        # 1. 更新信号优化器的需求流量（用于Webster模型）
        if hasattr(self.signal_optimizer, 'demand_flow'):
            for edge_id, flow in edge_flows.items():
                # 转换为小时流量
                flow_vph = flow * 3600 / 10  # 假设10秒采样间隔
                self.signal_optimizer.demand_flow[edge_id] = max(flow_vph, 100)
        
        # 2. 传递路径流量数据（用于协同先验函数）
        if hasattr(self.signal_optimizer, 'path_flow_data'):
            self.signal_optimizer.path_flow_data = route_feedback.get('path_flows', {})
        
        # 3. 构建并传递路径-交叉口关联矩阵（用于流量映射公式(2)）
        path_intersection_matrix = self._build_path_intersection_matrix(route_feedback)
        if hasattr(self.signal_optimizer, 'path_intersection_matrix'):
            self.signal_optimizer.path_intersection_matrix = path_intersection_matrix
        
        # 4. 更新协同先验的路径分量
        if hasattr(self.signal_optimizer, 'update_cooperative_prior'):
            self.signal_optimizer.update_cooperative_prior(
                path_flows=route_feedback.get('path_flows', {}),
                path_edges=route_feedback.get('path_edges', {}),
                edge_flows=edge_flows
            )
        
        # 5. 【新增】预测信号优化的响应
        current_green_times = self.signal_state.get('green_times', {})
        predicted_green_changes = self.predict_signal_response(edge_flows, current_green_times)
        
        # 将预测的配时变化传递给信号优化器（用于提前规划）
        if hasattr(self.signal_optimizer, 'update_predicted_green_changes'):
            self.signal_optimizer.update_predicted_green_changes(predicted_green_changes)
        
        # 记录传递的数据
        self.route_to_signal_data = {
            'path_flows': route_feedback.get('path_flows', {}),
            'edge_flows': edge_flows,
            'predicted_green_changes': predicted_green_changes,
            'timestamp': self.last_update_time
        }
        
        # 更新历史记录
        self.last_edge_flows = edge_flows.copy()
        self.last_green_times = current_green_times.copy()
    
    def _build_path_intersection_matrix(self, route_feedback):
        """
        构建路径-交叉口关联矩阵 δ_ir
        
        对应论文公式(2): q_i = Σ f_r · δ_ir
        
        Args:
            route_feedback: 路径流量反馈
            
        Returns:
            dict: {(intersection_id, path_id): 1 or 0}
        """
        matrix = {}
        
        if not self.signal_optimizer or not hasattr(self.signal_optimizer, 'intersections'):
            return matrix
        
        intersections = set(self.signal_optimizer.intersections.keys())
        path_edges = route_feedback.get('path_edges', {})
        
        for path_id, edges in path_edges.items():
            for edge_id in edges:
                # 检查该路段是否进入某个信号交叉口
                for tl_id, info in self.signal_optimizer.intersections.items():
                    incoming_edges = info.get('incoming_edges', [])
                    if edge_id in incoming_edges:
                        matrix[(tl_id, path_id)] = 1
        
        return matrix
    
    def adjust_coupling_strength(self, traffic_state):
        """
        根据交通状态动态调整耦合强度
        
        仅在 'dynamic' 模式下生效，其他模式保持固定值
        
        Args:
            traffic_state: 当前交通状态
        """
        # 非动态模式不调整
        if self.coupling_mode != 'dynamic':
            return
        
        avg_density = traffic_state.get('avg_density', 0)
        congested_count = len(traffic_state.get('congested_edges', []))
        total_queue = traffic_state.get('total_queue', 0)
        
        # 记录旧值用于比较
        old_coupling = self.coupling_strength
        old_level = self._get_congestion_level_name(old_coupling)
        
        # 基于多个指标计算拥堵程度
        congestion_level = 0
        level_details = []
        
        # 占有率指标
        if avg_density > 0.7:
            congestion_level += 0.4
            level_details.append(f"密度高({avg_density:.1%})")
        elif avg_density > 0.5:
            congestion_level += 0.2
            level_details.append(f"密度中({avg_density:.1%})")
        elif avg_density > 0.3:
            congestion_level += 0.1
            level_details.append(f"密度低({avg_density:.1%})")
        
        # 拥堵路段数量指标
        if congested_count > 20:
            congestion_level += 0.3
            level_details.append(f"拥堵路段多({congested_count}条)")
        elif congested_count > 10:
            congestion_level += 0.2
            level_details.append(f"拥堵路段中({congested_count}条)")
        elif congested_count > 5:
            congestion_level += 0.1
            level_details.append(f"拥堵路段少({congested_count}条)")
        
        # 总排队指标
        if total_queue > 200:
            congestion_level += 0.3
            level_details.append(f"排队严重({total_queue:.0f}辆)")
        elif total_queue > 100:
            congestion_level += 0.2
            level_details.append(f"排队中等({total_queue:.0f}辆)")
        elif total_queue > 50:
            congestion_level += 0.1
            level_details.append(f"排队轻微({total_queue:.0f}辆)")
        
        # 更新耦合强度（0.3 - 0.9）
        self.coupling_strength = min(0.9, max(0.3, 0.3 + congestion_level))
        new_level = self._get_congestion_level_name(self.coupling_strength)
        
        # 根据耦合强度调整权重
        if self.coupling_strength > 0.7:
            # 高拥堵：信号优化更重要
            self.signal_weight = 0.7
            self.route_weight = 0.3
            strategy = "信号优先"
        elif self.coupling_strength > 0.5:
            # 中等拥堵：均衡
            self.signal_weight = 0.5
            self.route_weight = 0.5
            strategy = "均衡协调"
        else:
            # 低拥堵：路径诱导更灵活
            self.signal_weight = 0.4
            self.route_weight = 0.6
            strategy = "路径灵活"
        
        # 输出耦合强度变化信息
        change = self.coupling_strength - old_coupling
        if abs(change) > 0.05:
            # 有显著变化时输出详细信息
            change_symbol = "↑" if change > 0 else "↓"
            print(f"    [耦合调整] {old_coupling:.2f}({old_level}) → {self.coupling_strength:.2f}({new_level}) {change_symbol}")
            if level_details:
                print(f"               原因: {', '.join(level_details)}")
            print(f"               策略: {strategy} (信号{self.signal_weight:.0%}/路径{self.route_weight:.0%})")
    
    def _get_congestion_level_name(self, coupling):
        """根据耦合强度返回拥堵等级名称"""
        if coupling > 0.7:
            return "高拥堵"
        elif coupling > 0.5:
            return "中拥堵"
        else:
            return "低拥堵"
    
    def apply_coordination_strategy(self, traffic_state, signal_feedback, route_feedback):
        """
        应用协调策略 - 使用实际存在的属性让权重真正起作用
        
        权重的实际作用机制（基于现有属性）：
        1. 信号权重(w_s)：控制信号优化对路径诱导的影响强度
           - 调整 edge_weights（拥堵路段effort放大）
           - 调整 reroute_threshold（重路由敏感度）
        2. 路径权重(w_r)：控制路径诱导对信号优化的影响强度
           - 调整 demand_flow（基于路径流量更新需求）
           - 调整 cooperative_prior_data（协同先验权重）
        
        具体体现：
        - 信号优先(70/30)：路径诱导更多地适应信号配时，effort调整更激进
        - 路径优先(40/60)：信号优化更多地考虑路径流量变化
        - 均衡(50/50)：双方平等协调
        - 独立模式：不进行任何协调调整，两模块独立运行
        
        Args:
            traffic_state: 交通状态
            signal_feedback: 信号反馈
            route_feedback: 路径反馈
        """
        # 独立模式：仅记录，不进行协调调整
        if self.coupling_mode == 'independent':
            self.coordination_history.append({
                'time': self.last_update_time,
                'coupling_strength': 0.0,
                'signal_weight': 0.0,
                'route_weight': 0.0,
                'congested_count': len(traffic_state.get('congested_edges', [])),
                'total_queue': traffic_state.get('total_queue', 0),
                'avg_density': traffic_state.get('avg_density', 0),
                'mode': 'independent'
            })
            return
        
        congested_edges = traffic_state.get('congested_edges', [])
        edge_flows = route_feedback.get('edge_flows', {})
        
        # ========== 1. 基于信号权重调整路径诱导 ==========
        # 信号权重越高，路径诱导越需要配合信号
        if self.route_guidance:
            # 1.1 调整拥堵路段的effort值（使用实际存在的edge_weights）
            if hasattr(self.route_guidance, 'edge_weights'):
                for edge_id in congested_edges:
                    if edge_id in self.route_guidance.edge_weights:
                        current_effort = self.route_guidance.edge_weights[edge_id]
                        
                        # 基于信号权重的调整因子：信号权重越高，调整越大
                        # w_s=0.7时，factor=1.35; w_s=0.4时，factor=1.2
                        boost_factor = 1.0 + self.signal_weight * 0.5
                        
                        # 直接修改edge_weights（这个属性确实存在）
                        self.route_guidance.edge_weights[edge_id] = current_effort * boost_factor
            
            # 1.2 调整重路由阈值（使用实际存在的reroute_threshold）
            if hasattr(self.route_guidance, 'reroute_threshold'):
                # 信号权重越高，重路由阈值越低（更容易触发重路由以配合信号）
                # 基础阈值 * (1 - 信号权重 * 0.5)
                # w_s=0.7时，阈值降低35%; w_s=0.4时，阈值降低20%
                base_threshold = self.route_guidance.REROUTE_THRESHOLD_MAP.get(
                    self.route_guidance.flow_level, 0.05
                )
                adjusted_threshold = base_threshold * (1.0 - self.signal_weight * 0.5)
                self.route_guidance.reroute_threshold = max(0.0, adjusted_threshold)
            
            # 1.3 调整信号延误的影响权重（通过signal_delays的缩放）
            if hasattr(self.route_guidance, 'signal_delays') and self.route_guidance.signal_delays:
                # 信号权重越高，信号延误对路径选择的影响越大
                scale_factor = 0.5 + self.signal_weight  # w_s=0.7时，factor=1.2
                for edge_id in self.route_guidance.signal_delays:
                    self.route_guidance.signal_delays[edge_id] *= scale_factor
        
        # ========== 2. 基于路径权重调整信号优化 ==========
        # 路径权重越高，信号优化越需要考虑路径流量变化
        if self.signal_optimizer:
            # 2.1 基于路径流量更新需求流量（使用实际存在的demand_flow）
            if hasattr(self.signal_optimizer, 'demand_flow'):
                for edge_id, flow in edge_flows.items():
                    if edge_id in self.signal_optimizer.demand_flow:
                        current_demand = self.signal_optimizer.demand_flow[edge_id]
                        # 路径权重越高，实际流量对需求预测的影响越大
                        # 混合公式：new_demand = (1-w_r)*current + w_r*actual
                        actual_flow_vph = flow * 3600 / 10  # 转换为小时流量
                        blended_demand = (1 - self.route_weight) * current_demand + \
                                        self.route_weight * actual_flow_vph
                        self.signal_optimizer.demand_flow[edge_id] = max(blended_demand, 100)
            
            # 2.2 更新协同先验数据的权重（使用实际存在的cooperative_prior_data）
            if hasattr(self.signal_optimizer, 'cooperative_prior_data'):
                # 路径权重越高，协同先验的影响越大
                self.signal_optimizer.cooperative_prior_data['route_weight'] = self.route_weight
                self.signal_optimizer.cooperative_prior_data['signal_weight'] = self.signal_weight
                
                # 更新拥堵路段信息，供协同先验使用
                self.signal_optimizer.cooperative_prior_data['congested_edges'] = congested_edges
                self.signal_optimizer.cooperative_prior_data['edge_flows'] = edge_flows
            
            # 2.3 基于拥堵状态调整相位的需求流量（通过edge_phase映射）
            if hasattr(self.signal_optimizer, 'edge_phase') and hasattr(self.signal_optimizer, 'demand_flow'):
                for edge_id in congested_edges:
                    if edge_id in self.signal_optimizer.edge_phase:
                        # 拥堵路段的需求流量增加，促使信号给予更多绿灯
                        # 增加幅度与路径权重成正比
                        if edge_id in self.signal_optimizer.demand_flow:
                            boost = 1.0 + self.route_weight * 0.3  # w_r=0.6时，增加18%
                            self.signal_optimizer.demand_flow[edge_id] *= boost
        
        # ========== 3. 基于权重的预测步长调整 ==========
        # MSA步长也受权重影响：信号权重高时，路径响应预测更保守
        if self.prediction_enabled:
            # 信号权重越高，MSA步长越小（路径变化更渐进）
            self.msa_step_size = 0.3 + 0.3 * self.route_weight
            self.msa_step_size = np.clip(self.msa_step_size, 0.2, 0.6)
        
        # 记录协调动作
        coordination_record = {
            'time': self.last_update_time,
            'coupling_strength': self.coupling_strength,
            'signal_weight': self.signal_weight,
            'route_weight': self.route_weight,
            'congested_count': len(congested_edges),
            'total_queue': traffic_state.get('total_queue', 0),
            'avg_density': traffic_state.get('avg_density', 0),
            'actions': []
        }
        
        # 记录实际执行的协调动作
        if self.route_guidance and hasattr(self.route_guidance, 'edge_weights'):
            coordination_record['actions'].append(f'edge_weights调整({len(congested_edges)}条拥堵路段)')
        if self.route_guidance and hasattr(self.route_guidance, 'reroute_threshold'):
            coordination_record['actions'].append(f'reroute_threshold={self.route_guidance.reroute_threshold:.3f}')
        if self.signal_optimizer and hasattr(self.signal_optimizer, 'demand_flow'):
            coordination_record['actions'].append(f'demand_flow更新({len(edge_flows)}条路段)')
        
        self.coordination_history.append(coordination_record)

    def coordinate(self, current_time):
        """
        执行一次协调（在协调时间点调用）
        
        协调流程（增强版，含预测机制）：
        1. 采集交通状态
        2. 获取信号和路径反馈
        3. 验证上一轮预测准确性
        4. 计算预测均衡状态
        5. 双向传递信息（含预测）
        6. 调整耦合强度
        7. 应用协调策略
        
        Args:
            current_time: 当前仿真时间
        """
        # Step 1: 采集交通状态
        traffic_state = self.collect_traffic_state()
        
        # Step 2: 获取双向反馈
        signal_feedback = self.get_signal_feedback()
        route_feedback = self.get_route_feedback()
        
        # Step 3: 验证上一轮预测准确性（自适应调整参数）
        if self.prediction_enabled:
            actual_flows = traffic_state.get('edge_flows', {})
            actual_green = signal_feedback.get('green_times', {})
            self.validate_predictions(actual_flows, actual_green)
        
        # Step 4: 计算预测均衡状态
        equilibrium = None
        if self.prediction_enabled:
            equilibrium = self.compute_predicted_equilibrium(signal_feedback, route_feedback)
        
        # Step 5: 双向信息传递（含预测）
        self.pass_signal_to_route(signal_feedback)
        self.pass_route_to_signal(route_feedback)
        
        # Step 6: 动态调整耦合强度
        self.adjust_coupling_strength(traffic_state)
        
        # Step 7: 应用协调策略
        self.apply_coordination_strategy(traffic_state, signal_feedback, route_feedback)
        
        # 输出协调信息
        congested_count = len(traffic_state.get('congested_edges', []))
        prediction_info = ""
        if equilibrium:
            prediction_info = f", pred_iter={equilibrium.get('iterations', 0)}"
            if equilibrium.get('converged'):
                prediction_info += "(收敛)"
        
        print(f"  [Coordination] coupling={self.coupling_strength:.2f}, "
              f"congested={congested_count}, queue={traffic_state.get('total_queue', 0):.0f}"
              f", λ_msa={self.msa_step_size:.3f}{prediction_info}")
    
    def step(self, current_time):
        """
        仿真步进（每步调用）
        
        检查是否到达协调时间点，如果是则执行协调
        
        Args:
            current_time: 当前仿真时间
        """
        if not self.enabled:
            return
        
        # 预热期不协调
        if current_time < self.WARMUP_TIME:
            return
        
        # 检查是否到达协调时间点
        time_since_warmup = current_time - self.WARMUP_TIME
        if time_since_warmup > 0 and time_since_warmup % self.update_interval == 0:
            if current_time != self.last_update_time:
                self.last_update_time = current_time
                self.coordinate(current_time)
    
    def get_coupling_state(self):
        """
        获取当前耦合状态（用于监控）
        
        Returns:
            dict: 耦合状态信息
        """
        return {
            'enabled': self.enabled,
            'coupling_strength': self.coupling_strength,
            'signal_weight': self.signal_weight,
            'route_weight': self.route_weight,
            'last_update_time': self.last_update_time,
            'coordination_count': len(self.coordination_history),
            'traffic_summary': {
                'total_queue': self.traffic_state.get('total_queue', 0),
                'avg_speed': self.traffic_state.get('avg_speed', 0),
                'avg_density': self.traffic_state.get('avg_density', 0),
                'congested_count': len(self.traffic_state.get('congested_edges', []))
            }
        }
    
    def get_coordination_summary(self):
        """
        获取协调历史摘要
        
        Returns:
            dict: 协调历史统计
        """
        if not self.coordination_history:
            return {'count': 0}
        
        coupling_values = [h['coupling_strength'] for h in self.coordination_history]
        queue_values = [h['total_queue'] for h in self.coordination_history]
        
        return {
            'count': len(self.coordination_history),
            'avg_coupling': np.mean(coupling_values),
            'max_coupling': max(coupling_values),
            'avg_queue': np.mean(queue_values),
            'max_queue': max(queue_values)
        }


class CoordinationStrategy(ABC):
    """
    协调策略抽象基类
    
    实现此类以创建自定义协调策略
    """
    
    @abstractmethod
    def compute_coordination(self, traffic_state, signal_state, route_state):
        """
        计算协调动作
        
        Args:
            traffic_state: 交通状态
            signal_state: 信号状态
            route_state: 路径状态
            
        Returns:
            dict: 协调动作
        """
        pass


class DensityBasedStrategy(CoordinationStrategy):
    """
    基于密度的协调策略
    
    根据路段密度调整信号和路径的协调
    """
    
    def __init__(self, density_threshold=0.5):
        self.density_threshold = density_threshold
    
    def compute_coordination(self, traffic_state, signal_state, route_state):
        """基于密度的协调"""
        actions = {
            'signal_adjustment': {},
            'route_adjustment': {},
            'priority_edges': []
        }
        
        # 识别高密度路段
        for edge_id, density in traffic_state.get('edge_densities', {}).items():
            if density > self.density_threshold:
                actions['priority_edges'].append(edge_id)
                
                # 路径调整：增加effort权重
                actions['route_adjustment'][edge_id] = {
                    'action': 'increase_effort',
                    'factor': 1.5 + density
                }
        
        return actions


class QueueBasedStrategy(CoordinationStrategy):
    """
    基于排队的协调策略
    
    根据排队长度调整信号和路径的协调
    """
    
    def __init__(self, queue_threshold=10):
        self.queue_threshold = queue_threshold
    
    def compute_coordination(self, traffic_state, signal_state, route_state):
        """基于排队的协调"""
        actions = {
            'signal_adjustment': {},
            'route_adjustment': {},
            'critical_edges': []
        }
        
        # 识别高排队路段
        for edge_id, queue in traffic_state.get('edge_queues', {}).items():
            if queue > self.queue_threshold:
                actions['critical_edges'].append(edge_id)
                
                # 信号调整建议：增加绿灯时间
                actions['signal_adjustment'][edge_id] = {
                    'action': 'extend_green',
                    'amount': min(queue * 2, 15)  # 最多延长15秒
                }
                
                # 路径调整：强烈建议绕行
                actions['route_adjustment'][edge_id] = {
                    'action': 'avoid',
                    'weight_multiplier': 2.0 + queue / 10
                }
        
        return actions
