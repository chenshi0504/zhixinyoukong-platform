"""编译版路由模块的学生模式兼容层。

平台有一部分路由以 ``.pyd`` 形式发布（源码不在仓库里），它们直接调用
``subprocess.Popen('start "标题" cmd /k "..."', shell=True)`` 在服务器桌面弹
CMD 窗口。学生模式要求"绝不弹窗"，但又不能在仓库里改到这些编译模块的源码，
因此在导入后把模块内的 ``subprocess`` 全局替换成一层代理：

- ``start "标题" cmd /k "..."`` 改写为隐藏窗口的 ``cmd /c ...``，输出写入
  ``backend/logs/compiled_router_console.log``；
- 其余 ``Popen`` / ``run`` 调用追加 ``CREATE_NO_WINDOW`` + ``SW_HIDE``；
- 演示模式完全透传，保持原有的可见窗口行为。

只处理 ``.pyd`` / ``.so`` 模块，纯 Python 路由不受影响。
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from . import run_mode

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "compiled_router_console.log")

_START_CMD_RE = re.compile(
    r'^\s*start\s+"[^"]*"\s+cmd(?:\.exe)?\s+/[kK]\s+(.+?)\s*$',
    re.IGNORECASE | re.DOTALL,
)


def _is_compiled(module) -> bool:
    path = str(getattr(module, "__file__", "") or "").lower()
    return path.endswith((".pyd", ".so", ".dylib"))


def _open_console_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    handle = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    handle.write(f"\n[{run_mode.mode_label()}] 编译版路由子进程输出\n")
    handle.flush()
    return handle


def _hidden_options(kwargs: dict[str, Any]) -> dict[str, Any]:
    options = dict(kwargs)
    options.update(run_mode.server_process_kwargs())
    options["env"] = run_mode.child_env(options.get("env"))
    return options


def _strip_outer_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].strip()
    return text


class _SubprocessProxy:
    """只改窗口行为，其余属性原样转发给标准库 subprocess。"""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def Popen(self, args, **kwargs):
        if not run_mode.is_student_mode() or os.name != "nt":
            return subprocess.Popen(args, **kwargs)

        command = args[0] if isinstance(args, (list, tuple)) and args else args
        if isinstance(command, str):
            match = _START_CMD_RE.match(command)
            if match:
                inner = _strip_outer_quotes(match.group(1))
                handle = _open_console_log()
                handle.write(f"$ {inner}\n")
                handle.flush()
                options = _hidden_options(kwargs)
                options.pop("shell", None)
                options["stdin"] = subprocess.DEVNULL
                options["stdout"] = handle
                options["stderr"] = handle
                return subprocess.Popen(inner, shell=True, **options)

        return subprocess.Popen(args, **_hidden_options(kwargs))

    def run(self, args, **kwargs):
        if not run_mode.is_student_mode() or os.name != "nt":
            return subprocess.run(args, **kwargs)
        command = args[0] if isinstance(args, (list, tuple)) and args else args
        if isinstance(command, str):
            match = _START_CMD_RE.match(command)
            if match:
                inner = _strip_outer_quotes(match.group(1))
                handle = _open_console_log()
                options = _hidden_options(kwargs)
                options.pop("shell", None)
                options["stdin"] = subprocess.DEVNULL
                options["stdout"] = handle
                options["stderr"] = handle
                return subprocess.run(inner, shell=True, **options)
        return subprocess.run(args, **_hidden_options(kwargs))


_PROXY = _SubprocessProxy()


def silence_compiled_router(module) -> bool:
    """学生模式下把编译版路由模块里的 subprocess 换成静默代理。

    返回是否发生了替换，便于测试断言。
    """

    if not run_mode.is_student_mode():
        return False
    if not _is_compiled(module):
        return False
    current = getattr(module, "subprocess", None)
    if current is None or current is _PROXY:
        return False
    module.subprocess = _PROXY
    return True
