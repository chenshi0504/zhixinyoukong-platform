"""访问模式与本机控制权限。

平台可以绑定到局域网地址供学生访问。局域网学生可以触发平台基础后端 CMD，
也可以启动「交通流重构（DTALite/NEXTA）」与「三层级模块（信号优化、路径诱导、
车速控制、三层级协同）」的仿真：这些进程会由后端在运行平台的本机弹出 CMD 窗口
执行，状态与结果再通过轮询接口反馈给局域网页面。

其余会直接接管本机硬件/程序的操作（CARLA、VIC-Sim、车规级小车 HIL 控制、
SUMO/CARLA 模拟器启动等）仍然只有运行平台的这台电脑（回环地址）可以触发。
这里不读取 ``X-Forwarded-For`` 等可伪造请求头，避免学生通过修改请求头绕过限制。
"""

from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import Request


def client_host(request: Request) -> str:
    """返回 TCP 连接的来源地址。没有连接信息时按远程访问处理。"""

    client = request.client
    return str(client.host) if client and client.host else ""


def is_local_request(request: Request) -> bool:
    """判断请求是否来自运行后端的本机。"""

    host = client_host(request).strip().strip("[]")
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
        mapped = getattr(address, "ipv4_mapped", None)
        return address.is_loopback or bool(mapped and mapped.is_loopback)
    except ValueError:
        # 测试客户端及部分 ASGI 适配器可能提供 ``localhost`` 而不是 IP。
        return host.lower() == "localhost"


def access_context(request: Request) -> dict[str, Any]:
    """构造供前端使用的访问上下文。"""

    local = is_local_request(request)
    return {
        "access_mode": "local" if local else "lan",
        "is_local": local,
        "can_control_local_services": local,
        # 平台基础后端 CMD 和预热是幂等入口，局域网学生也可以触发；
        # CARLA、SUMO、DTALite 等本机仿真控制仍由 requires_local_control 保护。
        "can_start_experiment_backends": True,
        "client_host": client_host(request),
        "default_account": {"username": "student", "password": "123456"},
    }


# 这些接口会直接启动/停止本机程序。状态查询（GET）不在列表中，局域网学生
# 仍然可以查看当前服务状态。
#
# 注意：以下两类接口已按需求对局域网开放，会由后端在运行平台的本机弹出 CMD
# 窗口执行，局域网页面通过 /status、/results 等只读接口获得反馈，因此不再
# 归入本机专属拦截：
#   1. 交通流重构：/api/reconstruction/run-dtalite、launch-nexta、
#      save-params、generate-report、export-network-doc；
#   2. 三层级模块：/api/signal-optimization/*、/api/path-guidance/*、
#      /api/vehicle-speed/*、/api/three-level/* 的 run/reset/stop 类写操作。
LOCAL_CONTROL_PATHS = {
    ("POST", "/api/carla-sim/native/start"),
    ("POST", "/api/carla-sim/start-mqtt"),
    ("POST", "/api/carla-sim/start-receiver"),
    ("POST", "/api/carla-sim/start"),
    ("POST", "/api/carla-sim/stop"),
    ("POST", "/api/carla-sim/launch-software"),
    ("POST", "/api/carla-sim/stop-software"),
    ("POST", "/api/v1/simulators/sumo-gui/launch"),
    ("POST", "/api/v1/simulators/carla/launch"),
    ("POST", "/api/vehicle-control/native/start"),
    ("POST", "/api/vehicle-control/start-mqtt"),
    ("POST", "/api/vehicle-control/start-simulation"),
    ("POST", "/api/vehicle-control/stop-simulation"),
    # 真实/虚拟小车指令下发、目标节点下发与状态重置都会驱动 HIL 闭环，
    # 属于本机实验台操作，局域网学生不得触发。
    ("POST", "/api/vehicle-control/reset"),
    ("POST", "/api/vehicle-control/send-command"),
    ("POST", "/api/vehicle-control/road-topology/goal-node"),
    ("POST", "/api/v1/multi_level_coordination/start"),
}


def _under(prefix: str, path: str) -> bool:
    """判断路径是否等于前缀本身或位于该前缀之下。"""

    return path == prefix or path.startswith(prefix + "/")


def requires_local_control(request: Request) -> bool:
    """判断请求是否命中需要本机权限的进程控制接口。"""

    method = request.method.upper()
    path = request.url.path.rstrip("/") or "/"
    if (method, path) in LOCAL_CONTROL_PATHS:
        return True
    # 模拟器名称可能不是固定的 sumo/carla，统一保护其 launch 路由。
    if method == "POST" and path.startswith("/api/v1/simulators/") and path.endswith("/launch"):
        return True
    if method == "POST" and path.startswith("/api/carla-sim/"):
        return True
    if method == "POST" and path.startswith("/api/simulation/"):
        return True
    # 车规级 HIL 车辆控制的写操作（含 compat 兼容路由 /api/cars 与
    # /api/road-topology）全部归本机。只拦截写操作，GET 状态查询仍然开放。
    if method == "POST" and _under("/api/vehicle-control", path):
        return True
    if method == "POST" and (_under("/api/cars", path) or _under("/api/road-topology", path)):
        return True
    return False
