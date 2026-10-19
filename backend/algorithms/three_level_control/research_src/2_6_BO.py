"""
标准贝叶斯优化 (Bayesian Optimization) 信号优化

文件编号: 2_6 (sig=6)
配置编码: 1_6_{flow}_X 表示使用标准BO算法

消融实验：验证TuRBO信赖域机制的贡献
与TuRBO的区别：无信赖域约束，全局搜索

特点：
- 标准高斯过程代理模型
- 全局采集函数优化（无信赖域）
- 用于消融实验，验证信赖域机制的贡献
"""
import os
import numpy as np
import pandas as pd
import traci
import sumolib
import torch
from typing import Dict, List, Optional

# 尝试导入botorch
try:
    from botorch.models import SingleTaskGP
    from botorch.fit import fit_gpytorch_mll
    from botorch.acquisition import ExpectedImprovement
    from botorch.optim import optimize_acqf
    from gpytorch.mlls import ExactMarginalLogLikelihood
    BOTORCH_AVAILABLE = True
except ImportError:
    BOTORCH_AVAILABLE = False
    print("Warning: botorch not available, BO optimizer will use fallback")


def get_device():
    """自动检测并返回最佳设备"""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class BOOptimizer:
    """
    标准贝叶斯优化信号优化器（无信赖域，用于消融实验）
    
    与TuRBO的区别：
    - TuRBO: 使用信赖域约束搜索空间
    - BO: 全局搜索，无信赖域约束
    """
    
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
        self.dtype = torch.float64
        
        # 优化参数
        self.optimization_interval = 300
        self.n_init = 5         # 减少初始采样点
        self.max_evals = 20     # 减少最大评估次数（避免过长运行）
        
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
        
        # BO历史数据
        self.X_history = []
        self.Y_history = []
    
    def auto_initialize(self, data_dir: str = None):
        """自动初始化"""
        print("[BO] Initializing...")
        
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
    
    def _generate_initial_samples(self, n_samples: int) -> np.ndarray:
        """生成初始采样点（拉丁超立方采样）"""
        samples = np.zeros((n_samples, self.dim))
        
        for i in range(self.dim):
            # 拉丁超立方采样
            perm = np.random.permutation(n_samples)
            samples[:, i] = (perm + np.random.rand(n_samples)) / n_samples
            samples[:, i] = self.lb[i] + samples[:, i] * (self.ub[i] - self.lb[i])
        
        return samples
    
    def optimize(self) -> np.ndarray:
        """
        执行标准贝叶斯优化（无信赖域）
        
        Returns:
            最优绿灯时间配置
        """
        if self.dim == 0:
            return None
        
        print(f"  [BO] Starting optimization...")
        print(f"    Dimensions: {self.dim}")
        print(f"    n_init: {self.n_init}, max_evals: {self.max_evals}")
        print(f"    Device: {self.device}")
        
        # 初始采样
        X_init = self._generate_initial_samples(self.n_init)
        Y_init = np.array([self._objective_function(x) for x in X_init]).reshape(-1, 1)
        
        best_x = X_init[np.argmin(Y_init)]
        best_y = np.min(Y_init)
        
        print(f"    Initial best: {best_y:.2f}")
        
        if BOTORCH_AVAILABLE:
            try:
                # 转换为tensor
                train_X = torch.tensor(X_init, dtype=self.dtype, device=self.device)
                train_Y = torch.tensor(-Y_init, dtype=self.dtype, device=self.device)  # 取负（最大化）
                
                # 归一化边界
                bounds = torch.tensor(
                    np.vstack([self.lb, self.ub]), 
                    dtype=self.dtype, 
                    device=self.device
                )
                
                # 使用botorch进行优化
                for i in range(self.max_evals - self.n_init):
                    try:
                        # 归一化训练数据
                        train_X_normalized = (train_X - bounds[0]) / (bounds[1] - bounds[0])
                        
                        # 标准化Y值以提高数值稳定性
                        Y_mean = train_Y.mean()
                        Y_std = train_Y.std() + 1e-6
                        train_Y_normalized = (train_Y - Y_mean) / Y_std
                        
                        # 拟合GP模型
                        model = SingleTaskGP(train_X_normalized, train_Y_normalized)
                        mll = ExactMarginalLogLikelihood(model.likelihood, model)
                        fit_gpytorch_mll(mll)
                        
                        # 优化采集函数（EI）
                        best_f_normalized = (train_Y.max() - Y_mean) / Y_std
                        EI = ExpectedImprovement(model, best_f=best_f_normalized)
                        
                        candidate_normalized, _ = optimize_acqf(
                            EI,
                            bounds=torch.tensor([[0.0]*self.dim, [1.0]*self.dim], 
                                               dtype=self.dtype, device=self.device),
                            q=1,
                            num_restarts=3,
                            raw_samples=10,
                        )
                        
                        # 反归一化
                        candidate = candidate_normalized * (bounds[1] - bounds[0]) + bounds[0]
                        new_x = candidate.cpu().numpy().flatten()
                        
                        # 评估
                        new_y = self._objective_function(new_x)
                        
                        # 更新数据
                        train_X = torch.cat([train_X, candidate])
                        train_Y = torch.cat([train_Y, torch.tensor([[-new_y]], dtype=self.dtype, device=self.device)])
                        
                        if new_y < best_y:
                            best_y = new_y
                            best_x = new_x
                            print(f"    Iter {i+1}: New best = {best_y:.2f}")
                    except Exception as e:
                        print(f"    Iter {i+1}: GP fitting failed ({e}), using random sample")
                        new_x = np.random.uniform(self.lb, self.ub)
                        new_y = self._objective_function(new_x)
                        if new_y < best_y:
                            best_y = new_y
                            best_x = new_x
            except Exception as e:
                print(f"    BO failed: {e}, using random search fallback")
                for i in range(self.max_evals - self.n_init):
                    new_x = np.random.uniform(self.lb, self.ub)
                    new_y = self._objective_function(new_x)
                    if new_y < best_y:
                        best_y = new_y
                        best_x = new_x
        else:
            # 回退：随机搜索
            print("    Using random search fallback...")
            for i in range(self.max_evals - self.n_init):
                new_x = np.random.uniform(self.lb, self.ub)
                new_y = self._objective_function(new_x)
                
                if new_y < best_y:
                    best_y = new_y
                    best_x = new_x
        
        # 应用周期约束
        optimal = self._apply_cycle_constraint(best_x)
        
        print(f"    Best objective: {best_y:.2f}")
        print(f"    Optimal greens (first 8): {[int(t) for t in optimal[:8]]}")
        
        if best_y < self.best_objective:
            self.best_objective = best_y
        
        return optimal
    
    def _apply_cycle_constraint(self, u: np.ndarray) -> np.ndarray:
        """应用周期约束"""
        result = u.copy()
        
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
                
                cycle = info['cycle']
                total_green = sum(green_times)
                if total_green > 0 and abs(total_green - cycle) > 0.1:
                    scale = cycle / total_green
                    green_times = [g * scale for g in green_times]
                
                green_times = [max(int(self.MIN_GREEN), min(int(self.MAX_GREEN), int(round(g)))) 
                               for g in green_times]
                
                for idx, gt in enumerate(green_times):
                    self.green_time_records.append({
                        'time': current_time, 'tl_id': tl_id,
                        'phase_idx': idx * 2, 'green_time': gt
                    })
                
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
        print(f"[BO] Optimization #{self.optimization_count} at t={current_time}s")
        print(f"{'='*60}")
        
        if is_first:
            print(f"  Algorithm: Standard Bayesian Optimization (no trust region)")
            print(f"  Purpose: Ablation study for trust region mechanism")
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
        
        print(f"\n[BO] Summary")
        print(f"  Total optimizations: {self.optimization_count}")
        print(f"  Best objective: {self.best_objective:.2f}")
        print(f"  Green times saved: {output_path}")
