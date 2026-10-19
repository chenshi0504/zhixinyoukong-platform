"""
Effort-based路径选择计算模块 (3_1)
用于在仿真过程中基于实时effort计算最优路径

本模块是路径诱导的核心算法模块，被3_route_guidance.py调用
这是我们论文的主要方法 (route=1)

核心功能：
1. 构建路网图（从SUMO路网）
2. 基于实时effort计算Dijkstra最短路径
3. 为CAV选择最优路径
4. 整合信号灯配时信息，计算信号延迟

effort计算公式（基于论文Theory_PIA-TuRBO_Coupled.md）：
    总effort = 自由流时间 + 拥堵延迟 + 信号延迟
    
信号延迟基于Webster模型：
    d_signal = d_uniform + d_random + d_overflow

使用方式：
- 模式2 (route=1): 纯路径诱导
- 模式3: 双层协调（与信号优化配合）
- 模式4 (cc=1): 交叉耦合协调（我们的方法）
"""
import heapq
from collections import defaultdict
import traci


class SignalInfoManager:
    """
    信号灯信息管理器
    负责建立边与信号灯的映射关系，并基于Webster模型计算信号延迟
    
    映射关系：
    - edge_to_tls: 边 -> 下游信号灯ID
    - edge_to_link_index: 边 -> 对应的link索引（用于确定相位）
    - tls_timing: 信号灯 -> 配时信息（周期、相位等）
    - edge_green_time: 边 -> 绿灯时间（预计算）
    """
    
    # Webster模型参数
    SATURATION_FLOW = 1800  # 饱和流率 (veh/h/lane)
    MAX_SATURATION_DEGREE = 0.95  # 最大饱和度限制
    OVERFLOW_ALPHA = 0.5  # 溢出延迟系数
    OVERFLOW_BETA = 2.0   # 溢出延迟指数
    
    def __init__(self):
        # 边 -> 下游信号灯ID的映射
        self.edge_to_tls = {}  # {edge_id: tls_id}
        
        # 边 -> 对应link索引的映射（用于确定相位）
        self.edge_to_link_index = {}  # {edge_id: [link_indices]}
        
        # 信号灯 -> 配时信息的映射
        self.tls_timing = {}  # {tls_id: {'cycle': C, 'phases': [...]}}
        
        # 边 -> 绿灯时间的映射（预计算）
        self.edge_green_time = {}  # {edge_id: green_time}
        
        # 边 -> 车道数缓存
        self.edge_lane_count = {}  # {edge_id: lane_count}
        
        # ========== 交叉耦合：来自信号优化器的预测延误 ==========
        self.predicted_delays = {}  # {edge_id: delay_seconds}
        self.use_predicted_delays = True  # 是否优先使用预测延误
        self.predicted_delays_timestamp = 0  # 预测延误的时间戳
        
        self.initialized = False
    
    def build_signal_mapping(self):
        """
        从SUMO网络构建边与信号灯的映射关系
        在仿真开始后调用一次
        
        通过TraCI获取：
        1. 所有信号灯ID
        2. 每个信号灯控制的连接（controlled links）
        3. 信号配时程序（phases, durations）
        """
        print("  Building signal-edge mapping...")
        
        # 获取所有信号灯
        tls_ids = traci.trafficlight.getIDList()
        print(f"    Found {len(tls_ids)} traffic lights")
        
        for tls_id in tls_ids:
            try:
                # 获取该信号灯控制的所有连接
                # 返回格式: [[(incoming_lane, outgoing_lane, via_lane), ...], ...]
                # 外层列表索引对应相位状态字符串中的位置
                controlled_links = traci.trafficlight.getControlledLinks(tls_id)
                
                # 获取信号配时程序
                programs = traci.trafficlight.getAllProgramLogics(tls_id)
                if programs:
                    program = programs[0]  # 使用第一个（当前）程序
                    
                    # 计算周期长度
                    cycle_length = sum(phase.duration for phase in program.phases)
                    
                    self.tls_timing[tls_id] = {
                        'cycle': cycle_length,
                        'phases': program.phases,
                        'phase_count': len(program.phases)
                    }
                
                # 建立边到信号灯的映射
                for link_idx, link_group in enumerate(controlled_links):
                    for link in link_group:
                        if len(link) >= 1:
                            incoming_lane = link[0]
                            # 从lane ID提取edge ID (格式: "edge_id_lane_index")
                            incoming_edge = incoming_lane.rsplit('_', 1)[0]
                            
                            # 跳过内部边
                            if not incoming_edge.startswith(':'):
                                self.edge_to_tls[incoming_edge] = tls_id
                                
                                if incoming_edge not in self.edge_to_link_index:
                                    self.edge_to_link_index[incoming_edge] = []
                                if link_idx not in self.edge_to_link_index[incoming_edge]:
                                    self.edge_to_link_index[incoming_edge].append(link_idx)
            
            except traci.TraCIException as e:
                print(f"    Warning: Failed to get info for TLS {tls_id}: {e}")
                continue
        
        # 预计算每条边的绿灯时间
        self._calculate_edge_green_times()
        
        # 缓存车道数
        self._cache_lane_counts()
        
        self.initialized = True
        print(f"    Signal mapping built: {len(self.edge_to_tls)} edges connected to traffic lights")
        print(f"    Average cycle length: {self._get_avg_cycle():.1f}s")
    
    def _calculate_edge_green_times(self):
        """
        预计算每条边对应的绿灯时间
        通过分析相位状态字符串确定
        
        相位状态字符串说明：
        - 'G': 绿灯（受保护）
        - 'g': 绿灯（需让行）
        - 'r': 红灯
        - 'y': 黄灯
        """
        for edge_id, tls_id in self.edge_to_tls.items():
            if tls_id not in self.tls_timing:
                continue
            
            timing = self.tls_timing[tls_id]
            link_indices = self.edge_to_link_index.get(edge_id, [])
            
            if not link_indices:
                continue
            
            # 计算该边在所有相位中的总绿灯时间
            total_green = 0
            for phase in timing['phases']:
                state = phase.state  # 如 "GGrrGGrr"
                
                # 检查该边对应的任一link是否为绿灯
                is_green = False
                for link_idx in link_indices:
                    if link_idx < len(state) and state[link_idx] in ['G', 'g']:
                        is_green = True
                        break
                
                if is_green:
                    total_green += phase.duration
            
            self.edge_green_time[edge_id] = total_green
    
    def _cache_lane_counts(self):
        """缓存边的车道数"""
        for edge_id in self.edge_to_tls.keys():
            try:
                self.edge_lane_count[edge_id] = traci.edge.getLaneNumber(edge_id)
            except:
                self.edge_lane_count[edge_id] = 2  # 默认值
    
    def _get_avg_cycle(self):
        """获取平均周期长度"""
        if not self.tls_timing:
            return 0
        cycles = [t['cycle'] for t in self.tls_timing.values()]
        return sum(cycles) / len(cycles)
    
    def get_lane_count(self, edge_id):
        """获取边的车道数"""
        if edge_id in self.edge_lane_count:
            return self.edge_lane_count[edge_id]
        try:
            count = traci.edge.getLaneNumber(edge_id)
            self.edge_lane_count[edge_id] = count
            return count
        except:
            return 2  # 默认值
    
    # ==================== 交叉耦合接口方法 ====================
    
    def update_timing(self, tls_id, green_times, cycle):
        """
        更新信号灯配时信息（交叉耦合：信号→路径）
        
        接收来自信号优化器的最新配时方案，更新本地缓存的绿灯时间。
        这使得路径诱导能够使用最新的信号配时来计算更准确的延误。
        
        Args:
            tls_id: 信号灯ID
            green_times: 各相位绿灯时间列表
            cycle: 周期长度
        """
        if tls_id not in self.tls_timing:
            return
        
        # 更新周期
        self.tls_timing[tls_id]['cycle'] = cycle
        
        # 更新各路段的绿灯时间
        # 需要根据相位-路段映射关系更新
        for edge_id, link_indices in self.edge_to_link_index.items():
            if self.edge_to_tls.get(edge_id) != tls_id:
                continue
            
            # 计算该路段的总绿灯时间
            # 简化处理：假设green_times按相位顺序排列
            total_green = 0
            for link_idx in link_indices:
                # 将link_idx映射到相位索引（简化：假设每2个link对应一个相位）
                phase_idx = link_idx // 2
                if phase_idx < len(green_times):
                    total_green = max(total_green, green_times[phase_idx])
            
            if total_green > 0:
                self.edge_green_time[edge_id] = total_green
    
    def update_predicted_delays(self, predicted_delays, timestamp=None):
        """
        接收来自信号优化器的延误预测（交叉耦合：信号→路径）
        
        信号优化器基于当前配时方案和Webster模型预测各路段的信号延误，
        路径诱导模块使用这些预测值来计算更准确的路径代价。
        
        这是双向耦合机制的正向传递：
        信号优化 → 延误预测 → 路径诱导 → effort计算 → 路径选择
        
        Args:
            predicted_delays: {edge_id: delay_seconds} 预测延误字典
            timestamp: 预测时间戳（仿真时间）
        """
        if predicted_delays:
            self.predicted_delays = predicted_delays.copy()
            self.predicted_delays_timestamp = timestamp or 0
            
            # 统计信息
            valid_count = len([d for d in predicted_delays.values() if d > 0])
            avg_delay = sum(predicted_delays.values()) / len(predicted_delays) if predicted_delays else 0
            
            print(f"    [信号→路径] 接收预测延误: {valid_count}/{len(predicted_delays)} 路段, "
                  f"平均延误 {avg_delay:.1f}s")
    
    def get_predicted_delay(self, edge_id):
        """
        获取路段的预测延误（来自信号优化器）
        
        Args:
            edge_id: 路段ID
            
        Returns:
            float: 预测延误（秒），如果没有预测则返回None
        """
        if self.use_predicted_delays and edge_id in self.predicted_delays:
            return self.predicted_delays[edge_id]
        return None
    
    def calculate_signal_delay(self, edge_id, arrival_flow_vph=None):
        """
        基于Webster模型计算边的平均信号延迟
        
        Webster延迟公式（来自论文）：
        d_total = d_uniform + d_random + d_overflow
        
        其中：
        - d_uniform = C(1-λ)² / [2(1-λx)]  均匀延迟
        - d_random = x² / [2q(1-x)]        随机延迟
        - d_overflow = α·max(0, x-1)^β     溢出延迟
        
        参数：
        - C: 周期长度
        - λ = g/C: 绿信比
        - x = q·C / (3600·g): 饱和度
        - q: 到达流量 (veh/h)
        
        Args:
            edge_id: 路段ID
            arrival_flow_vph: 到达流量(veh/h)，如果为None则从SUMO获取
        
        Returns:
            signal_delay: 平均信号延迟（秒）
        """
        # ========== 优先使用来自信号优化器的预测延误 ==========
        # 这是双向耦合机制的关键：信号优化器基于全局视角和优化后的配时
        # 计算的延误预测比本地实时计算更准确
        predicted = self.get_predicted_delay(edge_id)
        if predicted is not None:
            return predicted
        
        # ========== 如果没有预测延误，则实时计算 ==========
        # 检查是否有信号灯控制
        tls_id = self.edge_to_tls.get(edge_id)
        if not tls_id or tls_id not in self.tls_timing:
            return 0  # 无信号灯控制，延迟为0
        
        timing = self.tls_timing[tls_id]
        C = timing['cycle']  # 周期长度
        
        # 获取绿灯时间，默认为周期的50%
        g = self.edge_green_time.get(edge_id, C * 0.5)
        
        # 避免除零
        if C <= 0 or g <= 0:
            return 0
        
        # 绿信比 λ
        lambda_i = g / C
        
        # 获取到达流量
        if arrival_flow_vph is None:
            arrival_flow_vph = self._estimate_arrival_flow(edge_id)
        
        # 车道数
        lane_count = self.get_lane_count(edge_id)
        
        # 通行能力 = 饱和流率 × 车道数 × 绿信比
        capacity = self.SATURATION_FLOW * lane_count * lambda_i
        
        # 饱和度 x
        if capacity > 0:
            x = arrival_flow_vph / capacity
        else:
            x = 0.5
        
        # 限制饱和度，避免数值问题
        x = min(x, self.MAX_SATURATION_DEGREE)
        
        # ========== Webster延迟计算 ==========
        
        # 1. 均匀延迟 d_uniform
        denominator = 1 - lambda_i * x
        if denominator > 0.01:  # 避免除零
            d_uniform = C * (1 - lambda_i) ** 2 / (2 * denominator)
        else:
            # 接近饱和时使用简化公式
            d_uniform = C * (1 - lambda_i) / 2
        
        # 2. 随机延迟 d_random
        if arrival_flow_vph > 0 and x < 1:
            # 转换为veh/s
            q_per_sec = arrival_flow_vph / 3600
            d_random = x ** 2 / (2 * q_per_sec * (1 - x))
            # 限制随机延迟的最大值
            d_random = min(d_random, C * 0.5)
        else:
            d_random = 0
        
        # 3. 溢出延迟 d_overflow
        if x > self.MAX_SATURATION_DEGREE:
            d_overflow = self.OVERFLOW_ALPHA * (x - self.MAX_SATURATION_DEGREE) ** self.OVERFLOW_BETA * 100
        else:
            d_overflow = 0
        
        # 总信号延迟
        total_delay = d_uniform + d_random + d_overflow
        
        return total_delay
    
    def _estimate_arrival_flow(self, edge_id):
        """
        估计边的到达流量（veh/h）
        
        使用SUMO的实时数据估计
        """
        try:
            # 获取当前边上的车辆数
            veh_count = traci.edge.getLastStepVehicleNumber(edge_id)
            
            # 获取平均速度
            mean_speed = traci.edge.getLastStepMeanSpeed(edge_id)
            if mean_speed < 0.1:
                mean_speed = 5.0  # 默认低速
            
            # 获取边长度
            lane_id = f"{edge_id}_0"
            try:
                edge_length = traci.lane.getLength(lane_id)
            except:
                edge_length = 200  # 默认长度
            
            # 估计流量：基于占有率和速度
            # 简化估计：假设车辆以当前速度通过
            if edge_length > 0:
                # 通过时间（秒）
                travel_time = edge_length / mean_speed
                # 流量估计（veh/h）
                if travel_time > 0:
                    flow_estimate = veh_count / travel_time * 3600
                else:
                    flow_estimate = 500
            else:
                flow_estimate = 500
            
            # 限制在合理范围内
            return max(100, min(flow_estimate, 3000))
            
        except:
            return 500  # 默认流量
    
    def get_signal_info(self, edge_id):
        """
        获取边对应的信号灯信息（用于调试）
        
        Returns:
            dict: 包含信号灯ID、周期、绿灯时间等信息
        """
        tls_id = self.edge_to_tls.get(edge_id)
        if not tls_id:
            return None
        
        timing = self.tls_timing.get(tls_id, {})
        return {
            'tls_id': tls_id,
            'cycle': timing.get('cycle', 0),
            'green_time': self.edge_green_time.get(edge_id, 0),
            'green_ratio': self.edge_green_time.get(edge_id, 0) / timing.get('cycle', 1) if timing.get('cycle', 0) > 0 else 0,
            'link_indices': self.edge_to_link_index.get(edge_id, [])
        }


