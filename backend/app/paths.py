"""
路径配置 — 兼容开发模式和 PyInstaller 打包模式。
所有模块应从此处导入路径常量，而非自行用 __file__ 计算。

打包模式下，安装目录（如 C:\Program Files\智信优控）是只读的，
所有运行时需要写入的文件（数据库、上传、算法输出等）放到
%APPDATA%\智信优控\ 下。
"""
import os
import sys

if getattr(sys, 'frozen', False):
    # PyInstaller 打包模式：sys._MEIPASS 指向 _internal 目录
    _INTERNAL_DIR = sys._MEIPASS
    BACKEND_DIR = os.path.join(_INTERNAL_DIR, 'backend')
    PROJECT_ROOT = _INTERNAL_DIR

    # 运行时可写目录（%APPDATA%\智信优控）
    RUNTIME_DATA_DIR = os.path.join(
        os.environ.get('APPDATA', os.path.expanduser('~')),
        '智信优控'
    )
    os.makedirs(RUNTIME_DATA_DIR, exist_ok=True)
else:
    # 开发模式：本文件在 backend/app/paths.py
    BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
    # 开发模式下可写目录就是项目本身
    RUNTIME_DATA_DIR = PROJECT_ROOT

FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'frontend')
ALGORITHMS_DIR = os.path.join(BACKEND_DIR, 'algorithms')

# 可写路径 — 打包模式下指向 %APPDATA%，开发模式下指向项目目录
UPLOADS_DIR = os.path.join(RUNTIME_DATA_DIR, 'backend', 'uploads') if getattr(sys, 'frozen', False) else os.path.join(BACKEND_DIR, 'uploads')
DB_PATH = os.path.join(RUNTIME_DATA_DIR, 'backend', 'data.db') if getattr(sys, 'frozen', False) else os.path.join(BACKEND_DIR, 'data.db')
RUNTIME_ALGO_DIR = os.path.join(RUNTIME_DATA_DIR, 'backend', 'algorithms') if getattr(sys, 'frozen', False) else ALGORITHMS_DIR

# DTALite 工具目录
DTALITE_DIR = os.path.join(ALGORITHMS_DIR, 'traffic_reconstruction', 'dtalite')

def resolve_external_project_root(name, env_var, legacy_default=None, marker=None):
    """解析外部配套项目（VIC-Sim / HIL 等）的根目录。

    优先级：
      1. 环境变量（显式指定，安装版或多份拷贝时使用）
      2. 项目根目录下的同名子目录（本仓库把配套项目放在平台根目录下，
         例如 <项目根>/VIC-Sim）
      3. 历史硬编码的开发机路径（如 D:\\chenshi\\VIC-Sim）

    marker: 相对路径，用于判断候选目录是否是可用的项目根
            （例如 'backend/server.py'）。不传则只判断目录是否存在。
    """
    def _usable(path):
        if not path or not os.path.isdir(path):
            return False
        return marker is None or os.path.exists(os.path.join(path, marker))

    env_value = (os.environ.get(env_var) or '').strip()
    if env_value:
        return os.path.abspath(env_value)

    bundled = os.path.join(PROJECT_ROOT, name)
    if _usable(bundled):
        return bundled

    if legacy_default and _usable(legacy_default):
        return os.path.abspath(legacy_default)

    # 都不存在时返回约定的内置目录，便于日志和报错指向期望位置
    return bundled


def algo_output_dir(module_name: str, subdir: str = 'output') -> str:
    """
    获取算法模块的输出目录。

    Args:
        module_name: 算法模块名称（如 'traffic_prediction', 'traffic_reconstruction'）
        subdir: 子目录名称（默认 'output'）

    Returns:
        输出目录的完整路径
    """
    output_path = os.path.join(RUNTIME_ALGO_DIR, module_name, subdir)
    os.makedirs(output_path, exist_ok=True)
    return output_path
