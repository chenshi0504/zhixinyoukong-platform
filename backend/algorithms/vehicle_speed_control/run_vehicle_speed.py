"""
车速控制仿真运行脚本 - 平台调用入口
使用 SUMO + TraCI 直接控制 CAV 车辆速度

用法:
    python run_vehicle_speed.py --algorithm idm --flow 4 --pr 40 [--no-gui]

算法选项:
    idm   - IDM (智能驾驶员模型)
    acc   - ACC (自适应巡航控制)
    cacc  - CACC (协同自适应巡航控制)
    pid   - PID (经典PID速度控制)
"""
import os
import sys
import json
import time
import math
import argparse
import xml.etree.ElementTree as ET

# SUMO 环境
SUMO_HOME = os.environ.get('SUMO_HOME')

if not SUMO_HOME:
    print("[错误] SUMO_HOME 环境变量未设置")
    print("请按照以下步骤配置：")
    print("1. 右键'此电脑' → 属性 → 高级系统设置 → 环境变量")
    print("2. 在'系统变量'中新建：")
    print("   变量名：SUMO_HOME")
    print("   变量值：C:\\Program Files (x86)\\Eclipse\\Sumo")
    print("3. 重启命令行窗口")
    sys.exit(1)

# 验证SUMO_HOME是否有效
if not os.path.isdir(SUMO_HOME):
    print(f"[错误] SUMO_HOME 路径无效: {SUMO_HOME}")
    sys.exit(1)

# 添加SUMO工具路径
sys.path.append(os.path.join(SUMO_HOME, 'tools'))

import traci
from sumolib import checkBinary

def _student_mode():
    """平台学生模式：后端不弹出 SUMO-GUI 等窗口。"""
    return os.environ.get('ZXK_RUN_MODE', '').strip().lower() in {
        'student', 'student_mode', '学生', '学生模式', '0', 'false', 'no', 'off',
    }


ALGO_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(os.path.dirname(ALGO_ROOT), 'signal_optimization', 'config')
OUTPUT_DIR = os.path.join(ALGO_ROOT, 'output')

ALGORITHM_MAP = {
    'idm':  {'name': 'IDM',  'desc': '智能驾驶员模型，基于前车距离和速度差的跟驰模型'},
    'acc':  {'name': 'ACC',  'desc': '自适应巡航控制，雷达感知+PID调节的跟车控制'},
    'cacc': {'name': 'CACC', 'desc': '协同自适应巡航控制，V2V通信+编队行驶'},
    'pid':  {'name': 'PID',  'desc': '经典PID速度控制，目标速度跟踪'},
}


# ============================================================
# 车速控制算法实现
# ============================================================

class IDMController:
    """智能驾驶员模型 (Intelligent Driver Model)"""
    def __init__(self, v0=13.89, T=1.5, a_max=1.5, b=2.0, s0=2.0, delta=4):
        self.v0 = v0        # 期望速度 (m/s) ~50km/h
        self.T = T           # 安全时距 (s)
        self.a_max = a_max   # 最大加速度 (m/s^2)
        self.b = b           # 舒适减速度 (m/s^2)
        self.s0 = s0         # 最小间距 (m)
        self.delta = delta   # 加速指数

    def compute_accel(self, v, dv, s):
        """计算加速度: v=当前速度, dv=与前车速度差, s=与前车间距"""
        s_star = self.s0 + max(0, v * self.T + v * dv / (2 * math.sqrt(self.a_max * self.b)))
        if s < 0.1:
            s = 0.1
        a = self.a_max * (1 - (v / self.v0) ** self.delta - (s_star / s) ** 2)
        return max(-self.b * 2, min(a, self.a_max))


