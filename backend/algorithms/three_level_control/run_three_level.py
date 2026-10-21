"""
三层级协同优化控制仿真运行器
在同一个SUMO仿真中同时运行：信号优化 + 路径诱导 + 车速控制

用法:
    python run_three_level.py --signal turbo --path dijkstra --speed idm --flow 4 --pr 40

层级开关:
    --no-signal  禁用信号优化
    --no-path    禁用路径诱导
    --no-speed   禁用车速控制

参数:
    --signal-interval  信号优化时间间隔(s), 默认600
    --path-interval    重路由间隔(s), 默认30
    --speed-dt         车速控制步长(s), 默认0.5
    --max-time         最大仿真时间(s), 默认3600
    --accept-rate      CAV采纳率(%), 默认100
"""
import os
import sys
import json
import time
import math
import random
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
RESEARCH_SRC = os.path.join(ALGO_ROOT, 'research_src')
SIGNAL_OPT_DIR = os.path.join(os.path.dirname(ALGO_ROOT), 'signal_optimization')
CONFIG_DIR = os.path.join(SIGNAL_OPT_DIR, 'config')
DATA_DIR = os.path.join(SIGNAL_OPT_DIR, 'data')
OUTPUT_DIR = os.path.join(ALGO_ROOT, 'output')
MODELS_DIR = os.path.join(SIGNAL_OPT_DIR, 'models')

# 将 research_src 加入路径
sys.path.insert(0, RESEARCH_SRC)
sys.path.insert(0, DATA_DIR)

# ============================================================
# 车速控制算法（复用 vehicle_speed_control 的实现）
# ============================================================
class IDMController:
    def __init__(self, v0=13.89, T=1.5, a_max=1.5, b=2.0, s0=2.0, delta=4):
        self.v0, self.T, self.a_max, self.b, self.s0, self.delta = v0, T, a_max, b, s0, delta
    def compute_accel(self, v, dv, s):
        s_star = self.s0 + max(0, v * self.T + v * dv / (2 * math.sqrt(self.a_max * self.b)))
        s = max(s, 0.1)
        a = self.a_max * (1 - (v / self.v0) ** self.delta - (s_star / s) ** 2)
        return max(-self.b * 2, min(a, self.a_max))

class ACCController:
    def __init__(self, v_desired=13.89, k_p=0.4, k_d=0.1, time_gap=1.8, min_gap=3.0):
        self.v_desired, self.k_p, self.k_d, self.time_gap, self.min_gap = v_desired, k_p, k_d, time_gap, min_gap
    def compute_accel(self, v, dv, s):
        desired_gap = self.min_gap + v * self.time_gap
        gap_error = s - desired_gap
        if s < desired_gap * 1.5:
            a = self.k_p * gap_error - self.k_d * dv
        else:
            a = self.k_p * (self.v_desired - v)
        return max(-3.0, min(a, 2.0))

class CACCController:
    def __init__(self, v_desired=13.89, k_p=0.5, k_d=0.15, k_a=0.1, time_gap=0.8, min_gap=2.0):
        self.v_desired, self.k_p, self.k_d, self.k_a, self.time_gap, self.min_gap = v_desired, k_p, k_d, k_a, time_gap, min_gap
    def compute_accel(self, v, dv, s, leader_a=0):
        desired_gap = self.min_gap + v * self.time_gap
        gap_error = s - desired_gap
        return max(-3.0, min(self.k_p * gap_error - self.k_d * dv + self.k_a * leader_a, 2.0))

class PIDController:
    def __init__(self, v_target=13.89, kp=0.5, ki=0.01, kd=0.1):
        self.v_target, self.kp, self.ki, self.kd = v_target, kp, ki, kd
        self.integral, self.prev_error = {}, {}
    def compute_accel(self, veh_id, v):
        error = self.v_target - v
        if veh_id not in self.integral:
            self.integral[veh_id] = 0; self.prev_error[veh_id] = 0
        self.integral[veh_id] = max(-50, min(50, self.integral[veh_id] + error))
        d_error = error - self.prev_error[veh_id]
        self.prev_error[veh_id] = error
        return max(-3.0, min(self.kp * error + self.ki * self.integral[veh_id] + self.kd * d_error, 2.0))

SPEED_CONTROLLERS = {'idm': IDMController, 'acc': ACCController, 'cacc': CACCController, 'pid': PIDController}

