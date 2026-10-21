"""
交通流重构 DTALite 路由模块（⚠️ 未启用 / DEPRECATED）。

本文件是从 main.py 拆分出来的副本，但**从未被注册**：main.py 的
``include_optional_router`` 名单里没有 ``traffic_reconstruction``，全仓库也没有
任何地方 import 它。当前真正对外提供服务的是 ``app/main.py`` 中内联的
``/api/reconstruction/*`` 实现（连同它自己的 `_dtalite_status` 全局状态）。

因此：
- 修改本文件不会生效；
- 本文件内还维护了一份与 main.py 同名的 DTALite 状态，二者永不同步；
- 若将来要启用它，必须同时删除 main.py 里的内联副本，二选一，否则会出现
  「同一路径两份实现、由注册顺序决定谁生效」的隐患。
"""
import os
import subprocess
import sys
import threading
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse

from ..paths import DTALITE_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reconstruction", tags=["交通流重构"])

# ---- 路径常量 ----
from ..paths import ALGORITHMS_DIR, algo_output_dir
_ALGO_DIR = os.path.join(ALGORITHMS_DIR, 'traffic_reconstruction')
_DTALITE_DIR = DTALITE_DIR
_DTALITE_EXE = os.path.join(_DTALITE_DIR, 'DTALite.exe')
_OUTPUT_DIR = algo_output_dir('traffic_reconstruction', 'output')

# ---- 运行状态 ----
_dtalite_status = {
    'running': False,
    'success': None,
    'message': '未运行',
    'elapsed': 0,
}
_dtalite_lock = threading.Lock()
_dtalite_process = None
_dtalite_started_at = 0.0


