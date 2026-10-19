"""
信号优化仿真运行器 - 平台调用入口
仅运行模式1（纯信号优化），不含PIA-TuRBO

用法:
    python run_signal_opt.py --algorithm turbo --flow 4 [--gui]

算法选项:
    turbo  - TuRBO (信任域贝叶斯优化) sig=2
    bo     - BO (标准贝叶斯优化) sig=6
    dqn    - DQN (深度Q网络, 需预训练模型) sig=4
    ppo    - PPO (近端策略优化, 需预训练模型) sig=5
    ga     - GA (遗传算法) sig=7
    pso    - PSO (粒子群优化) sig=8

流量等级:
    2 - 1.2x基准流量
    4 - 1.6x基准流量
    6 - 2.0x基准流量
"""
import os
import sys
import json
import time
import argparse
import platform

# 项目路径
ALGO_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ALGO_ROOT, 'src')
CONFIG_DIR = os.path.join(ALGO_ROOT, 'config')
DATA_DIR = os.path.join(ALGO_ROOT, 'data')
OUTPUT_DIR = os.path.join(ALGO_ROOT, 'output')
RESULTS_DIR = os.path.join(ALGO_ROOT, 'results')
MODELS_DIR = os.path.join(ALGO_ROOT, 'models')

# 将 src 加入 Python 路径
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, DATA_DIR)

# 算法映射
ALGORITHM_MAP = {
    'turbo': {'sig': 2, 'name': 'TuRBO', 'module': '2_2_TuRBO', 'class': 'TuRBOOptimizer', 'pretrain': False},
    'bo':    {'sig': 6, 'name': 'BO',    'module': '2_6_BO',    'class': 'BOOptimizer',    'pretrain': False},
    'dqn':   {'sig': 4, 'name': 'DQN',   'module': '2_4_DQN',   'class': 'RLOptimizer',   'pretrain': True},
    'ppo':   {'sig': 5, 'name': 'PPO',   'module': '2_3_PPO',   'class': 'PPOOptimizer',  'pretrain': True},
    'ga':    {'sig': 7, 'name': 'GA',    'module': '2_5_GA',    'class': 'GAOptimizer',    'pretrain': False},
    'pso':   {'sig': 8, 'name': 'PSO',   'module': '2_8_PSO',   'class': 'PSOOptimizer',  'pretrain': False},
}


def ensure_dirs():
    """确保输出目录存在"""
    for d in [OUTPUT_DIR, RESULTS_DIR]:
        os.makedirs(d, exist_ok=True)


def get_config_name(sig, flow):
    """生成实验编码: 1_{sig}_{flow}_X"""
    return f"1_{sig}_{flow}_X"


def generate_routes(flow_level, output_dir=None):
    """
    生成SUMO路由文件（从OD矩阵 + 最短路径查找表生成 trip 文件）

    Args:
        flow_level: 流量等级 (2, 4, 6)
        output_dir: 输出目录，如果指定则路由文件保存到该目录

    Returns:
        route_file: 生成的路由文件路径
        vehicle_count: 车辆数量
    """
    from batch_generate_routes import generate_baseline_route_file
    print(f"[1] Generating route file for flow level {flow_level}...")
    route_file, vehicle_count = generate_baseline_route_file(
        config_dir=CONFIG_DIR,
        data_dir=DATA_DIR,
        flow_level=flow_level,
        output_dir=output_dir
    )
    if route_file:
        print(f"    >> Route file: {route_file} ({vehicle_count} vehicles)")
    else:
        print(f"    [ERROR] Failed to generate route file")
    return route_file, vehicle_count