class ACCController:
    """自适应巡航控制 (Adaptive Cruise Control)"""
    def __init__(self, v_desired=13.89, k_p=0.4, k_d=0.1, time_gap=1.8, min_gap=3.0):
        self.v_desired = v_desired
        self.k_p = k_p
        self.k_d = k_d
        self.time_gap = time_gap
        self.min_gap = min_gap

    def compute_accel(self, v, dv, s):
        desired_gap = self.min_gap + v * self.time_gap
        gap_error = s - desired_gap
        if s < desired_gap * 1.5:
            a = self.k_p * gap_error - self.k_d * dv
        else:
            speed_error = self.v_desired - v
            a = self.k_p * speed_error
        return max(-3.0, min(a, 2.0))


class CACCController:
    """协同自适应巡航控制 (Cooperative ACC)"""
    def __init__(self, v_desired=13.89, k_p=0.5, k_d=0.15, k_a=0.1, time_gap=0.8, min_gap=2.0):
        self.v_desired = v_desired
        self.k_p = k_p
        self.k_d = k_d
        self.k_a = k_a
        self.time_gap = time_gap
        self.min_gap = min_gap
        self.leader_accel = {}

    def compute_accel(self, v, dv, s, leader_a=0):
        desired_gap = self.min_gap + v * self.time_gap
        gap_error = s - desired_gap
        a = self.k_p * gap_error - self.k_d * dv + self.k_a * leader_a
        return max(-3.0, min(a, 2.0))


class PIDController:
    """PID速度控制器"""
    def __init__(self, v_target=13.89, kp=0.5, ki=0.01, kd=0.1):
        self.v_target = v_target
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral = {}
        self.prev_error = {}

    def compute_accel(self, veh_id, v):
        error = self.v_target - v
        if veh_id not in self.integral:
            self.integral[veh_id] = 0
            self.prev_error[veh_id] = 0
        self.integral[veh_id] += error
        self.integral[veh_id] = max(-50, min(50, self.integral[veh_id]))
        d_error = error - self.prev_error[veh_id]
        self.prev_error[veh_id] = error
        a = self.kp * error + self.ki * self.integral[veh_id] + self.kd * d_error
        return max(-3.0, min(a, 2.0))


# ============================================================
# 路由文件生成（基于信号优化的OD矩阵路由 + CAV标记）
# ============================================================

# 信号优化的数据目录（OD矩阵和最短路径）
SIGNAL_OPT_DIR = os.path.join(os.path.dirname(ALGO_ROOT), 'signal_optimization')
DATA_DIR = os.path.join(SIGNAL_OPT_DIR, 'data')


def generate_route_file(flow_level, pr, output_dir):
    """基于信号优化的OD矩阵生成路由，并按渗透率标记CAV车辆"""
    import random
    random.seed(42)

    # 先用信号优化的路由生成器生成基础路由
    sys.path.insert(0, DATA_DIR)
    from batch_generate_routes import generate_baseline_route_file
    sys.path.pop(0)

    base_route, vehicle_count = generate_baseline_route_file(
        config_dir=CONFIG_DIR,
        data_dir=DATA_DIR,
        flow_level=flow_level,
        output_dir=output_dir
    )
    if not base_route:
        print("  [ERROR] 基础路由生成失败")
        return None, 0, 0

    # 读取生成的路由文件，注入CAV车辆类型
    tree = ET.parse(base_route)
    root = tree.getroot()

    # 收集所有trip/vehicle元素
    trips = root.findall('.//trip') + root.findall('.//vehicle')
    total_vehicles = len(trips)
    cav_count = int(total_vehicles * pr / 100)
    cav_indices = set(random.sample(range(total_vehicles), cav_count))

    # 移除已有的vType，添加normal和CAV两种
    for vtype in root.findall('vType'):
        root.remove(vtype)

    # 在最前面插入vType定义
    vtype_cav = ET.Element('vType')
    vtype_cav.set('id', 'CAV')
    vtype_cav.set('accel', '2.6')
    vtype_cav.set('decel', '4.5')
    vtype_cav.set('sigma', '0.0')
    vtype_cav.set('length', '5.0')
    vtype_cav.set('maxSpeed', '16.67')
    vtype_cav.set('color', '1,0,0')
    vtype_cav.set('guiShape', 'passenger/sedan')

    vtype_normal = ET.Element('vType')
    vtype_normal.set('id', 'normal')
    vtype_normal.set('accel', '2.6')
    vtype_normal.set('decel', '4.5')
    vtype_normal.set('sigma', '0.5')
    vtype_normal.set('length', '5.0')
    vtype_normal.set('maxSpeed', '16.67')
    vtype_normal.set('color', '1,1,0')

    root.insert(0, vtype_cav)
    root.insert(0, vtype_normal)

    # 标记CAV车辆
    for i, trip in enumerate(trips):
        if i in cav_indices:
            trip.set('type', 'CAV')
        else:
            trip.set('type', 'normal')

    # 写回文件
    rou_file = os.path.join(output_dir, 'vehicles.rou.xml')
    tree.write(rou_file, encoding='utf-8', xml_declaration=True)
    print(f"  路由文件: {rou_file} ({total_vehicles} 辆, CAV {cav_count} 辆)")
    return rou_file, total_vehicles, cav_count


