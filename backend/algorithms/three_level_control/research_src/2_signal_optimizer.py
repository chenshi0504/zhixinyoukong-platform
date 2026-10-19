"""
信号优化模块 - 基类/接口
提供信号配时优化的统一接口，具体算法在子模块中实现

可用的优化算法:
- 2_1_PIA_TuRBO.py: PIA-TuRBO (Physics-Informed Adaptive TuRBO)
- 2_2_TuRBO.py: TuRBO (Trust Region Bayesian Optimization)
- 2_3_PPO.py: PPO (Proximal Policy Optimization)
- 2_4_DQN.py: DQN (Deep Q-Network)
- 2_5_GA.py: GA (Genetic Algorithm)
"""
import traci
from abc import ABC, abstractmethod


class SignalOptimizerBase(ABC):
    """
    信号优化器基类
    定义信号优化的统一接口
    """
    
    def __init__(self, enabled=False):
        """
        初始化信号优化器
        
        Args:
            enabled: 是否启用优化
        """
        self.enabled = enabled
        self.traffic_lights = []
        self.initialized = False
    
    def initialize(self):
        """初始化信号灯列表"""
        if self.enabled:
            self.traffic_lights = traci.trafficlight.getIDList()
            self.initialized = True
            print(f"Signal optimizer initialized with {len(self.traffic_lights)} traffic lights")
            self._on_initialize()
    
    def _on_initialize(self):
        """子类可重写的初始化钩子"""
        pass
    
    @abstractmethod
    def optimize(self, current_time):
        """
        执行信号优化
        
        Args:
            current_time: 当前仿真时间
        """
        pass
    
    @abstractmethod
    def should_optimize(self, current_time):
        """
        判断是否应该执行优化
        
        Args:
            current_time: 当前仿真时间
            
        Returns:
            bool: 是否执行优化
        """
        pass


class SignalOptimizer(SignalOptimizerBase):
    """
    简单信号优化器（占位符实现）
    用于不需要信号优化的场景
    """
    
    def __init__(self, enabled=False):
        super().__init__(enabled)
    
    def optimize(self, current_time):
        """不执行任何优化"""
        pass
    
    def should_optimize(self, current_time):
        """始终返回False"""
        return False
    
    def step(self, current_time):
        """仿真步进（占位符实现）"""
        pass


# ============== 信号配时工具函数 ==============

def get_current_program(traffic_light_id):
    """
    获取当前信号配时方案
    
    Args:
        traffic_light_id: 信号灯ID
        
    Returns:
        当前信号配时程序
    """
    programs = traci.trafficlight.getAllProgramLogics(traffic_light_id)
    current_program_id = traci.trafficlight.getProgram(traffic_light_id)
    for program in programs:
        if program.programID == current_program_id:
            return program
    raise ValueError(f"No program found with ID {current_program_id}")


def update_phase_durations(program, new_green_durations):
    """
    修改相位时长及最大最小绿灯时间
    
    Args:
        program: 信号配时程序
        new_green_durations: 新的绿灯时长列表
        
    Returns:
        修改后的程序
    """
    green_phases = [phase for phase in program.phases if "G" in phase.state or "g" in phase.state]
    if len(green_phases) != len(new_green_durations):
        raise ValueError(f"Number of green phases ({len(green_phases)}) does not match "
                        f"the provided durations ({len(new_green_durations)})!")
    for i, phase in enumerate(green_phases):
        phase.duration = new_green_durations[i]
        phase.maxDur = new_green_durations[i]
        phase.minDur = new_green_durations[i]
    return program


def set_new_program(traffic_light_id, program_new):
    """
    设置新的信号配时方案
    
    Args:
        traffic_light_id: 信号灯ID
        program_new: 新的信号配时程序
    """
    traci.trafficlight.setProgramLogic(traffic_light_id, program_new)


def get_traffic_light_info(traffic_light_id):
    """
    获取信号灯详细信息
    
    Args:
        traffic_light_id: 信号灯ID
        
    Returns:
        dict: 信号灯信息
    """
    return {
        'id': traffic_light_id,
        'program': traci.trafficlight.getProgram(traffic_light_id),
        'phase': traci.trafficlight.getPhase(traffic_light_id),
        'phase_duration': traci.trafficlight.getPhaseDuration(traffic_light_id),
        'next_switch': traci.trafficlight.getNextSwitch(traffic_light_id),
        'controlled_lanes': traci.trafficlight.getControlledLanes(traffic_light_id),
    }