def prepare_sumo_config(config_name, route_file):
    """准备SUMO临时配置文件"""
    import xml.etree.ElementTree as ET

    sumo_config = os.path.join(CONFIG_DIR, 'siouxfalls.sumocfg')
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    view_file = os.path.join(CONFIG_DIR, 'osm.view.xml')

    exp_output_dir = os.path.join(OUTPUT_DIR, config_name)
    exp_input_dir = os.path.join(CONFIG_DIR, 'input', config_name)
    os.makedirs(exp_output_dir, exist_ok=True)
    os.makedirs(exp_input_dir, exist_ok=True)

    tree = ET.parse(sumo_config)
    root = tree.getroot()

    # 设置绝对路径
    for elem in root.findall('.//route-files'):
        elem.set('value', os.path.abspath(route_file))
    for elem in root.findall('.//net-file'):
        elem.set('value', os.path.abspath(net_file))
    for elem in root.findall('.//gui-settings-file'):
        elem.set('value', os.path.abspath(view_file))

    # 输出文件
    for elem in root.findall('.//output/*'):
        tag = elem.tag
        if tag == 'summary-output':
            elem.set('value', os.path.join(exp_output_dir, 'summary.xml'))
        elif tag == 'tripinfo-output':
            elem.set('value', os.path.join(exp_output_dir, 'tripinfo.xml'))
        elif tag == 'edgedata-output':
            elem.set('value', os.path.join(exp_output_dir, 'edgedata.xml'))

    temp_config = os.path.join(exp_input_dir, 'temp.sumocfg')
    tree.write(temp_config)

    return temp_config, exp_output_dir, exp_input_dir


def load_optimizer(algo_key, net_file, input_dir, flow_level=4):
    """动态加载优化器"""
    from importlib import import_module

    algo_info = ALGORITHM_MAP[algo_key]
    mod = import_module(algo_info['module'])
    cls = getattr(mod, algo_info['class'])

    optimizer = cls(net_file, input_dir)
    optimizer.auto_initialize(input_dir)
    optimizer.enabled = True

    exp_output_dir = os.path.join(OUTPUT_DIR, 'current')
    os.makedirs(exp_output_dir, exist_ok=True)
    optimizer.set_output_dir(exp_output_dir)
    optimizer.record_initial_green_times()

    # 加载预训练模型（DQN/PPO）
    if algo_info['pretrain'] and hasattr(optimizer, 'load_model'):
        model_file = os.path.join(MODELS_DIR, f"{algo_key}_flow{flow_level}_final.pth")
        if os.path.exists(model_file):
            success = optimizer.load_model(model_file)
            if success and hasattr(optimizer, 'set_inference_mode'):
                optimizer.set_inference_mode(True)
            print(f"    Pretrained model: {os.path.basename(model_file)} ({'OK' if success else 'FAILED'})")
        else:
            print(f"    [WARN] Pretrained model not found: {model_file}")

    return optimizer


