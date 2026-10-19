"""
粒子群优化算法 (Particle Swarm Optimization) 信号优化

文件编号: 2_8 (sig=8)
配置编码: 1_8_{flow}_X 表示使用PSO算法

传统元启发式优化方法，用于对比实验
验证贝叶斯优化相对于传统方法的优势

特点：
- 基于群体智能的全局搜索
- 粒子速度-位置更新机制
- 收敛速度快，但容易早熟收敛
- 天然适合连续优化问题（如信号配时）
"""
import os
import numpy as np
import pandas as pd
import traci
import sumolib
from typing import Dict, List, Tuple, Optional


class PSOOptimizer:
    """
    粒子群优化信号优化器
    
    用于对比实验，验证贝叶斯优化的优势
    PSO特点：收敛快但容易陷入局部最优
    """
    
    SATURATION_FLOW_PER_LANE = 1800
    MIN_GREEN = 15
    MAX_GREEN = 60
    SAMPLE_INTERVAL = 10
    MAX_SAMPLES = 30
    
    # PSO超参数（保守设置）
    SWARM_SIZE = 20           # 粒子数量
    MAX_ITERATIONS = 15       # 最大迭代次数
    W_START = 0.9             # 初始惯性权重
    W_END = 0.4               # 最终惯性权重
    C1 = 1.5                  # 认知系数（个体学习因子）
    C2 = 1.5                  # 社会系数（群体学习因子）
    V_MAX_RATIO = 0.2         # 最大速度比例（相对于搜索范围）
    
    def __init__(self, net_file: str, config_dir: str = None):
        self.net_file = net_file
        self.config_dir = config_dir
        self.net = None
        
        # 优化参数
        self.optimization_interval = 300
        
        # 决策变量
        self.lb = None
        self.ub = None
        self.dim = 0
        
        # 交叉口信息
        self.intersections = {}
        self.edge_phase = {}
        self.saturation_flow = {}
        
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
        self.iteration_history = []
        self.best_solution = None     # 历史最优解（用于下一轮初始化）
    
    def auto_initialize(self, data_dir: str = None):
        """自动初始化"""
        print("[PSO] Initializing...")
        
        if data_dir:
            xml_file = os.path.join(data_dir, 'signal_config.xml')
            if os.path.exists(xml_file):
                self._load_from_xml_file(xml_file)
                self.initialized = True
                return
        
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
            
            self.net = sumolib.net.readNet(self.net_file)
            
            for edge in self.net.getEdges():
                edge_id = edge.getID()
                if not edge_id.startswith(':'):
                    self.saturation_flow[edge_id] = edge.getLaneNumber() * self.SATURATION_FLOW_PER_LANE
            
            print(f"  Loaded from: {xml_file}")
            print(f"  {self.dim} vars, {len(self.intersections)} intersections")
            
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
    
    def _objective_function(self, u: np.ndarray) -> float:
        """目标函数：Webster延误"""
        total_delay = 0.0
        
        for tl_id, info in self.intersections.items():
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            incoming_edges = info.get('incoming_edges', [])
            
            for p in range(num_phases):
                g = u[begin + p] if begin + p < len(u) else 30
                g = max(g, self.MIN_GREEN)
                lambda_i = g / cycle
                
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                queue = self.snapshot_queue.get(edge_id, 0) if edge_id else 0
                flow = self.snapshot_flow.get(edge_id, 500) if edge_id else 500
                S = self.saturation_flow.get(edge_id, 3600) if edge_id else 3600
                
                capacity = S * lambda_i
                x = flow / capacity if capacity > 0 else 0.5
                x = min(x, 0.95)
                
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

    def _initialize_swarm(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        初始化粒子群（改进版：利用历史最优解）
        
        策略：
        - 如果有历史最优解，将其作为粒子之一
        - 在历史最优解周围生成变异粒子
        - 其余粒子随机生成，保持多样性
        
        Returns:
            positions: 粒子位置 (swarm_size, dim)
            velocities: 粒子速度 (swarm_size, dim)
        """
        positions = []
        
        # 1. 如果有历史最优解，加入粒子群
        if self.best_solution is not None:
            positions.append(self.best_solution.copy())
            
            # 2. 在历史最优解周围生成变异粒子（占粒子群的40%）
            num_mutants = int(self.SWARM_SIZE * 0.4)
            for _ in range(num_mutants):
                mutant = self.best_solution.copy()
                # 小范围变异
                for i in range(self.dim):
                    if np.random.rand() < 0.3:  # 30%的维度变异
                        sigma = (self.ub[i] - self.lb[i]) * 0.1  # 10%范围内变异
                        mutant[i] += np.random.normal(0, sigma)
                        mutant[i] = np.clip(mutant[i], self.lb[i], self.ub[i])
                positions.append(mutant)
        
        # 3. 如果有当前配时，也加入粒子群
        if self.current_timing is not None and len(positions) < self.SWARM_SIZE:
            positions.append(self.current_timing.copy())
        
        # 4. 其余随机生成
        while len(positions) < self.SWARM_SIZE:
            individual = np.random.uniform(self.lb, self.ub)
            positions.append(individual)
        
        positions = np.array(positions[:self.SWARM_SIZE])
        
        # 初始化速度（小随机值）
        v_max = (self.ub - self.lb) * self.V_MAX_RATIO
        velocities = np.random.uniform(-v_max, v_max, size=(self.SWARM_SIZE, self.dim))
        
        return positions, velocities
    

    
    def _apply_cycle_constraint(self, position: np.ndarray) -> np.ndarray:
        """应用周期约束"""
        result = position.copy()
        
        for tl_id, info in self.intersections.items():
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            
            greens = result[begin:end+1]
            total = sum(greens)
            
            if total > 0 and abs(total - cycle) > 0.1:
                scale = cycle / total
                for i in range(len(greens)):
                    result[begin + i] = np.clip(greens[i] * scale, self.MIN_GREEN, self.MAX_GREEN)
        
        return result
    
    def optimize(self) -> np.ndarray:
        """
        执行粒子群优化
        
        PSO核心公式：
        v_i(t+1) = w * v_i(t) + c1 * r1 * (pbest_i - x_i) + c2 * r2 * (gbest - x_i)
        x_i(t+1) = x_i(t) + v_i(t+1)
        
        Returns:
            最优绿灯时间配置
        """
        if self.dim == 0:
            return None
        
        print(f"  [PSO] Starting optimization...")
        print(f"    Dimensions: {self.dim}")
        print(f"    Swarm size: {self.SWARM_SIZE}, Iterations: {self.MAX_ITERATIONS}")
        print(f"    w: {self.W_START}->{self.W_END}, c1={self.C1}, c2={self.C2}")
        

        
        # 初始化粒子群
        positions, velocities = self._initialize_swarm()
        
        # 计算最大速度
        v_max = (self.ub - self.lb) * self.V_MAX_RATIO
        
        # 评估初始适应度
        fitness = np.array([self._objective_function(p) for p in positions])
        
        # 初始化个体最优和全局最优
        pbest_positions = positions.copy()
        pbest_fitness = fitness.copy()
        
        gbest_idx = np.argmin(fitness)
        gbest_position = positions[gbest_idx].copy()
        gbest_fitness = fitness[gbest_idx]
        
        self.iteration_history = [(0, gbest_fitness)]
        
        # 迭代优化
        for iteration in range(self.MAX_ITERATIONS):
            # 线性递减惯性权重
            w = self.W_START - (self.W_START - self.W_END) * iteration / self.MAX_ITERATIONS
            
            for i in range(self.SWARM_SIZE):
                # 随机系数
                r1 = np.random.rand(self.dim)
                r2 = np.random.rand(self.dim)
                
                # 更新速度
                cognitive = self.C1 * r1 * (pbest_positions[i] - positions[i])
                social = self.C2 * r2 * (gbest_position - positions[i])
                velocities[i] = w * velocities[i] + cognitive + social
                
                # 速度限制
                velocities[i] = np.clip(velocities[i], -v_max, v_max)
                
                # 更新位置
                positions[i] = positions[i] + velocities[i]
                
                # 边界处理（反弹策略）
                for d in range(self.dim):
                    if positions[i, d] < self.lb[d]:
                        positions[i, d] = self.lb[d]
                        velocities[i, d] *= -0.5  # 反弹
                    elif positions[i, d] > self.ub[d]:
                        positions[i, d] = self.ub[d]
                        velocities[i, d] *= -0.5
                
                # 应用周期约束
                positions[i] = self._apply_cycle_constraint(positions[i])
                
                # 评估新位置
                new_fitness = self._objective_function(positions[i])
                fitness[i] = new_fitness
                
                # 更新个体最优
                if new_fitness < pbest_fitness[i]:
                    pbest_fitness[i] = new_fitness
                    pbest_positions[i] = positions[i].copy()
                    
                    # 更新全局最优
                    if new_fitness < gbest_fitness:
                        gbest_fitness = new_fitness
                        gbest_position = positions[i].copy()
            
            self.iteration_history.append((iteration + 1, gbest_fitness))
        
        # 应用周期约束
        optimal = self._apply_cycle_constraint(gbest_position)
        
        print(f"    Best objective: {gbest_fitness:.2f}")
        print(f"    Optimal greens (first 8): {[int(t) for t in optimal[:8]]}")
        
        # 更新历史最优解
        if gbest_fitness < self.best_objective:
            self.best_objective = gbest_fitness
            self.best_solution = optimal.copy()
        elif self.best_solution is None:
            # 第一次优化，保存当前最优
            self.best_solution = optimal.copy()
        
        return optimal
    
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
    
    def step(self, current_time: float):
        """仿真步进"""
        if not self.enabled:
            return
        
        WARMUP_TIME = 600
        
        self.collect_traffic_data(current_time)
        
        if current_time < WARMUP_TIME:
            return
        
        if current_time == WARMUP_TIME:
            self.optimization_count = 1
            self._run_optimization(current_time, is_first=True)
            return
        
        time_since_warmup = current_time - WARMUP_TIME
        if time_since_warmup > 0 and time_since_warmup % self.optimization_interval == 0:
            self.optimization_count += 1
            self._run_optimization(current_time, is_first=False)
    
    def _run_optimization(self, current_time: float, is_first: bool = False):
        """执行一次优化"""
        print(f"\n{'='*60}")
        print(f"[PSO] Optimization #{self.optimization_count} at t={current_time}s")
        print(f"{'='*60}")
        
        if is_first:
            print(f"  Algorithm: Particle Swarm Optimization")
            print(f"  Purpose: Traditional metaheuristic baseline")
            print(f"  Optimization interval: {self.optimization_interval}s")
            print(f"{'='*60}")
        
        self.create_snapshot()
        
        optimal = self.optimize()
        if optimal is not None:
            self.apply_timing(optimal, current_time)
            print(f"  ✓ Signal timing applied to {len(self.intersections)} intersections")
        
        self.clear_history()
    
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
        
        print(f"\n[PSO] Summary")
        print(f"  Total optimizations: {self.optimization_count}")
        print(f"  Best objective: {self.best_objective:.2f}")
        print(f"  Green times saved: {output_path}")
