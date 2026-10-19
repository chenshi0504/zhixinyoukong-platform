"""
机器码生成模块
根据硬件信息生成唯一的机器标识字符串。
"""
import hashlib
import platform
import subprocess
import uuid


def _get_cpu_id() -> str:
    """获取 CPU 序列号（Windows）。"""
    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "ProcessorId"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        if len(lines) >= 2:
            return lines[1]
    except Exception:
        pass
    return ""


def _get_disk_serial() -> str:
    """获取系统盘序列号（Windows）。"""
    try:
        result = subprocess.run(
            ["wmic", "diskdrive", "get", "SerialNumber"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        if len(lines) >= 2:
            return lines[1]
    except Exception:
        pass
    return ""


def _get_board_serial() -> str:
    """获取主板序列号（Windows）。"""
    try:
        result = subprocess.run(
            ["wmic", "baseboard", "get", "SerialNumber"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        if len(lines) >= 2:
            return lines[1]
    except Exception:
        pass
    return ""


def _get_mac_address() -> str:
    """获取 MAC 地址作为备用标识。"""
    try:
        mac = uuid.getnode()
        return format(mac, "012x")
    except Exception:
        return ""


def generate_machine_id() -> str:
    """
    生成机器码：SHA256(cpu_id + disk_serial + board_serial + mac)[:32]
    返回 32 位十六进制字符串。
    """
    parts = [
        _get_cpu_id(),
        _get_disk_serial(),
        _get_board_serial(),
        _get_mac_address(),
        platform.node(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


if __name__ == "__main__":
    mid = generate_machine_id()
    print(f"机器码: {mid}")
