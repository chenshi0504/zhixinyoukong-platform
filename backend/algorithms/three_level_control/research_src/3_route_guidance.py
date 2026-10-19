"""
路径诱导模块（主模块）- 基于TD-MPC预测框架
包括CAV标记和动态重路由功能

模块结构：
- 3_route_guidance.py (本文件): 路径诱导主控制器（含预测功能）
- 3_1_Effort.py: 基于Effort的路径选择算法（Dijkstra最短路径）
- 3_2_DQN.py: 基于DQN的路径诱导（深度强化学习）
- 3_3_SSP.py: 基于SSP的路径诱导（时空叠加规划）

实验模式：
- 模式3.1: 纯路径诱导(Effort) = 3_route_guidance + 3_1_Effort
- 模式3.2: 纯路径诱导(DQN) = 3_route_guidance + 3_2_DQN
- 模式3.3: 纯路径诱导(SSP) = 3_route_guidance + 3_3_SSP

重路由机制说明：
1. 每50秒（决策时间点），系统更新全网路段的effort值
2. 使用3_1_Effort中的Dijkstra算法计算最优路径
3. 如果新路径比当前路径代价更低，车辆会切换到新路径
4. 只有路径实际发生改变的车辆会被记录到日志中

TD-MPC预测框架（新增）：
1. 借鉴TD-MPC思想：显式物理模型 + 预测推演
2. 预测未来1个决策周期（50秒）的路段状态
3. 物理推演：
   - 排队演化：基于当前排队和消散速率
   - 流量演化：基于信号配时变化（来自信号优化器的MPC预测）
   - BPR延误：基于预测流量而非当前流量
4. 无需神经网络训练，纯物理模型推演
5. 实现前瞻性路径规划，提高路径选择准确性
"""
import random
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import traci

# 导入路径选择计算模块
try:
    from importlib import import_module
    paths_choice_module = import_module('3_1_Effort')
    DynamicRouter = paths_choice_module.DynamicRouter
    get_vehicle_destination = paths_choice_module.get_vehicle_destination
    calculate_route_cost = paths_choice_module.calculate_route_cost
    EffortLogger = paths_choice_module.EffortLogger
except ImportError:
    DynamicRouter = None
    EffortLogger = None

# 导入其他路径诱导算法模块（可选）
try:
    dqn_module = import_module('3_2_DQN')
    RLRouter = dqn_module.RLRouter  # 3_2_DQN中的类名是RLRouter
except ImportError:
    RLRouter = None

try:
    ssp_module = import_module('3_3_SSP')
    SSPRouter = ssp_module.SSPRouter
except ImportError:
    SSPRouter = None


# 车辆类型定义
CAV_TYPE = "CAV"
HV_TYPE = "HV"

# 默认路由更新间隔（秒）
DEFAULT_UPDATE_INTERVAL = 30