def prepare_sumo_config(config_name, route_file, output_dir):
    """准备SUMO配置文件"""
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    view_file = os.path.join(CONFIG_DIR, 'osm.view.xml')

    cfg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{net_file}"/>
        <route-files value="{os.path.abspath(route_file)}"/>
    </input>
    <output>
        <tripinfo-output value="{os.path.join(output_dir, 'tripinfo.xml')}"/>
        <summary-output value="{os.path.join(output_dir, 'summary.xml')}"/>
    </output>
    <time>
        <begin value="0"/>
        <end value="6000"/>
    </time>
    <gui_only>
        <gui-settings-file value="{view_file}"/>
    </gui_only>
</configuration>"""

    cfg_file = os.path.join(output_dir, 'temp.sumocfg')
    with open(cfg_file, 'w', encoding='utf-8') as f:
        f.write(cfg_content)
    return cfg_file


# ============================================================
# 主仿真函数
# ============================================================

def get_leader_info(veh_id):
    """获取前车信息"""
    try:
        leader = traci.vehicle.getLeader(veh_id, 100)
        if leader and leader[0]:
            leader_id, gap = leader
            leader_speed = traci.vehicle.getSpeed(leader_id)
            my_speed = traci.vehicle.getSpeed(veh_id)
            return leader_speed, my_speed - leader_speed, gap, leader_id
    except Exception:
        pass
    return None, 0, 999, None


def run_vehicle_speed(algorithm, flow_level, pr, use_gui=True, params=None):
    """运行车速控制仿真
    params: dict, 可选的算法参数覆盖（从前端编辑器解析）
    """
    if algorithm not in ALGORITHM_MAP:
        print(f"[ERROR] 未知算法: {algorithm}")
        return None

    algo_info = ALGORITHM_MAP[algorithm]
    config_name = f"speed_{algorithm}_{flow_level}_{pr}"

    print("=" * 60)
    print(f"  车速控制仿真 - {algo_info['name']} ({algo_info['desc']})")
    print(f"  配置: {config_name}")
    print(f"  流量等级: {flow_level} | CAV渗透率: {pr}%")
    print(f"  GUI: {'是' if use_gui else '否'}")
    print("=" * 60)

    exp_dir = os.path.join(OUTPUT_DIR, config_name)
    os.makedirs(exp_dir, exist_ok=True)

    # Step 1: 生成路由
    print("\n[1/4] 生成路由文件...")
    route_file, total_veh, cav_count = generate_route_file(flow_level, pr, exp_dir)

    # Step 2: 准备SUMO配置
    print("[2/4] 准备SUMO配置...")
    cfg_file = prepare_sumo_config(config_name, route_file, exp_dir)

    # Step 3: 启动SUMO-GUI
    print("[3/4] 启动SUMO仿真...")
    sumo_binary = checkBinary('sumo-gui' if use_gui else 'sumo')
    sumo_cmd = [sumo_binary, "-c", cfg_file, "--no-warnings", "--step-length", "0.5"]
    if use_gui:
        sumo_cmd += ["--start", "--quit-on-end"]
    try:
        traci.start(sumo_cmd)
        print(f"  {'SUMO-GUI' if use_gui else 'SUMO'} 已连接")
    except Exception as e:
        print(f"  [ERROR] SUMO启动失败: {e}")
        return None

    # Step 4: 初始化控制器（支持前端传入的自定义参数）
    p = params or {}
    if algorithm == 'idm':
        controller = IDMController(
            v0=float(p.get('v0', 13.89)), T=float(p.get('T', 1.5)),
            a_max=float(p.get('a_max', 1.5)), b=float(p.get('b', 2.0)),
            s0=float(p.get('s0', 2.0)), delta=int(p.get('delta', 4)))
    elif algorithm == 'acc':
        controller = ACCController(
            v_desired=float(p.get('v_desired', 13.89)), k_p=float(p.get('k_p', 0.4)),
            k_d=float(p.get('k_d', 0.1)), time_gap=float(p.get('time_gap', 1.8)),
            min_gap=float(p.get('min_gap', 3.0)))
    elif algorithm == 'cacc':
        controller = CACCController(
            v_desired=float(p.get('v_desired', 13.89)), k_p=float(p.get('k_p', 0.5)),
            k_d=float(p.get('k_d', 0.15)), k_a=float(p.get('k_a', 0.1)),
            time_gap=float(p.get('time_gap', 0.8)), min_gap=float(p.get('min_gap', 2.0)))
    elif algorithm == 'pid':
        controller = PIDController(
            v_target=float(p.get('v_target', 13.89)), kp=float(p.get('kp', 0.5)),
            ki=float(p.get('ki', 0.01)), kd=float(p.get('kd', 0.1)))
    if p:
        print(f"  自定义参数: {p}")

    # 仿真主循环
    print("[4/4] 运行仿真...")
    start_time = time.time()
    step = 0
    max_steps = 10000
    stats = {'speeds': [], 'accels': [], 'controlled': 0, 'steps': 0}

    while traci.simulation.getMinExpectedNumber() > 0 and step < max_steps:
        traci.simulationStep()
        step += 1

        # 每步(0.5s)对CAV执行车速控制，非CAV由SUMO跟驰模型自动控制
        step_cav_count = 0
        step_cav_speeds = []
        for veh_id in traci.vehicle.getIDList():
            if traci.vehicle.getTypeID(veh_id) != 'CAV':
                continue

            v = traci.vehicle.getSpeed(veh_id)

            if algorithm == 'pid':
                a = controller.compute_accel(veh_id, v)
            else:
                leader_speed, dv, gap, leader_id = get_leader_info(veh_id)
                if leader_speed is None:
                    if algorithm == 'pid':
                        a = controller.compute_accel(veh_id, v)
                    else:
                        a = controller.compute_accel(v, 0, 999)
                else:
                    if algorithm == 'cacc':
                        try:
                            la = traci.vehicle.getAcceleration(leader_id)
                        except Exception:
                            la = 0
                        a = controller.compute_accel(v, dv, gap, la)
                    else:
                        a = controller.compute_accel(v, dv, gap)

            new_speed = max(0, v + a * 0.5)  # dt=0.5s (仿真步长)
            traci.vehicle.setSpeed(veh_id, new_speed)
            stats['controlled'] += 1
            step_cav_count += 1
            step_cav_speeds.append(v)

            if step % 20 == 0:
                stats['speeds'].append(v)
                stats['accels'].append(a)

        # 每2步(1秒)打印一次控制信息
        if step % 2 == 0:
            sim_time = step * 0.5
            n_veh = len(traci.vehicle.getIDList())
            avg_spd = sum(step_cav_speeds) / len(step_cav_speeds) * 3.6 if step_cav_speeds else 0
            print(f"  [t={sim_time:.0f}s] 在线车辆: {n_veh} | CAV控制: {step_cav_count} 辆 | CAV均速: {avg_spd:.1f} km/h")

    traci.close()
    runtime = time.time() - start_time
    stats['steps'] = step
    print(f"\n  仿真完成，共 {step} 步，耗时 {runtime:.0f}s")

    # 收集结果
    results = collect_results(config_name, algo_info, flow_level, pr, runtime, stats, exp_dir)
    return results


def collect_results(config_name, algo_info, flow_level, pr, runtime, stats, exp_dir):
    """收集仿真结果"""
    results = {
        'algorithm': algo_info['name'],
        'config_name': config_name,
        'flow_level': flow_level,
        'pr': pr,
        'runtime': round(runtime, 1),
        'total_steps': stats['steps'],
        'control_actions': stats['controlled'],
    }

    # 从 tripinfo.xml 提取指标
    tripinfo_file = os.path.join(exp_dir, 'tripinfo.xml')
    if os.path.exists(tripinfo_file):
        try:
            tree = ET.parse(tripinfo_file)
            root = tree.getroot()
            delays = []
            durations = []
            fuel_list = []
            for trip in root.findall('tripinfo'):
                delays.append(float(trip.get('timeLoss', 0)))
                durations.append(float(trip.get('duration', 0)))
            results['average_delay'] = round(sum(delays) / len(delays), 2) if delays else 0
            results['total_time'] = round(sum(durations), 2)
            results['throughput'] = len(delays)
            print(f"  tripinfo: {len(delays)} 辆车完成")
        except Exception as e:
            print(f"  [WARN] 读取tripinfo失败: {e}")

    # 速度统计
    if stats['speeds']:
        results['avg_speed'] = round(sum(stats['speeds']) / len(stats['speeds']) * 3.6, 2)
        results['speed_std'] = round((sum((s * 3.6 - results['avg_speed'])**2 for s in stats['speeds']) / len(stats['speeds'])) ** 0.5, 2)
    if stats['accels']:
        results['avg_accel'] = round(sum(abs(a) for a in stats['accels']) / len(stats['accels']), 3)

    # 保存结果
    result_file = os.path.join(exp_dir, 'results.json')
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  结果已保存: {result_file}")

    print(f"\n{'=' * 60}")
    print(f"  仿真完成！")
    print(f"  算法: {algo_info['name']}")
    print(f"  平均延误: {results.get('average_delay', '--')}s")
    print(f"  平均速度: {results.get('avg_speed', '--')} km/h")
    print(f"  速度标准差: {results.get('speed_std', '--')} km/h")
    print(f"  吞吐量: {results.get('throughput', '--')} 辆")
    print(f"  耗时: {runtime:.0f}s")
    print(f"{'=' * 60}")

    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='车速控制仿真')
    parser.add_argument('--algorithm', '-a', type=str, default='idm',
                        choices=list(ALGORITHM_MAP.keys()),
                        help='车速控制算法 (idm/acc/cacc/pid)')
    parser.add_argument('--flow', '-f', type=int, default=4,
                        choices=[2, 4, 6], help='流量等级')
    parser.add_argument('--pr', '-p', type=int, default=40,
                        help='CAV渗透率 (20/40/60/80)')
    parser.add_argument('--no-gui', action='store_true',
                        help='不使用 SUMO GUI')
    parser.add_argument('--params', type=str, default=None,
                        help='JSON格式的算法参数覆盖')
    parser.add_argument('--params-file', type=str, default=None,
                        help='算法参数JSON文件路径')

    args = parser.parse_args()
    params = None
    if args.params_file and os.path.exists(args.params_file):
        with open(args.params_file, 'r', encoding='utf-8') as f:
            params = json.load(f)
    elif args.params:
        params = json.loads(args.params)
    use_gui = (not args.no_gui) and not _student_mode()
    run_vehicle_speed(args.algorithm, args.flow, args.pr,
                      use_gui=use_gui, params=params)