class DynamicRouter:
    """
    动态路由计算器
    基于实时路网状态计算最优路径
    
    整合信号灯延迟后的effort计算：
    总effort = 基础effort（自由流+拥堵） + 信号延迟
    """
    
    def __init__(self):
        """初始化路由计算器"""
        self.graph = defaultdict(dict)  # {from_edge: {to_edge: weight}}
        self.edge_to_node = {}  # edge -> (from_node, to_node)
        self.node_to_edges = defaultdict(list)  # node -> [outgoing_edges]
        self.initialized = False
        
        # 新增：信号灯信息管理器
        self.signal_manager = SignalInfoManager()
        
        # 是否启用信号延迟计算
        self.enable_signal_delay = True
    
    def build_graph_from_sumo(self):
        """
        从SUMO路网构建图结构
        在仿真开始后调用一次
        """
        print("Building graph from SUMO network...")
        
        # 获取所有边
        edge_ids = traci.edge.getIDList()
        
        for edge_id in edge_ids:
            # 跳过内部边（交叉口内的连接边）
            if edge_id.startswith(':'):
                continue
            
            # 获取边的连接关系
            # 通过lane获取后续边
            lane_count = traci.edge.getLaneNumber(edge_id)
            if lane_count > 0:
                lane_id = f"{edge_id}_0"
                try:
                    # 获取该lane可以到达的后续lane
                    links = traci.lane.getLinks(lane_id)
                    for link in links:
                        next_lane = link[0]
                        next_edge = next_lane.rsplit('_', 1)[0]
                        if not next_edge.startswith(':'):
                            # 初始权重为1，后续会用实时effort更新
                            self.graph[edge_id][next_edge] = 1.0
                except:
                    continue
        
        print(f"  Graph built: {len(self.graph)} edges with connections")
        
        # 新增：构建信号灯映射
        self.signal_manager.build_signal_mapping()
        
        self.initialized = True
    
    def update_weights_from_effort(self, edge_weights, include_signal_delay=True):
        """
        用实时effort更新图的权重
        
        Args:
            edge_weights: {edge_id: effort_value} 字典（基础effort：自由流+拥堵延迟）
            include_signal_delay: 是否包含信号延迟（默认True）
        """
        for from_edge, neighbors in self.graph.items():
            for to_edge in neighbors:
                # 基础effort（自由流时间 + 拥堵延迟）
                base_effort = edge_weights.get(to_edge, 1.0)
                
                # 新增：信号延迟
                signal_delay = 0
                if include_signal_delay and self.enable_signal_delay and self.signal_manager.initialized:
                    signal_delay = self.signal_manager.calculate_signal_delay(to_edge)
                
                # 综合effort = 基础effort + 信号延迟
                total_effort = base_effort + signal_delay
                
                self.graph[from_edge][to_edge] = max(total_effort, 0.1)  # 避免0权重
    
    def dijkstra(self, start_edge, end_edge, blocked_edges=None):
        """
        Dijkstra最短路径算法
        
        Args:
            start_edge: 起始边ID
            end_edge: 目标边ID
            blocked_edges: 需要避开的拥堵路段集合（可选）
        
        Returns:
            path: 边ID列表，如果无路径则返回None
            cost: 路径总代价
        """
        if blocked_edges is None:
            blocked_edges = set()
        
        if start_edge == end_edge:
            return [start_edge], 0
        
        # 优先队列: (cost, edge, path)
        heap = [(0, start_edge, [start_edge])]
        visited = set()
        
        while heap:
            cost, current, path = heapq.heappop(heap)
            
            if current in visited:
                continue
            visited.add(current)
            
            if current == end_edge:
                return path, cost
            
            # 遍历邻居
            for next_edge, weight in self.graph.get(current, {}).items():
                if next_edge not in visited:
                    # 如果下一条边是拥堵路段且不是终点，跳过
                    if next_edge in blocked_edges and next_edge != end_edge:
                        continue
                    
                    new_cost = cost + weight
                    new_path = path + [next_edge]
                    heapq.heappush(heap, (new_cost, next_edge, new_path))
        
        return None, float('inf')
    
    def find_best_route(self, current_edge, destination_edge, edge_weights, blocked_edges=None):
        """
        为车辆找到最优路径，避开拥堵路段
        
        Args:
            current_edge: 当前所在边
            destination_edge: 目的地边
            edge_weights: 实时effort字典（基础effort）
            blocked_edges: 需要避开的拥堵路段集合（可选）
        
        Returns:
            best_path: 最优路径（边列表）
            cost: 路径代价
        """
        if blocked_edges is None:
            blocked_edges = set()
        
        # 更新权重（包含信号延迟）
        self.update_weights_from_effort(edge_weights, include_signal_delay=self.enable_signal_delay)
        
        # 首先尝试避开管控路段计算路径
        if blocked_edges:
            path, cost = self.dijkstra(current_edge, destination_edge, blocked_edges)
            
            # 如果找到了绕行路径，返回
            if path is not None:
                return path, cost
            
            # 如果无法绕行（必须经过管控路段才能到达终点）
            # 仍然计算路径，但让调用方决定是否使用
            path, cost = self.dijkstra(current_edge, destination_edge, set())
            return path, cost
        
        # 没有拥堵路段，正常计算
        path, cost = self.dijkstra(current_edge, destination_edge)
        return path, cost
    
    def get_edge_signal_info(self, edge_id):
        """
        获取边的信号灯信息（用于调试和分析）
        
        Args:
            edge_id: 边ID
        
        Returns:
            dict: 信号灯信息，如果无信号灯则返回None
        """
        return self.signal_manager.get_signal_info(edge_id)
    
    def set_signal_delay_enabled(self, enabled):
        """
        设置是否启用信号延迟计算
        
        Args:
            enabled: True启用，False禁用
        """
        self.enable_signal_delay = enabled
        print(f"  Signal delay calculation: {'Enabled' if enabled else 'Disabled'}")


