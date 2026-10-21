"""
A*路径诱导算法

文件编号: 3_2 (route=2, 旧编号route=3)
配置编码: 2_2_{flow}_{pr} 表示使用A*算法

传统启发式路径规划方法，用于对比实验
只考虑路段长度，不考虑实时交通状态

特点：
- 基于启发式搜索
- 只使用路段长度作为代价
- 不考虑拥堵和信号延误
- 每30秒更新一次路径
"""
import traci
import heapq
from typing import Dict, List, Tuple, Optional


class AstarRouter:
    """
    A*路径规划器
    
    只考虑路段长度的传统路径规划方法
    用于对比实验，验证考虑实时交通状态的优势
    """
    
    def __init__(self, net_file: str, update_interval: int = 30):
        """
        初始化A*路由器
        
        Args:
            net_file: SUMO路网文件路径
        """
        import sumolib
        self.net = sumolib.net.readNet(net_file)
        self.update_interval = update_interval
        self.total_assignments = 0
        self.total_rerouted = 0
        self.last_update_step = 0
        self.edge_lengths = {}  # 路段长度缓存
        self._build_edge_lengths()
    
    def _build_edge_lengths(self):
        """构建路段长度字典"""
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            if not edge_id.startswith(':'):
                self.edge_lengths[edge_id] = edge.getLength()
    
    def _heuristic(self, edge_id: str, dest_edge_id: str) -> float:
        """
        A*启发式函数：使用直线距离
        
        Args:
            edge_id: 当前路段ID
            dest_edge_id: 目标路段ID
            
        Returns:
            float: 启发式估计距离
        """
        try:
            current_edge = self.net.getEdge(edge_id)
            dest_edge = self.net.getEdge(dest_edge_id)
            
            # 获取路段中心点坐标
            current_pos = current_edge.getShape()[len(current_edge.getShape())//2]
            dest_pos = dest_edge.getShape()[len(dest_edge.getShape())//2]
            
            # 计算欧几里得距离
            dx = current_pos[0] - dest_pos[0]
            dy = current_pos[1] - dest_pos[1]
            return (dx**2 + dy**2)**0.5
        except:
            return 0.0
    
    def find_route(self, origin_edge: str, dest_edge: str) -> List[str]:
        """
        使用A*算法查找最短路径
        
        Args:
            origin_edge: 起点路段
            dest_edge: 终点路段
            
        Returns:
            List[str]: 路径（路段ID列表）
        """
        if origin_edge == dest_edge:
            return [origin_edge]
        
        # A*搜索
        # 优先队列：(f_score, g_score, edge_id, path)
        open_set = [(0.0, 0.0, origin_edge, [origin_edge])]
        closed_set = set()
        g_scores = {origin_edge: 0.0}
        
        while open_set:
            f_score, g_score, current_edge, path = heapq.heappop(open_set)
            
            if current_edge in closed_set:
                continue
            
            if current_edge == dest_edge:
                return path
            
            closed_set.add(current_edge)
            
            # 获取后继路段
            try:
                edge = self.net.getEdge(current_edge)
                for next_edge in edge.getOutgoing():
                    next_edge_id = next_edge.getID()
                    
                    # 跳过内部路段
                    if next_edge_id.startswith(':'):
                        continue
                    
                    # 计算g_score（实际代价）
                    edge_length = self.edge_lengths.get(next_edge_id, 100.0)
                    tentative_g = g_score + edge_length
                    
                    # 如果找到更好的路径
                    if next_edge_id not in g_scores or tentative_g < g_scores[next_edge_id]:
                        g_scores[next_edge_id] = tentative_g
                        h_score = self._heuristic(next_edge_id, dest_edge)
                        f_score = tentative_g + h_score
                        
                        new_path = path + [next_edge_id]
                        heapq.heappush(open_set, (f_score, tentative_g, next_edge_id, new_path))
            except:
                continue
        
        # 如果找不到路径，返回空列表
        return []
    
    def get_route_for_vehicle(self, veh_id: str) -> Optional[List[str]]:
        """
        为车辆计算A*路径
        
        Args:
            veh_id: 车辆ID
            
        Returns:
            Optional[List[str]]: 路径（路段ID列表），如果失败返回None
        """
        try:
            # 获取当前位置和目的地
            current_edge = traci.vehicle.getRoadID(veh_id)
            route = traci.vehicle.getRoute(veh_id)
            
            if not route or len(route) == 0:
                return None
            
            dest_edge = route[-1]
            
            # 跳过内部路段
            if current_edge.startswith(':'):
                return None
            
            # 如果已经在目的地路段，不需要重新规划
            if current_edge == dest_edge:
                return None
            
            # 使用A*查找路径
            new_route = self.find_route(current_edge, dest_edge)
            
            if new_route and len(new_route) > 1:
                return new_route
            
            return None
        except:
            return None

    def _format_congestion_edges(self, max_items: int = 5) -> tuple:
        congested_edges = []
        for edge_id in self.edge_lengths.keys():
            try:
                halting = int(traci.edge.getLastStepHaltingNumber(edge_id))
                vehicles = int(traci.edge.getLastStepVehicleNumber(edge_id))
                lane_count = max(1, int(traci.edge.getLaneNumber(edge_id)))
                capacity_hint = max(1, int(lane_count * self.edge_lengths.get(edge_id, 100.0) / 10))
            except Exception:
                continue

            occupancy_ratio = vehicles / capacity_hint
            if halting > 0 or occupancy_ratio >= 0.8:
                congested_edges.append((edge_id, halting, vehicles, occupancy_ratio))

        congested_edges.sort(key=lambda item: (item[1], item[3], item[2]), reverse=True)
        if not congested_edges:
            return 0, "无明显拥堵路段"

        items = [
            f"{edge}(排队{halting}辆, 车辆{vehicles}辆, 占用率{occupancy_ratio:.2f})"
            for edge, halting, vehicles, occupancy_ratio in congested_edges[:max_items]
        ]
        suffix = f"...等{len(congested_edges)}条" if len(congested_edges) > max_items else ""
        return len(congested_edges), "，".join(items) + suffix
    
    def update(self, sim_step: int):
        """
        更新路径诱导（每个仿真步调用）
        
        A*算法只考虑路段长度，为每辆CAV车辆计算最短路径
        
        Args:
            sim_step: 当前仿真时间步
        """
        # 第一个30s周期结束后开始更新
        if sim_step <= 0 or sim_step % self.update_interval != 0:
            return
        if sim_step == self.last_update_step:
            return
        self.last_update_step = sim_step
        
        try:
            # 获取所有CAV车辆
            all_vehicles = traci.vehicle.getIDList()
            cav_vehicles = [v for v in all_vehicles if traci.vehicle.getTypeID(v) == 'CAV']
            
            rerouted_count = 0
            
            for veh_id in cav_vehicles:
                try:
                    new_route = self.get_route_for_vehicle(veh_id)
                    if new_route and len(new_route) > 1:
                        traci.vehicle.setRoute(veh_id, new_route)
                        rerouted_count += 1
                        self.total_rerouted += 1
                except:
                    continue
            self.total_assignments += len(cav_vehicles)

            congestion_count, congestion_text = self._format_congestion_edges()
            print(
                f"[{sim_step}s] 路径诱导决策(A*): 评估{len(cav_vehicles)}辆CAV，"
                f"{rerouted_count}辆CAV更改路径；拥堵候选路段{congestion_count}条",
                flush=True
            )
            print(f"    拥堵路段Top: {congestion_text}", flush=True)
        except:
            pass
    
    def save_route_changes(self, config_name: str, flow_level: int, pr: str):
        """
        保存路由变更记录（兼容接口）
        
        A*算法不记录详细的路由变更，此方法为空实现
        
        Args:
            config_name: 配置名称
            flow_level: 流量等级
            pr: 渗透率
        """
        # A*算法不记录详细的路由变更
        pass


def get_vehicle_destination(veh_id: str) -> Optional[str]:
    """
    获取车辆目的地
    
    Args:
        veh_id: 车辆ID
        
    Returns:
        Optional[str]: 目的地路段ID
    """
    try:
        route = traci.vehicle.getRoute(veh_id)
        if route and len(route) > 0:
            return route[-1]
        return None
    except:
        return None


def calculate_route_cost(route: List[str], edge_lengths: Dict[str, float]) -> float:
    """
    计算路径代价（总长度）
    
    Args:
        route: 路径（路段ID列表）
        edge_lengths: 路段长度字典
        
    Returns:
        float: 路径总长度
    """
    total_length = 0.0
    for edge_id in route:
        total_length += edge_lengths.get(edge_id, 100.0)
    return total_length


class EffortLogger:
    """
    路径规划日志记录器（占位符）
    保持与Effort方法的接口兼容
    """
    
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.route_changes = []
    
    def log_route_change(self, veh_id: str, old_route: List[str], new_route: List[str], 
                        old_cost: float, new_cost: float, reason: str = "astar"):
        """记录路径变化"""
        self.route_changes.append({
            'veh_id': veh_id,
            'old_route': old_route,
            'new_route': new_route,
            'old_cost': old_cost,
            'new_cost': new_cost,
            'reason': reason
        })
    
    def save_logs(self):
        """保存日志（占位符）"""
        pass
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'total_route_changes': len(self.route_changes)
        }
