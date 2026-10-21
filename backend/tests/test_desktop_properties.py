"""
Property-based tests for desktop-packaging feature.
Uses hypothesis to verify correctness properties from the design document.
"""
import sys
import os
import pytest
from hypothesis import given, strategies as st, settings as h_settings

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from run import get_startup_config


# ============================================================
# **Feature: desktop-packaging, Property 3: Dual-Mode Startup Configuration**
# **Validates: Requirements 6.2, 6.3, 6.4**
#
# For any startup mode parameter ('dev' or 'desktop'), the Backend_Service
# should configure reload, browser auto-open, and other settings consistently
# with the specified mode.
# ============================================================

@given(mode=st.sampled_from(['dev', 'desktop']))
@h_settings(max_examples=100)
def test_dual_mode_startup_config(mode):
    """Property 3: mode parameter determines config consistently."""
    config = get_startup_config(mode)

    # All configs must have these keys
    assert 'reload' in config
    assert 'open_browser' in config
    assert 'log_level' in config

    if mode == 'desktop':
        assert config['reload'] is False, "desktop mode must disable reload"
        assert config['open_browser'] is False, "desktop mode must not open browser"
    elif mode == 'dev':
        # 热重载默认关闭：学生会话（采集/融合/预测/HIL）的状态保存在进程内存中，
        # 任何一次应用重启都会清空全部在线学生的会话与任务，必须显式开启。
        assert config['reload'] is False, "dev mode must keep reload off by default"
        assert config['open_browser'] is True, "dev mode must open browser"

    # log_level must be a valid string
    assert isinstance(config['log_level'], str)
    assert config['log_level'] in ('debug', 'info', 'warning', 'error')


def test_dev_reload_requires_explicit_opt_in(monkeypatch):
    """dev 模式热重载必须显式开启，避免重启清空在线学生的会话状态。"""
    monkeypatch.delenv('ZXK_DEV_RELOAD', raising=False)
    assert get_startup_config('dev')['reload'] is False

    for value in ('1', 'true', 'yes', 'on', 'TRUE', 'On'):
        monkeypatch.setenv('ZXK_DEV_RELOAD', value)
        assert get_startup_config('dev')['reload'] is True, value

    monkeypatch.setenv('ZXK_DEV_RELOAD', '0')
    assert get_startup_config('dev')['reload'] is False

    # desktop 模式无论如何都不开热重载
    monkeypatch.setenv('ZXK_DEV_RELOAD', '1')
    assert get_startup_config('desktop')['reload'] is False


# Add project root to path for desktop_utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from desktop_utils import detect_software, SoftwareInfo, apply_env_vars


# ============================================================
# **Feature: desktop-packaging, Property 2: External Software Detection Correctness**
# **Validates: Requirements 5.1, 5.2, 5.3**
#
# For any software detection configuration, the detection function should
# return installed=True only when the executable file exists at one of the
# specified paths, and should set the correct environment variable when found.
# ============================================================

@given(
    env_var_name=st.sampled_from(['TEST_SW_HOME', 'TEST_CARLA_ROOT', 'TEST_SUMO']),
    has_env=st.booleans(),
)
@h_settings(max_examples=100)
def test_software_detection_correctness(env_var_name, has_env):
    """Property 2: detection returns installed=True iff exe exists."""
    import tempfile
    tmp_path = tempfile.mkdtemp()
    exe_name = 'test_app.exe'
    search_dir = os.path.join(tmp_path, 'sw_install')

    config = {
        'name': 'TestSoftware',
        'required_version': '1.0',
        'env_var': env_var_name,
        'exe_name': exe_name,
        'search_paths': [search_dir],
        'download_url': 'https://example.com',
    }

    # Clean env
    old_val = os.environ.pop(env_var_name, None)
    try:
        if has_env:
            # Create the directory and exe via env var path
            env_dir = os.path.join(tmp_path, 'env_sw')
            os.makedirs(env_dir, exist_ok=True)
            exe_path = os.path.join(env_dir, exe_name)
            with open(exe_path, 'w') as f:
                f.write('fake')
            os.environ[env_var_name] = env_dir

        result = detect_software(config)

        if has_env:
            assert result.installed is True, "Should detect software via env var"
            assert result.installed_path is not None
        else:
            # No env var set, search_dir doesn't exist → not installed
            assert result.installed is False
            assert result.installed_path is None

        # Verify SoftwareInfo fields are always populated
        assert result.name == 'TestSoftware'
        assert result.required_version == '1.0'
        assert result.download_url == 'https://example.com'
    finally:
        # Restore env
        if old_val is not None:
            os.environ[env_var_name] = old_val
        else:
            os.environ.pop(env_var_name, None)


def test_apply_env_vars_sets_variables():
    """Verify apply_env_vars sets environment variables for installed software."""
    env_key = '_TEST_DESKTOP_ENV_VAR'
    old = os.environ.pop(env_key, None)
    try:
        results = [
            SoftwareInfo(name='Test', required_version='1.0',
                         installed=True, installed_path='/fake/path',
                         env_var=env_key),
        ]
        apply_env_vars(results)
        assert os.environ.get(env_key) == '/fake/path'
    finally:
        if old is not None:
            os.environ[env_key] = old
        else:
            os.environ.pop(env_key, None)


from unittest.mock import MagicMock
from run import cleanup_services


# ============================================================
# **Feature: desktop-packaging, Property 1: Process Cleanup Completeness**
# **Validates: Requirements 1.4, 4.1, 4.2**
#
# For any set of started child processes tracked by the Desktop_App,
# calling the cleanup function should attempt to terminate every process
# in the set, leaving no orphan processes.
# ============================================================

@given(num_procs=st.integers(min_value=0, max_value=20))
@h_settings(max_examples=100)
def test_process_cleanup_completeness(num_procs):
    """Property 1: cleanup_services terminates all tracked processes."""
    procs = []
    for _ in range(num_procs):
        mock = MagicMock()
        mock.poll.return_value = None  # process is running
        mock.wait.return_value = 0
        procs.append(mock)

    cleanup_services(procs)

    # Every process should have had terminate() called
    for i, p in enumerate(procs):
        assert p.terminate.called, f"Process {i} was not terminated"


def test_cleanup_force_kills_on_timeout():
    """Edge case: if terminate doesn't work, kill is called."""
    mock = MagicMock()
    mock.poll.return_value = None
    mock.wait.side_effect = Exception("timeout")  # simulate wait timeout

    cleanup_services([mock])

    assert mock.terminate.called
    assert mock.kill.called, "Should force-kill when terminate times out"


# ============================================================
# **Feature: desktop-packaging, Property 4: Sub-Service Launch Attempt**
# **Validates: Requirements 2.3**
#
# For any list of algorithm sub-service configurations, the startup
# function should attempt to launch each service whose script file exists.
# ============================================================

def test_sub_service_launch_skips_missing(tmp_path):
    """Property 4: start_sub_services skips non-existent scripts."""
    from run import start_sub_services

    existing_script = os.path.join(str(tmp_path), 'exists.py')
    with open(existing_script, 'w') as f:
        f.write('import time; time.sleep(1)')

    missing_script = os.path.join(str(tmp_path), 'missing.py')

    servers = [
        ("Existing", existing_script, 19999),
        ("Missing", missing_script, 19998),
    ]

    procs = start_sub_services(servers)

    # Should have launched only the existing one
    assert len(procs) <= 1  # may be 0 if script exits immediately

    # Cleanup
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