SIGNAL_MAP = {
    'turbo': {'sig': 2, 'name': 'TuRBO'}, 'bo': {'sig': 6, 'name': 'BO'},
    'dqn': {'sig': 4, 'name': 'DQN'}, 'ppo': {'sig': 5, 'name': 'PPO'},
    'ga': {'sig': 7, 'name': 'GA'}, 'pso': {'sig': 8, 'name': 'PSO'},
}
PATH_MAP = {
    'dijkstra': {'route': 1, 'name': 'Dijkstra', 'type': 'guidance'},
    'ssp': {'route': 3, 'name': 'SSP', 'type': 'ssp'},
    'astar': {'route': 2, 'name': 'A*', 'type': 'astar'},
}
SPEED_MAP = {'idm': 'IDM', 'acc': 'ACC', 'cacc': 'CACC', 'pid': 'PID'}

def get_leader_info(veh_id):
    try:
        leader = traci.vehicle.getLeader(veh_id, 100)
        if leader and leader[0]:
            lid, gap = leader
            return traci.vehicle.getSpeed(lid), traci.vehicle.getSpeed(veh_id) - traci.vehicle.getSpeed(lid), gap, lid
    except: pass
    return None, 0, 999, None


def count_online_cavs():
    """Return active adopted CAVs and passive CAVs currently in SUMO."""
    active = 0
    passive = 0
    for veh_id in traci.vehicle.getIDList():
        try:
            veh_type = traci.vehicle.getTypeID(veh_id)
        except Exception:
            continue
        if veh_type == 'CAV':
            active += 1
        elif veh_type == 'CAV_passive':
            passive += 1
    return active, passive


def print_signal_timing_snapshot(sim_time, prefix):
    """Print a compact signal timing snapshot for the visible backend console."""
    try:
        tl_ids = list(traci.trafficlight.getIDList())
    except Exception as exc:
        print(f"  [信号配时] t={sim_time:.0f}s 无法读取信号灯: {exc}", flush=True)
        return
    if not tl_ids:
        print(f"  [信号配时] t={sim_time:.0f}s 当前路网未检测到信号灯", flush=True)
        return
    samples = []
    for tl_id in tl_ids[:3]:
        try:
            phase = traci.trafficlight.getPhase(tl_id)
            remaining = traci.trafficlight.getNextSwitch(tl_id) - sim_time
            samples.append(f"{tl_id}:相位{phase},剩余{max(0, remaining):.1f}s")
        except Exception:
            samples.append(f"{tl_id}:读取失败")
    print(f"  [信号配时] t={sim_time:.0f}s {prefix} | 信号灯{len(tl_ids)}个 | " + "；".join(samples), flush=True)


def get_signal_optimization_count(signal_opt):
    count = getattr(signal_opt, 'optimization_count', None)
    return count if isinstance(count, (int, float)) else None


def get_signal_timing_signature(signal_opt):
    timing = getattr(signal_opt, 'current_timing', None)
    if timing is None:
        return None
    try:
        return tuple(round(float(value), 3) for value in list(timing))
    except Exception:
        return repr(timing)


def print_signal_optimization_log(signal_opt, sim_time, algo_name, optimization_count):
    if optimization_count is not None and optimization_count > 0:
        count_text = f"第{int(optimization_count)}次"
    else:
        count_text = "本次"
    print(f"  [信号优化] t={sim_time:.0f}s 算法={algo_name} {count_text}优化完成", flush=True)

    timing = getattr(signal_opt, 'current_timing', None)
    if timing is not None:
        try:
            values = [f"{float(value):.1f}s" for value in list(timing)[:8]]
            suffix = "..." if len(list(timing)) > 8 else ""
            print(f"    信号配时向量: {', '.join(values)}{suffix}", flush=True)
        except Exception:
            pass

    print_signal_timing_snapshot(sim_time, "优化后")