def run_simulation(algo_key, flow_level, use_gui=False):
    """
    运行信号优化仿真

    Returns:
        dict: 仿真结果
    """
    import traci
    from sumolib import checkBinary

    algo_info = ALGORITHM_MAP[algo_key]
    sig = algo_info['sig']
    config_name = get_config_name(sig, flow_level)

    print("=" * 60)
    print(f"Signal Optimization Simulation")
    print(f"  Algorithm: {algo_info['name']} (sig={sig})")
    print(f"  Flow level: {flow_level}")
    print(f"  Config: {config_name}")
    print(f"  GUI: {'Yes' if use_gui else 'No'}")
    print("=" * 60)

    ensure_dirs()

    # Step 1: 生成路由文件（从OD矩阵生成真正的SUMO trip文件）
    exp_input_dir = os.path.join(CONFIG_DIR, 'input', config_name)
    os.makedirs(exp_input_dir, exist_ok=True)

    route_file, vehicle_count = generate_routes(flow_level, output_dir=exp_input_dir)
    if route_file is None:
        print("[ERROR] Failed to generate route file, aborting.")
        return None

    # Step 2: 准备SUMO配置
    net_file = os.path.join(CONFIG_DIR, 'siouxfalls.net.xml')
    temp_config, exp_output_dir, _ = prepare_sumo_config(config_name, route_file)

    # Step 3: 启动SUMO-GUI（独立窗口展示仿真过程）
    sumo_binary = checkBinary('sumo-gui')
    try:
        traci.start([sumo_binary, "-c", temp_config, "--no-warnings",
                     "--start", "--quit-on-end"])
        print("[OK] SUMO-GUI connected")
    except Exception as e:
        print(f"[ERROR] Failed to start SUMO: {e}")
        return None

    # Step 4: 初始化优化器
    print(f"[4] Initializing {algo_info['name']} optimizer...")
    try:
        optimizer = load_optimizer(algo_key, net_file, exp_input_dir, flow_level)
        print(f"    Optimizer ready: {optimizer.dim} decision variables")
    except Exception as e:
        print(f"[ERROR] Failed to init optimizer: {e}")
        traci.close()
        return None

    # Step 5: 初始化评价器
    from importlib import import_module
    eval_mod = import_module('4_evaluator')
    evaluator = eval_mod.SimulationEvaluator()

    # Step 6: 仿真主循环
    print("[5] Running simulation...")
    start_time = time.time()
    sim_step = 0
    max_sim_time = 10000

    while traci.simulation.getMinExpectedNumber() > 0 and sim_step < max_sim_time:
        traci.simulationStep()
        sim_step += 1

        evaluator.collect_step_data()
        evaluator.print_progress(interval=200)

        # 信号优化
        optimizer.step(sim_step)

    traci.close()
    runtime = time.time() - start_time

    # 保存绿灯时长记录
    if hasattr(optimizer, 'save_green_times_to_excel'):
        optimizer.set_output_dir(exp_output_dir)
        optimizer.save_green_times_to_excel()

    # 获取结果
    results = evaluator.get_results()
    results['config_name'] = config_name
    results['algorithm'] = algo_info['name']
    results['flow_level'] = flow_level
    results['runtime'] = round(runtime, 1)

    # 保存结果JSON
    result_file = os.path.join(exp_output_dir, 'results.json')
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("Simulation Results:")
    print(f"  Average Delay: {results['average_delay']:.2f}s")
    print(f"  Total Travel Time: {results['total_time']:.0f}s")
    print(f"  Throughput: {results['throughput']} vehicles")
    print(f"  Total Fuel: {results['total_fuel']:.2f}L")
    print(f"  Runtime: {runtime:.1f}s")
    print(f"  Output: {exp_output_dir}")
    print("=" * 60)

    # 清理临时配置
    if os.path.exists(temp_config):
        os.remove(temp_config)

    return results


def generate_result_charts(config_name):
    """生成结果图表"""
    try:
        from importlib import import_module
        analysis = import_module('5_analysis')
        visualizer = import_module('6_visualizer')

        exp_output_dir = os.path.join(OUTPUT_DIR, config_name)
        exp_results_dir = os.path.join(RESULTS_DIR, config_name)
        os.makedirs(exp_results_dir, exist_ok=True)

        # 分析并生成图表
        if hasattr(analysis, 'analyze_results'):
            analysis.analyze_results(exp_output_dir, exp_results_dir)
        if hasattr(visualizer, 'generate_charts'):
            visualizer.generate_charts(exp_output_dir, exp_results_dir)

        print(f"Charts saved to: {exp_results_dir}")
        return exp_results_dir
    except Exception as e:
        print(f"[WARN] Chart generation failed: {e}")
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Signal Optimization Simulation')
    parser.add_argument('--algorithm', '-a', type=str, default='turbo',
                        choices=list(ALGORITHM_MAP.keys()),
                        help='Optimization algorithm')
    parser.add_argument('--flow', '-f', type=int, default=4,
                        choices=[2, 4, 6],
                        help='Flow level (2=1.2x, 4=1.6x, 6=2.0x)')
    parser.add_argument('--gui', action='store_true',
                        help='Use SUMO GUI')

    args = parser.parse_args()

    results = run_simulation(args.algorithm, args.flow, args.gui)
    if results:
        print("\nGenerating charts...")
        generate_result_charts(results['config_name'])
