import json
import os
import runpy
import subprocess
import sys

_ENV_SCRIPT = "ZXK_RUN_PY_SCRIPT"
_ENV_ARGS = "ZXK_RUN_PY_ARGS"
_ENV_WORKDIR = "ZXK_RUN_PY_WORKDIR"


def build_script_command(script_path, cwd=None, script_args=None):
    abs_script_path = os.path.abspath(script_path)
    workdir = os.path.abspath(cwd or os.path.dirname(abs_script_path))
    args = list(script_args or [])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if getattr(sys, "frozen", False):
        env[_ENV_SCRIPT] = abs_script_path
        env[_ENV_WORKDIR] = workdir
        env[_ENV_ARGS] = json.dumps(args, ensure_ascii=False)
        return [sys.executable], env

    return [sys.executable, abs_script_path, *args], env


def launch_script(script_path, cwd=None, script_args=None, new_console=True):
    cmd, env = build_script_command(script_path, cwd=cwd, script_args=script_args)
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        cmd,
        cwd=os.path.abspath(cwd or os.path.dirname(os.path.abspath(script_path))),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def dispatch_script_from_env():
    script_path = os.environ.pop(_ENV_SCRIPT, "").strip()
    if not script_path:
        return False

    workdir = os.environ.pop(_ENV_WORKDIR, "").strip() or os.path.dirname(script_path)
    raw_args = os.environ.pop(_ENV_ARGS, "[]")
    try:
        script_args = json.loads(raw_args)
    except Exception:
        script_args = []
    if not isinstance(script_args, list):
        script_args = []

    abs_script_path = os.path.abspath(script_path)
    if not os.path.isfile(abs_script_path):
        raise FileNotFoundError(abs_script_path)

    os.chdir(os.path.abspath(workdir))
    raw_pythonpath = os.environ.get("PYTHONPATH", "")
    for extra_path in [item for item in raw_pythonpath.split(os.pathsep) if item]:
        if extra_path not in sys.path and os.path.isdir(extra_path):
            sys.path.insert(0, extra_path)
    script_dir = os.path.dirname(abs_script_path)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    sys.argv = [abs_script_path, *[str(arg) for arg in script_args]]
    runpy.run_path(abs_script_path, run_name="__main__")
    return True
