"""
Application startup script.
Supports two modes:
  - dev:     python run.py (auto-open browser; hot reload only when ZXK_DEV_RELOAD=1)
  - desktop: called from desktop_app.py (reload=False, no browser)

热重载默认关闭：学生会话状态保存在进程内存中，任何一次应用重启都会清空
全部在线学生的会话与任务，因此只有显式设置 ZXK_DEV_RELOAD=1 才会开启。
"""
import sys
import os
import shutil
import time
import subprocess
import threading
import atexit
import signal

# Add backend directory to path
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_FROZEN_BACKEND_DIR = os.path.join(_MODULE_DIR, 'backend')
_BACKEND_DIR = _FROZEN_BACKEND_DIR if getattr(sys, 'frozen', False) and os.path.isdir(_FROZEN_BACKEND_DIR) else _MODULE_DIR
sys.path.insert(0, _BACKEND_DIR)

# 本次启动日志里有中文和 ✓/✗ 符号。若控制台或重定向后的 stdout 使用 gbk，
# 打印这些字符会抛 UnicodeEncodeError 并中断整个启动流程。这里统一改成
# utf-8 并对无法编码的字符降级替换，保证任何终端环境下都能正常启动。
for _stream_name in ('stdout', 'stderr'):
    _stream = getattr(sys, _stream_name, None)
    try:
        if _stream is not None and hasattr(_stream, 'reconfigure'):
            _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from app.config import settings
from app import run_mode

LOCAL_APP_HOST = settings.LOCAL_APP_HOST
LOCAL_APP_PORT = settings.LOCAL_APP_PORT
LOGIN_URL = f'http://localhost:{LOCAL_APP_PORT}/src/pages/登录界面/login.html'