def generate_route_file(flow_level, pr, accept_rate, output_dir):
    """生成路由文件，标记CAV和采纳CAV"""
    random.seed(42)
    from batch_generate_routes import generate_baseline_route_file
    base_route, vehicle_count = generate_baseline_route_file(
        config_dir=CONFIG_DIR, data_dir=DATA_DIR,
        flow_level=flow_level, output_dir=output_dir
    )
    if not base_route:
        print("  [ERROR] 路由生成失败"); return None, 0, 0

    tree = ET.parse(base_route)
    root = tree.getroot()
    trips = root.findall('.//trip') + root.findall('.//vehicle')
    total = len(trips)
    cav_count = int(total * pr / 100)
    cav_indices = set(random.sample(range(total), cav_count))
    # 采纳率：只有部分CAV会执行路径诱导和车速控制
    accept_count = int(cav_count * accept_rate / 100)
    accept_indices = set(random.sample(list(cav_indices), accept_count))

    for vtype in root.findall('vType'): root.remove(vtype)
    vt_cav = ET.Element('vType'); vt_cav.set('id', 'CAV')
    vt_cav.set('accel', '2.6'); vt_cav.set('decel', '4.5'); vt_cav.set('sigma', '0.0')
    vt_cav.set('length', '5.0'); vt_cav.set('maxSpeed', '16.67')
    vt_cav.set('color', '1,0,0'); vt_cav.set('guiShape', 'passenger/sedan')
    vt_normal = ET.Element('vType'); vt_normal.set('id', 'normal')
    vt_normal.set('accel', '2.6'); vt_normal.set('decel', '4.5'); vt_normal.set('sigma', '0.5')
    vt_normal.set('length', '5.0'); vt_normal.set('maxSpeed', '16.67'); vt_normal.set('color', '1,1,0')
    # 不采纳的CAV用另一种类型标记（外观是CAV但行为由SUMO控制）
    vt_cav_passive = ET.Element('vType'); vt_cav_passive.set('id', 'CAV_passive')
    vt_cav_passive.set('accel', '2.6'); vt_cav_passive.set('decel', '4.5'); vt_cav_passive.set('sigma', '0.3')
    vt_cav_passive.set('length', '5.0'); vt_cav_passive.set('maxSpeed', '16.67')
    vt_cav_passive.set('color', '1,0.5,0'); vt_cav_passive.set('guiShape', 'passenger/sedan')
    root.insert(0, vt_cav_passive); root.insert(0, vt_cav); root.insert(0, vt_normal)

    for i, trip in enumerate(trips):
        if i in accept_indices: trip.set('type', 'CAV')
        elif i in cav_indices: trip.set('type', 'CAV_passive')
        else: trip.set('type', 'normal')

    rou_file = os.path.join(output_dir, 'vehicles.rou.xml')
    tree.write(rou_file, encoding='utf-8', xml_declaration=True)
    print(f"  路由: {total} 辆, CAV {cav_count} 辆 (采纳 {accept_count} 辆)")
    return rou_file, total, cav_count


def prepare_sumo_config(config_name, route_file, output_dir, max_time):
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    view_file = os.path.join(CONFIG_DIR, 'osm.view.xml')
    cfg = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{net_file}"/>
        <route-files value="{os.path.abspath(route_file)}"/>
    </input>
    <output>
        <tripinfo-output value="{os.path.join(output_dir, 'tripinfo.xml')}"/>
        <summary-output value="{os.path.join(output_dir, 'summary.xml')}"/>
    </output>
    <time><begin value="0"/><end value="{max_time}"/></time>
    <gui_only><gui-settings-file value="{view_file}"/></gui_only>
