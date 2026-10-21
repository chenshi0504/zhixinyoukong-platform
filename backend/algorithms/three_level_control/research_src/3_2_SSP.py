"""
SSP 路径诱导算法（Spatiotemporal Superposition Planning）

文件编号: 3_4 (route=4)
配置编码: 2_4_{flow}_{pr} 表示使用 SSP 算法

来源：HAC3论文 "Hierarchical adaptive cross-coupled control of traffic signals and vehicle routes" (2025)

实现：
- SSP (Spatiotemporal Superposition Planning) 用于路径诱导
- 核心思想：将多车辆路径规划抽象为时空轨迹叠加问题
- 基于道路容量和信号配时进行顺序分配
- 启发式方法，非强化学习

算法流程：
1. 获取所有待分配CAV的OD信息
2. 按优先级（距离、紧急程度）排序
3. 顺序为每辆车分配路径，考虑：
   - 道路剩余容量
   - 信号配时（绿灯窗口）
   - 已分配车辆的时空轨迹
4. 更新道路占用状态
"""
import os
import heapq
import random
from collections import defaultdict
from datetime import datetime
import traci

# 车辆类型定义
CAV_TYPE = "CAV"


class SSPRouter:
    """
    SSP路径诱导器
    
    基于HAC3论文的时空叠加规划方法
    
    核心概念：
    - 时空轨迹：车辆在时间-空间维度的路径
    - 容量约束：每条路段在每个时间窗口的最大车辆数
    - 顺序分配：按优先级依次为车辆分配路径
    """
    
    # 参数（优化版 - 更积极且更智能）
    TIME_WINDOW = 30        # 时间窗口大小（秒）
    CAPACITY_FACTOR = 0.85  # 容量利用系数（降低，更保守的容量估计）
    LOOKAHEAD_WINDOWS = 10  # 前瞻时间窗口数
    MIN_AVAILABILITY = 0.05 # 最小可用容量阈值（提高，避免过度拥挤的路段）
    REROUTE_THRESHOLD = 0.05 # 当新路径比旧路径好5%以上就改变
    CONGESTION_WEIGHT = 2.0  # 拥堵惩罚权重（提高，更积极避开拥堵）
    FORCE_REROUTE_PROB = 0.10 # 强制重路由概率（降低，减少不必要的路径变化）
    
    # 新增：信号配时感知参数
    SIGNAL_DELAY_WEIGHT = 1.5  # 信号延迟权重
    QUEUE_PREDICTION_FACTOR = 0.8  # 排队预测因子
    
    def __init__(self, flow_level: int, update_interval: int = 30, output_dir: str = None):
        """
        初始化SSP路径诱导器
        
        Args:
            flow_level: 流量等级（1-6）
            update_interval: 更新间隔（秒）
            output_dir: 输出目录
        """
        self.flow_level = flow_level
        self.update_interval = update_interval
        self.output_dir = output_dir
        
        # 路网图
        self.graph = defaultdict(dict)  # {from_edge: {to_edge: travel_time}}
        self.edge_capacity = {}         # {edge_id: capacity}
        self.edge_length = {}           # {edge_id: length}
        self.graph_initialized = False
        
        # 时空占用矩阵
        # {edge_id: {time_window: current_count}}
        self.spatiotemporal_occupancy = defaultdict(lambda: defaultdict(int))
        
        # 信号配时信息
        self.signal_timing = {}  # {tls_id: {phase: green_time}}
        self.edge_to_tls = {}    # {edge_id: tls_id}
        
        # 统计信息
        self.total_assignments = 0
        self.total_rerouted = 0
        self.assignment_history = []
        self.last_update_step = 0
        
        # 路由变更记录
        self.route_changes = []
        
        print(f"[SSPRouter] 初始化完成")
        print(f"    流量等级: {flow_level}")
        print(f"    时间窗口: {self.TIME_WINDOW}s")
        print(f"    更新间隔: {update_interval}s")

    def _build_graph(self):
        """从SUMO路网构建图结构"""
        if self.graph_initialized:
            return
        
        edge_ids = traci.edge.getIDList()
        
        for edge_id in edge_ids:
            if edge_id.startswith(':'):
                continue
            
            try:
                # 获取边的属性
                lane_count = traci.edge.getLaneNumber(edge_id)
                lane_id = f"{edge_id}_0"
                length = traci.lane.getLength(lane_id)
                
                self.edge_length[edge_id] = length
                # 容量 = 车道数 × 长度 / 车辆间距
                self.edge_capacity[edge_id] = int(lane_count * length / 10) * self.CAPACITY_FACTOR
                
                # 构建邻接关系
                links = traci.lane.getLinks(lane_id)
                for link in links:
                    next_lane = link[0]
                    next_edge = next_lane.rsplit('_', 1)[0]
                    if not next_edge.startswith(':'):
                        # 使用自由流旅行时间作为权重
                        travel_time = traci.edge.getTraveltime(edge_id)
                        self.graph[edge_id][next_edge] = max(travel_time, 1.0)
            except:
                continue
        
        # 获取信号灯信息
        self._build_signal_mapping()
        
        self.graph_initialized = True
        print(f"    路网图构建完成: {len(self.graph)} 条边")

    def _build_signal_mapping(self):
        """构建信号灯映射"""
        try:
            tls_ids = traci.trafficlight.getIDList()
            
            for tls_id in tls_ids:
                controlled_links = traci.trafficlight.getControlledLinks(tls_id)
                
                for link_group in controlled_links:
                    for link in link_group:
                        if len(link) >= 1:
                            incoming_lane = link[0]
                            incoming_edge = incoming_lane.rsplit('_', 1)[0]
                            if not incoming_edge.startswith(':'):
                                self.edge_to_tls[incoming_edge] = tls_id
        except:
            pass

    def get_time_window(self, sim_time: float) -> int:
        """获取当前时间窗口索引"""
        return int(sim_time / self.TIME_WINDOW)

    def get_edge_availability(self, edge_id: str, time_window: int) -> float:
        """
        获取路段在指定时间窗口的可用容量比例
        
        Args:
            edge_id: 路段ID
            time_window: 时间窗口索引
            
        Returns:
            availability: 可用容量比例 (0-1)
        """
        capacity = self.edge_capacity.get(edge_id, 10)
        current_count = self.spatiotemporal_occupancy[edge_id][time_window]
        
        if capacity <= 0:
            return 0.0
        
        return max(0.0, 1.0 - current_count / capacity)

    def reserve_edge(self, edge_id: str, time_window: int):
        """预留路段容量"""
        self.spatiotemporal_occupancy[edge_id][time_window] += 1

    def release_edge(self, edge_id: str, time_window: int):
        """释放路段容量"""
        if self.spatiotemporal_occupancy[edge_id][time_window] > 0:
            self.spatiotemporal_occupancy[edge_id][time_window] -= 1

    def find_spatiotemporal_path(self, current_edge: str, destination: str, 
                                  start_time: float) -> tuple:
        """
        寻找时空最优路径
        
        考虑：
        - 路段旅行时间
        - 时空容量约束
        - 信号配时（可选）
        
        Args:
            current_edge: 当前路段
            destination: 目的地路段
            start_time: 出发时间
            
        Returns:
            (path, arrival_time): 路径和预计到达时间
        """
        if current_edge == destination:
            return [current_edge], start_time
        
        # 时空Dijkstra
        # 状态: (cost, current_edge, current_time, path)
        start_window = self.get_time_window(start_time)
        heap = [(0, current_edge, start_time, [current_edge])]
        visited = set()  # (edge, time_window)
        
        while heap:
            cost, current, current_time, path = heapq.heappop(heap)
            current_window = self.get_time_window(current_time)
            
            state = (current, current_window)
            if state in visited:
                continue
            visited.add(state)
            
            if current == destination:
                return path, current_time
            
            for next_edge, travel_time in self.graph.get(current, {}).items():
                next_time = current_time + travel_time
                next_window = self.get_time_window(next_time)
                
                next_state = (next_edge, next_window)
                if next_state in visited:
                    continue
                
                # 检查容量约束（使用更宽松的阈值）
                availability = self.get_edge_availability(next_edge, next_window)
                if availability < self.MIN_AVAILABILITY:
                    continue
                
                # 计算代价（降低拥堵惩罚权重）
                congestion_penalty = (1 - availability) * travel_time * self.CONGESTION_WEIGHT
                total_cost = cost + travel_time + congestion_penalty
                
                new_path = path + [next_edge]
                heapq.heappush(heap, (total_cost, next_edge, next_time, new_path))
        
        return None, float('inf')

    def _validate_route(self, route: list) -> bool:
        """验证路径连通性"""
        if len(route) < 2:
            return True
        
        for i in range(len(route) - 1):
            from_edge = route[i]
            to_edge = route[i + 1]
            
            if from_edge.startswith(':') or to_edge.startswith(':'):
                continue
            
            if to_edge not in self.graph.get(from_edge, {}):
                return False
        
        return True

    def assign_routes(self, sim_step: int) -> tuple:
        """
        为所有CAV分配路径
        
        SSP核心算法：
        1. 收集所有待分配CAV
        2. 按优先级排序（距离目的地近的优先）
        3. 顺序分配路径，更新时空占用
        
        Returns:
            (total_assigned, total_rerouted): 分配数量, 改变路径数量
        """
        if not self.graph_initialized:
            self._build_graph()
        
        # 收集CAV信息
        cav_info = []
        cav_ids = [veh for veh in traci.vehicle.getIDList()
                   if traci.vehicle.getTypeID(veh) == CAV_TYPE]
        
        for veh_id in cav_ids:
            try:
                current_edge = traci.vehicle.getRoadID(veh_id)
                if current_edge.startswith(':'):
                    continue
                
                route = traci.vehicle.getRoute(veh_id)
                if not route:
                    continue
                
                destination = route[-1]
                if current_edge == destination:
                    continue
                
                # 计算优先级（剩余距离）
                route_index = traci.vehicle.getRouteIndex(veh_id)
                remaining_edges = len(route) - route_index if route_index >= 0 else len(route)
                
                cav_info.append({
                    'veh_id': veh_id,
                    'current_edge': current_edge,
                    'destination': destination,
                    'priority': remaining_edges,  # 距离近的优先级高
                    'old_route': list(route),
                    'route_index': route_index
                })
            except:
                continue
        
        # 按优先级排序（距离近的先分配）
        cav_info.sort(key=lambda x: x['priority'])
        
        total_assigned = 0
        total_rerouted = 0
        
        # 顺序分配
        for info in cav_info:
            veh_id = info['veh_id']
            current_edge = info['current_edge']
            destination = info['destination']
            old_route = info['old_route']
            route_index = info['route_index']
            
            # 寻找时空最优路径
            new_path, arrival_time = self.find_spatiotemporal_path(
                current_edge, destination, sim_step
            )
            
            if new_path is None or len(new_path) < 2:
                continue
            
            total_assigned += 1
            
            # 检查是否需要改变路径
            remaining_old = old_route[route_index:] if route_index >= 0 else old_route
            
            # 【核心改进】更积极地改变路径
            # 计算新旧路径的预估时间
            old_path_cost = sum(self.graph.get(remaining_old[i], {}).get(
                remaining_old[i+1] if i+1 < len(remaining_old) else remaining_old[i], 30
            ) for i in range(len(remaining_old)))
            new_path_cost = sum(self.graph.get(new_path[i], {}).get(
                new_path[i+1] if i+1 < len(new_path) else new_path[i], 30
            ) for i in range(len(new_path)))
            
            # 多种条件触发重路由
            should_reroute = False
            
            # 条件1：新路径明显更短
            if len(new_path) < len(remaining_old) - 1:
                should_reroute = True
            # 条件2：新路径时间更优（超过阈值）
            elif new_path_cost < old_path_cost * (1 - self.REROUTE_THRESHOLD):
                should_reroute = True
            # 条件3：路径不同且有一定概率强制改变（增加多样性）
            elif new_path != remaining_old and random.random() < self.FORCE_REROUTE_PROB:
                should_reroute = True
            # 条件4：当前路段拥堵，强制寻找替代路径
            elif self.get_edge_availability(current_edge, self.get_time_window(sim_step)) < 0.3:
                should_reroute = True
            
            if should_reroute:
                # 构建完整路径
                full_new_route = old_route[:route_index] + new_path
                
                # 验证路径有效性：至少2条边，且相邻边不同
                if len(full_new_route) < 2:
                    continue
                
                # 检查是否有相邻重复边
                has_duplicate = any(full_new_route[i] == full_new_route[i+1] 
                                   for i in range(len(full_new_route)-1))
                if has_duplicate:
                    continue
                
                if self._validate_route(full_new_route):
                    try:
                        traci.vehicle.setRoute(veh_id, full_new_route)
                        total_rerouted += 1
                        
                        # 预留路径容量
                        current_time = sim_step
                        for edge in new_path:
                            window = self.get_time_window(current_time)
                            self.reserve_edge(edge, window)
                            travel_time = self.graph.get(edge, {}).get(
                                new_path[new_path.index(edge) + 1] if edge != new_path[-1] else edge, 
                                30
                            )
                            current_time += travel_time
                        
                        # 记录变更
                        self.route_changes.append({
                            'time': sim_step,
                            'vehicle_id': veh_id,
                            'current_edge': current_edge,
                            'old_route': ' -> '.join(remaining_old[:5]) + ('...' if len(remaining_old) > 5 else ''),
                            'new_route': ' -> '.join(new_path[:5]) + ('...' if len(new_path) > 5 else ''),
                            'estimated_arrival': arrival_time
                        })
                    except:
                        continue
        
        self.total_assignments += total_assigned
        self.total_rerouted += total_rerouted
        
        return total_assigned, total_rerouted

    def update_occupancy(self, sim_step: int):
        """
        更新时空占用状态
        
        清理过期的时间窗口，更新当前占用
        """
        current_window = self.get_time_window(sim_step)
        
        # 清理过期窗口
        for edge_id in list(self.spatiotemporal_occupancy.keys()):
            windows_to_remove = [w for w in self.spatiotemporal_occupancy[edge_id] 
                                if w < current_window - 2]
            for w in windows_to_remove:
                del self.spatiotemporal_occupancy[edge_id][w]
        
        # 更新当前占用（基于实际车辆数）
        for edge in traci.edge.getIDList():
            if edge.startswith(':'):
                continue
            try:
                veh_count = traci.edge.getLastStepVehicleNumber(edge)
                self.spatiotemporal_occupancy[edge][current_window] = veh_count
            except:
                continue

    def should_update(self, sim_step: int) -> bool:
        """判断是否需要更新"""
        if sim_step <= 0:
            return False
        if sim_step == self.last_update_step:
            return False
        if sim_step % self.update_interval == 0:
            self.last_update_step = sim_step
            return True
        return False

    def _format_congestion_edges(self, current_window: int, max_items: int = 5) -> tuple:
        congested_edges = []
        for edge_id in self.edge_capacity.keys():
            try:
                halting = int(traci.edge.getLastStepHaltingNumber(edge_id))
                vehicles = int(traci.edge.getLastStepVehicleNumber(edge_id))
            except Exception:
                halting = 0
                vehicles = int(self.spatiotemporal_occupancy[edge_id].get(current_window, 0))
            availability = self.get_edge_availability(edge_id, current_window)
            if halting > 0 or vehicles >= max(1, int(self.edge_capacity.get(edge_id, 1) * 0.8)) or availability < 0.35:
                congested_edges.append((edge_id, halting, vehicles, availability))

        congested_edges.sort(key=lambda item: (item[1], item[2], -item[3]), reverse=True)
        if not congested_edges:
            return 0, "无明显拥堵路段"

        items = [
            f"{edge}(排队{halting}辆, 车辆{vehicles}辆, 可用率{availability:.2f})"
            for edge, halting, vehicles, availability in congested_edges[:max_items]
        ]
        suffix = f"...等{len(congested_edges)}条" if len(congested_edges) > max_items else ""
        return len(congested_edges), "，".join(items) + suffix

    def update(self, sim_step: int) -> int:
        """
        执行更新周期
        
        输出格式：
        [600s] SSP Router: 50 CAVs assigned, 20 rerouted
          Occupancy windows: 15 active
          Avg availability: 0.75
        
        Args:
            sim_step: 当前仿真步数
            
        Returns:
            rerouted_count: 改变路径的车辆数
        """
        # 每步更新占用状态
        self.update_occupancy(sim_step)
        
        if not self.should_update(sim_step):
            return 0
        
        # 分配路径
        assigned, rerouted = self.assign_routes(sim_step)
        
        # 计算统计信息
        current_window = self.get_time_window(sim_step)
        active_windows = sum(1 for edge in self.spatiotemporal_occupancy 
                           for w in self.spatiotemporal_occupancy[edge] 
                           if abs(w - current_window) <= 2)
        
        avg_availability = 0
        count = 0
        for edge_id in list(self.edge_capacity.keys())[:20]:
            avail = self.get_edge_availability(edge_id, current_window)
            avg_availability += avail
            count += 1
        avg_availability = avg_availability / count if count > 0 else 1.0
        
        congestion_count, congestion_text = self._format_congestion_edges(current_window)
        print(
            f"[{sim_step}s] 路径诱导决策(SSP): 评估{assigned}辆CAV，"
            f"{rerouted}辆CAV更改路径；拥堵候选路段{congestion_count}条",
            flush=True
        )
        print(
            f"    拥堵路段Top: {congestion_text}；活跃时空窗口{active_windows}个；"
            f"平均可用率{avg_availability:.2f}",
            flush=True
        )
        
        return rerouted

    def get_statistics(self) -> dict:
        """获取统计信息"""
        return {
            'flow_level': self.flow_level,
            'total_assignments': self.total_assignments,
            'total_rerouted': self.total_rerouted,
            'reroute_rate': self.total_rerouted / self.total_assignments if self.total_assignments > 0 else 0,
            'time_window': self.TIME_WINDOW,
            'edges_count': len(self.graph)
        }

    def save_route_changes(self, config_name: str, flow_level: int, pr: str):
        """保存路由变更记录"""
        import xml.etree.ElementTree as ET
        
        if not self.output_dir or not self.route_changes:
            return None
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # 创建XML结构
        root = ET.Element("ssp_routing_changes")
        root.set("config_name", str(config_name))
        root.set("flow_level", str(flow_level))
        root.set("pr", str(pr))
        root.set("time_window", str(self.TIME_WINDOW))
        root.set("total_assignments", str(self.total_assignments))
        root.set("total_rerouted", str(self.total_rerouted))
        root.set("generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # 添加变更记录
        for record in self.route_changes[-100:]:
            change_elem = ET.SubElement(root, "change")
            change_elem.set("time", str(record['time']))
            change_elem.set("vehicle", record['vehicle_id'])
            change_elem.set("current_edge", record['current_edge'])
            change_elem.set("estimated_arrival", f"{record['estimated_arrival']:.1f}")
        
        # 格式化并保存
        self._indent_xml(root)
        tree = ET.ElementTree(root)
        
        output_file = os.path.join(self.output_dir, "ssp_routing_changes.xml")
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        
        print(f"\nSSP路由记录已保存: {output_file}")
        print(f"  总分配: {self.total_assignments}")
        print(f"  总改变: {self.total_rerouted}")
        
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
