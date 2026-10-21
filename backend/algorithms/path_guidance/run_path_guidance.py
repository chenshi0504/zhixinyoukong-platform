"""
路径诱导算法运行脚本 - 平台调用入口
直接调用 Research 项目的 main_batch 函数，启动 SUMO-GUI

用法:
    python run_path_guidance.py --algorithm ssp --flow 4 --flow-mode normal --pr 40 [--no-gui]
    python run_path_guidance.py --algorithm ssp --flow 4 --flow-mode high --pr 40 [--no-gui]

算法选项:
    dijkstra - Dijkstra (经典最短路径算法) route=1
    ssp      - SSP (逐次最短路径算法)     route=3
    astar    - A* (启发式搜索算法)        route=2

流量模式:
    normal - 普通模式（当前流量）
    high   - 高流量模式（当前流量 × 1.7）

兼容旧调用:
    --flow 仍接受 2/4/6，未传 --flow-mode 时按普通模式运行。

渗透率 (pr):
    20, 40, 60, 80 等 (CAV渗透率百分比)
"""
import os
import sys
import json
import time
import argparse
import functools
import builtins
import csv

print = functools.partial(builtins.print, flush=True)

# 本地输出目录
ALGO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _student_mode():
    """平台学生模式：后端不弹出 SUMO-GUI 等窗口。"""
    return os.environ.get('ZXK_RUN_MODE', '').strip().lower() in {
        'student', 'student_mode', '学生', '学生模式', '0', 'false', 'no', 'off',
    }


def _resolve_python():
    """智能解析 Python 解释器路径（frozen 模式下绝不使用 sys.executable）"""
    env_py = os.environ.get('ZXK_ALGO_PYTHON_EXE')
    if env_py and os.path.isfile(env_py):
        return env_py
    if getattr(sys, 'frozen', False):
        internal = os.path.dirname(sys.executable)
        for c in [
            os.path.join(internal, 'python_env', 'Scripts', 'python.exe'),
            os.path.join(internal, 'python_env', 'python.exe'),
            os.path.join(os.path.dirname(internal), 'python_env', 'Scripts', 'python.exe'),
        ]:
            if os.path.isfile(c):
                return c
    if not getattr(sys, 'frozen', False):
        return sys.executable
    import shutil
    py = shutil.which('python')
    if py:
        return py
    raise RuntimeError('无法找到可用的 Python 解释器，请设置 ZXK_ALGO_PYTHON_EXE 环境变量')


def _resolve_research_dir():
    """解析 research_src 目录（支持开发和打包模式）"""
    # 1. 环境变量优先
    env_dir = os.environ.get('ZXK_RESEARCH_DIR')
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    # 2. 相对路径: ../three_level_control/research_src
    candidate = os.path.normpath(os.path.join(ALGO_ROOT, '..', 'three_level_control', 'research_src'))
    if os.path.isdir(candidate):
        return candidate
    # 3. frozen 模式: _internal/backend/algorithms/three_level_control/research_src
    if getattr(sys, 'frozen', False):
        internal = os.path.dirname(sys.executable)
        frozen_candidate = os.path.join(internal, 'backend', 'algorithms', 'three_level_control', 'research_src')
        if os.path.isdir(frozen_candidate):
            return frozen_candidate
    # 4. 当前目录下的 research_src/
    local = os.path.join(ALGO_ROOT, 'research_src')
    if os.path.isdir(local):
        return local
    # 返回最可能的路径，后续操作会报错明确提示
    print(f'[WARN] 未找到 research_src 目录，尝试使用: {candidate}')
    return candidate


RESEARCH_SRC = _resolve_research_dir()
RESEARCH_DIR = os.path.dirname(RESEARCH_SRC)
SIGNAL_OPT_CONFIG_DIR = os.path.normpath(os.path.join(ALGO_ROOT, '..', 'signal_optimization', 'config'))
SIGNAL_OPT_DATA_DIR = os.path.normpath(os.path.join(ALGO_ROOT, '..', 'signal_optimization', 'data'))