def _get_algo_log_dir():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = _BACKEND_DIR
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def _log_algo_event(message):
    line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}'
    print(line)
    try:
        with open(os.path.join(_get_algo_log_dir(), 'algo-startup.log'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

# 算法子服务配置
_ALGO_DIR = os.path.join(_BACKEND_DIR, 'algorithms')
ALGORITHM_SERVERS = [
    # 注：数据融合、交通流预测、数据采集已编译为.pyd模块，由主服务直接导入
    ("交通流重构", os.path.join(_ALGO_DIR, 'traffic_reconstruction', 'service.py'), 5001),
    ("SUMO仿真算法测试", os.path.join(_ALGO_DIR, 'simulation', 'service.py'), 8001),
]


def get_startup_config(mode='dev'):
    """根据启动模式返回配置字典。
    mode='dev':     开发模式，自动打开浏览器，热重载由 ZXK_DEV_RELOAD 决定
    mode='desktop': 桌面模式，reload=False，不打开浏览器
    """
    if mode == 'desktop':
        return {
            'reload': False,
            'open_browser': False,
            'reload_dirs': None,
            'log_level': 'warning',
        }
    else:
        # 学生会话（采集 / 融合 / 预测 / 小车 HIL）的状态全部保存在进程内存里。
        # 而各模块在运行期会往 runtime/、algorithms/ 等目录复制或生成 .py 文件
        # （例如采集会复制 yolo11_tracker.py），watchfiles 会把它判定为源码变更
        # 并重启应用，导致所有在线学生的会话与任务瞬间被清空、相互干扰。
        # 因此默认关闭热重载；确实需要时用 ZXK_DEV_RELOAD=1 显式开启。
        dev_reload = os.environ.get('ZXK_DEV_RELOAD', '').strip().lower() in {'1', 'true', 'yes', 'on'}
        return {
            'reload': dev_reload,
            'open_browser': True,
            # 只监听应用源码目录，且必须用绝对路径，避免热重载把整个 backend
            # 都纳入监视范围。
            'reload_dirs': [os.path.join(_BACKEND_DIR, 'app')],
            # 关键：runtime / algorithms / uploads 等目录在运行期会被写入 .py
            # 文件（每个学生会话会复制算法目录、生成自定义算法脚本）。一旦这些
            # 写入触发热重载，应用会重启并清空全部内存态会话状态，导致学生之间
            # 相互影响。这里显式排除，保证热重载只响应 app 源码改动。
            'reload_excludes': [
                'runtime/**',
                'algorithms/**',
                'uploads/**',
                'logs/**',
                'tests/**',
                'data/**',
                'knowledge_base/**',
                '**/__pycache__/**',
                '**/*.pyc',
            ],
            'log_level': 'info',
        }


def kill_port_processes(ports):
    """尝试杀掉占用指定端口的进程（仅Windows）"""
    killed = []
    for port in ports:
        try:
            result = subprocess.run(
                f'netstat -ano | findstr ":{port}" | findstr "LISTENING"',
                shell=True, capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0:
                        try:
                            subprocess.run(f'taskkill /F /PID {pid} /T', shell=True,
                                           capture_output=True, timeout=5)
                            killed.append((port, pid))
                        except Exception:
                            pass
        except Exception:
            pass
    if killed:
        time.sleep(1)
    return killed


def resolve_algorithm_python():
    """返回算法子服务应使用的 Python 命令。"""
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

    for env_name in ('ZXK_ALGO_PYTHON_EXE', 'ZXK_PYTHON_EXE'):
        python_exe = os.environ.get(env_name, '').strip()
        if python_exe:
            return [python_exe]

    python_path = shutil.which('python')
    if python_path:
        return [python_path]

    py_launcher = shutil.which('py')
    if py_launcher:
        return [py_launcher]

    return None


def start_algorithm_server(name, script_path, port):
    """启动单个算法子服务，返回进程对象或None"""
    try:
        python_cmd = resolve_algorithm_python()
        _log_algo_event(f'{name}: script={script_path}')
        if not python_cmd:
            _log_algo_event(f'{name}: 未找到可用 Python 解释器')
            print(f'  ✗ {name} 启动失败: 未找到可用的 Python 解释器，请安装 Python 或设置 ZXK_ALGO_PYTHON_EXE')
            return None
        _log_algo_event(f'{name}: python={python_cmd}')

        child_env = run_mode.child_env()
        existing_pythonpath = child_env.get('PYTHONPATH', '')
        child_env['PYTHONPATH'] = _BACKEND_DIR if not existing_pythonpath else _BACKEND_DIR + os.pathsep + existing_pythonpath
        child_env['PYTHONIOENCODING'] = 'utf-8'

        log_dir = _get_algo_log_dir()
        stdout_log = os.path.join(log_dir, f'algo_{port}.stdout.log')
        stderr_log = os.path.join(log_dir, f'algo_{port}.stderr.log')
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0

        with open(stdout_log, 'a', encoding='utf-8') as stdout_handle, open(stderr_log, 'a', encoding='utf-8') as stderr_handle:
            proc = subprocess.Popen(
                python_cmd + [script_path],
                cwd=os.path.dirname(script_path),
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creationflags,
            )
        time.sleep(0.5)
        if proc.poll() is not None:
            _log_algo_event(f'{name}: 启动后立即退出 code={proc.returncode} stderr={stderr_log}')
            print(f'  ✗ {name} 启动后立即退出 (code={proc.returncode})')
            return None
        _log_algo_event(f'{name}: 已启动 pid={proc.pid} port={port} stdout={stdout_log} stderr={stderr_log}')
        print(f'  ✓ {name} 已启动: http://localhost:{port}  (PID {proc.pid})')
        return proc
    except Exception as e:
        _log_algo_event(f'{name}: 启动异常 {e}')
        print(f'  ✗ {name} 启动失败: {e}')
        return None


def init_database():
    """初始化数据库"""
    from app.init_db import init_database as _init
    _init()


def start_sub_services(servers=None):
    """启动所有算法子服务，返回进程列表。
    servers: [(name, script_path, port), ...] 如果为None则使用默认配置
    """
    if servers is None:
        servers = ALGORITHM_SERVERS
    processes = []
    for name, script_path, port in servers:
        if os.path.exists(script_path):
            proc = start_algorithm_server(name, script_path, port)
            if proc:
                processes.append(proc)
            time.sleep(0.3)
        else:
            _log_algo_event(f'{name}: 脚本不存在 {script_path}')
            print(f'  ⚠ {name} 跳过: {os.path.basename(script_path)} 不存在')
    return processes


def cleanup_services(processes):
    """清理所有子进程。先尝试terminate，5秒后force kill。"""
    for p in processes:
        try:
            if p.poll() is None:
                p.terminate()
        except Exception:
            pass
    # 等待最多5秒
    deadline = time.time() + 5
    for p in processes:
        try:
            remaining = max(0, deadline - time.time())
            p.wait(timeout=remaining)
        except Exception:
            # 超时，强制杀掉
            try:
                p.kill()
            except Exception:
                pass


def start_services(mode='dev', on_stage=None):
    """启动所有后端服务。

    Args:
        mode: 'dev' 或 'desktop'
        on_stage: 可选回调函数 on_stage(stage_name, percent)，用于更新启动进度

    Returns:
        (child_processes, config) — 子进程列表和启动配置
    """
    config = get_startup_config(mode)

    def _report(stage, pct):
        if on_stage:
            on_stage(stage, pct)
        print(f'  [{pct}%] {stage}')

    # 0. 清理旧进程
    _report('清理旧进程...', 5)
    algorithm_ports = [port for _, _, port in ALGORITHM_SERVERS]
    # 只清理本平台真正会监听的端口：主服务 + ALGORITHM_SERVERS 声明的子服务。
    # 历史上这里还硬编码了 5000/5002/5003，但本仓库已无对应服务，继续清理会
    # 误杀机器上其它软件占用这些端口的进程。
    ports_to_clean = [LOCAL_APP_PORT] if getattr(sys, 'frozen', False) else sorted(set([LOCAL_APP_PORT] + algorithm_ports))
    kill_port_processes(ports_to_clean)

    # 1. 初始化数据库
    _report('初始化数据库...', 15)
    init_database()

    # 2. 启动算法子服务
    _report('启动算法子服务...', 30)
    if getattr(sys, 'frozen', False):
        _log_algo_event('packaged mode: skip standalone algorithm services')
        child_processes = []
    else:
        child_processes = start_sub_services()

    # 3. 启动主FastAPI服务（在当前线程或后台线程）
    _report('启动主平台服务...', 60)

    return child_processes, config


def run_uvicorn(config):
    """启动uvicorn服务（阻塞调用）"""
    import uvicorn
    kwargs = {
        'host': LOCAL_APP_HOST,
        'port': LOCAL_APP_PORT,
        'log_level': config.get('log_level', 'info'),
    }
    if config.get('reload'):
        kwargs['reload'] = True
        kwargs['reload_dirs'] = config.get('reload_dirs') or [os.path.join(_BACKEND_DIR, 'app')]
        if config.get('reload_excludes'):
            kwargs['reload_excludes'] = config['reload_excludes']
    else:
        kwargs['reload'] = False

    uvicorn.run("app.main:app", **kwargs)


def disable_conflicting_pyd(app_dir=None):
    """开发模式下，临时重命名与 .py 同名的 .pyd 文件，避免 uvicorn reload 加载旧版。
    返回被重命名的文件列表 [(pyd_path, renamed_path), ...]。
    """
    import glob
    if app_dir is None:
        app_dir = os.path.join(_BACKEND_DIR, 'app')
    renamed = []
    for py_file in glob.glob(os.path.join(app_dir, '**', '*.py'), recursive=True):
        base = os.path.splitext(py_file)[0]
        module_name = os.path.basename(base)
        pyd_pattern = os.path.join(os.path.dirname(py_file), f"{module_name}*.pyd")
        for pyd in glob.glob(pyd_pattern):
            disabled = pyd + '.dev_disabled'
            if os.path.exists(disabled):
                idx = 1
                while os.path.exists(f'{disabled}.{idx}'):
                    idx += 1
                disabled = f'{disabled}.{idx}'
            try:
                os.rename(pyd, disabled)
                renamed.append((pyd, disabled))
                print(f'  ⚠ 已禁用冲突的 .pyd: {os.path.relpath(pyd, _BACKEND_DIR)}')
            except Exception as e:
                print(f'  ✗ 无法重命名 {pyd}: {e}')
    return renamed


def restore_pyd(renamed_list):
    """恢复被 disable_conflicting_pyd 重命名的 .pyd 文件。"""
    for pyd, disabled in renamed_list:
        try:
            if os.path.exists(disabled):
                os.rename(disabled, pyd)
        except Exception:
            pass


def main():
    """开发模式入口（python run.py）"""
    print("=" * 60)
    print("  综合交通实验教学平台 - 后端服务（开发模式）")
    print(f"  运行模式: {run_mode.mode_label()}（{'弹窗演示' if run_mode.allow_visible_windows() else '静默运行'}）")
    print("=" * 60)

    # 开发模式下禁用冲突的 .pyd 文件
    disabled_pyds = disable_conflicting_pyd()

    child_processes, config = start_services(mode='dev')

    # 打印服务信息
    print("\n" + "-" * 60)
    print(f"  前端页面: http://localhost:{LOCAL_APP_PORT}")
    print(f"  API文档:  http://localhost:{LOCAL_APP_PORT}/api/docs")
    print("-" * 60)

    # 自动打开浏览器（统一启动脚本会设置 PLATFORM_SILENT=1，此时跳过）。
    # 学生模式下不占用服务器桌面，也不弹浏览器。
    if (
        config.get('open_browser')
        and os.environ.get('PLATFORM_SILENT') != '1'
        and not run_mode.is_student_mode()
    ):
        import webbrowser
        threading.Timer(3, lambda: webbrowser.open(LOGIN_URL)).start()

    # 注册退出清理
    def _cleanup():
        cleanup_services(child_processes)
        restore_pyd(disabled_pyds)

    atexit.register(_cleanup)
    signal.signal(signal.SIGINT, lambda *_: (_cleanup(), sys.exit(0)))

    # 启动uvicorn（阻塞）
    run_uvicorn(config)


if __name__ == "__main__":
    main()