def mark_cav_vehicles(input_rou, output_rou, cav_percent=0.8):
    """
    标记网联车辆（CAV）
    支持<vehicle>和<trip>两种格式
    
    Args:
        input_rou: 输入路径文件
        output_rou: 输出路径文件
        cav_percent: CAV渗透率（0-1）
    
    Returns:
        cav_ids: CAV车辆ID列表
    """
    cav_ids = []
    
    # 设置随机种子保证可重复性
    random.seed(42)
    
    with open(input_rou, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 检查是否需要添加CAV车辆类型定义
    has_cav_vtype = False
    has_hv_vtype = False
    for line in lines:
        if 'vType' in line and f'id="{CAV_TYPE}"' in line:
            has_cav_vtype = True
        if 'vType' in line and f'id="{HV_TYPE}"' in line:
            has_hv_vtype = True
    
    modified = []
    for line in lines:
        # 处理<vehicle>或<trip>元素
        if '<vehicle' in line or '<trip' in line:
            # 提取车辆ID
            vehicle_id = None
            if 'id="' in line:
                vehicle_id = line.split('id="')[1].split('"')[0]
            
            # 按概率标记为CAV
            if random.random() < cav_percent:
                # 替换或添加车辆类型为CAV
                if 'type="' in line:
                    # 替换现有类型
                    import re
                    line = re.sub(r'type="[^"]*"', f'type="{CAV_TYPE}"', line)
                else:
                    # 添加类型属性
                    if '<vehicle' in line:
                        line = line.replace('<vehicle ', f'<vehicle type="{CAV_TYPE}" ')
                    elif '<trip' in line:
                        line = line.replace('<trip ', f'<trip type="{CAV_TYPE}" ')
                if vehicle_id:
                    cav_ids.append(vehicle_id)
            else:
                # 标记为HV
                if 'type="' in line:
                    import re
                    line = re.sub(r'type="[^"]*"', f'type="{HV_TYPE}"', line)
                else:
                    if '<vehicle' in line:
                        line = line.replace('<vehicle ', f'<vehicle type="{HV_TYPE}" ')
                    elif '<trip' in line:
                        line = line.replace('<trip ', f'<trip type="{HV_TYPE}" ')
        
        # 在第一个vType后添加CAV和HV类型定义（如果不存在）
        if '<vType' in line and 'id="passenger"' in line:
            modified.append(line)
            if not has_cav_vtype:
                # CAV标记为红色，增强变道和右转能力
                modified.append('  <vType id="CAV" accel="2.6" decel="4.5" sigma="0.3" length="5.0" maxSpeed="70.0" '
                              'lcStrategic="100" lcCooperative="1.0" lcSpeedGain="2.0" lcKeepRight="0" '
                              'color="1,0,0"/>\n')
                has_cav_vtype = True
            if not has_hv_vtype:
                # HV保持默认黄色，也增强变道能力
                modified.append('  <vType id="HV" accel="2.6" decel="4.5" sigma="0.5" length="5.0" maxSpeed="70.0" '
                              'lcStrategic="100" lcCooperative="1.0" lcSpeedGain="1.5" '
                              'color="1,1,0"/>\n')
                has_hv_vtype = True
            continue
        
        modified.append(line)
    
    with open(output_rou, 'w', encoding='utf-8') as f:
        f.writelines(modified)
    
    return cav_ids


class RouteGuidance:
    """
    路径诱导器 - 基于实时路网状态的动态重路由
    
    重路由机制：
    1. 每50秒更新全网effort值
    2. 使用自定义Dijkstra算法基于effort计算最优路径
    3. 如果新路径比当前路径更优，则切换路径
    4. 记录所有路径实际发生改变的车辆信息
    
    effort计算机制（基于论文Theory_PIA-TuRBO_Coupled.md）：
    - 基础effort（本模块计算）：
      * 自由流时间 = (路段长度 - 排队车辆数 × 车辆长度 / 车道数) / 平均速度
      * 拥堵延迟时间 = 自由流时间 × 0.15 × (flow/capacity)^4  (BPR函数)
    - 信号延迟（3_1_Effort.py中计算，基于Webster模型）：
      * d_uniform = C(1-λ)² / [2(1-λx)]  均匀延迟
      * d_random = x² / [2q(1-x)]        随机延迟
      * d_overflow = α·max(0, x-1)^β     溢出延迟
    - 总effort = 自由流时间 + 拥堵延迟 + 信号延迟
    
    路段管控（可选功能，通过enable_edge_control控制）：
    - 启用时：检测拥堵路段并强制CAV绕行
    - 禁用时：仅基于effort值进行路由优化，不强制绕行
    """
    
    # effort计算参数
    VEHICLE_LENGTH = 5.0  # 车辆长度（米）
    LANE_COUNT = 2  # 默认车道数
    DELAY_PER_VEHICLE = 2.0  # 每辆排队车辆带来的延迟（秒）
    
    # 预测参数（TD-MPC思想）
    PREDICTION_HORIZON = 30  # 预测时域（秒），与决策周期一致
    FLOW_SENSITIVITY = 0.3   # 流量对信号变化的敏感系数
    QUEUE_DISCHARGE_RATE = 0.5  # 排队消散率（每秒）
    
    # 低流量优化参数（新增）
    MIN_CONGESTION_FACTOR = 0.05  # 最小拥堵因子，确保低流量下也有差异
    QUEUE_WEIGHT = 2.0  # 排队权重，放大排队影响
    DISTANCE_WEIGHT = 0.1  # 距离权重，鼓励选择更短路径
    
    # 重路由决策阈值
    # 低流量时设置阈值避免无效重路由导致绕远路
    # 高流量时不设阈值，充分发挥路径诱导效果
    REROUTE_THRESHOLD_MAP = {
        1: 0.05,  # 5%阈值，低流量适度重路由
        2: 0.03,  # 3%阈值，低流量适度重路由
        3: 0.02,  # 2%阈值
        4: 0.0,   # 无阈值
        5: 0.0,   # 无阈值
        6: 0.0,   # 无阈值
    }
    
    def __init__(self, update_interval=DEFAULT_UPDATE_INTERVAL, output_dir=None, 
                 flow_level=1, enable_edge_control=False, mode='2_0', pr=80,
                 enable_effort_log=True):
        """
        初始化路径诱导器
        
        Args:
            update_interval: 路径更新间隔（秒），默认30秒
            output_dir: 路由变更日志输出目录
            flow_level: 流量等级（1-6），用于确定管控阈值
            enable_edge_control: 是否启用路段管控（强制绕行），默认False
                - False: 模式2.0，纯路径诱导（仅基于effort优化）
                - True:  模式2.1，路径诱导+路段管控
            mode: 实验模式（用于日志文件命名）
            pr: 渗透率（用于日志文件命名）
            enable_effort_log: 是否启用effort日志记录
        """
        self.update_interval = update_interval
        self.edge_weights = {}
        self.last_update_step = 0
        
        # 路由变更记录
        self.route_changes = []  # 存储所有路由变更记录
        self.output_dir = output_dir
        
        # 统计信息
        self.total_reroute_attempts = 0
        self.total_route_changes = 0
        
        # 动态路由计算器
        self.router = None
        self.router_initialized = False
        
        # 历史旅行时间记录（用于计算平均值）
        self.travel_time_history = {}  # {edge_id: [travel_times]}
        self.sample_interval = 10  # 采样间隔（秒），每10秒采样一次
        self.max_samples = update_interval // self.sample_interval  # 最大样本数
        self.last_congestion_edges = []
        
        # 路段管控器（可选）
        self.enable_edge_control = enable_edge_control
        self.edge_controller = None
        self.flow_level = flow_level
        
        # 重路由决策阈值（根据流量等级动态调整）
        self.reroute_threshold = self.REROUTE_THRESHOLD_MAP.get(flow_level, 0.05)
        print(f"    重路由阈值: {self.reroute_threshold*100:.0f}% (Flow={flow_level})")
        
        # Effort日志记录器
        self.effort_logger = None
        self.enable_effort_log = enable_effort_log
        self.mode = mode
        self.pr = pr
        if enable_effort_log and EffortLogger is not None and output_dir:
            self.effort_logger = EffortLogger(output_dir, mode, flow_level, pr)
            print(f"    Effort日志: 已启用")
        
        if enable_edge_control and EdgeController is not None:
            self.edge_controller = EdgeController(flow_level=flow_level, enabled=True)
            print(f"    路段管控: 已启用")
        else:
            print(f"    路段管控: 已禁用（仅基于effort优化路由）")
    
    def collect_travel_time(self, sim_step):
        """
        收集当前时刻各路段的旅行时间
        每10秒采样一次，用于计算100秒内的平均旅行时间
        
        Args:
            sim_step: 当前仿真步数
        """
        # 只在采样时间点采集数据
        if sim_step % self.sample_interval != 0:
            return
        
        for edge in traci.edge.getIDList():
            if edge.startswith(':'):
                continue
            try:
                travel_time = traci.edge.getTraveltime(edge)
                if edge not in self.travel_time_history:
                    self.travel_time_history[edge] = []
                self.travel_time_history[edge].append(travel_time)
                
                # 只保留最近max_samples个样本（10个）
                if len(self.travel_time_history[edge]) > self.max_samples:
                    self.travel_time_history[edge] = self.travel_time_history[edge][-self.max_samples:]
            except traci.TraCIException:
                continue
    
    def _predict_future_flow(self, edge_id, current_flow, lane_count, halting_count):
        """
        预测未来流量（物理推演，借鉴TD-MPC思想）
        
        预测机制：
        1. 显式物理模型：基于排队演化和信号配时变化
        2. 无需神经网络训练
        3. 利用信号优化器提供的配时预测
        
        预测公式：
        f(t+Δt) = f(t) + Δf_signal + Δf_queue
        
        其中：
        - Δf_signal: 信号配时变化导致的流量变化
        - Δf_queue: 排队消散导致的流量变化
        
        Args:
            edge_id: 路段ID
            current_flow: 当前流量（车辆数）
            lane_count: 车道数
            halting_count: 排队车辆数
            
        Returns:
            predicted_flow: 预测的流量（车辆数）
        """
        # 基础预测：当前流量
        predicted_flow = current_flow
        
        # 1. 信号配时变化的影响（如果有预测配时信息）
        if hasattr(self, 'predicted_signal_changes') and edge_id in self.predicted_signal_changes:
            # 从信号优化器获取的配时变化预测
            signal_change_ratio = self.predicted_signal_changes[edge_id]
            # 流量对信号变化的响应：绿灯增加 -> 流量增加
            delta_flow_signal = current_flow * self.FLOW_SENSITIVITY * signal_change_ratio
            predicted_flow += delta_flow_signal
        
        # 2. 排队消散的影响
        if halting_count > 0:
            # 排队车辆会在未来逐渐消散，增加通过流量
            # 消散速度取决于车道数和饱和流率
            discharge_capacity = lane_count * 1800 / 3600  # 每秒可消散的车辆数
            potential_discharge = min(halting_count, discharge_capacity * self.PREDICTION_HORIZON)
            # 排队消散会增加流量（但不会超过容量限制）
            delta_flow_queue = potential_discharge * self.QUEUE_DISCHARGE_RATE
            predicted_flow += delta_flow_queue
        
        # 3. 容量约束
        max_capacity = lane_count * 1800 / 3600 * self.PREDICTION_HORIZON
        predicted_flow = min(predicted_flow, max_capacity)
        
        # 4. 非负约束
        predicted_flow = max(0, predicted_flow)
        
        return predicted_flow
    
    def update_predicted_signal_changes(self, signal_changes):
        """
        接收来自信号优化器的配时变化预测
        
        这是TD-MPC预测框架的关键输入：
        - 信号优化器通过MPC预测未来3步的配时
        - 路径诱导利用这些预测来推演流量变化
        - 实现前瞻性的路径规划
        
        Args:
            signal_changes: {edge_id: green_time_change_ratio}
                例如：{'edge1': 0.1} 表示绿灯时间增加10%
        """
        if not hasattr(self, 'predicted_signal_changes'):
            self.predicted_signal_changes = {}
        
        self.predicted_signal_changes = signal_changes.copy() if signal_changes else {}
        
        # 统计信息
        if signal_changes:
            positive_changes = sum(1 for v in signal_changes.values() if v > 0)
            negative_changes = sum(1 for v in signal_changes.values() if v < 0)
            print(f"    [预测] 接收信号配时变化预测: {positive_changes}↑ {negative_changes}↓")
    
    def update_network_weights(self):
        """
        更新全网路段effort值（= 自由流时间 + 拥堵延迟时间 + 信号延迟时间）
        
        effort计算策略（优化版，解决低流量问题）：
        1. 自由流时间 = 有效长度 / 平均速度
        2. 拥堵延迟时间 = 改进的BPR函数 + 排队惩罚
           - 低流量下：增加最小拥堵因子，确保路径差异
           - 排队惩罚：直接基于排队车辆数，不依赖流量比
        3. 信号延迟时间 = Webster延迟（来自信号管理器）
        4. 距离惩罚 = 路段长度 × 距离权重（鼓励选择更短路径）
        
        低流量优化：
        - 增加排队权重，放大排队影响
        - 添加最小拥堵因子，避免所有路径effort相同
        - 使用信号管理器计算信号延迟
        """
        congestion_edges = []
        for edge in traci.edge.getIDList():
            if edge.startswith(':'):
                continue
            try:
                # 获取路段基本信息
                lanes = traci.edge.getLaneNumber(edge)
                lane_count = lanes if lanes > 0 else self.LANE_COUNT
                first_lane = f"{edge}_0"
                edge_length = traci.lane.getLength(first_lane)
                
                # 获取排队车辆数
                halting_count = traci.edge.getLastStepHaltingNumber(edge)
                
                # 获取平均速度
                if edge in self.travel_time_history and self.travel_time_history[edge]:
                    avg_travel_time = sum(self.travel_time_history[edge]) / len(self.travel_time_history[edge])
                    avg_speed = edge_length / avg_travel_time if avg_travel_time > 0 else 13.89
                else:
                    avg_speed = traci.edge.getLastStepMeanSpeed(edge)
                    if avg_speed < 0.1:
                        avg_speed = 0.1
                
                # 1. 自由流时间
                queue_length = halting_count * self.VEHICLE_LENGTH / max(lane_count, self.LANE_COUNT)
                effective_length = max(edge_length - queue_length, edge_length * 0.1)
                free_flow_time = effective_length / avg_speed
                
                # 2. 拥堵延迟（改进版，解决低流量问题）
                vehicle_count = traci.edge.getLastStepVehicleNumber(edge)
                predicted_flow = self._predict_future_flow(edge, vehicle_count, lane_count, halting_count)
                
                # 容量计算
                capacity = lane_count * 1800 / 3600 * free_flow_time
                flow_ratio = predicted_flow / capacity if capacity > 0 else 0
                flow_ratio = min(flow_ratio, 1.5)
                
                # 改进的BPR延迟：添加最小拥堵因子
                alpha = 0.15
                beta = 4
                bpr_delay = free_flow_time * alpha * (flow_ratio ** beta)
                
                # 排队惩罚（直接基于排队数，不依赖流量比）
                # 这在低流量下也能有效区分路径
                queue_penalty = halting_count * self.QUEUE_WEIGHT
                
                # 最小拥堵因子：确保即使低流量也有差异
                min_congestion = free_flow_time * self.MIN_CONGESTION_FACTOR * (vehicle_count / max(lane_count, 1))
                
                congestion_delay = max(bpr_delay, min_congestion) + queue_penalty
                
                # 3. 信号延迟（从信号管理器获取）
                signal_delay = 0
                if self.router and self.router_initialized and self.router.signal_manager.initialized:
                    signal_delay = self.router.signal_manager.calculate_signal_delay(edge)
                elif hasattr(self, 'signal_delays') and edge in self.signal_delays:
                    signal_delay = self.signal_delays[edge]
                
                # 4. 距离惩罚（鼓励选择更短路径）
                distance_penalty = edge_length * self.DISTANCE_WEIGHT
                
                # 总effort
                total_effort = free_flow_time + congestion_delay + signal_delay + distance_penalty
                
                traci.edge.setEffort(edge, total_effort)
                self.edge_weights[edge] = total_effort
                if halting_count > 0 or flow_ratio >= 0.8 or congestion_delay >= max(1.0, free_flow_time * 0.2):
                    congestion_edges.append({
                        'edge': edge,
                        'halting': int(halting_count),
                        'vehicles': int(vehicle_count),
                        'flow_ratio': flow_ratio,
                        'delay': congestion_delay,
                        'effort': total_effort,
                    })
                
            except traci.TraCIException:
                continue
        self.last_congestion_edges = sorted(
            congestion_edges,
            key=lambda item: (item['halting'], item['delay'], item['vehicles'], item['effort']),
            reverse=True
        )
        
        # 清空历史记录
        self.travel_time_history = {}

    def _preview_route(self, route_edges, max_edges=4):
        if not route_edges:
            return "无"
        edges = list(route_edges)
        if len(edges) <= max_edges + 1:
            return " -> ".join(edges)
        return " -> ".join(edges[:max_edges]) + f" -> ... -> {edges[-1]}"

    def _format_congestion_edges(self, max_items=5):
        congestion_edges = getattr(self, 'last_congestion_edges', []) or []
        if not congestion_edges:
            return 0, "无明显排队/延误路段"
        items = []
        for item in congestion_edges[:max_items]:
            items.append(
                f"{item['edge']}(排队{item['halting']}辆, 延误{item['delay']:.1f}s, effort={item['effort']:.1f})"
            )
        suffix = f"...等{len(congestion_edges)}条" if len(congestion_edges) > max_items else ""
        return len(congestion_edges), ", ".join(items) + suffix

    def _format_control_edges(self, max_items=5):
        if not self.enable_edge_control:
            return "管控路段: 未启用"
        blocked_edges = self.get_blocked_edges()
        blocked_count = len(blocked_edges)
        if blocked_count == 0:
            return "管控路段: 0条"
        blocked_info = {}
        if self.edge_controller and hasattr(self.edge_controller, 'get_blocked_edges_info'):
            blocked_info = self.edge_controller.get_blocked_edges_info()
        if blocked_info:
            items = [f"{edge}(排队{halting}辆)" for edge, halting in list(blocked_info.items())[:max_items]]
        else:
            items = list(blocked_edges)[:max_items]
        suffix = f"...等{blocked_count}条" if blocked_count > max_items else ""
        threshold = self.edge_controller.queue_threshold if self.edge_controller and hasattr(self.edge_controller, 'queue_threshold') else "N/A"
        return f"管控路段: {blocked_count}条(阈值>={threshold}) " + ", ".join(items) + suffix

    def _print_decision_log(self, sim_step, reroute_count, change_count, decision_changes):
        congestion_count, congestion_text = self._format_congestion_edges()
        control_text = self._format_control_edges()
        print(
            f"[{sim_step}s] 路径诱导决策: 评估{reroute_count}辆CAV，{change_count}辆CAV更改路径；"
            f"拥堵候选路段{congestion_count}条；{control_text}",
            flush=True
        )
        print(f"    拥堵路段Top: {congestion_text}", flush=True)
        if decision_changes:
            for record in decision_changes[:5]:
                old_route = self._preview_route(record.get('old_route_edges', []))
                new_route = self._preview_route(record.get('new_route_edges', []))
                print(
                    f"    CAV改道: {record.get('vehicle_id')} | {record.get('switch_reason', '路径优化')} | "
                    f"cost {record.get('old_cost', 0):.1f}->{record.get('new_cost', 0):.1f} "
                    f"({record.get('cost_reduction', '--')}) | {old_route} => {new_route}",
                    flush=True
                )
            if len(decision_changes) > 5:
                print(f"    还有{len(decision_changes) - 5}辆CAV发生路径变化，详见 route_changes.xml", flush=True)
        else:
            print(
                f"    本轮无CAV路径变化：新路径收益未超过{self.reroute_threshold*100:.0f}%阈值，或路径未发生变化/不可连通。",
                flush=True
            )
    
    def get_blocked_edges(self):
        """
        获取当前管控路段（如果启用了路段管控）
        
        Returns:
            blocked_edges: 被管控的路段集合，如果未启用则返回空集合
        """
        if self.edge_controller:
            return self.edge_controller.get_blocked_edges()
        return set()
    
    def detect_controlled_edges(self):
        """
        检测管控路段（委托给EdgeController）
        
        Returns:
            blocked_edges: 被管控的路段集合
        """
        if self.edge_controller:
            return self.edge_controller.detect_controlled_edges()
        return set()
    
    def _validate_route(self, route):
        """
        验证路径的连通性
        
        Args:
            route: 路径（边列表）
        
        Returns:
            bool: 路径是否连通
        """
        if len(route) < 2:
            return True
        
        for i in range(len(route) - 1):
            from_edge = route[i]
            to_edge = route[i + 1]
            
            # 跳过内部边
            if from_edge.startswith(':') or to_edge.startswith(':'):
                continue
            
            # 检查是否有连接
            try:
                lane_id = f"{from_edge}_0"
                links = traci.lane.getLinks(lane_id)
                connected_edges = set()
                for link in links:
                    next_lane = link[0]
                    next_edge = next_lane.rsplit('_', 1)[0]
                    if not next_edge.startswith(':'):
                        connected_edges.add(next_edge)
                
                if to_edge not in connected_edges:
                    return False
            except:
                return False
        
        return True
    
    def init_router(self):
        """初始化动态路由计算器（在仿真开始后调用一次）"""
        if DynamicRouter is None:
            print("Warning: DynamicRouter not available, using SUMO rerouteEffort")
            return
        
        if not self.router_initialized:
            self.router = DynamicRouter()
            self.router.build_graph_from_sumo()
            self.router_initialized = True
            
            # 打印信号延迟功能状态
            if self.router.signal_manager.initialized:
                print(f"    Signal delay calculation: Enabled (Webster model)")
            else:
                print(f"    Signal delay calculation: Disabled")
            
            # 同时初始化EdgeController的路由器
            if self.edge_controller:
                self.edge_controller.init_router()
    
    def reroute_cavs(self, sim_step):
        """
        对所有CAV进行重新路由，并记录路径变更
        使用自定义Dijkstra算法计算最优路径
        
        路由决策逻辑：
        - 获取车辆当前路径（即上一次决策后的路径）
        - 基于最新的effort值计算新的最优路径
        - 若启用路段管控，还会避开管控路段
        - 若新路径代价比当前路径更低，则更新为新路径
        - 路径改变是相对于上一次决策的路径，而非初始路径
        
        Args:
            sim_step: 当前仿真时间步
            
        Returns:
            (reroute_count, change_count): 尝试重路由的车辆数, 实际改变路径的车辆数
        """
        reroute_count = 0
        change_count = 0
        decision_changes = []
        
        # 初始化路由器（首次调用时）
        if not self.router_initialized:
            self.init_router()
        
        # 获取管控路段（如果启用了路段管控）
        blocked_edges = self.get_blocked_edges()
        
        cav_ids = [veh for veh in traci.vehicle.getIDList()
                   if traci.vehicle.getTypeID(veh) == CAV_TYPE]
        
        for veh_id in cav_ids:
            try:
                # 获取车辆当前状态
                current_edge = traci.vehicle.getRoadID(veh_id)
                
                # 跳过在交叉口内部的车辆
                if current_edge.startswith(':'):
                    continue
                
                old_route = list(traci.vehicle.getRoute(veh_id))
                current_edge_index = traci.vehicle.getRouteIndex(veh_id)
                
                # 获取剩余路径（从当前位置到终点）
                remaining_old_route = old_route[current_edge_index:] if current_edge_index >= 0 else old_route
                
                if len(remaining_old_route) < 2:
                    # 路径太短，无需重路由
                    continue
                
                destination_edge = remaining_old_route[-1]
                
                # 如果当前路段就是目的地，无需重路由
                if current_edge == destination_edge:
                    continue
                
                # 检查当前剩余路径是否包含管控路段（仅在启用路段管控时）
                must_reroute = False
                blocked_in_route = []
                if self.enable_edge_control and blocked_edges:
                    blocked_in_route = [e for e in remaining_old_route[1:] if e in blocked_edges]
                    must_reroute = len(blocked_in_route) > 0
                
                # 计算当前路径的代价
                old_cost = calculate_route_cost(remaining_old_route, self.edge_weights)
                
                # 使用自定义路由器计算新路径
                # 如果启用路段管控，会避开管控路段；否则不考虑管控路段
                edges_to_avoid = blocked_edges if self.enable_edge_control else set()
                
                if self.router:
                    new_path, new_cost = self.router.find_best_route(
                        current_edge, destination_edge, self.edge_weights, edges_to_avoid
                    )
                else:
                    # 回退到SUMO的rerouteEffort
                    traci.vehicle.rerouteEffort(veh_id)
                    new_route = list(traci.vehicle.getRoute(veh_id))
                    new_edge_index = traci.vehicle.getRouteIndex(veh_id)
                    new_path = new_route[new_edge_index:] if new_edge_index >= 0 else new_route
                    new_cost = calculate_route_cost(new_path, self.edge_weights)
                
                reroute_count += 1
                
                # 判断是否需要切换路径
                should_switch = False
                switch_reason = ""
                
                if must_reroute and new_path:
                    # 强制绕行：当前路径包含管控路段，必须切换（仅在启用路段管控时）
                    new_blocked = [e for e in new_path[:-1] if e in blocked_edges and e != current_edge]
                    if len(new_blocked) == 0:
                        should_switch = True
                        switch_reason = f"强制绕行(避开{blocked_in_route})"
                    elif len(new_blocked) < len(blocked_in_route):
                        should_switch = True
                        switch_reason = f"部分绕行(减少{len(blocked_in_route)-len(new_blocked)}个管控路段)"
                elif new_path and new_path != remaining_old_route:
                    # 普通优化：只有当收益超过阈值时才切换路径
                    # 这避免了低流量下频繁无效切换导致的额外行驶距离
                    if new_cost < old_cost:
                        cost_reduction = (old_cost - new_cost) / old_cost if old_cost > 0 else 0
                        # 检查收益是否超过阈值
                        if cost_reduction >= self.reroute_threshold:
                            should_switch = True
                            switch_reason = f"代价优化({cost_reduction*100:.1f}%)"
                
                if should_switch:
                    # 检查新路径是否有效（至少2个不同的路段）
                    if not new_path or len(new_path) < 2:
                        continue
                    
                    # 检查新路径的起点和终点是否相同（无效路径）
                    if len(new_path) == 1 or new_path[0] == new_path[-1]:
                        continue
                    
                    # 验证新路径的连通性
                    full_new_route = old_route[:current_edge_index] + new_path
                    if not self._validate_route(full_new_route):
                        # 路径不连通，跳过此次重路由
                        continue
                    
                    # 设置新路径
                    try:
                        traci.vehicle.setRoute(veh_id, full_new_route)
                    except (traci.TraCIException, Exception) as e:
                        # 设置失败（路径无效或其他原因），静默跳过
                        continue
                    
                    change_count += 1
                    
                    # 记录路径变更
                    cost_reduction = (old_cost - new_cost) / old_cost if old_cost > 0 else 0
                    change_record = {
                        'time': sim_step,
                        'vehicle_id': veh_id,
                        'current_edge': current_edge,
                        'old_route': ' -> '.join(remaining_old_route),
                        'new_route': ' -> '.join(new_path),
                        'old_cost': old_cost,
                        'new_cost': new_cost,
                        'cost_reduction': f"{cost_reduction*100:.1f}%",
                        'switch_reason': switch_reason,
                        'old_route_edges': remaining_old_route,
                        'new_route_edges': new_path
                    }
                    self.route_changes.append(change_record)
                    decision_changes.append(change_record)
                
                # 设置变道模式
                traci.vehicle.setLaneChangeMode(veh_id, 1621)
                
            except traci.TraCIException:
                continue
            except Exception as e:
                continue
        
        self.total_reroute_attempts += reroute_count
        self.total_route_changes += change_count
        
        return reroute_count, change_count, decision_changes
    
    def should_update(self, sim_step):
        """
        判断是否需要更新路径
        
        时间安排：
        - 第一个30s周期结束后开始路径诱导
        - 之后每update_interval秒更新一次
        
        Args:
            sim_step: 当前仿真步数
        
        Returns:
            bool: 是否需要更新
        """
        if sim_step <= 0:
            return False
        if sim_step == self.last_update_step:
            return False
        if sim_step % self.update_interval == 0:
            self.last_update_step = sim_step
            return True
        return False
    
    def check_and_reroute_urgent(self, sim_step):
        """
        实时检查即将进入管控路段的CAV，强制绕行
        每个仿真步调用，确保CAV不会进入管控路段
        仅在启用路段管控时生效
        
        Args:
            sim_step: 当前仿真步数
            
        Returns:
            urgent_reroute_count: 紧急绕行的车辆数
        """
        # 如果未启用路段管控，直接返回
        if not self.enable_edge_control:
            return 0
        
        # 委托给EdgeController处理
        if self.edge_controller:
            return self.edge_controller.check_urgent_reroute(sim_step, self.edge_weights)
        
        return 0
    
    def update(self, sim_step):
        """
        执行路径更新
        
        决策流程：
        1. 更新全网effort值（自由流时间 + 拥堵延迟）
        2. 如果启用路段管控，检测管控路段
        3. 重新规划CAV路由（基于effort，可选避开管控路段）
        4. 若新路径优于上一次决策的路径，则更新路径
        
        Args:
            sim_step: 当前仿真步数
        
        Returns:
            change_count: 实际改变路径的车辆数量
        """
        # 每10秒检查紧急绕行（仅在启用路段管控时执行）
        if self.enable_edge_control and sim_step > 0 and sim_step % 10 == 0:
            urgent_count = self.check_and_reroute_urgent(sim_step)
            if urgent_count:
                print(f"[{sim_step}s] 路径诱导紧急绕行: {urgent_count}辆CAV因即将进入管控路段调整路径", flush=True)
        
        if self.should_update(sim_step):
            # Step 1: 更新全网effort值
            self.update_network_weights()
            
            # Step 2: 检测管控路段（如果启用）
            if self.enable_edge_control:
                self.detect_controlled_edges()
            
            # Step 3 & 4: 重新规划CAV路由
            reroute_count, change_count, decision_changes = self.reroute_cavs(sim_step)
            
            # Step 5: 记录effort日志（如果启用）
            if self.effort_logger and self.router and self.router.signal_manager:
                self.effort_logger.log_effort_update(
                    sim_step, self.edge_weights, 
                    self.router.signal_manager, self.router
                )
            
            self._print_decision_log(sim_step, reroute_count, change_count, decision_changes)
            
            return change_count
        return 0
    
    def save_route_changes(self, mode, flow, pr):
        """
        保存路由变更记录到XML文件
        
        新目录结构：直接保存到实验配置目录
        - output/{config_name}/route_changes.xml
        
        Args:
            mode: 实验模式
            flow: 流量等级
            pr: CAV渗透率
        """
        if not self.output_dir:
            return None
        
        # 新目录结构：直接保存到output_dir（实验配置目录）
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # 创建XML结构
        root = ET.Element("route_changes")
        root.set("mode", str(mode))
        root.set("flow", str(flow))
        root.set("pr", str(pr))
        root.set("update_interval", str(self.update_interval))
        root.set("total_reroute_attempts", str(self.total_reroute_attempts))
        root.set("total_route_changes", str(self.total_route_changes))
        root.set("generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # 添加每条变更记录
        for record in self.route_changes:
            change_elem = ET.SubElement(root, "change")
            change_elem.set("time", str(record['time']))
            change_elem.set("vehicle", record['vehicle_id'])
            change_elem.set("current_edge", record['current_edge'])
            change_elem.set("old_route", record['old_route'])
            change_elem.set("new_route", record['new_route'])
        
        # 添加统计摘要
        summary = ET.SubElement(root, "summary")
        summary.set("total_changes", str(len(self.route_changes)))
        
        # 按时间点统计
        time_stats = {}
        for record in self.route_changes:
            t = record['time']
            time_stats[t] = time_stats.get(t, 0) + 1
        
        for t, count in sorted(time_stats.items()):
            time_elem = ET.SubElement(summary, "time_point")
            time_elem.set("time", str(t))
            time_elem.set("changes", str(count))
        
        # 格式化并保存
        self._indent_xml(root)
        tree = ET.ElementTree(root)
        
        # 新目录结构：直接保存到实验配置目录
        output_file = os.path.join(self.output_dir, "route_changes.xml")
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        
        print(f"\n路由变更记录已保存: {output_file}")
        print(f"  总重路由尝试: {self.total_reroute_attempts}")
        print(f"  实际路径改变: {self.total_route_changes}")
        
        # 同时保存effort日志
        if self.effort_logger:
            self.effort_logger.save_to_xml()
        
        return output_file
    
    def _indent_xml(self, elem, level=0):
        """格式化XML输出"""
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i
    
    def get_statistics(self):
        """获取路由变更统计信息"""
        return {
            'total_reroute_attempts': self.total_reroute_attempts,
            'total_route_changes': self.total_route_changes,
            'change_rate': self.total_route_changes / self.total_reroute_attempts if self.total_reroute_attempts > 0 else 0,
            'changes_by_time': self._get_changes_by_time()
        }
    
    def _get_changes_by_time(self):
        """按时间点统计路径变更"""
        time_stats = {}
        for record in self.route_changes:
            t = record['time']
            time_stats[t] = time_stats.get(t, 0) + 1
        return time_stats
    
    # ========== 信号优化协同接口 ==========
    
    def get_path_flow_data(self):
        """
        获取路径流量数据（供信号优化器使用）
        
        基于路由变更记录和当前CAV路径，估计各路径的流量
        
        Returns:
            path_flows: 路径流量字典 {path_id: flow_vph}
            path_edges: 路径边序列 {path_id: [edge_ids]}
        """
        path_flows = {}
        path_edges = {}
        
        try:
            # 获取所有CAV的当前路径
            cav_ids = [veh for veh in traci.vehicle.getIDList()
                       if traci.vehicle.getTypeID(veh) == CAV_TYPE]
            
            # 统计每条路径的车辆数
            path_counts = {}  # {path_tuple: count}
            path_edge_map = {}  # {path_tuple: [edges]}
            
            for veh_id in cav_ids:
                try:
                    route = tuple(traci.vehicle.getRoute(veh_id))
                    if route:
                        if route not in path_counts:
                            path_counts[route] = 0
                            path_edge_map[route] = list(route)
                        path_counts[route] += 1
                except:
                    continue
            
            # 转换为流量（假设仿真时间为1小时，简化处理）
            # 实际流量 = 车辆数 × 3600 / 仿真时长
            sim_time = traci.simulation.getTime()
            if sim_time > 0:
                flow_factor = 3600 / sim_time
            else:
                flow_factor = 1
            
            for i, (path_tuple, count) in enumerate(path_counts.items()):
                path_id = f"path_{i}"
                path_flows[path_id] = count * flow_factor
                path_edges[path_id] = list(path_tuple)
            
            return path_flows, path_edges
            
        except Exception as e:
            print(f"  Warning: Failed to get path flow data: {e}")
            return {}, {}

    
    # ==================== 交叉耦合接口方法 ====================
    
    def update_signal_delays(self, predicted_delays, timestamp=None):
        """
        接收来自信号优化器的延误预测（交叉耦合：信号→路径）
        
        这是双向耦合机制的正向传递：
        信号优化器 → Webster延误预测 → 路径诱导 → effort计算 → 路径选择
        
        Args:
            predicted_delays: {edge_id: delay_seconds}
            timestamp: 预测时间戳（仿真时间）
        """
        if not hasattr(self, 'signal_delays'):
            self.signal_delays = {}
        
        self.signal_delays.update(predicted_delays)
        
        # 获取当前仿真时间作为时间戳
        if timestamp is None:
            try:
                timestamp = traci.simulation.getTime()
            except:
                timestamp = 0
        
        # 将信号延误传递给路由器的信号管理器
        if self.router and hasattr(self.router, 'signal_manager'):
            signal_manager = self.router.signal_manager
            if hasattr(signal_manager, 'update_predicted_delays'):
                signal_manager.update_predicted_delays(predicted_delays, timestamp)
        
        # 统计信息
        valid_delays = [d for d in predicted_delays.values() if d > 0]
        avg_delay = sum(valid_delays) / len(valid_delays) if valid_delays else 0
        print(f"  [路径诱导] 接收信号延误预测: {len(valid_delays)}/{len(predicted_delays)} 路段, "
              f"平均延误 {avg_delay:.1f}s")
    
    def get_path_flows_feedback(self):
        """
        获取路径流量反馈信息（交叉耦合：路径→信号）
        
        Returns:
            dict: 包含路径流量、路段流量、路径-路段关系的反馈数据
        """
        feedback = {
            'path_flows': {},
            'edge_flows': {},
            'path_edges': {}
        }
        
        # 使用已有的 get_path_flow_data 方法
        path_flows, path_edges = self.get_path_flow_data()
        feedback['path_flows'] = path_flows
        feedback['path_edges'] = path_edges
        
        # 获取路段流量
        try:
            for edge_id in traci.edge.getIDList():
                if edge_id.startswith(':'):
                    continue
                flow = traci.edge.getLastStepVehicleNumber(edge_id)
                feedback['edge_flows'][edge_id] = flow
        except Exception as e:
            print(f"  Warning: Failed to get edge flows: {e}")
        
        return feedback
    
    def update_predicted_flow_changes(self, predicted_changes):
        """
        接收来自协调层的预测流量变化（交叉耦合：协调层→路径诱导）
        
        协调层基于信号配时变化预测路径诱导会如何响应（流量重分布）。
        路径诱导可以利用这些预测来：
        1. 提前调整effort权重，引导车辆绕行
        2. 预判拥堵路段，提前规划替代路径
        3. 平滑流量变化，避免剧烈波动
        
        预测公式（来自协调层）：
        Δf_e = f_e · (exp(-θ·Δd_e) - 1)
        
        Args:
            predicted_changes: {edge_id: predicted_flow_change} 预测的流量变化
        """
        if not hasattr(self, 'predicted_flow_changes'):
            self.predicted_flow_changes = {}
        
        self.predicted_flow_changes = predicted_changes.copy() if predicted_changes else {}
        
        # 统计信息
        if predicted_changes:
            positive_changes = sum(1 for v in predicted_changes.values() if v > 0)
            negative_changes = sum(1 for v in predicted_changes.values() if v < 0)
            total_change = sum(predicted_changes.values())
            
            print(f"    [协调层→路径] 接收预测流量变化: "
                  f"{positive_changes}↑ {negative_changes}↓, 净变化 {total_change:+.1f}")
        
        # 利用预测调整effort权重（提前引导）
        self._adjust_effort_from_prediction(predicted_changes)
    
    def _adjust_effort_from_prediction(self, predicted_changes):
        """
        根据预测的流量变化调整effort权重
        
        如果协调层预测某路段流量将增加（因为延误减少），
        可以适当提高该路段的effort，避免过度集中。
        
        如果预测某路段流量将减少（因为延误增加），
        可以适当降低替代路段的effort，引导车辆绕行。
        
        Args:
            predicted_changes: 预测的流量变化
        """
        if not predicted_changes or not hasattr(self, 'edge_weights'):
            return
        
        # 预测调整系数（较小，避免过度干预）
        adjustment_factor = 0.1
        
        for edge_id, flow_change in predicted_changes.items():
            if edge_id not in self.edge_weights:
                continue
            
            current_effort = self.edge_weights[edge_id]
            
            if flow_change > 1:  # 预测流量增加
                # 适当增加effort，避免过度集中
                boost = 1.0 + adjustment_factor * min(flow_change / 10, 0.3)
                self.edge_weights[edge_id] = current_effort * boost
            elif flow_change < -1:  # 预测流量减少
                # 该路段延误增加导致车辆绕行，不需要额外调整
                # 但可以记录用于后续分析
                pass