</configuration>"""
    cfg_file = os.path.join(output_dir, 'temp.sumocfg')
    with open(cfg_file, 'w', encoding='utf-8') as f: f.write(cfg)
    return cfg_file


def init_signal_optimizer(algo_key, flow_level, exp_input_dir, exp_output_dir, signal_interval):
    """初始化信号优化器（复用 research_src 的模块）"""
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    info = SIGNAL_MAP[algo_key]
    # 生成 signal_config.xml
    tools_dir = os.path.join(RESEARCH_SRC, 'tools')
    sys.path.insert(0, tools_dir)
    from regenerate_signal_config import extract_phase_edge_mapping, generate_signal_config_file
    mapping = extract_phase_edge_mapping(net_file)
    generate_signal_config_file(mapping, exp_input_dir)
    sys.path.pop(0)

    from importlib import import_module
    mod_map = {'turbo': '2_2_TuRBO', 'bo': '2_6_BO', 'dqn': '2_4_DQN', 'ppo': '2_3_PPO', 'ga': '2_5_GA', 'pso': '2_8_PSO'}
    cls_map = {'turbo': 'TuRBOOptimizer', 'bo': 'BOOptimizer', 'dqn': 'RLOptimizer', 'ppo': 'PPOOptimizer', 'ga': 'GAOptimizer', 'pso': 'PSOOptimizer'}
    mod = import_module(mod_map[algo_key])
    cls = getattr(mod, cls_map[algo_key])
    opt = cls(net_file, exp_input_dir)
    opt.auto_initialize(exp_input_dir)
    opt.enabled = True
    opt.set_output_dir(exp_output_dir)
    if hasattr(opt, 'optimization_interval'):
        opt.optimization_interval = max(1, int(signal_interval))
    opt.record_initial_green_times()
    # 加载预训练模型
    if algo_key in ('dqn', 'ppo') and hasattr(opt, 'load_model'):
        model_file = os.path.join(MODELS_DIR, f"{algo_key}_flow{flow_level}_final.pth")
        if os.path.exists(model_file):
            if opt.load_model(model_file) and hasattr(opt, 'set_inference_mode'):
                opt.set_inference_mode(True)
            print(f"  预训练模型: {os.path.basename(model_file)}")
    print(f"  信号优化器: {info['name']} ({opt.dim} 决策变量)")
    return opt


def init_route_guidance(algo_key, flow_level, exp_output_dir, path_interval):
    """初始化路径诱导器"""
    info = PATH_MAP[algo_key]
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    from importlib import import_module
    if info['type'] == 'guidance':
        route_mod = import_module('3_route_guidance')
        rg = route_mod.RouteGuidance(
            update_interval=path_interval, output_dir=exp_output_dir,
            flow_level=flow_level, enable_edge_control=False,
            mode='three_level', pr='', enable_effort_log=True
        )
        return rg, 'RouteGuidance'
    elif info['type'] == 'ssp':
        ssp_mod = import_module('3_2_SSP')
        return ssp_mod.SSPRouter(flow_level=flow_level, update_interval=path_interval, output_dir=exp_output_dir), 'SSPRouter'
    elif info['type'] == 'astar':
        astar_mod = import_module('3_3_Astar')
        return astar_mod.AstarRouter(net_file, update_interval=path_interval), 'AstarRouter'
    return None, 'None'

def run_three_level(args):
    """三层级协同仿真主函数"""
    enable_signal = not args.no_signal
    enable_path = not args.no_path
    enable_speed = not args.no_speed
    enabled_count = sum([enable_signal, enable_path, enable_speed])

    # 构建 config_name
    parts = ['3L']
    if enable_signal: parts.append(f's{args.signal}')
    if enable_path: parts.append(f'p{args.path}')
    if enable_speed: parts.append(f'v{args.speed}')
    parts.append(f'f{args.flow}')
    parts.append(f'pr{args.pr}')
    config_name = '_'.join(parts)

    print("  [验证] 统一三层级仿真已启动；CMD仅显示信号配时与路径诱导消息")
    if enable_path:
        print("  [验证] 路径诱导会作用于 type=CAV 的采纳车辆；未采纳CAV标记为 CAV_passive")
    print("=" * 60)
    print("  三层级协同优化控制仿真")
    print(f"  配置: {config_name}")
    if enable_signal: print(f"  上层-信号优化: {SIGNAL_MAP[args.signal]['name']} (间隔 {args.signal_interval}s)")
    else: print("  上层-信号优化: 禁用")
    if enable_path: print(f"  中层-路径诱导: {PATH_MAP[args.path]['name']} (间隔 {args.path_interval}s)")
    else: print("  中层-路径诱导: 禁用")
    print(f"  流量等级: {args.flow} | CAV渗透率: {args.pr}% | 采纳率: {args.accept_rate}%")
    print(f"  最大仿真时间: {args.max_time}s")
    print("=" * 60)

    exp_dir = os.path.join(OUTPUT_DIR, config_name)
    exp_input_dir = os.path.join(exp_dir, 'input')
    os.makedirs(exp_dir, exist_ok=True)
    os.makedirs(exp_input_dir, exist_ok=True)

    # [1] 生成路由
    print("\n[1/5] 生成路由文件...")
    route_file, total_veh, cav_count = generate_route_file(args.flow, args.pr, args.accept_rate, exp_dir)
    if not route_file: return None
    accepted_cav_count = int(cav_count * args.accept_rate / 100)
    print(f"  [CAV] 总车辆={total_veh} | CAV={cav_count} | 采纳路径/车速控制={accepted_cav_count} | 未采纳={max(0, cav_count - accepted_cav_count)}", flush=True)

    # [2] 准备SUMO配置
    print("[2/5] 准备SUMO配置...")
    cfg_file = prepare_sumo_config(config_name, route_file, exp_dir, args.max_time)

    # [3] 初始化各层级
    print("[3/5] 初始化各层级...")
    signal_opt = None
    if enable_signal:
        signal_opt = init_signal_optimizer(args.signal, args.flow, exp_input_dir, exp_dir, args.signal_interval)

    route_guidance = None
    route_controller = None
    rg_type = 'None'
    if enable_path:
        rg, rg_type = init_route_guidance(args.path, args.flow, exp_dir, args.path_interval)
        if rg_type == 'RouteGuidance': route_guidance = rg
        else: route_controller = rg
        print(f"  路径诱导器: {PATH_MAP[args.path]['name']} ({rg_type})")

    speed_ctrl = None
    if enable_speed:
        speed_ctrl = SPEED_CONTROLLERS[args.speed]()

    # [4] 启动SUMO（演示模式=sumo-gui，学生模式=无界面 sumo）
    use_gui = (not getattr(args, 'no_gui', False)) and not _student_mode()
    print(f"[4/5] 启动SUMO仿真...（{'SUMO-GUI' if use_gui else '无界面 sumo'}）")
    sumo_binary = checkBinary('sumo-gui' if use_gui else 'sumo')
    sumo_cmd = [sumo_binary, "-c", cfg_file, "--no-warnings",
                "--step-length", str(args.speed_dt)]
    if use_gui:
        sumo_cmd += ["--start", "--quit-on-end"]
    try:
        traci.start(sumo_cmd)
        print(f"  {'SUMO-GUI' if use_gui else 'SUMO'} 已连接")
    except Exception as e:
        print(f"  [ERROR] SUMO启动失败: {e}"); return None

    # 初始化评价器
    from importlib import import_module
    eval_mod = import_module('4_evaluator')
    evaluator = eval_mod.SimulationEvaluator()

    # [5] 仿真主循环
    print("[5/5] 运行仿真...")
    start_time = time.time()
    step = 0
    dt = args.speed_dt
    max_steps = int(args.max_time / dt)
    speed_stats = {'speeds': [], 'accels': [], 'controlled': 0}

    while traci.simulation.getMinExpectedNumber() > 0 and step < max_steps:
        traci.simulationStep()
        step += 1
        sim_time = step * dt
        sim_tick = int(sim_time)

        # 评价器收集数据
        evaluator.collect_step_data()

        # === 上层：信号优化 ===
        if signal_opt:
            before_count = get_signal_optimization_count(signal_opt)
            before_signature = get_signal_timing_signature(signal_opt)
            signal_opt.step(sim_time)
            after_count = get_signal_optimization_count(signal_opt)
            after_signature = get_signal_timing_signature(signal_opt)
            count_changed = before_count is not None and after_count is not None and after_count != before_count
            timing_changed = before_signature is not None and after_signature is not None and after_signature != before_signature
            if count_changed or timing_changed:
                print_signal_optimization_log(signal_opt, sim_time, SIGNAL_MAP[args.signal]['name'], after_count)

        # === 中层：路径诱导 ===
        if route_guidance:
            route_guidance.collect_travel_time(sim_time)
            route_guidance.update(sim_tick)
        elif route_controller:
            route_controller.update(sim_tick)

        # === 下层：车速控制（仅控制采纳的CAV） ===
        if speed_ctrl:
            step_cav_count = 0
            step_cav_speeds = []
            for veh_id in traci.vehicle.getIDList():
                if traci.vehicle.getTypeID(veh_id) != 'CAV':
                    continue
                v = traci.vehicle.getSpeed(veh_id)
                if args.speed == 'pid':
                    a = speed_ctrl.compute_accel(veh_id, v)
                else:
                    ls, dv, gap, lid = get_leader_info(veh_id)
                    if ls is None:
                        a = speed_ctrl.compute_accel(v, 0, 999) if args.speed != 'pid' else speed_ctrl.compute_accel(veh_id, v)
                    elif args.speed == 'cacc':
                        try: la = traci.vehicle.getAcceleration(lid)
                        except: la = 0
                        a = speed_ctrl.compute_accel(v, dv, gap, la)
                    else:
                        a = speed_ctrl.compute_accel(v, dv, gap)
                new_speed = max(0, v + a * dt)
                traci.vehicle.setSpeed(veh_id, new_speed)
                speed_stats['controlled'] += 1
                step_cav_count += 1
                step_cav_speeds.append(v)
                if step % 20 == 0:
                    speed_stats['speeds'].append(v)
                    speed_stats['accels'].append(a)

    traci.close()
    runtime = time.time() - start_time
    print(f"\n  仿真完成，共 {step} 步 ({step*dt:.0f}s)，耗时 {runtime:.0f}s")

    # 保存信号优化记录
    if signal_opt and hasattr(signal_opt, 'save_green_times_to_excel'):
        signal_opt.save_green_times_to_excel()

    # 收集结果
    results = evaluator.get_results()
    results['config_name'] = config_name
    results['flow_level'] = args.flow
    results['pr'] = args.pr
    results['accept_rate'] = args.accept_rate
    results['runtime'] = round(runtime, 1)
    results['vehicle_count'] = total_veh
    results['cav_count'] = cav_count
    results['accepted_cav_count'] = int(cav_count * args.accept_rate / 100)
    results['enabled_levels'] = []
    if enable_signal: results['enabled_levels'].append('signal')
    if enable_path: results['enabled_levels'].append('path')
    if enable_speed: results['enabled_levels'].append('speed')
    results['signal_algo'] = SIGNAL_MAP[args.signal]['name'] if enable_signal else None
    results['path_algo'] = PATH_MAP[args.path]['name'] if enable_path else None
    results['speed_algo'] = SPEED_MAP[args.speed] if enable_speed else None
    results['signal_interval'] = args.signal_interval if enable_signal else None
    results['path_interval'] = args.path_interval if enable_path else None
    results['speed_dt'] = args.speed_dt if enable_speed else None
    if route_guidance and hasattr(route_guidance, 'get_statistics'):
        results['path_guidance_stats'] = route_guidance.get_statistics()
        results['path_route_changes'] = results['path_guidance_stats'].get('total_route_changes')
    elif route_controller and hasattr(route_controller, 'get_statistics'):
        results['path_guidance_stats'] = route_controller.get_statistics()
        results['path_route_changes'] = (
            results['path_guidance_stats'].get('total_route_changes')
            or results['path_guidance_stats'].get('total_rerouted')
        )

    # 速度统计
    if speed_stats['speeds']:
        results['avg_speed'] = round(sum(speed_stats['speeds']) / len(speed_stats['speeds']) * 3.6, 2)
        results['speed_std'] = round((sum((s*3.6 - results['avg_speed'])**2 for s in speed_stats['speeds']) / len(speed_stats['speeds'])) ** 0.5, 2)

    # tripinfo
    tripinfo_file = os.path.join(exp_dir, 'tripinfo.xml')
    if os.path.exists(tripinfo_file):
        try:
            tree = ET.parse(tripinfo_file)
            delays, durations = [], []
            for trip in tree.getroot().findall('tripinfo'):
                delays.append(float(trip.get('timeLoss', 0)))
                durations.append(float(trip.get('duration', 0)))
            if delays:
                results['average_delay'] = round(sum(delays) / len(delays), 2)
                results['total_time'] = round(sum(durations), 2)
                results['throughput'] = len(delays)
        except: pass

    result_file = os.path.join(exp_dir, 'results.json')
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  三层级协同仿真完成！")
    print(f"  平均延误: {results.get('average_delay', '--')}s")
    print(f"  吞吐量: {results.get('throughput', '--')} 辆")
    print(f"  耗时: {runtime:.0f}s")
    print(f"{'=' * 60}")
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='三层级协同优化控制仿真')
    parser.add_argument('--signal', type=str, default='turbo', choices=list(SIGNAL_MAP.keys()))
    parser.add_argument('--path', type=str, default='dijkstra', choices=list(PATH_MAP.keys()))
    parser.add_argument('--speed', type=str, default='idm', choices=list(SPEED_CONTROLLERS.keys()))
    parser.add_argument('--flow', type=int, default=4, choices=[2, 4, 6])
    parser.add_argument('--pr', type=int, default=40)
    parser.add_argument('--signal-interval', type=int, default=600)
    parser.add_argument('--path-interval', type=int, default=30)
    parser.add_argument('--speed-dt', type=float, default=0.5)
    parser.add_argument('--max-time', type=int, default=3600)
    parser.add_argument('--accept-rate', type=int, default=100)
    parser.add_argument('--no-signal', action='store_true')
    parser.add_argument('--no-path', action='store_true')
    parser.add_argument('--no-speed', action='store_true')
    parser.add_argument('--no-gui', action='store_true', help='不使用 SUMO GUI（学生模式自动启用）')
    args = parser.parse_args()
    result = run_three_level(args)
    sys.exit(0 if result else 1)
