"""演示模式 / 学生模式（运行模式）测试。

覆盖：
- 模式解析与默认值（默认学生模式，避免误弹窗口）
- 访问上下文与健康接口暴露运行模式
- 后端 CMD 启动：演示模式建可见控制台，学生模式静默且输出进日志
- 实验算法 CMD：学生模式不经过 cmd.exe，不弹窗
- SUMO：学生模式降级为无界面 sumo，纯 GUI 工具明确拒绝
- CARLA：学生模式不自动拉起图形窗口，且不计入整体就绪
- 启动批处理确实包含模式询问
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import run_mode
from app import main as main_module
from app.routers import experiment_launchers
from app.routers import simulators


ROOT = Path(__file__).resolve().parents[2]
BAT_PATH = ROOT / "启动平台前后端.bat"


def _request(path: str, method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 41000),
            "server": ("test", 80),
        }
    )


class FakePopen:
    """记录 Popen 参数，不真正启动进程。"""

    last_call = None

    def __init__(self, *args, **kwargs):
        FakePopen.last_call = {"args": args, "kwargs": kwargs}
        self.pid = 43210
        self.returncode = None

    def poll(self):
        return None


def test_normalize_mode_aliases_and_default():
    assert run_mode.normalize_mode("demo") == "demo"
    assert run_mode.normalize_mode("演示模式") == "demo"
    assert run_mode.normalize_mode("1") == "demo"
    assert run_mode.normalize_mode("student") == "student"
    assert run_mode.normalize_mode("学生模式") == "student"
    assert run_mode.normalize_mode("0") == "student"
    # 未设置 / 无法识别 → 默认学生模式
    assert run_mode.normalize_mode("") == "student"
    assert run_mode.normalize_mode(None) == "student"
    assert run_mode.normalize_mode("whatever") == "student"


def test_run_mode_defaults_to_student(monkeypatch):
    monkeypatch.delenv(run_mode.ENV_RUN_MODE, raising=False)
    assert run_mode.get_run_mode() == "student"
    assert run_mode.allow_visible_windows() is False
    assert run_mode.prefer_sumo_gui() is False
    assert run_mode.child_env()["ZXK_RUN_MODE"] == "student"

    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "demo")
    assert run_mode.is_demo_mode() is True
    assert run_mode.allow_visible_windows() is True
    assert run_mode.prefer_sumo_gui() is True


def test_access_context_reports_run_mode(monkeypatch):
    from app.access_mode import access_context

    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    context = access_context(_request("/api/v1/access-context"))
    assert context["run_mode"] == "student"
    assert context["run_mode_label"] == "学生模式"
    assert context["can_launch_windows"] is False
    assert context["windows_suppressed"] is True
    # 学生模式不影响前端取任务与回传结果
    assert context["can_start_experiment_backends"] is True

    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "demo")
    context = access_context(_request("/api/v1/access-context"))
    assert context["run_mode"] == "demo"
    assert context["can_launch_windows"] is True


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属的窗口创建标志")
def test_launch_visible_cmd_student_mode_is_silent(monkeypatch, tmp_path):
    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    monkeypatch.setattr(main_module.subprocess, "Popen", FakePopen)
    log_path = str(tmp_path / "svc.log")

    main_module._launch_visible_cmd(
        "SUMO simulation backend",
        str(tmp_path),
        [sys.executable, "-c", "print('ok')"],
        run_mode.child_env(),
        log_path,
    )

    call = FakePopen.last_call
    kwargs = call["kwargs"]
    assert call["args"][0][:2] == ["cmd.exe", "/c"]
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert "startupinfo" in kwargs
    # 学生模式没有控制台，命令输出必须写入日志
    cmd_files = list(Path(tmp_path).glob("experiment_backend_*.cmd"))
    assert cmd_files, "应生成启动脚本"
    script = cmd_files[0].read_text(encoding="utf-8")
    assert ">>" in script and "2>&1" in script
    assert log_path in script
    # 控制台输出单独落盘，避免与被启动脚本自己写的 log_path 冲突
    assert ".console.log" in script


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属的窗口创建标志")
def test_launch_visible_cmd_demo_mode_opens_console(monkeypatch, tmp_path):
    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "demo")
    monkeypatch.setattr(main_module.subprocess, "Popen", FakePopen)
    log_path = str(tmp_path / "svc.log")

    main_module._launch_visible_cmd(
        "SUMO simulation backend",
        str(tmp_path),
        [sys.executable, "-c", "print('ok')"],
        run_mode.child_env(),
        log_path,
    )

    kwargs = FakePopen.last_call["kwargs"]
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    assert "startupinfo" not in kwargs
    script = next(Path(tmp_path).glob("experiment_backend_*.cmd")).read_text(encoding="utf-8")
    assert ">>" not in script


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属的窗口创建标志")
def test_experiment_console_student_mode_skips_cmd(monkeypatch, tmp_path):
    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    monkeypatch.setattr(experiment_launchers.subprocess, "Popen", FakePopen)
    log_path = str(tmp_path / "backend_cmd.log")

    experiment_launchers.launch_visible_console(
        "路径诱导仿真",
        str(tmp_path),
        [sys.executable, "-c", "print('ok')"],
        experiment_launchers.process_env(),
        log_path,
    )

    call = FakePopen.last_call
    assert call["args"][0][0] == sys.executable, "学生模式不应再经过 cmd.exe"
    kwargs = call["kwargs"]
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert kwargs["stdout"] is not None
    assert Path(log_path).read_text(encoding="utf-8").count("student mode") >= 1


def test_sumo_gui_degrades_to_headless_in_student_mode(monkeypatch):
    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    monkeypatch.setattr(
        simulators,
        "_find_executable",
        lambda tool: r"C:\SUMO\bin\sumo.exe" if tool == "sumo" else None,
    )
    monkeypatch.setattr(simulators, "_resolve_launch_file", lambda payload: None)

    command, _cwd, _selected = simulators._launch_command("sumo-gui", simulators.LaunchRequest())
    assert Path(command[0]).name.lower() == "sumo.exe"

    with pytest.raises(Exception) as excinfo:
        simulators._launch_command("netedit", simulators.LaunchRequest())
    assert "学生模式" in str(excinfo.value)


def test_carla_skipped_in_student_mode(monkeypatch):
    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    monkeypatch.setattr(main_module, "_is_port_listening", lambda port: False)
    carla = main_module._ensure_experiment_carla()
    assert carla["skipped"] is True
    assert carla["required"] is False
    assert "学生模式" in carla["message"]

    monkeypatch.setattr(
        main_module,
        "_ensure_experiment_vic_sim",
        lambda: {"id": "vic_sim", "name": "VIC-Sim", "ready": True, "required": True},
    )
    stack = main_module._ensure_experiment_native_stack()
    assert stack["ready"] is True, "跳过 CARLA 不应让整体就绪判定失败"
    assert stack["skipped"] == ["carla"]


def test_compiled_router_start_command_is_silenced(monkeypatch, tmp_path):
    """编译版路由用 start ... cmd /k 弹窗，学生模式必须改写为隐藏 cmd /c。"""
    import types

    from app import compiled_router_compat as compat

    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    monkeypatch.setattr(compat, "LOG_PATH", str(tmp_path / "compiled.log"))

    fake_module = types.SimpleNamespace(__file__="demo.pyd", subprocess=subprocess)
    assert compat.silence_compiled_router(fake_module) is True

    captured = {}

    class FakePopen:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(compat.subprocess, "Popen", FakePopen)
    fake_module.subprocess.Popen(
        'start "信号优化" cmd /k "python -u run_signal_opt.py --algorithm turbo"',
        shell=True,
        cwd=str(tmp_path),
    )

    assert captured["args"][0] == "python -u run_signal_opt.py --algorithm turbo"
    assert "start " not in captured["args"][0]
    assert captured["kwargs"]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert "startupinfo" in captured["kwargs"]
    assert captured["kwargs"]["shell"] is True


def test_compiled_router_untouched_in_demo_mode(monkeypatch):
    import types

    from app import compiled_router_compat as compat

    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "demo")
    fake_module = types.SimpleNamespace(__file__="demo.pyd", subprocess=subprocess)
    assert compat.silence_compiled_router(fake_module) is False

    # 纯 Python 模块永远不替换
    monkeypatch.setenv(run_mode.ENV_RUN_MODE, "student")
    pure_module = types.SimpleNamespace(__file__="demo.py", subprocess=subprocess)
    assert compat.silence_compiled_router(pure_module) is False


def test_launcher_bat_asks_for_mode():
    script = BAT_PATH.read_text(encoding="utf-8")
    assert "请选择运行模式" in script
    assert "演示模式" in script and "学生模式" in script
    assert "ZXK_RUN_MODE=student" in script
    assert "choice /c 12" in script
    # 默认选项必须是学生模式（2）
    assert "/d 2" in script
    assert "默认按学生模式" in script
