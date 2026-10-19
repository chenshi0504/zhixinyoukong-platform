from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ALGO_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ALGO_DIR / "output"
SHARED_STATE = ALGO_DIR / "shared_vehicle_state.json"
CONTROL_CMD = ALGO_DIR / "control_command.json"

NET_FILE = ALGO_DIR / "school.net.xml"
SUMOCFG_FILE = ALGO_DIR / "school.sumocfg"
NODES_FILE = ALGO_DIR / "school.nod.xml"
EDGES_FILE = ALGO_DIR / "school.edg.xml"

VEHICLE_ID = "CAV_0"

ECON_LOOP_EDGES = [
    "eg_loop_northwest",
    "eg_loop_north",
    "eg_loop_east_top",
    "eg_loop_east_mid",
    "eg_loop_east_link",
    "eg_loop_east_lower",
    "eg_loop_south",
    "eg_loop_southwest",
    "eg_loop_west_lower",
    "eg_loop_west_mid",
    "eg_loop_west_upper",
    "eg_loop_west_to_nw",
]

NODE_COORDS = {
    "J_NW": (-72.0, 130.0),
    "J_N": (-20.0, 148.0),
    "J_NE": (36.0, 148.0),
    "J_E1": (48.0, 94.0),
    "J_E2": (70.0, 48.0),
    "J_E3": (84.0, 8.0),
    "J_SE": (96.0, -88.0),
    "J_S": (38.0, -98.0),
    "J_SW": (-28.0, -90.0),
    "J_W1": (-62.0, -52.0),
    "J_W2": (-66.0, 18.0),
    "J_W3": (-74.0, 80.0),
}

EDGE_NODES = {
    "eg_loop_northwest": ("J_NW", "J_N"),
    "eg_loop_north": ("J_N", "J_NE"),
    "eg_loop_east_top": ("J_NE", "J_E1"),
    "eg_loop_east_mid": ("J_E1", "J_E2"),
    "eg_loop_east_link": ("J_E2", "J_E3"),
    "eg_loop_east_lower": ("J_E3", "J_SE"),
    "eg_loop_south": ("J_SE", "J_S"),
    "eg_loop_southwest": ("J_S", "J_SW"),
    "eg_loop_west_lower": ("J_SW", "J_W1"),
    "eg_loop_west_mid": ("J_W1", "J_W2"),
    "eg_loop_west_upper": ("J_W2", "J_W3"),
    "eg_loop_west_to_nw": ("J_W3", "J_NW"),
}

ROUTE_ALIASES = {
    "econ_loop": ECON_LOOP_EDGES,
    "economics_loop": ECON_LOOP_EDGES,
    "jinguan_loop": ECON_LOOP_EDGES,
    "management_loop": ECON_LOOP_EDGES,
    "经管学院环线": ECON_LOOP_EDGES,
    "经管学院": ECON_LOOP_EDGES,
}


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    try:
        os.replace(temp_path, path)
    except PermissionError:
        time.sleep(0.02)
        try:
            os.replace(temp_path, path)
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            try:
                temp_path.unlink()
            except OSError:
                pass


def write_state(payload: dict) -> None:
    atomic_write_json(SHARED_STATE, payload)


def read_command(last_mtime: float) -> tuple[dict | None, float]:
    try:
        mtime = CONTROL_CMD.stat().st_mtime
    except FileNotFoundError:
        return None, last_mtime
    if mtime <= last_mtime:
        return None, last_mtime
    try:
        with CONTROL_CMD.open("r", encoding="utf-8") as f:
            return json.load(f), mtime
    except Exception:
        return None, mtime


