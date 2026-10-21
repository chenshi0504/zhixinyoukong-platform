"""Launch a CARLA-SUMO co-simulation with an optional OpenDRIVE map.

This wrapper keeps the platform-side campus scene runnable without editing the
CARLA installation. It loads a CARLA town or OpenDRIVE map first, then delegates
the tick synchronization to CARLA's bundled Co-Simulation/Sumo script.
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace


def _append_runtime_paths(carla_root: Path, sumo_home: Path | None) -> None:
    egg_pattern = carla_root / "PythonAPI" / "carla" / "dist" / (
        "carla-*%d.%d-%s.egg"
        % (
            sys.version_info.major,
            sys.version_info.minor,
            "win-amd64" if os.name == "nt" else "linux-x86_64",
        )
    )
    eggs = glob.glob(str(egg_pattern))
    if eggs:
        sys.path.append(eggs[0])

    co_sim_root = carla_root / "Co-Simulation" / "Sumo"
    sys.path.insert(0, str(co_sim_root))

    if sumo_home is not None:
        os.environ["SUMO_HOME"] = str(sumo_home)
        sys.path.append(str(sumo_home / "tools"))


def _load_carla_world(args: argparse.Namespace) -> None:
    import carla

    client = carla.Client(args.carla_host, args.carla_port)
    client.set_timeout(args.carla_timeout)

    if args.xodr:
        xodr_path = Path(args.xodr).resolve()
        data = xodr_path.read_text(encoding="utf-8", errors="replace")
        params = carla.OpendriveGenerationParameters(
            vertex_distance=2.0,
            max_road_length=500.0,
            wall_height=0.0,
            additional_width=0.6,
            smooth_junctions=True,
            enable_mesh_visibility=True,
        )
        client.generate_opendrive_world(data, params)
        print(f"[CARLA] OpenDRIVE map loaded: {xodr_path}")
    elif args.town:
        client.load_world(args.town)
        print(f"[CARLA] Town loaded: {args.town}")

    time.sleep(args.map_warmup)


def _vehicle_spectator_transform(actor, distance: float, height: float, pitch: float):
    import carla

    transform = actor.get_transform()
    loc = transform.location
    rot = transform.rotation
    yaw = math.radians(rot.yaw)
    return carla.Transform(
        carla.Location(
            x=loc.x - distance * math.cos(yaw),
            y=loc.y - distance * math.sin(yaw),
            z=loc.z + height,
        ),
        carla.Rotation(pitch=pitch, yaw=rot.yaw, roll=0.0),
    )


def _install_follow_spectator(sync_module, args: argparse.Namespace) -> None:
    original_tick = sync_module.SimulationSynchronization.tick
    state = {"target": None, "waiting_logged": False, "warning": None}

    def tick_with_spectator(self):
        original_tick(self)

        try:
            target_actor_id = None
            target_sumo_id = None
            if args.follow_sumo_id:
                target_sumo_id = args.follow_sumo_id
                target_actor_id = self.sumo2carla_ids.get(args.follow_sumo_id)
            if target_actor_id is None and self.sumo2carla_ids:
                target_sumo_id, target_actor_id = next(iter(self.sumo2carla_ids.items()))
            if target_actor_id is None:
                if not state["waiting_logged"]:
                    print("[CARLA] Spectator view: waiting for target SUMO vehicle", flush=True)
                    state["waiting_logged"] = True
                return
            actor = self.carla.get_actor(target_actor_id)
            if actor is None:
                return
            self.carla.world.get_spectator().set_transform(
                _vehicle_spectator_transform(
                    actor, args.follow_distance, args.follow_height, args.follow_pitch
                )
            )
            target = (target_sumo_id, target_actor_id)
            if state["target"] != target:
                print(
                    f"[CARLA] Spectator view: third SUMO vehicle={target_sumo_id} CARLA actor={target_actor_id}",
                    flush=True,
                )
                state["target"] = target
        except Exception as exc:
            warning = str(exc)
            if state["warning"] != warning:
                print(f"[CARLA] Warning: could not update follow spectator: {exc}", flush=True)
                state["warning"] = warning

    sync_module.SimulationSynchronization.tick = tick_with_spectator


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carla-root", required=True)
    parser.add_argument("--sumo-home")
    parser.add_argument("--sumo-cfg", required=True)
    parser.add_argument("--xodr")
    parser.add_argument("--town")
    parser.add_argument("--carla-host", default="127.0.0.1")
    parser.add_argument("--carla-port", type=int, default=2000)
    parser.add_argument("--sumo-host", default=None)
    parser.add_argument("--sumo-port", type=int, default=None)
    parser.add_argument("--sumo-gui", action="store_true")
    parser.add_argument("--step-length", type=float, default=0.05)
    parser.add_argument("--client-order", type=int, default=1)
    parser.add_argument("--tls-manager", choices=["none", "sumo", "carla"], default="none")
    parser.add_argument("--sync-vehicle-color", action="store_true")
    parser.add_argument("--sync-vehicle-lights", action="store_true")
    parser.add_argument("--sync-vehicle-all", action="store_true")
    parser.add_argument("--spectator-view", choices=["top", "none", "third"], default="third")
    parser.add_argument("--follow-sumo-id")
    parser.add_argument("--follow-first-vehicle", action="store_true")
    parser.add_argument("--follow-distance", type=float, default=8.0)
    parser.add_argument("--follow-height", type=float, default=4.0)
    parser.add_argument("--follow-pitch", type=float, default=-15.0)
    parser.add_argument("--carla-timeout", type=float, default=60.0)
    parser.add_argument("--map-warmup", type=float, default=2.0)
    args = parser.parse_args()

    if args.spectator_view == "top":
        print("[CARLA] Spectator view: legacy top requested; using vehicle rear-follow view", flush=True)
        args.spectator_view = "third"
        args.follow_first_vehicle = True
    elif args.spectator_view == "third" and not args.follow_sumo_id:
        args.follow_first_vehicle = True

    carla_root = Path(args.carla_root).resolve()
    sumo_home = Path(args.sumo_home).resolve() if args.sumo_home else None
    _append_runtime_paths(carla_root, sumo_home)

    if args.sync_vehicle_all:
        args.sync_vehicle_color = True
        args.sync_vehicle_lights = True

    if args.xodr or args.town:
        _load_carla_world(args)

    import run_synchronization as carla_sumo_sync
    if args.spectator_view == "third":
        _install_follow_spectator(carla_sumo_sync, args)

    sync_args = SimpleNamespace(
        sumo_cfg_file=str(Path(args.sumo_cfg).resolve()),
        carla_host=args.carla_host,
        carla_port=args.carla_port,
        sumo_host=args.sumo_host,
        sumo_port=args.sumo_port,
        sumo_gui=args.sumo_gui and os.environ.get("ZXK_RUN_MODE", "").strip().lower() not in {
            "student", "student_mode", "学生", "学生模式", "0", "false", "no", "off",
        },
        step_length=args.step_length,
        client_order=args.client_order,
        sync_vehicle_lights=args.sync_vehicle_lights,
        sync_vehicle_color=args.sync_vehicle_color,
        tls_manager=args.tls_manager,
    )
    carla_sumo_sync.synchronization_loop(sync_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