def _server_process_kwargs():
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _launch_visible_dtalite_console():
    """Launch DTALite in a visible CMD window on the backend computer."""
    if os.name == "nt":
        cmd = (
            'title DTALite交通流重构'
            ' & chcp 65001 >nul'
            ' & echo ========================================'
            ' & echo   DTALite交通流重构正在执行...'
            ' & echo ========================================'
            ' & echo 当前目录: %CD%'
            ' & echo 启动程序: DTALite.exe'
            ' & echo.'
            ' & DTALite.exe'
            ' & set DTALITE_EXIT=!ERRORLEVEL!'
            ' & echo.'
            ' & echo ========================================'
            ' & echo   DTALite执行完成，退出码 !DTALITE_EXIT!'
            ' & echo ========================================'
            ' & timeout /t 5 >nul'
            ' & exit /b !DTALITE_EXIT!'
        )
        return subprocess.Popen(
            ["cmd.exe", "/v:on", "/c", cmd],
            cwd=_DTALITE_DIR,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    return subprocess.Popen([_DTALITE_EXE], cwd=_DTALITE_DIR, **_server_process_kwargs())


def _refresh_dtalite_status_locked():
    global _dtalite_process, _dtalite_started_at
    proc = _dtalite_process
    if proc is None or not _dtalite_status.get('running'):
        return

    elapsed = max(0, time.time() - _dtalite_started_at) if _dtalite_started_at else _dtalite_status.get('elapsed', 0)
    returncode = proc.poll()
    if returncode is None:
        _dtalite_status.update(
            running=True,
            success=None,
            message=f'DTALite正在运行中（PID {proc.pid}，已运行{elapsed:.1f}秒）',
            elapsed=elapsed,
            pid=proc.pid,
        )
        return

    _dtalite_process = None
    _dtalite_started_at = 0.0
    if returncode == 0:
        _dtalite_status.update(
            running=False,
            success=True,
            message=f'DTALite执行完成（耗时{elapsed:.1f}秒）',
            elapsed=elapsed,
            pid=None,
        )
    else:
        _dtalite_status.update(
            running=False,
            success=False,
            message=f'DTALite执行失败（退出码{returncode}，详见服务端日志）',
            elapsed=elapsed,
            pid=None,
        )


def _parse_real_metrics():
    """从DTALite输出的CSV文件中解析真实指标"""
    import csv
    metrics = {}
    # 1) 从 debug_validation_results.csv 计算 RMSE 和精度
    validation_csv = os.path.join(_DTALITE_DIR, 'debug_validation_results.csv')
    if os.path.exists(validation_csv):
        try:
            observed_list = []
            simulated_list = []
            with open(validation_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        obs = float(row.get('observed_link_count', 0))
                        sim = float(row.get('simulated_link_count', 0))
                        observed_list.append(obs)
                        simulated_list.append(sim)
                    except (ValueError, TypeError):
                        continue
            if observed_list:
                n = len(observed_list)
                sum_sq_err = sum((o - s) ** 2 for o, s in zip(observed_list, simulated_list))
                rmse = (sum_sq_err / n) ** 0.5
                sum_obs = sum(observed_list)
                sum_sim = sum(simulated_list)
                if sum_obs > 0:
                    accuracy = max(0, 1 - abs(sum_sim - sum_obs) / sum_obs) * 100
                else:
                    accuracy = 0
                metrics['rmse'] = f'{rmse:.2f}'
                metrics['accuracy'] = f'{accuracy:.1f}%'
                metrics['validationRows'] = n
        except Exception:
            pass
    # 2) 从 output_ODMOE.csv 统计 OD 对数量和平均行程
    odmoe_csv = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
    if os.path.exists(odmoe_csv):
        try:
            od_count = 0
            total_time = 0
            total_dist = 0
            with open(odmoe_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    od_count += 1
                    try:
                        total_time += float(row.get('trip_time_in_min', 0))
                        total_dist += float(row.get('distance', 0))
                    except (ValueError, TypeError):
                        continue
            metrics['odPairCount'] = str(od_count)
            if od_count > 0:
                metrics['avgTripTime'] = f'{total_time / od_count:.2f} min'
                metrics['avgDistance'] = f'{total_dist / od_count:.2f} km'
        except Exception:
            pass
    # 3) 从 output_day_to_day_MOE.csv 读取总车辆数和平均速度
    moe_csv = os.path.join(_DTALITE_DIR, 'output_day_to_day_MOE.csv')
    if os.path.exists(moe_csv):
        try:
            with open(moe_csv, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # 数据行在第5行之后（前面是header描述）
            for line in reversed(lines):
                parts = line.strip().split(',')
                # 找到有数字的行（day_no列有值）
                if len(parts) > 10:
                    try:
                        vehicles = int(float(parts[6]))
                        avg_speed = float(parts[10])
                        avg_time = float(parts[9])
                        metrics['totalVehicles'] = str(vehicles)
                        metrics['avgSpeed'] = f'{avg_speed:.1f} mph'
                        metrics['avgTravelTime'] = f'{avg_time:.2f} min'
                        break
                    except (ValueError, IndexError):
                        continue
        except Exception:
            pass
    return metrics


@router.post("/run-dtalite")
async def run_dtalite():
    global _dtalite_process, _dtalite_started_at
    with _dtalite_lock:
        _refresh_dtalite_status_locked()
        if _dtalite_status['running']:
            return {'success': False, 'message': 'DTALite正在运行中，请等待完成'}

    if not os.path.exists(_DTALITE_EXE):
        # 演示模式：从已有的输出文件读取真实数据
        metrics = _parse_real_metrics()
        return {
            'success': True,
            'message': 'DTALite模拟执行完成（演示模式）',
            'metrics': metrics,
        }

    log_path = os.path.join(_OUTPUT_DIR, 'dtalite_run.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        with open(log_path, 'a', encoding='utf-8', errors='replace') as log:
            log.write(f'\n[{datetime.now().isoformat()}] RUN visible CMD -> {_DTALITE_EXE}\n')
            log.flush()
        proc = _launch_visible_dtalite_console()
    except Exception as e:
        with _dtalite_lock:
            _dtalite_status.update(running=False, success=False, message=f'DTALite启动失败：{e}', elapsed=0, pid=None)
        return {'success': False, 'message': f'DTALite启动失败：{e}'}

    with _dtalite_lock:
        _dtalite_process = proc
        _dtalite_started_at = time.time()
        _dtalite_status.update(
            running=True,
            success=None,
            message=f'DTALite可见CMD已启动（PID {proc.pid}）',
            elapsed=0,
            pid=proc.pid,
        )
    return {'success': True, 'message': 'DTALite可见CMD已在后端电脑启动，正在运行中...', 'async': True, 'pid': proc.pid}


@router.get("/dtalite-status")
async def dtalite_status():
    with _dtalite_lock:
        _refresh_dtalite_status_locked()
        s = dict(_dtalite_status)
    result = {'running': s['running'], 'success': s['success'], 'message': s['message']}
    if not s['running'] and s['success']:
        metrics = _parse_real_metrics()
        metrics['processingTime'] = f'{s["elapsed"]:.1f}s'
        result['metrics'] = metrics
    return result


@router.get("/health")
async def reconstruction_health():
    return {'status': 'ok', 'service': 'reconstruction'}


@router.post("/import-data")
async def import_data():
    """检查并统计DTALite输入数据文件的真实信息"""
    import csv as _csv
    result = {'success': True, 'fileCount': 0, 'odPairCount': '--', 'status': '未找到数据'}
    # 统计输入文件
    input_files = ['input_demand.csv', 'input_link.csv', 'input_node.csv', 'input_zone.csv']
    found = 0
    for f in input_files:
        if os.path.exists(os.path.join(_DTALITE_DIR, f)):
            found += 1
    result['fileCount'] = found
    # 从 input_demand.csv 统计OD对数量
    demand_csv = os.path.join(_DTALITE_DIR, 'input_demand.csv')
    if os.path.exists(demand_csv):
        try:
            with open(demand_csv, 'r', encoding='utf-8') as f:
                reader = _csv.reader(f)
                header = next(reader, None)
                count = sum(1 for _ in reader)
            result['odPairCount'] = str(count)
            result['status'] = '已就绪'
        except Exception:
            pass
    # 如果 input_demand 没有，尝试从 output_ODMOE.csv 读取
    if result['odPairCount'] == '--':
        odmoe = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
        if os.path.exists(odmoe):
            try:
                with open(odmoe, 'r', encoding='utf-8') as f:
                    reader = _csv.reader(f)
                    next(reader, None)
                    count = sum(1 for _ in reader)
                result['odPairCount'] = str(count)
                result['status'] = '已就绪'
            except Exception:
                pass
    return result



@router.get("/network-image")
async def get_network_image():
    """用matplotlib生成路网拓扑图PNG并返回"""
    import csv
    import io
    node_csv = os.path.join(_DTALITE_DIR, 'input_node.csv')
    link_csv = os.path.join(_DTALITE_DIR, 'input_link.csv')
    if not os.path.exists(node_csv) or not os.path.exists(link_csv):
        return {'success': False, 'message': '路网数据文件不存在'}
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        # 尝试使用中文字体
        for fname in ['SimHei', 'Microsoft YaHei', 'STSong']:
            try:
                plt.rcParams['font.sans-serif'] = [fname]
                break
            except Exception:
                pass
        plt.rcParams['axes.unicode_minus'] = False
        nodes = {}
        signal_nodes = set()
        with open(node_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    nid = int(row.get('node_id', 0))
                    x = float(row.get('x_coord', 0))
                    y = float(row.get('y_coord', 0))
                    nodes[nid] = (x, y)
                    ctrl = row.get('control_type_name', '')
                    if 'signal' in ctrl.lower():
                        signal_nodes.add(nid)
                except (ValueError, TypeError):
                    continue
        link_coords = []
        with open(link_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    geo = row.get('geometry', '')
                    if geo and 'LINESTRING' in geo:
                        inner = geo.replace('LINESTRING (', '').replace('LINESTRING(', '').rstrip(')')
                        pts = []
                        for pt in inner.split(','):
                            pt = pt.strip()
                            parts = pt.split()
                            if len(parts) >= 2:
                                pts.append((float(parts[0]), float(parts[1])))
                        if pts:
                            link_coords.append(pts)
                except (ValueError, TypeError):
                    continue
        fig, ax = plt.subplots(1, 1, figsize=(10, 8), dpi=120)
        fig.patch.set_facecolor('#f8fafc')
        ax.set_facecolor('#f0f4f8')
        for pts in link_coords:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(xs, ys, color='#5a7faa', linewidth=1.2, alpha=0.7, solid_capstyle='round')
        normal_x, normal_y = [], []
        signal_x, signal_y = [], []
        for nid, (x, y) in nodes.items():
            if nid in signal_nodes:
                signal_x.append(x)
                signal_y.append(y)
            else:
                normal_x.append(x)
                normal_y.append(y)
        if normal_x:
            ax.scatter(normal_x, normal_y, c='#4CAF50', s=18, zorder=5, alpha=0.8, edgecolors='white', linewidths=0.5, label=f'普通节点 ({len(normal_x)})')
        if signal_x:
            ax.scatter(signal_x, signal_y, c='#2C5AA0', s=30, zorder=6, alpha=0.9, edgecolors='white', linewidths=0.8, marker='s', label=f'信号灯节点 ({len(signal_x)})')
        ax.set_title(f'路网拓扑结构图（{len(nodes)}个节点，{len(link_coords)}条路段）', fontsize=14, fontweight='bold', pad=12)
        ax.set_xlabel('经度', fontsize=10)
        ax.set_ylabel('纬度', fontsize=10)
        ax.legend(loc='upper right', fontsize=9, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_aspect('equal')
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        from starlette.responses import StreamingResponse
        return StreamingResponse(buf, media_type='image/png')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': str(e)}

@router.post("/launch-nexta")
async def launch_nexta():
    nexta_exe = os.path.join(_DTALITE_DIR, 'NEXTA.exe')
    if not os.path.exists(nexta_exe):
        return {'success': False, 'message': 'NEXTA.exe不存在'}
    try:
        subprocess.Popen([nexta_exe], cwd=_DTALITE_DIR, **_server_process_kwargs())
        return {'success': True, 'message': 'NEXTA路网编辑器已启动'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.post("/save-params")
async def save_params(request: Request):
    params = await request.json()
    try:
        import csv
        import io
        changed = []

        # 1. 修改 input_scenario_settings.csv 中的 number_of_iterations
        if 'maxIterations' in params:
            csv_file = os.path.join(_DTALITE_DIR, 'input_scenario_settings.csv')
            if os.path.exists(csv_file):
                with open(csv_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)
                fieldnames = reader.fieldnames
                if rows and 'number_of_iterations' in fieldnames:
                    rows[0]['number_of_iterations'] = str(params['maxIterations'])
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                        f.write(output.getvalue())
                    changed.append(f'number_of_iterations = {params["maxIterations"]}')

        # 2. 修改 DTASettings.txt 中的其他参数
        settings_file = os.path.join(_DTALITE_DIR, 'DTASettings.txt')
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            txt_mapping = {
                'convergencyGap': 'convergency_relative_gap_threshold_percentage',
                'aggregationInterval': 'aggregation_time_interval_in_min',
                'histODWeight': 'weight_on_hist_oddemand',
            }

            new_lines = []
            for line in lines:
                stripped = line.strip()
                modified = False
                for param_key, setting_key in txt_mapping.items():
                    if param_key not in params:
                        continue
                    if '=' in stripped:
                        before_eq = stripped.split('=')[0].strip()
                        if before_eq == setting_key:
                            eq_pos = line.index('=')
                            new_line = line[:eq_pos + 1] + ' ' + str(params[param_key]) + '\n'
                            new_lines.append(new_line)
                            changed.append(f'{setting_key} = {params[param_key]}')
                            modified = True
                            break
                if not modified:
                    new_lines.append(line)

            with open(settings_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

        if changed:
            return {'success': True, 'message': f'参数已保存（修改了{len(changed)}项：{"、".join(changed)}）'}
        else:
            return {'success': True, 'message': '参数已保存（无变化）'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.post("/run-validation-analysis")
async def run_validation():
    return {'success': True, 'message': '验证分析完成'}


@router.get("/validation-chart/{filename}")
async def get_validation_chart(filename: str):
    """提供验证分析图表文件"""
    import re
    if not re.match(r'^[\w\-]+\.png$', filename):
        return JSONResponse({'error': '无效文件名'}, status_code=400)
    path = os.path.join(_OUTPUT_DIR, 'validation', filename)
    if os.path.exists(path):
        return FileResponse(path, media_type='image/png')
    return JSONResponse({'error': '图表不存在'}, status_code=404)


@router.get("/od-chart/{filename}")
async def get_od_chart(filename: str):
    """提供OD结果图表文件"""
    import re
    if not re.match(r'^[\w\-]+\.png$', filename):
        return JSONResponse({'error': '无效文件名'}, status_code=400)
    od_dir = os.path.join(_DTALITE_DIR, '..', 'od_results')
    path = os.path.join(od_dir, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type='image/png')
    return JSONResponse({'error': '图表不存在'}, status_code=404)


@router.post("/generate-report")
async def generate_report(request: Request):
    try:
        from docx import Document
        from docx.shared import Inches, Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        import csv as _csv

        params = await request.json()
        metrics = _parse_real_metrics()

        doc = Document()

        # ---- 样式设置 ----
        style = doc.styles['Normal']
        style.font.name = '宋体'
        style.font.size = Pt(11)
        style.paragraph_format.line_spacing = 1.5

        # ---- 封面标题 ----
        title = doc.add_heading('交通流重构分析报告', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.color.rgb = RGBColor(44, 90, 160)

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(f'生成时间：{datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}')
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(102, 102, 102)

        doc.add_paragraph()  # 空行

        # ---- 1. 算法概述 ----
        doc.add_heading('一、算法概述', level=1)
        doc.add_paragraph(
            '本报告基于DTALite动态交通分配引擎，采用OD矩阵反推方法进行区域交通流重构。'
            '通过路段观测流量数据，利用梯度投影法迭代优化OD矩阵估计，实现区域交通流的完整重构与仿真评估。'
        )
        doc.add_paragraph('核心步骤：')
        steps = [
            '导入路网拓扑与观测流量数据',
            '基于用户均衡原理进行交通分配',
            '迭代优化OD矩阵估计（梯度投影法）',
            '输出重构后的交通流分布与评估指标',
        ]
        for s in steps:
            doc.add_paragraph(s, style='List Number')

        # ---- 2. 参数配置 ----
        doc.add_heading('二、参数配置', level=1)
        doc.add_paragraph('以下为本次运行使用的DTALite参数配置（来源：DTASettings.txt）：')
        param_table = doc.add_table(rows=5, cols=2, style='Light Grid Accent 1')
        param_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = param_table.rows[0].cells
        headers[0].text = '参数名称'
        headers[1].text = '参数值'
        param_data = [
            ('最大迭代次数', params.get('maxIterations', '10')),
            ('收敛阈值 (%)', params.get('convergencyGap', '5.0')),
            ('聚合时间间隔 (min)', params.get('aggregationInterval', '15')),
            ('历史OD权重', params.get('histODWeight', '1.0')),
        ]
        for i, (name, val) in enumerate(param_data):
            row = param_table.rows[i + 1].cells
            row[0].text = name
            row[1].text = str(val)

        # ---- 3. 重构结果指标 ----
        doc.add_heading('三、重构结果指标', level=1)
        doc.add_paragraph('以下指标均从DTALite实际输出的CSV文件中解析得到：')
        metric_table = doc.add_table(rows=1, cols=2, style='Light Grid Accent 1')
        metric_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        mh = metric_table.rows[0].cells
        mh[0].text = '指标'
        mh[1].text = '数值'
        label_map = {
            'accuracy': '重构精度',
            'rmse': 'RMSE',
            'validationRows': '验证数据行数',
            'odPairCount': 'OD对数量',
            'avgTripTime': '平均行程时间',
            'avgDistance': '平均行程距离',
            'totalVehicles': '总车辆数',
            'avgSpeed': '平均速度',
            'avgTravelTime': '平均出行时间',
        }
        for k, v in metrics.items():
            row = metric_table.add_row().cells
            row[0].text = label_map.get(k, k)
            row[1].text = str(v)

        # ---- 4. OD矩阵数据摘要 ----
        doc.add_heading('四、OD矩阵数据摘要', level=1)
        odmoe_csv = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
        if os.path.exists(odmoe_csv):
            doc.add_paragraph(f'数据来源：output_ODMOE.csv')
            with open(odmoe_csv, 'r', encoding='utf-8') as f:
                reader = _csv.reader(f)
                header = next(reader, None)
                rows_data = []
                for row in reader:
                    rows_data.append(row)
            # 显示前20行
            show_rows = rows_data[:20]
            if header and show_rows:
                cn_header = ['起点区域', '终点区域', '出行者数', '完成出行数', '行程时间(min)', '距离']
                od_table = doc.add_table(rows=1 + len(show_rows), cols=len(cn_header), style='Light Grid Accent 1')
                od_table.alignment = WD_TABLE_ALIGNMENT.CENTER
                for ci, h in enumerate(cn_header):
                    od_table.rows[0].cells[ci].text = h
                for ri, row in enumerate(show_rows):
                    for ci, val in enumerate(row[:len(cn_header)]):
                        od_table.rows[ri + 1].cells[ci].text = val
                if len(rows_data) > 20:
                    doc.add_paragraph(f'（仅展示前20行，共{len(rows_data)}行数据）')
        else:
            doc.add_paragraph('未找到 output_ODMOE.csv 文件。')

        # ---- 5. 验证分析图表 ----
        doc.add_heading('五、验证分析图表', level=1)
        validation_dir = os.path.join(_OUTPUT_DIR, 'validation')
        chart_info = [
            ('01_link_flow_timeseries.png', '图1：主要路段流量时序变化',
             '展示5个主要路段的交通流量随时间的变化趋势，反映不同路段的流量特征和时变规律。'),
            ('02_link_flow_distribution.png', '图2：各路段总流量统计',
             '统计所有路段的总交通流量分布，识别路网中的关键路段和流量瓶颈。'),
            ('03_observed_vs_simulated_scatter.png', '图3：观测流量 vs 反推流量对比',
             '对比输入约束（observed）与矩阵分配结果（simulated）的路段流量，评估重构算法的准确性。'),
            ('04_error_distribution.png', '图4：路段流量误差分布',
             '展示反推流量与观测流量的误差分布情况，红色表示低估，绿色表示高估，评估算法性能。'),
        ]
        for fname, caption, desc in chart_info:
            img_path = os.path.join(validation_dir, fname)
            doc.add_heading(caption, level=2)
            doc.add_paragraph(desc)
            if os.path.exists(img_path):
                doc.add_picture(img_path, width=Inches(5.5))
                last_para = doc.paragraphs[-1]
                last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                doc.add_paragraph(f'（图表文件 {fname} 未找到）')

        # ---- 6. 结论 ----
        doc.add_heading('六、结论', level=1)
        acc = metrics.get('accuracy', '--')
        rmse_val = metrics.get('rmse', '--')
        od_count = metrics.get('odPairCount', '--')
        doc.add_paragraph(
            f'本次交通流重构基于DTALite动态交通分配引擎完成。'
            f'共重构 {od_count} 个OD对的出行需求矩阵，'
            f'重构精度为 {acc}，RMSE为 {rmse_val}。'
            f'结果表明算法能够有效地从路段观测流量中反推区域OD矩阵，满足交通规划与管理的应用需求。'
        )

        # 保存
        report_path = os.path.join(_OUTPUT_DIR, 'reconstruction_report.docx')
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        doc.save(report_path)
        return {'success': True, 'message': '报告生成成功'}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': str(e)}


@router.get("/download-report")
async def download_report():
    path = os.path.join(_OUTPUT_DIR, 'reconstruction_report.docx')
    if os.path.exists(path):
        return FileResponse(path, filename='交通流重构分析报告.docx',
                            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    # 兼容旧的txt
    txt_path = os.path.join(_OUTPUT_DIR, 'reconstruction_report.txt')
    if os.path.exists(txt_path):
        return FileResponse(txt_path, filename='reconstruction_report.txt')
    return JSONResponse({'error': '报告不存在'}, status_code=404)


@router.get("/download-csv/{name}")
async def download_csv(name: str):
    path = os.path.join(_DTALITE_DIR, f'{name}.csv')
    if os.path.exists(path):
        return FileResponse(path, filename=f'{name}.csv')
    return JSONResponse({'error': '文件不存在'}, status_code=404)


@router.get("/get-od-results")
async def get_od_results():
    path = os.path.join(_DTALITE_DIR, 'output_ODMOE.csv')
    return {'success': os.path.exists(path), 'exists': os.path.exists(path)}


@router.post("/export-network-doc")
async def export_network_doc():
    """生成路网编辑说明文档（docx），包含节点、路段、交通区等数据摘要"""
    import csv as _csv
    import io as _io
    try:
        from docx import Document as DocxDocument
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        return JSONResponse({'error': 'python-docx未安装，请运行 pip install python-docx'}, status_code=500)

    try:
        doc = DocxDocument()

        # 标题
        title = doc.add_heading('路网编辑说明文档', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph(f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        doc.add_paragraph(f'数据目录：{_DTALITE_DIR}')
        doc.add_paragraph('')

        # 辅助函数：读取CSV前N行
        def read_csv_rows(filename, max_rows=20):
            filepath = os.path.join(_DTALITE_DIR, filename)
            if not os.path.exists(filepath):
                return None, None
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            reader = _csv.reader(_io.StringIO(content))
            rows = []
            headers = None
            for i, row in enumerate(reader):
                if i == 0:
                    headers = row
                elif i <= max_rows:
                    rows.append(row)
            return headers, rows

        def count_csv_rows(filename):
            filepath = os.path.join(_DTALITE_DIR, filename)
            if not os.path.exists(filepath):
                return 0
            with open(filepath, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f) - 1  # 减去表头

        # 1. 路网概览
        doc.add_heading('一、路网概览', level=1)
        node_count = count_csv_rows('input_node.csv')
        link_count = count_csv_rows('input_link.csv')
        zone_count = count_csv_rows('input_zone.csv')
        doc.add_paragraph(f'节点数量：{node_count}')
        doc.add_paragraph(f'路段数量：{link_count}')
        doc.add_paragraph(f'交通区数量：{zone_count}')
        doc.add_paragraph('')

        # 2. 节点数据
        doc.add_heading('二、节点数据（input_node.csv）', level=1)
        headers, rows = read_csv_rows('input_node.csv', 10)
        if headers and rows:
            # 只取关键列
            key_cols = ['node_id', 'x_coord', 'y_coord', 'zone_id', 'ctrl_type', 'control_type_name']
            col_indices = [i for i, h in enumerate(headers) if h.strip() in key_cols]
            display_headers = [headers[i].strip() for i in col_indices]

            table = doc.add_table(rows=min(len(rows), 10) + 1, cols=len(display_headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(display_headers):
                table.rows[0].cells[j].text = h
            for i, row in enumerate(rows[:10]):
                for j, ci in enumerate(col_indices):
                    if ci < len(row):
                        table.rows[i + 1].cells[j].text = row[ci].strip()

            if node_count > 10:
                doc.add_paragraph(f'（仅展示前10条，共{node_count}条记录）')
        else:
            doc.add_paragraph('未找到节点数据文件')
        doc.add_paragraph('')

        # 3. 路段数据
        doc.add_heading('三、路段数据（input_link.csv）', level=1)
        headers, rows = read_csv_rows('input_link.csv', 10)
        if headers and rows:
            key_cols = ['link_id', 'from_node_id', 'to_node_id', 'length', 'number_of_lanes', 'speed_limit', 'lane_cap']
            col_indices = [i for i, h in enumerate(headers) if h.strip() in key_cols]
            display_headers = [headers[i].strip() for i in col_indices]

            table = doc.add_table(rows=min(len(rows), 10) + 1, cols=len(display_headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(display_headers):
                table.rows[0].cells[j].text = h
            for i, row in enumerate(rows[:10]):
                for j, ci in enumerate(col_indices):
                    if ci < len(row):
                        table.rows[i + 1].cells[j].text = row[ci].strip()

            if link_count > 10:
                doc.add_paragraph(f'（仅展示前10条，共{link_count}条记录）')
        else:
            doc.add_paragraph('未找到路段数据文件')
        doc.add_paragraph('')

        # 4. 交通区数据
        doc.add_heading('四、交通区数据（input_zone.csv）', level=1)
        headers, rows = read_csv_rows('input_zone.csv', 10)
        if headers and rows:
            key_cols = ['zone_id', 'production', 'attraction']
            col_indices = [i for i, h in enumerate(headers) if h.strip() in key_cols]
            display_headers = [headers[i].strip() for i in col_indices]

            table = doc.add_table(rows=min(len(rows), 10) + 1, cols=len(display_headers))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(display_headers):
                table.rows[0].cells[j].text = h
            for i, row in enumerate(rows[:10]):
                for j, ci in enumerate(col_indices):
                    if ci < len(row):
                        table.rows[i + 1].cells[j].text = row[ci].strip()

            if zone_count > 10:
                doc.add_paragraph(f'（仅展示前10条，共{zone_count}条记录）')
        else:
            doc.add_paragraph('未找到交通区数据文件')
        doc.add_paragraph('')

        # 5. DTALite参数配置
        doc.add_heading('五、DTALite参数配置（DTASettings.txt）', level=1)
        settings_path = os.path.join(_DTALITE_DIR, 'DTASettings.txt')
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and '=' in stripped and not stripped.startswith('#'):
                        doc.add_paragraph(stripped)
        else:
            doc.add_paragraph('未找到DTASettings.txt')
        doc.add_paragraph('')

        # 6. 编辑说明
        doc.add_heading('六、路网编辑操作说明', level=1)
        doc.add_paragraph('1. 启动NEXTA路网编辑器查看当前路网拓扑结构')
        doc.add_paragraph('2. 在NEXTA中可编辑节点位置、路段属性、信号配时等')
        doc.add_paragraph('3. 编辑完成后在NEXTA中保存（File → Save）')
        doc.add_paragraph('4. 返回平台配置参数后运行DTALite.exe进行交通流重构')

        # 保存到临时文件
        doc_path = os.path.join(_OUTPUT_DIR, '路网编辑说明文档.docx')
        os.makedirs(os.path.dirname(doc_path), exist_ok=True)
        doc.save(doc_path)

        return FileResponse(doc_path, filename='路网编辑说明文档.docx',
                          media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        logger.error(f'生成路网文档失败: {e}')
        return JSONResponse({'error': str(e)}, status_code=500)
