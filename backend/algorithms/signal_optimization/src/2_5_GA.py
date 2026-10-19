"""
遗传算法 (Genetic Algorithm) 信号优化

文件编号: 2_7 (sig=7)
配置编码: 1_7_{flow}_X 表示使用GA算法

传统元启发式优化方法，用于对比实验
验证贝叶斯优化相对于传统方法的优势

特点：
- 基于种群的全局搜索
- 选择、交叉、变异操作
- 无需梯度信息
"""
import os
import numpy as np
import pandas as pd
import traci
import sumolib
from typing import Dict, List, Tuple, Optional


class GAOptimizer:
    """
    遗传算法信号优化器
    
    用于对比实验，验证贝叶斯优化的优势
    """
    
    SATURATION_FLOW_PER_LANE = 1800
    MIN_GREEN = 15
    MAX_GREEN = 60
    SAMPLE_INTERVAL = 10
    MAX_SAMPLES = 30
    
    # GA超参数（改进版：更强的搜索能力）
    POPULATION_SIZE = 40      # 增大种群
    GENERATIONS = 20          # 增加代数
    CROSSOVER_RATE = 0.8      # 提高交叉率
    MUTATION_RATE = 0.1       # 提高变异率
    ELITE_SIZE = 4            # 精英数量
    TOURNAMENT_SIZE = 3       # 锦标赛规模
    IMPROVEMENT_THRESHOLD = 0.98  # 降低阈值，更容易应用改进
    
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
        self.generation_history = []  # 记录每代最优
        self.best_solution = None     # 历史最优解（用于下一轮初始化）
    
    def auto_initialize(self, data_dir: str = None):
        """自动初始化"""
        print("[GA] Initializing...")
        
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
    
    def _compute_webster_prior(self) -> np.ndarray:
        """
        计算 Webster 先验配时
        
        基于 Webster 最优周期公式，为 GA 提供一个好的起点
        """
        webster_timing = np.ones(self.dim) * 30  # 默认30秒
        
        for tl_id, info in self.intersections.items():
            cycle = info['cycle']
            begin, end = info['begin'], info['end']
            num_phases = end - begin + 1
            incoming_edges = info.get('incoming_edges', [])
            
            # 计算各相位的流量比
            y_values = []
            for p in range(num_phases):
                edge_id = incoming_edges[p] if p < len(incoming_edges) else None
                if edge_id:
                    q = self.snapshot_flow.get(edge_id, 500)  # 默认流量
                    s = self.saturation_flow.get(edge_id, 1800)
                    y = q / s if s > 0 else 0.3
                else:
                    y = 0.3  # 默认流量比
                y_values.append(min(y, 0.9))  # 限制最大流量比
            
            total_y = sum(y_values)
            if total_y <= 0:
                total_y = 0.3 * num_phases
            
            # Webster 绿灯时间分配
            effective_green = cycle - 4 * num_phases  # 扣除损失时间
            for p in range(num_phases):
                if total_y > 0:
                    g = effective_green * (y_values[p] / total_y)
                else:
                    g = effective_green / num_phases
                g = np.clip(g, self.MIN_GREEN, self.MAX_GREEN)
                webster_timing[begin + p] = g
        
        return webster_timing
    
    def _initialize_population(self) -> np.ndarray:
        """
        初始化种群（改进版：利用 Webster 先验和历史最优解）
        
        策略：
        - 加入 Webster 先验配时作为种子
        - 如果有历史最优解，将其作为种群的一部分
        - 在先验周围生成变异个体
        - 其余个体随机生成，保持多样性
        """
        population = []
        
        # 1. 计算 Webster 先验配时
        webster_prior = self._compute_webster_prior()
        population.append(webster_prior.copy())
        
        # 2. 在 Webster 先验周围生成变异个体（占种群的30%）
        num_webster_mutants = int(self.POPULATION_SIZE * 0.3)
        for _ in range(num_webster_mutants):
            mutant = webster_prior.copy()
            for i in range(self.dim):
                if np.random.rand() < 0.4:  # 40%的维度变异
                    sigma = (self.ub[i] - self.lb[i]) * 0.15
                    mutant[i] += np.random.normal(0, sigma)
                    mutant[i] = np.clip(mutant[i], self.lb[i], self.ub[i])
            population.append(mutant)
        
        # 3. 如果有历史最优解，加入种群
        if self.best_solution is not None:
            population.append(self.best_solution.copy())
            
            # 在历史最优解周围生成变异个体（占种群的20%）
            num_mutants = int(self.POPULATION_SIZE * 0.2)
            for _ in range(num_mutants):
                mutant = self.best_solution.copy()
                for i in range(self.dim):
                    if np.random.rand() < 0.3:
                        sigma = (self.ub[i] - self.lb[i]) * 0.1
                        mutant[i] += np.random.normal(0, sigma)
                        mutant[i] = np.clip(mutant[i], self.lb[i], self.ub[i])
                population.append(mutant)
        
        # 4. 如果有当前配时，也加入种群
        if self.current_timing is not None and len(population) < self.POPULATION_SIZE:
            population.append(self.current_timing.copy())
        
        # 5. 其余随机生成
        while len(population) < self.POPULATION_SIZE:
            individual = np.random.uniform(self.lb, self.ub)
            population.append(individual)
        
        return np.array(population[:self.POPULATION_SIZE])
    

    
    def _evaluate_population(self, population: np.ndarray) -> np.ndarray:
        """评估种群适应度"""
        fitness = np.array([self._objective_function(ind) for ind in population])
        return fitness
    
    def _tournament_selection(self, population: np.ndarray, fitness: np.ndarray) -> np.ndarray:
        """锦标赛选择"""
        selected = []
        for _ in range(self.POPULATION_SIZE - self.ELITE_SIZE):
            # 随机选择参赛者
            indices = np.random.choice(len(population), self.TOURNAMENT_SIZE, replace=False)
            # 选择最优者
            winner_idx = indices[np.argmin(fitness[indices])]
            selected.append(population[winner_idx].copy())
        return np.array(selected)
    
    def _crossover(self, parent1: np.ndarray, parent2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """均匀交叉"""
        if np.random.rand() > self.CROSSOVER_RATE:
            return parent1.copy(), parent2.copy()
        
        mask = np.random.rand(self.dim) < 0.5
        child1 = np.where(mask, parent1, parent2)
        child2 = np.where(mask, parent2, parent1)
        
        return child1, child2
    
    def _mutate(self, individual: np.ndarray) -> np.ndarray:
        """
        自适应高斯变异
        
        变异强度根据当前代数自适应调整
        """
        mutated = individual.copy()
        
        # 自适应变异率：早期高，后期低
        adaptive_rate = self.MUTATION_RATE * (1 + 0.5 * (1 - self.current_generation / self.GENERATIONS))
        
        for i in range(self.dim):
            if np.random.rand() < adaptive_rate:
                # 自适应变异强度
                sigma = (self.ub[i] - self.lb[i]) * 0.15
                mutated[i] += np.random.normal(0, sigma)
                mutated[i] = np.clip(mutated[i], self.lb[i], self.ub[i])
        
        return mutated
    
    def _apply_cycle_constraint(self, individual: np.ndarray) -> np.ndarray:
        """应用周期约束"""
        result = individual.copy()
        
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
        执行遗传算法优化（保守版）
        
        核心改进：如果当前配时已经不错，就保持不变
        
        Returns:
            最优绿灯时间配置
        """
        if self.dim == 0:
            return None
        
        print(f"  [GA] Starting optimization...")
        print(f"    Dimensions: {self.dim}")
        print(f"    Population: {self.POPULATION_SIZE}, Generations: {self.GENERATIONS}")
        print(f"    Crossover: {self.CROSSOVER_RATE}, Mutation: {self.MUTATION_RATE}")
        

        
        # 初始化种群
        population = self._initialize_population()
        fitness = self._evaluate_population(population)
        
        # 记录初始最优
        best_idx = np.argmin(fitness)
        best_individual = population[best_idx].copy()
        best_fitness = fitness[best_idx]
        
        self.generation_history = [(0, best_fitness)]
        
        # 记录当前代数（用于自适应变异）
        self.current_generation = 0
        
        # 进化迭代
        for gen in range(self.GENERATIONS):
            self.current_generation = gen
            
            # 精英保留
            elite_indices = np.argsort(fitness)[:self.ELITE_SIZE]
            elites = population[elite_indices].copy()
            
            # 选择
            selected = self._tournament_selection(population, fitness)
            
            # 交叉
            offspring = []
            for i in range(0, len(selected) - 1, 2):
                child1, child2 = self._crossover(selected[i], selected[i+1])
                offspring.extend([child1, child2])
            
            # 如果offspring数量不够，补充
            while len(offspring) < self.POPULATION_SIZE - self.ELITE_SIZE:
                offspring.append(selected[np.random.randint(len(selected))].copy())
            
            # 变异
            offspring = [self._mutate(ind) for ind in offspring[:self.POPULATION_SIZE - self.ELITE_SIZE]]
            
            # 应用约束
            offspring = [self._apply_cycle_constraint(ind) for ind in offspring]
            
            # 合并精英和后代
            population = np.vstack([elites, offspring])
            
            # 评估
            fitness = self._evaluate_population(population)
            
            # 更新最优
            gen_best_idx = np.argmin(fitness)
            if fitness[gen_best_idx] < best_fitness:
                best_fitness = fitness[gen_best_idx]
                best_individual = population[gen_best_idx].copy()
            
            self.generation_history.append((gen + 1, best_fitness))
        
        # 应用周期约束
        optimal = self._apply_cycle_constraint(best_individual)
        
        print(f"    Best objective: {best_fitness:.2f}")
        print(f"    Optimal greens (first 8): {[int(t) for t in optimal[:8]]}")
        
        # 更新历史最优解
        if best_fitness < self.best_objective:
            self.best_objective = best_fitness
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
        print(f"[GA] Optimization #{self.optimization_count} at t={current_time}s")
        print(f"{'='*60}")
        
        if is_first:
            print(f"  Algorithm: Genetic Algorithm")
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
        
        print(f"\n[GA] Summary")
        print(f"  Total optimizations: {self.optimization_count}")
        print(f"  Best objective: {self.best_objective:.2f}")
        print(f"  Green times saved: {output_path}")