# 将 research_src 加入 Python 路径，以便直接 import main_batch
for _dep_dir in (SIGNAL_OPT_DATA_DIR, RESEARCH_SRC):
    if os.path.isdir(_dep_dir) and _dep_dir not in sys.path:
        sys.path.insert(0, _dep_dir)
OUTPUT_DIR = os.path.join(ALGO_ROOT, 'output')
PATH_UPDATE_INTERVAL = 30
FLOW_MODE_MULTIPLIERS = {'normal': 1.0, 'high': 1.7}
FLOW_MODE_LABELS = {
    'normal': '普通模式（当前流量）',
    'high': '高流量模式（当前流量 × 1.7）',
}

# 算法映射: key -> route_code (用于 config_name)
ALGORITHM_MAP = {
    'dijkstra': {'route_code': 1, 'name': 'Dijkstra', 'desc': '经典最短路径算法（基于effort动态重路由）'},
    'ssp':      {'route_code': 3, 'name': 'SSP',      'desc': '逐次最短路径算法'},
    'astar':    {'route_code': 2, 'name': 'A*',       'desc': '启发式搜索算法'},
}


def get_config_name(route_code, flow_level, pr):
    """生成实验编码: 2_{route}_{flow}_{pr}"""
    return f"2_{route_code}_{flow_level}_{pr}"


def ensure_shared_inputs():
    """Validate the shared Sioux Falls assets used by main_batch."""
    required = [
        os.path.join(SIGNAL_OPT_CONFIG_DIR, 'siouxfalls.net.xml'),
        os.path.join(SIGNAL_OPT_CONFIG_DIR, 'siouxfalls.sumocfg'),
        os.path.join(SIGNAL_OPT_DATA_DIR, 'SiouxFalls_od.csv'),
        os.path.join(SIGNAL_OPT_DATA_DIR, 'shortest_paths_v2_routes.xml'),
    ]
    missing = [path for path in required if not os.path.isfile(path)]
    if missing:
        print("[ERROR] 路径诱导缺少必要输入文件:")
        for path in missing:
            print(f"  - {path}")
        return False
    return True


def configure_main_batch_route_update(main_batch_module):
    """Force the compiled main_batch entry to use the visible 30s path-decision cadence."""
    main_batch_module.UPDATE_INTERVAL = PATH_UPDATE_INTERVAL

    def force_update_interval(args, kwargs, index):
        args = list(args)
        if len(args) > index:
            args[index] = PATH_UPDATE_INTERVAL
        else:
            kwargs['update_interval'] = PATH_UPDATE_INTERVAL
        return tuple(args), kwargs

    if hasattr(main_batch_module, 'RouteGuidance') and not hasattr(main_batch_module, '_zxk_original_route_guidance'):
        main_batch_module._zxk_original_route_guidance = main_batch_module.RouteGuidance
        original_route_guidance = main_batch_module._zxk_original_route_guidance

        def route_guidance_30s(*args, **kwargs):
            args, kwargs = force_update_interval(args, kwargs, 0)
            return original_route_guidance(*args, **kwargs)

        main_batch_module.RouteGuidance = route_guidance_30s

    if hasattr(main_batch_module, 'SSPRouter') and not hasattr(main_batch_module, '_zxk_original_ssp_router'):
        main_batch_module._zxk_original_ssp_router = main_batch_module.SSPRouter
        original_ssp_router = main_batch_module._zxk_original_ssp_router

        def ssp_router_30s(*args, **kwargs):
            args, kwargs = force_update_interval(args, kwargs, 1)
            return original_ssp_router(*args, **kwargs)

        main_batch_module.SSPRouter = ssp_router_30s

    print(f"  路径诱导决策周期: {PATH_UPDATE_INTERVAL}s（首个周期结束即输出CMD决策日志）")