def get_vehicle_destination(veh_id):
    """
    获取车辆的目的地边
    
    Args:
        veh_id: 车辆ID
    
    Returns:
        destination_edge: 目的地边ID
    """
    route = traci.vehicle.getRoute(veh_id)
    if route:
        return route[-1]
    return None


def set_vehicle_route(veh_id, new_route):
    """
    设置车辆的新路径
    
    Args:
        veh_id: 车辆ID
        new_route: 新路径（边列表）
    
    Returns:
        success: 是否成功
    """
    try:
        # 检查新路径有效性
        if not new_route or len(new_route) < 2:
            return False
        
        # 检查是否有重复的连续边（无效路径）
        for i in range(len(new_route) - 1):
            if new_route[i] == new_route[i + 1]:
                return False
        
        # 获取当前路径
        current_route = list(traci.vehicle.getRoute(veh_id))
        route_index = traci.vehicle.getRouteIndex(veh_id)
        
        # 保留已经走过的部分，替换剩余部分
        if route_index >= 0:
            # 已走过的路径 + 新计算的路径
            final_route = current_route[:route_index] + new_route
        else:
            final_route = new_route
        
        # 再次检查最终路径有效性
        if len(final_route) < 2:
            return False
        
        # 检查起点和终点不能相同
        if final_route[0] == final_route[-1] and len(final_route) == 2:
            return False
        
        # 设置新路径
        traci.vehicle.setRoute(veh_id, final_route)
        return True
    except Exception as e:
        return False


