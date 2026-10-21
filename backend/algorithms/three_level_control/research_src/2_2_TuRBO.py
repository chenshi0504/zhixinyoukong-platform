"""
TuRBO 信号优化算法（纯贝叶斯优化，无MPC状态转移）

文件编号: 2_2 (sig=2)
配置编码: 1_2_{flow}_X 表示使用纯 TuRBO 算法

与 MPC-TuRBO (2_1) 的区别：
- 2_1 MPC-TuRBO: 使用MPC状态转移模型预测未来状态，多步优化
- 2_2 TuRBO: 单步优化，直接最小化当前Webster延误，无状态转移建模

使用 siouxfalls/src/turbo/ 库进行贝叶斯优化
支持 GPU 加速（自动检测 CUDA）
"""
import os
import numpy as np
import pandas as pd
import traci
import sumolib
import torch
from typing import Dict, List, Tuple, Optional
from turbo import Turbo1


def get_device():
    """自动检测并返回最佳设备"""
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class TuRBOOptimizer:
    """纯TuRBO信号优化器（无MPC状态转移，支持GPU加速）"""
    
    SATURATION_FLOW_PER_LANE = 1800
    MIN_GREEN = 15
    MAX_GREEN = 60
    SAMPLE_INTERVAL = 10
    MAX_SAMPLES = 30
    
    def __init__(self, net_file: str, config_dir: str = None):
        self.net_file = net_file
        self.config_dir = config_dir
        self.net = None
        
        # GPU 设置
        self.device = get_device()
        self.use_gpu = (self.device == "cuda")
        
        # 优化参数
        self.optimization_interval = 300
        self.n_init = 10        # TuRBO初始采样点
        self.max_evals = 50     # TuRBO最大评估次数
        self.batch_size = 4     # TuRBO批量大小
        
        # 决策变量
        self.lb = None
        self.ub = None
        self.dim = 0
        
        # 交叉口信息
        self.intersections = {}
        self.edge_phase = {}
        self.saturation_flow = {}
        
        # 路网结构
        self.edge_downstream = {}
        
        # 状态
        self.current_timing = None
        
        # 控制
        self.enabled = False
        self.initialized = False
        
        # 输出
        self.green_time_records = []
        self.output_dir = None
        
        # 数据采集
        self.queue_history = {}
        self.flow_history = {}
        self.snapshot_queue = {}
        self.snapshot_flow = {}
        self.last_sample_time = 0
        
        # 优化统计
        self.optimization_count = 0
        self.best_objective = float('inf')
    
    # ========== 初始化 ==========
    
    def auto_initialize(self, data_dir: str = None):
        """自动初始化"""
        print("[TuRBO] Initializing...")
        
        # 尝试从XML加载配置
        if data_dir:
            xml_file = os.path.join(data_dir, 'signal_config.xml')
            if os.path.exists(xml_file):
                self._load_from_xml_file(xml_file)
                self.initialized = True
                return
        
        # 从路网提取
        self._extract_from_network()
        self.initialized = True
    
    def _load_from_xml_file(self, xml_file: str):
        """从XML文件加载配置"""
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
            
            # 加载路网
            self.net = sumolib.net.readNet(self.net_file)
            
            # 设置饱和流率
            for edge in self.net.getEdges():
                edge_id = edge.getID()
                if not edge_id.startswith(':'):
                    self.saturation_flow[edge_id] = edge.getLaneNumber() * self.SATURATION_FLOW_PER_LANE
            
            self._extract_downstream_from_network()
            
            print(f"  Loaded from: {xml_file}")
            print(f"  {self.dim} vars, {len(self.intersections)} intersections")
            
        except Exception as e:
            print(f"  Warning: XML load failed: {e}")
            self._extract_from_network()

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
                lb_list.append(self.MIN_GREEN)
                ub_list.append(self.MAX_GREEN)
                if i < len(incoming_edges):
                    self.edge_phase[incoming_edges[i]] = i * 2
            
            var_index += num_phases
        
        self.lb = np.array(lb_list, dtype=np.float64)
        self.ub = np.array(ub_list, dtype=np.float64)
        self.dim = len(self.lb)
        
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            if not edge_id.startswith(':'):
                self.saturation_flow[edge_id] = edge.getLaneNumber() * self.SATURATION_FLOW_PER_LANE
        
        self._extract_downstream_from_network()
        print(f"  Extracted: {self.dim} variables")
    
    def _extract_downstream_from_network(self):
        """从路网提取下游路段信息"""
        if self.net is None:
            return
        
        for edge in self.net.getEdges():
            edge_id = edge.getID()
            if edge_id.startswith(':'):
                continue
            
            if edge_id not in self.edge_downstream:
                to_node = edge.getToNode()
                for conn in to_node.getConnections():
                    if conn.getFrom().getID() == edge_id:
                        downstream_id = conn.getTo().getID()
                        if not downstream_id.startswith(':'):
                            self.edge_downstream[edge_id] = downstream_id
                            break
    
    # ========== 数据采集 ==========
    
    def collect_traffic_data(self, current_time: float):
        """从SUMO仿真中实时采集交通数据"""
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
    
    def clear_history(self):
        """清空历史"""
        self.queue_history = {}
        self.flow_history = {}
    
    # ========== TuRBO 目标函数 ==========
    
    def _objective_function(self, u: np.ndarray) -> float:
        """
        目标函数：计算当前配时的Webster延误（单步，无状态转移）
        
        与MPC-TuRBO的区别：
        - MPC-TuRBO: 多步预测，考虑状态转移
        - TuRBO: 单步优化，只考虑当前状态
        
        Args:
            u: 决策变量（绿灯时间）
        Returns:
            总延误（车·秒）
        """
        total_delay = 0.0
        
        for tl_id, info in self.intersections.items():
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            incoming_edges = info.get('incoming_edges', [])
            
            for p in range(num_phases):
                g = u[begin + p] if begin + p < len(u) else 30
                g = max(g, self.MIN_GREEN)
                lambda_i = g / cycle  # 绿信比
                
                # 获取相位数据
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                queue = self.snapshot_queue.get(edge_id, 0) if edge_id else 0
                flow = self.snapshot_flow.get(edge_id, 500) if edge_id else 500
                S = self.saturation_flow.get(edge_id, 3600) if edge_id else 3600
                
                # 饱和度
                capacity = S * lambda_i
                x = flow / capacity if capacity > 0 else 0.5
                x = min(x, 0.95)
                
                # Webster延误模型
                # d_uniform = C(1-λ)² / [2(1-λx)]
                denom = 1 - lambda_i * x
                if denom > 0.01:
                    d_uniform = cycle * (1 - lambda_i)**2 / (2 * denom)
                else:
                    d_uniform = cycle * (1 - lambda_i) / 2
                
                # d_random = x² / [2q(1-x)]
                if flow > 0 and x < 1:
                    q_per_sec = flow / 3600
                    d_random = x**2 / (2 * q_per_sec * max(1 - x, 0.01))
                    d_random = min(d_random, cycle * 0.5)
                else:
                    d_random = 0
                
                # 排队消散延迟
                service_rate = (S / 3600) * lambda_i
                if service_rate > 0 and queue > 0:
                    queue_delay = queue * queue / (2 * service_rate)
                    queue_delay = min(queue_delay, queue * cycle)
                else:
                    queue_delay = 0
                
                # 到达车辆数
                arrivals = (flow / 3600) * 90  # 90秒控制周期
                arrivals = max(arrivals, 0.1)
                
                # 总延误
                phase_delay = (d_uniform + d_random) * arrivals + queue_delay
                total_delay += phase_delay
        
        return total_delay

    # ========== TuRBO 优化 ==========
    
    def optimize(self) -> np.ndarray:
        """
        执行TuRBO优化（支持GPU加速）
        
        使用Turbo1进行贝叶斯优化，寻找最优绿灯时间配置
        自动检测CUDA并启用GPU加速
        
        Returns:
            最优绿灯时间配置
        """
        if self.dim == 0:
            return None
        
        print(f"  [TuRBO] Starting optimization...")
        print(f"    Dimensions: {self.dim}")
        print(f"    Bounds: [{self.MIN_GREEN}, {self.MAX_GREEN}]")
        print(f"    n_init: {self.n_init}, max_evals: {self.max_evals}")
        print(f"    Device: {self.device} {'(GPU accelerated)' if self.use_gpu else '(CPU)'}")
        
        # 创建TuRBO优化器（启用GPU加速）
        turbo = Turbo1(
            f=self._objective_function,
            lb=self.lb,
            ub=self.ub,
            n_init=self.n_init,
            max_evals=self.max_evals,
            batch_size=self.batch_size,
            verbose=False,
            device=self.device,  # GPU加速
            dtype="float64"
        )
        
        # 执行优化
        turbo.optimize()
        
        # 获取最优解
        best_idx = np.argmin(turbo.fX)
        optimal = turbo.X[best_idx].copy()
        best_obj = turbo.fX[best_idx][0]
        
        # 应用周期约束
        optimal = self._apply_cycle_constraint(optimal)
        
        print(f"    Best objective: {best_obj:.2f}")
        print(f"    Optimal greens (first 8): {[int(t) for t in optimal[:8]]}")
        
        # 更新统计
        if best_obj < self.best_objective:
            self.best_objective = best_obj
        
        return optimal
    
    def _apply_cycle_constraint(self, u: np.ndarray) -> np.ndarray:
        """应用周期约束"""
        result = u.copy()
        
        for tl_id, info in self.intersections.items():
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            
            # 获取该交叉口的绿灯时间
            greens = result[begin:end+1]
            total = sum(greens)
            
            # 按比例调整
            if total > 0 and abs(total - cycle) > 0.1:
                scale = cycle / total
                for i in range(len(greens)):
                    result[begin + i] = np.clip(greens[i] * scale, self.MIN_GREEN, self.MAX_GREEN)
        
        return result
    
    # ========== 应用配时 ==========
    
    def apply_timing(self, u: np.ndarray, current_time: float = 0):
        """应用优化后的配时"""
        self.current_timing = u.copy()
        
        for tl_id, info in self.intersections.items():
            try:
                programs = traci.trafficlight.getAllProgramLogics(tl_id)
                if not programs:
                    continue
                program = programs[0]
                
                begin, end = info['begin'], info['end']
                green_times = list(map(float, u[begin:end+1]))
                
                # 周期约束
                cycle = info['cycle']
                total_green = sum(green_times)
                if total_green > 0 and abs(total_green - cycle) > 0.1:
                    scale = cycle / total_green
                    green_times = [g * scale for g in green_times]
                
                green_times = [max(int(self.MIN_GREEN), min(int(self.MAX_GREEN), int(round(g)))) 
                               for g in green_times]
                
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
    
    # ========== 仿真步进 ==========
    
    def step(self, current_time: float):
        """
        仿真步进 - TuRBO信号优化
        
        Args:
            current_time: 当前仿真时间（秒）
        """
        if not self.enabled:
            return
        
        WARMUP_TIME = 600  # 预热时间（秒）
        
        # 持续采集数据
        self.collect_traffic_data(current_time)
        
        # 预热期不优化
        if current_time < WARMUP_TIME:
            return
        
        # 第一次优化（预热结束后）
        if current_time == WARMUP_TIME:
            self.optimization_count = 1
            self._run_optimization(current_time, is_first=True)
            return
        
        # 常规优化周期
        time_since_warmup = current_time - WARMUP_TIME
        if time_since_warmup > 0 and time_since_warmup % self.optimization_interval == 0:
            self.optimization_count += 1
            self._run_optimization(current_time, is_first=False)
    
    def _run_optimization(self, current_time: float, is_first: bool = False):
        """执行一次优化"""
        print(f"\n{'='*60}")
        print(f"[TuRBO] Optimization #{self.optimization_count} at t={current_time}s")
        print(f"{'='*60}")
        
        if is_first:
            print(f"  Algorithm: TuRBO (Trust Region Bayesian Optimization)")
            print(f"  Objective: Webster delay model (single-step)")
            print(f"  Optimization interval: {self.optimization_interval}s")
            print(f"{'='*60}")
        
        # 创建快照
        self.create_snapshot()
        
        # 输出交叉口10和16的状态
        self._print_intersection_status(['10', '16'])
        
        # 执行优化
        optimal = self.optimize()
        if optimal is not None:
            self.apply_timing(optimal, current_time)
            print(f"  ✓ Signal timing applied to {len(self.intersections)} intersections")
            
            # 输出优化后的交叉口10和16配时
            self._print_optimized_timing(['10', '16'], optimal)
        
        self.clear_history()

    def _print_intersection_status(self, tl_ids: List[str]):
        """输出指定交叉口的状态"""
        print(f"\n  [Intersection Status]")
        
        for tl_id in tl_ids:
            if tl_id not in self.intersections:
                continue
            
            info = self.intersections[tl_id]
            incoming_edges = info.get('incoming_edges', [])
            num_phases = info['end'] - info['begin'] + 1
            
            queues = []
            vehicles = []
            pressures = []
            
            for p in range(num_phases):
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                q = 0
                v = 0
                
                if edge_id:
                    try:
                        q = traci.edge.getLastStepHaltingNumber(edge_id)
                        v = traci.edge.getLastStepVehicleNumber(edge_id)
                    except:
                        q = self.snapshot_queue.get(edge_id, 0)
                        v = int(self.snapshot_flow.get(edge_id, 0) / 3600 * 90)
                
                queues.append(int(q))
                vehicles.append(int(v))
                pressures.append(int(v + q * 2))
            
            print(f"  Intersection {tl_id} ({num_phases} phases):")
            print(f"    edges: {incoming_edges}")
            print(f"    queue: {queues}, vehicles: {vehicles}")
            print(f"    pressures: {pressures}")
    
    def _print_optimized_timing(self, tl_ids: List[str], optimal: np.ndarray):
        """输出优化后的配时"""
        print(f"\n  [Optimized Timing]")
        
        for tl_id in tl_ids:
            if tl_id not in self.intersections:
                continue
            
            info = self.intersections[tl_id]
            begin, end = info['begin'], info['end']
            greens = [int(optimal[begin + p]) for p in range(end - begin + 1)]
            
            print(f"  Intersection {tl_id}: greens={greens}")
    
    # ========== 输出 ==========
    
    def set_output_dir(self, output_dir: str):
        """设置输出目录"""
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
    
    def save_green_times_to_excel(self, filename: str = None):
        """保存绿灯时长到Excel"""
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
        
        self.print_optimization_summary()
        print(f"  Green times saved: {output_path}")
    
    def print_optimization_summary(self):
        """打印TuRBO优化总结"""
        print(f"\n{'='*60}")
        print(f"[TuRBO] Optimization Summary")
        print(f"{'='*60}")
        print(f"  Algorithm: TuRBO (Trust Region Bayesian Optimization)")
        print(f"  Total optimizations: {self.optimization_count}")
        print(f"  Optimization interval: {self.optimization_interval}s")
        print(f"  Intersections controlled: {len(self.intersections)}")
        print(f"  Decision variables: {self.dim}")
        print(f"  Best objective: {self.best_objective:.2f}")
        
        if self.green_time_records:
            df = pd.DataFrame(self.green_time_records)
            initial = df[df['time'] == 0]['green_time'].values
            final_time = df['time'].max()
            final = df[df['time'] == final_time]['green_time'].values
            
            if len(initial) > 0 and len(final) > 0:
                print(f"  Initial avg green: {np.mean(initial):.1f}s")
                print(f"  Final avg green: {np.mean(final):.1f}s")
                print(f"  Green time range: [{df['green_time'].min():.0f}s, {df['green_time'].max():.0f}s]")
        
        print(f"{'='*60}")