def _scale_generated_od(result, multiplier):
    """将 main_batch 刚生成的 OD 文件按倍率放大，返回同样的返回值结构。"""
    if not result or multiplier == 1.0:
        return result

    od_file = result[0] if isinstance(result, tuple) else result
    if not od_file or not os.path.isfile(od_file):
        return result

    rows = []
    total_trips = 0
    with open(od_file, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if 'Trips' not in fieldnames:
            return result
        for row in reader:
            try:
                trips = float(row.get('Trips') or 0)
            except (TypeError, ValueError):
                trips = 0
            scaled_trips = max(1, int(round(trips * multiplier)))
            row['Trips'] = str(scaled_trips)
            total_trips += scaled_trips
            rows.append(row)

    with open(od_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  高流量需求量已按 {multiplier:g} 倍放大: {total_trips:,} 辆")
    if isinstance(result, tuple):
        return od_file, total_trips
    return od_file


def configure_main_batch_flow(main_batch_module, flow_mode):
    """让编译版 main_batch 在生成本次实验 OD 后应用流量模式。"""
    if flow_mode not in FLOW_MODE_MULTIPLIERS:
        raise ValueError(f"不支持的流量模式: {flow_mode}")
    if not hasattr(main_batch_module, 'generate_scaled_od'):
        raise RuntimeError("当前 main_batch 不支持 OD 流量缩放，无法启动路径诱导仿真")

    original = getattr(main_batch_module, '_zxk_original_generate_scaled_od', None)
    if original is None:
        original = main_batch_module.generate_scaled_od
        main_batch_module._zxk_original_generate_scaled_od = original

    multiplier = FLOW_MODE_MULTIPLIERS[flow_mode]
    if multiplier == 1.0:
        main_batch_module.generate_scaled_od = original
        return

    def generate_scaled_od_with_mode(flow_level, experiment_id=None, output_dir=None):
        generated = original(flow_level, experiment_id=experiment_id, output_dir=output_dir)
        return _scale_generated_od(generated, multiplier)

    main_batch_module.generate_scaled_od = generate_scaled_od_with_mode


def simulation_outputs_fresh(config_name, started_at):
    """True only when this launch produced fresh SUMO output files."""
    output_dir = os.path.join(RESEARCH_DIR, "output", config_name)
    required = ("tripinfo.xml", "summary.xml")
    for name in required:
        path = os.path.join(output_dir, name)
        if not os.path.isfile(path):
            return False
        if os.path.getmtime(path) < started_at - 0.5:
            return False
    return True


def run_path_guidance(algorithm, flow_level, pr, use_gui=True, flow_mode='normal'):
    """
    运行路径诱导仿真
    直接调用 Research 项目的 main_batch() 函数，传入 use_gui=True 启动 SUMO-GUI
    （不再通过 subprocess 调用 main_batch.py，因为其单配置模式硬编码 use_gui=False）

    Args:
        algorithm: 算法名 ('dijkstra' / 'ssp' / 'astar')
        flow_level: 当前基准流量等级（界面模式默认使用 4）
        pr: CAV渗透率 (20/40/60/80)
        use_gui: 是否使用 SUMO GUI（默认True）
        flow_mode: normal（当前流量）或 high（当前流量 × 1.7）
    """
    if algorithm not in ALGORITHM_MAP:
        print(f"[ERROR] 未知算法: {algorithm}")
        return None

    if flow_mode not in FLOW_MODE_MULTIPLIERS:
        print(f"[ERROR] unknown flow mode: {flow_mode}")
        return None

    algo_info = ALGORITHM_MAP[algorithm]
    route_code = algo_info['route_code']
    config_name = get_config_name(route_code, flow_level, pr)
    if flow_mode == 'high':
        config_name += '_high'
    flow_multiplier = FLOW_MODE_MULTIPLIERS[flow_mode]

    print(f"  流量模式: {FLOW_MODE_LABELS[flow_mode]} | 基准等级: {flow_level} | 渗透率: {pr}%")
    print("=" * 60)
    print(f"  路径诱导仿真 - {algo_info['name']} ({algo_info['desc']})")
    print(f"  配置编码: {config_name}")
    print(f"  流量等级: {flow_level} | 渗透率: {pr}%")
    print(f"  GUI: {'是' if use_gui else '否'}")
    print("=" * 60)

    # 确保本地输出目录存在
    local_output_dir = os.path.join(OUTPUT_DIR, config_name)
    os.makedirs(local_output_dir, exist_ok=True)

    # 切换工作目录到 Research/src（main_batch 内部依赖相对路径）
    original_cwd = os.getcwd()
    os.chdir(RESEARCH_SRC)

    print(f"\n[1/3] 启动仿真...")
    print(f"  直接调用 main_batch('{config_name}', use_gui={use_gui})")
    print(f"  工作目录: {RESEARCH_SRC}")

    start_time = time.time()

    simulation_ok = False
    try:
        # 直接 import 并调用 main_batch 函数，传入 use_gui=True 启动 SUMO-GUI
        if not ensure_shared_inputs():
            return None
        import main_batch as _main_batch_module
        _main_batch_module.CONFIG_DIR = SIGNAL_OPT_CONFIG_DIR
        _main_batch_module.DATA_DIR = SIGNAL_OPT_DATA_DIR
        configure_main_batch_route_update(_main_batch_module)
        configure_main_batch_flow(_main_batch_module, flow_mode)
        if hasattr(_main_batch_module, 'print'):
            _main_batch_module.print = print
        _run_main_batch = _main_batch_module.main_batch
        _run_main_batch(config_name, use_gui=use_gui)
        simulation_ok = simulation_outputs_fresh(config_name, start_time)
        if not simulation_ok:
            print("  [ERROR] 本次运行未生成新的 SUMO 输出文件，仿真可能在算法内部提前失败")

        elapsed = time.time() - start_time
        print(f"\n[2/3] 仿真完成（耗时 {elapsed:.0f} 秒）")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n[ERROR] 仿真异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        os.chdir(original_cwd)

    if not simulation_ok:
        print("  [ERROR] 仿真未正常完成，结果收集已跳过")
        return None

    # [3/3] 收集结果
    print(f"\n[3/3] 收集结果...")
    results = collect_results(config_name, algo_info, flow_level, pr, elapsed, flow_mode, flow_multiplier)

    if results:
        # 保存结果到本地输出目录
        result_file = os.path.join(local_output_dir, 'results.json')
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  结果已保存: {result_file}")

        print(f"\n{'=' * 60}")
        print(f"  仿真完成！")
        print(f"  算法: {algo_info['name']}")
        print(f"  平均延误: {results.get('average_delay', '--')}s")
        print(f"  总行程时间: {results.get('total_time', '--')}s")
        print(f"  吞吐量: {results.get('throughput', '--')} 辆")
        print(f"  耗时: {elapsed:.0f}s")
        print(f"{'=' * 60}")
    else:
        print(f"  [WARN] 未找到结果文件，仿真可能仍在运行")

    return results


def collect_results(config_name, algo_info, flow_level, pr, elapsed, flow_mode='normal', flow_multiplier=1.0):
    """
    从 Research 项目的输出目录收集结果

    结果文件位于: D:\\chenshi\\Research\\Step2_Algorithm\\output\\{config_name}\\results.xlsx
    """
    research_output_dir = os.path.join(RESEARCH_DIR, "output", config_name)
    local_output_dir = os.path.join(OUTPUT_DIR, config_name)

    results = {
        'algorithm': algo_info['name'],
        'algorithm_key': [k for k, v in ALGORITHM_MAP.items() if v == algo_info][0],
        'config_name': config_name,
        'flow_level': flow_level,
        'flow_mode': flow_mode,
        'flow_mode_label': FLOW_MODE_LABELS.get(flow_mode, flow_mode),
        'flow_multiplier': flow_multiplier,
        'pr': pr,
        'runtime': round(elapsed, 1),
    }

    # 尝试读取 results.xlsx
    results_xlsx = os.path.join(research_output_dir, 'results.xlsx')
    if os.path.exists(results_xlsx):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(results_xlsx)
            ws = wb.active
            data = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[0] and row[1] is not None:
                    data[str(row[0]).strip()] = row[1]

            results['average_delay'] = round(float(data.get('Average Delay (s)', 0)), 2)
            results['total_time'] = round(float(data.get('Total Travel Time (s)', 0)), 2)
            results['total_fuel'] = round(float(data.get('Total Fuel (L)', 0)), 2)
            results['throughput'] = int(float(data.get('Throughput', 0)))
            results['vehicle_count'] = int(float(data.get('Vehicle Count', 0)))
            results['cav_count'] = int(float(data.get('CAV Count', 0)))
            results['cav_percent'] = float(data.get('CAV Penetration (%)', 0))

            print(f"  从 results.xlsx 读取结果成功")
        except Exception as e:
            print(f"  [WARN] 读取 results.xlsx 失败: {e}")
            _fill_from_tripinfo(results, research_output_dir)
    else:
        _fill_from_tripinfo(results, research_output_dir)

    # 复制图表文件到本地输出目录
    _copy_output_files(research_output_dir, local_output_dir)

    # 也检查 results 目录的图表
    research_results_dir = os.path.join(RESEARCH_DIR, "results", config_name)
    if os.path.exists(research_results_dir):
        _copy_output_files(research_results_dir, local_output_dir)

    return results


def _fill_from_tripinfo(results, output_dir):
    """从 tripinfo.xml 提取基本指标"""
    tripinfo_file = os.path.join(output_dir, 'tripinfo.xml')
    if not os.path.exists(tripinfo_file):
        return

    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(tripinfo_file)
        root = tree.getroot()

        delays = []
        travel_times = []
        for trip in root.findall('tripinfo'):
            delay = float(trip.get('timeLoss', 0))
            duration = float(trip.get('duration', 0))
            delays.append(delay)
            travel_times.append(duration)

        if delays:
            results['average_delay'] = round(sum(delays) / len(delays), 2)
            results['total_time'] = round(sum(travel_times), 2)
            results['throughput'] = len(delays)
            print(f"  从 tripinfo.xml 读取结果: {len(delays)} 辆车")
    except Exception as e:
        print(f"  [WARN] 读取 tripinfo.xml 失败: {e}")


def _copy_output_files(src_dir, dst_dir):
    """复制图表和数据文件到本地输出目录"""
    if not os.path.exists(src_dir):
        return

    import shutil
    extensions = ('.png', '.jpg', '.jpeg', '.xlsx', '.csv', '.json', '.xml')

    for f in os.listdir(src_dir):
        if f.lower().endswith(extensions) and f != 'results.json':
            src_file = os.path.join(src_dir, f)
            dst_file = os.path.join(dst_dir, f)
            if os.path.isfile(src_file):
                try:
                    shutil.copy2(src_file, dst_file)
                except Exception:
                    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='路径诱导仿真')
    parser.add_argument('--algorithm', '-a', type=str, default='dijkstra',
                        choices=list(ALGORITHM_MAP.keys()),
                        help='路径诱导算法 (dijkstra/ssp/astar)')
    parser.add_argument('--flow', '-f', type=int, default=4,
                        choices=[2, 4, 6],
                        help='兼容旧调用的流量等级（新界面使用 --flow-mode）')
    parser.add_argument('--flow-mode', choices=list(FLOW_MODE_MULTIPLIERS.keys()), default='normal',
                        help='流量模式：normal=当前流量，high=当前流量×1.7')
    parser.add_argument('--pr', '-p', type=int, default=40,
                        help='CAV渗透率 (20/40/60/80)')
    parser.add_argument('--no-gui', action='store_true',
                        help='不使用 SUMO GUI')

    args = parser.parse_args()

    use_gui = (not args.no_gui) and not _student_mode()
    result = run_path_guidance(args.algorithm, args.flow, args.pr, use_gui=use_gui, flow_mode=args.flow_mode)
    sys.exit(0 if result else 1)
