"""平台运行模式：演示模式（demo）/ 学生模式（student）。

两种模式共用同一套后端、算法与前端接口，区别只在于**后端是否会弹出窗口**：

- 演示模式（demo）：后端启动 CMD、SUMO-GUI、CARLA 等子进程时，在运行平台的
  桌面弹出可见窗口，便于课堂演示、讲解和排障。
- 学生模式（student）：后端启动同样的子进程，但一律静默执行（``CREATE_NO_WINDOW``
  + ``SW_HIDE``），不占用服务器桌面；SUMO 使用无界面的 ``sumo`` 可执行文件。
  前端轮询状态、任务分发、结果回传等链路与演示模式完全一致，学生照常使用。

模式由启动脚本写入环境变量 ``ZXK_RUN_MODE``。未设置或无法识别时按学生模式处理，
避免平台在教室服务器上误弹窗口；需要演示时显式选择演示模式。
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

ENV_RUN_MODE = "ZXK_RUN_MODE"

DEMO = "demo"
STUDENT = "student"

MODE_LABELS = {
    DEMO: "演示模式",
    STUDENT: "学生模式",
}

_DEMO_ALIASES = {
    "demo",
    "demo_mode",
    "演示",
    "演示模式",
    "show",
    "1",
    "true",
    "yes",
    "on",
}

_STUDENT_ALIASES = {
    "student",
    "student_mode",
    "学生",
    "学生模式",
    "class",
    "0",
    "false",
    "no",
    "off",
}


def normalize_mode(value: Any, default: str = STUDENT) -> str:
    """把任意输入归一为 ``demo`` 或 ``student``，无法识别时返回默认值。"""

    text = str(value or "").strip().lower()
    if text in _STUDENT_ALIASES:
        return STUDENT
    if text in _DEMO_ALIASES:
        return DEMO
    return default


def get_run_mode() -> str:
    """读取当前进程的运行模式（默认学生模式）。"""

    return normalize_mode(os.environ.get(ENV_RUN_MODE))


def is_demo_mode() -> bool:
    return get_run_mode() == DEMO


def is_student_mode() -> bool:
    return get_run_mode() == STUDENT


def mode_label(mode: str | None = None) -> str:
    return MODE_LABELS.get(mode or get_run_mode(), MODE_LABELS[STUDENT])


def allow_visible_windows() -> bool:
    """是否允许后端弹出 CMD / SUMO-GUI / CARLA 等可见窗口。"""

    return is_demo_mode()


def child_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """复制环境变量并写入运行模式，确保算法子进程继承同一模式。"""

    result = dict(os.environ if env is None else env)
    result[ENV_RUN_MODE] = get_run_mode()
    result.setdefault("PYTHONIOENCODING", "utf-8")
    result.setdefault("PYTHONUTF8", "1")
    return result


def hidden_startupinfo():
    """Windows 下隐藏子进程窗口的 STARTUPINFO；其它平台返回 ``None``。"""

    if os.name != "nt":
        return None
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        return info
    except Exception:
        return None


def server_process_kwargs() -> dict[str, Any]:
    """服务端后台子进程的静默启动参数（两种模式都静默）。"""

    if os.name != "nt":
        return {}
    options: dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    info = hidden_startupinfo()
    if info is not None:
        options["startupinfo"] = info
    return options


def window_creationflags(demo_flags: int | None = None) -> int:
    """按模式返回 ``creationflags``。

    演示模式返回 ``demo_flags``（默认新建可见控制台），学生模式返回
    ``CREATE_NO_WINDOW``。
    """

    if os.name != "nt":
        return 0
    if is_student_mode():
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if demo_flags is None:
        return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return demo_flags


def apply_window_mode(options: dict[str, Any], demo_flags: int | None = None) -> dict[str, Any]:
    """就地给学生模式下的 Popen 参数补上隐藏窗口设置。"""

    if is_student_mode() and os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        info = hidden_startupinfo()
        if info is not None:
            options.setdefault("startupinfo", info)
    elif demo_flags is not None and os.name == "nt":
        options.setdefault("creationflags", demo_flags)
    return options


def prefer_sumo_gui(default: bool = True) -> bool:
    """算法脚本默认是否打开 SUMO-GUI；学生模式一律无界面。"""

    if is_student_mode():
        return False
    return bool(default)


def describe() -> dict[str, Any]:
    """返回给接口/日志使用的模式描述。"""

    mode = get_run_mode()
    return {
        "run_mode": mode,
        "run_mode_label": mode_label(mode),
        "can_launch_windows": allow_visible_windows(),
        "windows_suppressed": is_student_mode(),
        "sumo_gui": prefer_sumo_gui(),
    }
