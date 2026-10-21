"""
评价指标模块
通过TraCI收集仿真数据并计算评价指标
"""
import traci


class SimulationEvaluator:
    """仿真评价器"""
    
    def __init__(self):
        self.vehicle_times = {}      # 记录车辆出发时间
        self.vehicle_delays = {}     # 记录车辆延误
        self.total_time = 0.0        # 总出行时间
        self.total_fuel = 0.0        # 总油耗
        self.step_count = 0          # 仿真步数
    
    def collect_step_data(self):
        """收集单个时间步的数据"""
        self.step_count += 1
        current_time = traci.simulation.getTime()
        
        # 延误和油耗统计
        for vehicle_id in traci.vehicle.getIDList():
            # 延误
            delay = traci.vehicle.getAccumulatedWaitingTime(vehicle_id)
            self.vehicle_delays[vehicle_id] = delay
            
            # 油耗
            fuel_ml = traci.vehicle.getFuelConsumption(vehicle_id)
            self.total_fuel += fuel_ml / 1000.0  # 转换为升
            
            # 记录出发时间
            if vehicle_id not in self.vehicle_times:
                self.vehicle_times[vehicle_id] = current_time
        
        # 出行时间统计
        arrived_vehicle_ids = traci.simulation.getArrivedIDList()
        for veh_id in arrived_vehicle_ids:
            if veh_id in self.vehicle_times:
                depart_time = self.vehicle_times.pop(veh_id)
                travel_time = current_time - depart_time
                self.total_time += travel_time
    
    def get_results(self):
        """计算并返回评价指标"""
        total_delay = sum(self.vehicle_delays.values())
        average_delay = total_delay / len(self.vehicle_delays) if self.vehicle_delays else 0
        throughput = len(self.vehicle_delays)
        
        results = {
            'average_delay': average_delay,
            'total_delay': total_delay,
            'total_time': self.total_time,
            'total_fuel': self.total_fuel,
            'throughput': throughput,
            'steps': self.step_count
        }
        
        return results
    
    def print_progress(self, interval=100):
        """打印仿真进度"""
        
        if self.step_count % interval == 0:
            vehicles = len(traci.vehicle.getIDList())
            print(f"Step: {self.step_count}, Vehicles: {vehicles}")