def ensure_sumo_environment() -> tuple[str | None, str | None]:
    project_sumo = ALGO_DIR.parents[2] / "software" / "SUMO"
    candidates = [
        os.environ.get("SUMO_HOME", "").strip().rstrip(";"),
        str(project_sumo),
        r"D:\Download\SUMO",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        tools_dir = Path(candidate) / "tools"
        bin_dir = Path(candidate) / "bin"
        if tools_dir.is_dir() and str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        if bin_dir.is_dir():
            os.environ.setdefault("SUMO_HOME", str(Path(candidate)))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

    sumo = shutil.which("sumo")
    sumo_gui = shutil.which("sumo-gui")
    return sumo, sumo_gui


def ensure_network() -> None:
    if NET_FILE.exists():
        src_mtime = max(NODES_FILE.stat().st_mtime, EDGES_FILE.stat().st_mtime)
        if NET_FILE.stat().st_mtime >= src_mtime:
            return

    netconvert = shutil.which("netconvert")
    if not netconvert:
        sumo_home = os.environ.get("SUMO_HOME", "")
        candidate = Path(sumo_home) / "bin" / "netconvert.exe"
        if candidate.exists():
            netconvert = str(candidate)
    if not netconvert:
        raise RuntimeError("netconvert not found; cannot build school.net.xml")

    cmd = [
        netconvert,
        "--node-files",
        str(NODES_FILE),
        "--edge-files",
        str(EDGES_FILE),
        "--output-file",
        str(NET_FILE),
        "--no-turnarounds",
        "true",
        "--no-internal-links",
        "false",
    ]
    subprocess.run(cmd, cwd=str(ALGO_DIR), check=True)


def resolve_route(route_arg: str | None) -> list[str]:
    raw = (route_arg or "econ_loop").strip()
    lowered = raw.lower()
    if raw in ROUTE_ALIASES:
        return ROUTE_ALIASES[raw]
    if lowered in ROUTE_ALIASES:
        return ROUTE_ALIASES[lowered]

    parts = [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    if parts and all(part in EDGE_NODES for part in parts):
        return parts

    print(f"Unknown route '{raw}', falling back to econ_loop")
    return ECON_LOOP_EDGES


def repeat_route(edges: list[str], repeats: int = 60) -> list[str]:
    return edges * max(1, repeats)


def edge_length(edge_id: str) -> float:
    a, b = EDGE_NODES[edge_id]
    x1, y1 = NODE_COORDS[a]
    x2, y2 = NODE_COORDS[b]
    return math.hypot(x2 - x1, y2 - y1)


def edge_angle(edge_id: str) -> float:
    a, b = EDGE_NODES[edge_id]
    x1, y1 = NODE_COORDS[a]
    x2, y2 = NODE_COORDS[b]
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def turn_direction(from_edge: str | None, to_edge: str | None) -> str:
    if not from_edge or not to_edge or from_edge not in EDGE_NODES or to_edge not in EDGE_NODES:
        return "--"
    diff = (edge_angle(to_edge) - edge_angle(from_edge) + 360) % 360
    if diff < 30 or diff > 330:
        return "straight"
    if 30 <= diff <= 150:
        return "left"
    if 210 <= diff <= 330:
        return "right"
    return "u-turn"


def fake_geo(x: float, y: float) -> tuple[float, float]:
    return 121.533000 + x * 0.00001, 38.886000 + y * 0.00001


def save_trajectory(trajectory: list[dict]) -> None:
    if not trajectory:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"cav_trajectory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        import pandas as pd

        pd.DataFrame(trajectory).to_excel(output, index=False)
        print(f"trajectory saved: {output}")
    except Exception as exc:
        csv_output = output.with_suffix(".csv")
        print(f"xlsx save failed ({exc}); writing csv: {csv_output}")
        keys = list(trajectory[0].keys())
        with csv_output.open("w", encoding="utf-8", newline="") as f:
            f.write(",".join(keys) + "\n")
            for row in trajectory:
                f.write(",".join(str(row.get(key, "")) for key in keys) + "\n")


def run_fallback(args: argparse.Namespace, route_edges: list[str]) -> None:
    print("SUMO/TraCI unavailable; using local path-following fallback")
    expanded = repeat_route(route_edges, 60)
    target_speed = max(0.1, float(args.speed))
    step_length = float(args.step_length)
    duration = float(args.duration)
    trajectory: list[dict] = []
    last_cmd_mtime = 0.0
    distance = 0.0
    step = 0
    start_time = time.time()

    write_state({"status": "running", "step": step, "route": route_edges, "message": "fallback running"})

    while time.time() - start_time < duration:
        command, last_cmd_mtime = read_command(last_cmd_mtime)
        if command:
            action = command.get("action")
            if action == "stop":
                break
            if action == "set_speed":
                target_speed = max(0.0, min(15.0, float(command.get("speed", target_speed))))

        distance += target_speed * step_length
        remaining = distance
        current_edge = expanded[-1]
        edge_pos = 0.0
        route_index = 0
        for i, edge_id in enumerate(expanded):
            length = edge_length(edge_id)
            if remaining <= length:
                current_edge = edge_id
                edge_pos = remaining
                route_index = i
                break
            remaining -= length

        a, b = EDGE_NODES[current_edge]
        x1, y1 = NODE_COORDS[a]
        x2, y2 = NODE_COORDS[b]
        length = edge_length(current_edge) or 1.0
        ratio = max(0.0, min(1.0, edge_pos / length))
        x = x1 + (x2 - x1) * ratio
        y = y1 + (y2 - y1) * ratio
        angle = edge_angle(current_edge)
        next_edge = expanded[route_index + 1] if route_index + 1 < len(expanded) else None
        longitude, latitude = fake_geo(x, y)

        state = {
            "status": "running",
            "step": step,
            "x": x,
            "y": y,
            "speed": target_speed,
            "angle": angle,
            "current_edge": current_edge,
            "edge_length": length,
            "dist_to_junction": max(0.0, length - edge_pos),
            "next_edge": next_edge,
            "turn_direction": turn_direction(current_edge, next_edge),
            "longitude": longitude,
            "latitude": latitude,
            "distance": distance,
            "route": route_edges,
            "timestamp": datetime.now().isoformat(),
        }
        trajectory.append(state)
        write_state(state)

        step += 1
        if args.realtime:
            time.sleep(step_length)

    write_state({"status": "completed", "step": step, "timestamp": datetime.now().isoformat(), "route": route_edges})
    save_trajectory(trajectory)


def run_sumo(args: argparse.Namespace, route_edges: list[str]) -> None:
    sumo, sumo_gui = ensure_sumo_environment()
    ensure_network()

    import traci

    binary = sumo if args.headless else (sumo_gui or sumo)
    if not binary:
        raise RuntimeError("sumo binary not found")

    expanded_edges = repeat_route(route_edges, 80)
    target_speed = max(0.1, min(15.0, float(args.speed)))
    step_length = float(args.step_length)
    duration = float(args.duration)
    route_id = f"route_{int(time.time())}"

    cmd = [
        binary,
        "-c",
        str(SUMOCFG_FILE),
        "--step-length",
        str(step_length),
        "--start",
        "--quit-on-end",
    ]
    print("starting SUMO:", " ".join(cmd))
    previous_cwd = Path.cwd()
    os.chdir(ALGO_DIR)
    try:
        traci.start(cmd)
    finally:
        os.chdir(previous_cwd)

    trajectory: list[dict] = []
    last_cmd_mtime = 0.0
    step = 0
    started = False
    start_time = time.time()

    try:
        traci.route.add(route_id, expanded_edges)
        traci.vehicle.add(VEHICLE_ID, route_id, typeID="cav", depart=0, departPos="0", departSpeed=str(target_speed))
        traci.vehicle.setSpeed(VEHICLE_ID, target_speed)
        started = True
        write_state({"status": "running", "step": step, "route": route_edges, "message": "sumo running"})

        while time.time() - start_time < duration:
            command, last_cmd_mtime = read_command(last_cmd_mtime)
            if command:
                action = command.get("action")
                if action == "stop":
                    break
                if action == "set_speed":
                    target_speed = max(0.0, min(15.0, float(command.get("speed", target_speed))))
                    if VEHICLE_ID in traci.vehicle.getIDList():
                        traci.vehicle.setSpeed(VEHICLE_ID, target_speed)
                if action == "set_route":
                    new_edges = resolve_route(command.get("route"))
                    expanded_edges = repeat_route(new_edges, 80)
                    route_edges = new_edges

            traci.simulationStep()
            step += 1

            if VEHICLE_ID not in traci.vehicle.getIDList():
                if started:
                    break
                continue

            traci.vehicle.setSpeed(VEHICLE_ID, target_speed)
            x, y = traci.vehicle.getPosition(VEHICLE_ID)
            speed = traci.vehicle.getSpeed(VEHICLE_ID)
            angle = traci.vehicle.getAngle(VEHICLE_ID)
            current_edge = traci.vehicle.getRoadID(VEHICLE_ID)
            route = list(traci.vehicle.getRoute(VEHICLE_ID))
            route_index = traci.vehicle.getRouteIndex(VEHICLE_ID)
            lane_id = traci.vehicle.getLaneID(VEHICLE_ID)
            lane_pos = traci.vehicle.getLanePosition(VEHICLE_ID)
            try:
                edge_len = traci.lane.getLength(lane_id)
            except Exception:
                edge_len = edge_length(current_edge) if current_edge in EDGE_NODES else 0.0
            next_edge = route[route_index + 1] if 0 <= route_index + 1 < len(route) else None
            longitude, latitude = fake_geo(x, y)

            state = {
                "status": "running",
                "step": step,
                "x": x,
                "y": y,
                "speed": speed,
                "target_speed": target_speed,
                "angle": angle,
                "current_edge": current_edge,
                "edge_length": edge_len,
                "dist_to_junction": max(0.0, edge_len - lane_pos),
                "next_edge": next_edge,
                "turn_direction": turn_direction(current_edge, next_edge),
                "longitude": longitude,
                "latitude": latitude,
                "distance": traci.vehicle.getDistance(VEHICLE_ID),
                "total_vehicles": traci.vehicle.getIDCount(),
                "route": route_edges,
                "timestamp": datetime.now().isoformat(),
            }
            trajectory.append(state)
            write_state(state)

            if args.realtime:
                time.sleep(step_length)

        write_state({"status": "completed", "step": step, "timestamp": datetime.now().isoformat(), "route": route_edges})
    finally:
        try:
            traci.close()
        except Exception:
            pass
        save_trajectory(trajectory)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vehicle control simulation for the economics-management loop")
    parser.add_argument("--route", default="econ_loop", help="Route alias or comma separated SUMO edge IDs")
    parser.add_argument("--speed", type=float, default=5.0, help="Target speed in m/s")
    parser.add_argument("--port", type=int, default=8813, help="Reserved for legacy launcher compatibility")
    parser.add_argument("--mqtt", action="store_true", help="Reserved for MQTT-enabled deployments")
    parser.add_argument("--duration", type=float, default=600.0, help="Maximum run time in seconds")
    parser.add_argument("--step-length", type=float, default=0.1, help="SUMO simulation step length")
    parser.add_argument("--headless", action="store_true", help="Use sumo instead of sumo-gui")
    parser.add_argument("--no-realtime", dest="realtime", action="store_false", help="Run as fast as possible")
    parser.set_defaults(realtime=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    route_edges = resolve_route(args.route)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        run_sumo(args, route_edges)
    except Exception as exc:
        print(f"SUMO run failed: {exc}")
        run_fallback(args, route_edges)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
