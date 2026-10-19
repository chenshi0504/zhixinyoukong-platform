#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local SUMO simulation service for the algorithm-testing page.

The browser must not call this service directly. The main FastAPI backend
proxies /api/simulation/* to http://127.0.0.1:8001 so remote users only need
the platform website address.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
SIGNAL_CONFIG_DIR = os.path.join(PROJECT_ROOT, "backend", "algorithms", "signal_optimization", "config")
SIGNAL_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "backend", "algorithms", "signal_optimization", "output")
SIMULATION_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
SIMULATION_REPORT_DIR = os.path.join(SIMULATION_OUTPUT_DIR, "reports")
SUMO_CONFIG_PATH = os.path.join(SIMULATION_OUTPUT_DIR, "web_sumo.sumocfg")
SERVICE_HOST = os.environ.get("SIMULATION_SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.environ.get("SIMULATION_SERVICE_PORT", "8001"))

CURRENT_SESSION = {
    "session_id": "web",
    "status": "ready",
    "message": "simulation service ready",
    "started_at": None,
    "process_pid": None,
}


def _sendable_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(_sendable_payload(payload), ensure_ascii=False, indent=2).encode("utf-8")


def _resolve_sumo_gui() -> str | None:
    sumo_home = os.environ.get("SUMO_HOME", "").strip().strip('"').rstrip(";")
    candidates = [
        shutil.which("sumo-gui"),
        os.path.join(sumo_home, "bin", "sumo-gui.exe") if sumo_home else None,
        os.path.join(PROJECT_ROOT, "tools", "sumo", "bin", "sumo-gui.exe"),
        os.path.join(PROJECT_ROOT, "software", "SUMO", "bin", "sumo-gui.exe"),
        r"C:\Program Files (x86)\Eclipse\Sumo\bin\sumo-gui.exe",
        r"C:\Program Files\Eclipse\Sumo\bin\sumo-gui.exe",
        r"D:\SUMO\bin\sumo-gui.exe",
        r"D:\software\SUMO\bin\sumo-gui.exe",
        r"D:\Download\SUMO\bin\sumo-gui.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _sumo_env(sumo_gui: str | None) -> dict:
    env = os.environ.copy()
    if sumo_gui:
        bin_dir = os.path.dirname(sumo_gui)
        env.setdefault("SUMO_HOME", os.path.dirname(bin_dir))
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _ensure_runtime_config() -> tuple[bool, str]:
    net_file = os.path.join(SIGNAL_CONFIG_DIR, "siouxfalls.net.xml")
    route_file = os.path.join(SIGNAL_CONFIG_DIR, "input", "1_2_4_X", "siouxfalls.rou.xml")
    gui_file = os.path.join(SIGNAL_CONFIG_DIR, "osm.view.xml")
    os.makedirs(SIMULATION_OUTPUT_DIR, exist_ok=True)

    missing = [path for path in (net_file, route_file) if not os.path.exists(path)]
    if missing:
        return False, "SUMO scenario files are missing: " + "; ".join(missing)

    summary_file = os.path.join(SIMULATION_OUTPUT_DIR, "summary.xml")
    tripinfo_file = os.path.join(SIMULATION_OUTPUT_DIR, "tripinfo.xml")
    edgedata_file = os.path.join(SIMULATION_OUTPUT_DIR, "edgedata.xml")
    config = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <input>
    <net-file value="{net_file}"/>
    <route-files value="{route_file}"/>
  </input>
  <time>
    <begin value="0"/>
  </time>
  <processing>
    <ignore-route-errors value="false"/>
    <time-to-teleport value="300"/>
    <max-depart-delay value="-1"/>
    <routing-algorithm value="dijkstra"/>
    <step-length value="1.0"/>
  </processing>
  <output>
    <summary-output value="{summary_file}"/>
    <tripinfo-output value="{tripinfo_file}"/>
    <edgedata-output value="{edgedata_file}"/>
  </output>
  <report>
    <verbose value="false"/>
    <no-step-log value="true"/>
    <duration-log.statistics value="true"/>
    <no-warnings value="false"/>
  </report>
  <gui_only>
    <start value="true"/>
    <quit-on-end value="true"/>
    <gui-settings-file value="{gui_file}"/>
  </gui_only>
</configuration>
"""
    with open(SUMO_CONFIG_PATH, "w", encoding="utf-8") as handle:
        handle.write(config)
    return True, SUMO_CONFIG_PATH


def _start_simulation() -> dict:
    ok, message = _ensure_runtime_config()
    if not ok:
        CURRENT_SESSION.update(status="failed", message=message)
        return {"success": False, "message": message}

    sumo_gui = _resolve_sumo_gui()
    if not sumo_gui:
        message = "sumo-gui not found. Install SUMO or keep tools/sumo in this project."
        CURRENT_SESSION.update(status="failed", message=message)
        return {"success": False, "message": message}

    try:
        proc = subprocess.Popen(
            [sumo_gui, "-c", SUMO_CONFIG_PATH],
            cwd=SIMULATION_OUTPUT_DIR,
            env=_sumo_env(sumo_gui),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        CURRENT_SESSION.update(
            session_id="web",
            status="running",
            message="SUMO simulation started on the server",
            started_at=datetime.now().isoformat(),
            process_pid=proc.pid,
        )
        return {
            "success": True,
            "session_id": "web",
            "message": "SUMO simulation started on the server",
        }
    except Exception as exc:
        CURRENT_SESSION.update(status="failed", message=str(exc))
        return {"success": False, "message": f"Failed to start SUMO: {exc}"}


def _analysis_source_files() -> tuple[str | None, str | None, str | None]:
    local_summary = os.path.join(SIMULATION_OUTPUT_DIR, "summary.xml")
    local_tripinfo = os.path.join(SIMULATION_OUTPUT_DIR, "tripinfo.xml")
    if os.path.exists(local_summary) and os.path.exists(local_tripinfo):
        return local_summary, local_tripinfo, SIMULATION_OUTPUT_DIR

    candidates = []
    for output_dir in glob.glob(os.path.join(SIGNAL_OUTPUT_DIR, "*")):
        if not os.path.isdir(output_dir):
            continue
        summary_file = os.path.join(output_dir, "summary.xml")
        tripinfo_file = os.path.join(output_dir, "tripinfo.xml")
        if os.path.exists(summary_file) and os.path.exists(tripinfo_file):
            modified = min(os.path.getmtime(summary_file), os.path.getmtime(tripinfo_file))
            candidates.append((modified, summary_file, tripinfo_file, output_dir))

    if not candidates:
        return None, None, None
    _, summary_file, tripinfo_file, output_dir = max(candidates, key=lambda item: item[0])
    return summary_file, tripinfo_file, output_dir


def _float_attr(elem: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(elem.get(name, default))
    except (TypeError, ValueError):
        return default


def _parse_analysis_data(summary_file: str, tripinfo_file: str, source_dir: str) -> dict:
    summary_steps = []
    trip_rows = []

    root = ET.parse(summary_file).getroot()
    for step in root.findall("step"):
        summary_steps.append(
            {
                "time": _float_attr(step, "time"),
                "running": _float_attr(step, "running"),
                "ended": _float_attr(step, "ended") or _float_attr(step, "arrived"),
                "halting": _float_attr(step, "halting"),
                "mean_speed": _float_attr(step, "meanSpeed"),
                "mean_waiting_time": _float_attr(step, "meanWaitingTime"),
            }
        )

    root = ET.parse(tripinfo_file).getroot()
    for trip in root.findall("tripinfo"):
        trip_rows.append(
            {
                "duration": _float_attr(trip, "duration"),
                "route_length": _float_attr(trip, "routeLength"),
                "waiting_time": _float_attr(trip, "waitingTime"),
                "time_loss": _float_attr(trip, "timeLoss"),
            }
        )

    vehicle_count = len(trip_rows)
    avg_duration = sum(t["duration"] for t in trip_rows) / vehicle_count if vehicle_count else 0
    avg_waiting = sum(t["waiting_time"] for t in trip_rows) / vehicle_count if vehicle_count else 0
    avg_length = sum(t["route_length"] for t in trip_rows) / vehicle_count if vehicle_count else 0
    avg_speed_values = [s["mean_speed"] for s in summary_steps if s["mean_speed"] > 0]
    avg_speed = sum(avg_speed_values) / len(avg_speed_values) if avg_speed_values else 0

    return {
        "summary_file": summary_file,
        "tripinfo_file": tripinfo_file,
        "source_dir": source_dir,
        "summary_steps": summary_steps,
        "trip_rows": trip_rows,
        "statistics": {
            "vehicle_count": vehicle_count,
            "avg_duration": avg_duration,
            "avg_waiting": avg_waiting,
            "avg_route_length": avg_length,
            "max_running": max((s["running"] for s in summary_steps), default=0),
            "max_ended": max((s["ended"] for s in summary_steps), default=0),
            "avg_speed": avg_speed,
        },
    }


def _polyline(points: list[tuple[float, float]], width: int, height: int, left: int, top: int, max_x: float, max_y: float) -> str:
    if not points or max_x <= 0 or max_y <= 0:
        return ""
    coords = []
    for x, y in points:
        sx = left + (x / max_x) * width
        sy = top + height - (y / max_y) * height
        coords.append(f"{sx:.1f},{sy:.1f}")
    return " ".join(coords)


def _build_time_series_svg(data: dict) -> str:
    steps = data["summary_steps"]
    if not steps:
        return ""
    max_x = max(s["time"] for s in steps) or 1
    max_y = max(max(s["running"], s["ended"], s["halting"]) for s in steps) or 1
    left, top, width, height = 70, 55, 820, 300
    running = _polyline([(s["time"], s["running"]) for s in steps], width, height, left, top, max_x, max_y)
    ended = _polyline([(s["time"], s["ended"]) for s in steps], width, height, left, top, max_x, max_y)
    halting = _polyline([(s["time"], s["halting"]) for s in steps], width, height, left, top, max_x, max_y)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="430" viewBox="0 0 960 430">
  <rect width="960" height="430" fill="#ffffff"/>
  <text x="480" y="30" text-anchor="middle" font-size="22" font-family="Microsoft YaHei, Arial" fill="#1f2937">SUMO仿真时间序列分析</text>
  <line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#94a3b8"/>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" stroke="#94a3b8"/>
  <polyline points="{running}" fill="none" stroke="#2563eb" stroke-width="3"/>
  <polyline points="{ended}" fill="none" stroke="#16a34a" stroke-width="3"/>
  <polyline points="{halting}" fill="none" stroke="#dc2626" stroke-width="3"/>
  <text x="75" y="392" font-size="13" font-family="Arial" fill="#64748b">time / s</text>
  <text x="18" y="190" font-size="13" font-family="Arial" fill="#64748b" transform="rotate(-90 18 190)">vehicles</text>
  <circle cx="710" cy="385" r="5" fill="#2563eb"/><text x="723" y="390" font-size="13" font-family="Microsoft YaHei, Arial">running</text>
  <circle cx="800" cy="385" r="5" fill="#16a34a"/><text x="813" y="390" font-size="13" font-family="Microsoft YaHei, Arial">ended</text>
  <circle cx="875" cy="385" r="5" fill="#dc2626"/><text x="888" y="390" font-size="13" font-family="Microsoft YaHei, Arial">halting</text>
</svg>"""


def _build_trip_svg(data: dict) -> str:
    stats = data["statistics"]
    bars = [
        ("车辆数", stats["vehicle_count"], "#2563eb"),
        ("平均时长(s)", stats["avg_duration"], "#16a34a"),
        ("平均等待(s)", stats["avg_waiting"], "#f59e0b"),
        ("平均速度(m/s)", stats["avg_speed"], "#dc2626"),
    ]
    max_value = max((value for _, value, _ in bars), default=1) or 1
    rows = []
    for i, (label, value, color) in enumerate(bars):
        y = 90 + i * 70
        bar_width = 620 * (value / max_value)
        rows.append(
            f'<text x="80" y="{y + 24}" font-size="15" font-family="Microsoft YaHei, Arial" fill="#334155">{escape(label)}</text>'
            f'<rect x="200" y="{y}" width="{bar_width:.1f}" height="34" rx="4" fill="{color}"/>'
            f'<text x="{210 + bar_width:.1f}" y="{y + 23}" font-size="14" font-family="Arial" fill="#0f172a">{value:.2f}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="430" viewBox="0 0 960 430">
  <rect width="960" height="430" fill="#ffffff"/>
  <text x="480" y="35" text-anchor="middle" font-size="22" font-family="Microsoft YaHei, Arial" fill="#1f2937">SUMO仿真行程指标分析</text>
  {''.join(rows)}
  <text x="80" y="385" font-size="13" font-family="Microsoft YaHei, Arial" fill="#64748b">数据源：{escape(os.path.basename(data['source_dir'] or 'simulation'))}</text>
</svg>"""


def _build_analysis_payload() -> dict:
    summary_file, tripinfo_file, source_dir = _analysis_source_files()
    if not summary_file or not tripinfo_file:
        return {
            "success": False,
            "message": "未找到summary.xml和tripinfo.xml，请先运行SUMO仿真或检查算法输出目录",
        }
    data = _parse_analysis_data(summary_file, tripinfo_file, source_dir)
    return {
        "success": True,
        "message": "分析完成",
        "data": {
            "has_results": True,
            "statistics": data["statistics"],
            "source_dir": source_dir,
            "time_series_svg": _build_time_series_svg(data),
            "trip_analysis_svg": _build_trip_svg(data),
        },
        "_analysis_data": data,
    }


def _write_docx_report(data: dict) -> str:
    os.makedirs(SIMULATION_REPORT_DIR, exist_ok=True)
    report_path = os.path.join(SIMULATION_REPORT_DIR, f"SUMO_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
    stats = data["statistics"]
    paragraphs = [
        "SUMO仿真算法测试报告",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"数据源目录：{data['source_dir']}",
        f"车辆数：{stats['vehicle_count']}",
        f"平均行程时间：{stats['avg_duration']:.2f} s",
        f"平均等待时间：{stats['avg_waiting']:.2f} s",
        f"平均路径长度：{stats['avg_route_length']:.2f} m",
        f"平均速度：{stats['avg_speed']:.2f} m/s",
        "说明：该报告由服务器端仿真分析服务生成，前端通过统一网站接口下载。",
    ]
    body = "".join(
        '<w:p><w:r><w:t xml:space="preserve">' + escape(paragraph) + "</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}<w:sectPr/></w:body>
</w:document>"""
    with zipfile.ZipFile(report_path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        docx.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        docx.writestr("word/document.xml", document)
    return report_path


def _download_report() -> dict:
    payload = _build_analysis_payload()
    if not payload.get("success"):
        return payload
    report_path = _write_docx_report(payload["_analysis_data"])
    return {
        "success": True,
        "file_path": report_path,
        "filename": f"SUMO_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


class SimulationHandler(BaseHTTPRequestHandler):
    server_version = "ZXYKSimulationService/1.0"

    def log_message(self, fmt: str, *args) -> None:
        logger.info("%s - %s", self.client_address[0], fmt % args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, result: dict) -> None:
        file_path = result.get("file_path")
        if not file_path or not os.path.exists(file_path):
            self._send_json(404, {"success": False, "message": "report file not found"})
            return

        filename = result.get("filename") or os.path.basename(file_path)
        content_type = result.get("content_type") or "application/octet-stream"
        file_size = os.path.getsize(file_path)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(file_size))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition")
        self.end_headers()
        with open(file_path, "rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            self._send_json(200, {"success": True, "status": "healthy", "service": "simulation", "session": CURRENT_SESSION})
            return
        if path == "/status":
            self._send_json(200, {"success": True, "data": CURRENT_SESSION, "session_id": query.get("session_id", ["web"])[0]})
            return
        if path == "/results":
            payload = _build_analysis_payload()
            self._send_json(200 if payload.get("success") else 404, payload)
            return
        if path == "/download_report":
            result = _download_report()
            if result.get("success"):
                self._send_file(result)
            else:
                self._send_json(404, result)
            return
        self._send_json(404, {"success": False, "message": "endpoint not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length:
            self.rfile.read(length)

        if path == "/start_simulation":
            result = _start_simulation()
            self._send_json(200 if result.get("success") else 409, result)
            return
        if path == "/analyze_results":
            payload = _build_analysis_payload()
            self._send_json(200 if payload.get("success") else 404, payload)
            return
        if path == "/download_report":
            result = _download_report()
            if result.get("success"):
                self._send_file(result)
            else:
                self._send_json(404, result)
            return
        self._send_json(404, {"success": False, "message": "endpoint not found"})


def main() -> None:
    os.makedirs(SIMULATION_OUTPUT_DIR, exist_ok=True)
    httpd = HTTPServer((SERVICE_HOST, SERVICE_PORT), SimulationHandler)
    logger.info("Simulation service listening on http://%s:%s", SERVICE_HOST, SERVICE_PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Simulation service stopped")


if __name__ == "__main__":
    main()