def calculate_route_cost(route, edge_weights):
    """
    计算路径的总代价
    
    Args:
        route: 边列表
        edge_weights: effort字典
    
    Returns:
        total_cost: 总代价
    """
    total = 0
    for edge in route:
        total += edge_weights.get(edge, 1.0)
    return total


class EffortLogger:
    """
    Effort计算过程日志记录器
    记录每次路径更新时的effort计算详情，输出为XML文件
    
    记录内容：
    - 时间戳
    - 每条边的基础effort（自由流时间 + 拥堵延迟）
    - 每条边的信号延迟（Webster模型各分量）
    - 综合effort
    """
    
    def __init__(self, output_dir, mode, flow, pr):
        """
        初始化日志记录器
        
        Args:
            output_dir: 输出目录（如 output/）
            mode: 实验模式
            flow: 流量等级
            pr: 渗透率
        """
        import os
        self.output_dir = os.path.join(output_dir, 'effort_logs')
        self.mode = mode
        self.flow = flow
        self.pr = pr
        
        # 创建输出目录
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # 日志记录
        self.records = []  # 存储所有时间点的记录
        self.enabled = True
    
    def log_effort_update(self, sim_step, edge_weights, signal_manager, router):
        """
        记录一次effort更新
        
        Args:
            sim_step: 仿真时间步
            edge_weights: 基础effort字典 {edge_id: base_effort}
            signal_manager: SignalInfoManager实例
            router: DynamicRouter实例
        """
        if not self.enabled:
            return
        
        timestamp_record = {
            'time': sim_step,
            'edges': []
        }
        
        # 只记录有信号灯的边（减少数据量）
        edges_to_log = list(signal_manager.edge_to_tls.keys()) if signal_manager.initialized else list(edge_weights.keys())[:20]
        
        for edge_id in edges_to_log:
            base_effort = edge_weights.get(edge_id, 0)
            
            # 获取信号延迟详情
            signal_detail = self._get_signal_delay_detail(edge_id, signal_manager)
            
            # 综合effort
            total_effort = base_effort + signal_detail.get('total_delay', 0)
            
            edge_record = {
                'edge_id': edge_id,
                'base_effort': round(base_effort, 3),
                'signal_delay': signal_detail,
                'total_effort': round(total_effort, 3)
            }
            timestamp_record['edges'].append(edge_record)
        
        self.records.append(timestamp_record)
    
    def _get_signal_delay_detail(self, edge_id, signal_manager):
        """
        获取信号延迟的详细计算过程
        
        Returns:
            dict: 包含各分量的详细信息
        """
        if not signal_manager.initialized:
            return {'total_delay': 0, 'has_signal': False}
        
        tls_id = signal_manager.edge_to_tls.get(edge_id)
        if not tls_id or tls_id not in signal_manager.tls_timing:
            return {'total_delay': 0, 'has_signal': False}
        
        timing = signal_manager.tls_timing[tls_id]
        C = timing['cycle']
        g = signal_manager.edge_green_time.get(edge_id, C * 0.5)
        
        if C <= 0 or g <= 0:
            return {'total_delay': 0, 'has_signal': True, 'cycle': C, 'green': g}
        
        lambda_i = g / C
        arrival_flow = signal_manager._estimate_arrival_flow(edge_id)
        lane_count = signal_manager.get_lane_count(edge_id)
        capacity = signal_manager.SATURATION_FLOW * lane_count * lambda_i
        x = min(arrival_flow / capacity, signal_manager.MAX_SATURATION_DEGREE) if capacity > 0 else 0.5
        
        # 计算各分量
        denominator = 1 - lambda_i * x
        if denominator > 0.01:
            d_uniform = C * (1 - lambda_i) ** 2 / (2 * denominator)
        else:
            d_uniform = C * (1 - lambda_i) / 2
        
        if arrival_flow > 0 and x < 1:
            q_per_sec = arrival_flow / 3600
            d_random = min(x ** 2 / (2 * q_per_sec * (1 - x)), C * 0.5)
        else:
            d_random = 0
        
        if x > signal_manager.MAX_SATURATION_DEGREE:
            d_overflow = signal_manager.OVERFLOW_ALPHA * (x - signal_manager.MAX_SATURATION_DEGREE) ** signal_manager.OVERFLOW_BETA * 100
        else:
            d_overflow = 0
        
        total_delay = d_uniform + d_random + d_overflow
        
        return {
            'has_signal': True,
            'tls_id': tls_id,
            'cycle': round(C, 1),
            'green': round(g, 1),
            'green_ratio': round(lambda_i, 3),
            'arrival_flow': round(arrival_flow, 1),
            'saturation': round(x, 3),
            'd_uniform': round(d_uniform, 3),
            'd_random': round(d_random, 3),
            'd_overflow': round(d_overflow, 3),
            'total_delay': round(total_delay, 3)
        }
    
    def save_to_xml(self):
        """
        保存日志到XML文件
        
        Returns:
            output_file: 输出文件路径
        """
        import xml.etree.ElementTree as ET
        from datetime import datetime
        
        if not self.records:
            print("  No effort records to save")
            return None
        
        # 创建XML结构
        root = ET.Element("effort_log")
        root.set("mode", str(self.mode))
        root.set("flow", str(self.flow))
        root.set("pr", str(self.pr))
        root.set("generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        root.set("total_updates", str(len(self.records)))
        
        # 添加每个时间点的记录
        for record in self.records:
            time_elem = ET.SubElement(root, "update")
            time_elem.set("time", str(record['time']))
            
            for edge_data in record['edges']:
                edge_elem = ET.SubElement(time_elem, "edge")
                edge_elem.set("id", edge_data['edge_id'])
                edge_elem.set("base_effort", str(edge_data['base_effort']))
                edge_elem.set("total_effort", str(edge_data['total_effort']))
                
                signal = edge_data['signal_delay']
                if signal.get('has_signal', False):
                    signal_elem = ET.SubElement(edge_elem, "signal")
                    signal_elem.set("tls_id", str(signal.get('tls_id', '')))
                    signal_elem.set("cycle", str(signal.get('cycle', 0)))
                    signal_elem.set("green", str(signal.get('green', 0)))
                    signal_elem.set("green_ratio", str(signal.get('green_ratio', 0)))
                    signal_elem.set("arrival_flow", str(signal.get('arrival_flow', 0)))
                    signal_elem.set("saturation", str(signal.get('saturation', 0)))
                    signal_elem.set("d_uniform", str(signal.get('d_uniform', 0)))
                    signal_elem.set("d_random", str(signal.get('d_random', 0)))
                    signal_elem.set("d_overflow", str(signal.get('d_overflow', 0)))
                    signal_elem.set("total_delay", str(signal.get('total_delay', 0)))
        
        # 格式化并保存
        self._indent_xml(root)
        tree = ET.ElementTree(root)
        
        output_file = f"{self.output_dir}/effort_log_{self.mode}_{self.flow}_{self.pr}.xml"
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        
        print(f"\n  Effort log saved: {output_file}")
        print(f"    Total updates: {len(self.records)}")
        if self.records:
            print(f"    Edges per update: {len(self.records[0]['edges'])}")
        
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
