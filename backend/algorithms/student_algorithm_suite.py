# -*- coding: utf-8 -*-
"""Unified offline packs for student-developed backend algorithms.

The suite turns backend algorithm modules into stable student tasks:
raw inputs, baseline outputs, submission templates, metadata, and evaluators.
It intentionally avoids requiring students to call SUMO, DTALite, CARLA, or
the platform runtime during algorithm development.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ALGORITHMS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = ALGORITHMS_DIR / "student_packs"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _metrics(y_true, y_pred) -> dict[str, float]:
    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    if true.size == 0:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "r2": 0.0}
    err = pred - true
    mae = float(np.mean(np.abs(err)))
    rmse = float(math.sqrt(np.mean(err**2)))
    non_zero = true != 0
    mape = float(np.mean(np.abs(err[non_zero] / true[non_zero])) * 100) if np.any(non_zero) else 0.0
    ss_tot = float(np.sum((true - np.mean(true)) ** 2))
    ss_res = float(np.sum(err**2))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 4),
        "r2": round(r2, 6),
    }


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def _require_columns(df: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{label} 缺少列: {', '.join(missing)}")


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    module_id: str
    title: str
    builder: Callable[[Path], dict]
    evaluator: Callable[[Path, Path], dict]


def build_traffic_prediction_pack(output_dir: Path) -> dict:
    module_path = ALGORITHMS_DIR / "traffic_prediction" / "student_algorithm_pack.py"
    spec = importlib.util.spec_from_file_location("traffic_prediction_student_pack", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.build_pack(output_dir)
    metadata["suite_task_id"] = "traffic_prediction"
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata


def evaluate_traffic_prediction(submission_path: Path, pack_dir: Path) -> dict:
    module_path = ALGORITHMS_DIR / "traffic_prediction" / "evaluate_student_submission.py"
    spec = importlib.util.spec_from_file_location("traffic_prediction_evaluator", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.evaluate_submission(submission_path, pack_dir)
    result.setdefault("task_id", "traffic_prediction")
    return result


def _fusion_records(split: str) -> pd.DataFrame:
    base = ALGORITHMS_DIR / "data_fusion"
    yolo_dir = base / "input" / "yolo" / split
    pc_dir = base / "input" / "pointcloud" / split
    classes = {
        0: "Cyclist",
        1: "Car",
        3: "Pedestrian",
        5: "Bus",
        6: "Truck",
    }
    frame_ids = {path.stem for path in yolo_dir.glob("*.json")} | {path.stem for path in pc_dir.glob("*.json")}
    rows = []
    for frame_id in sorted(frame_ids):
        yolo = {}
        pc = {}
        yolo_path = yolo_dir / f"{frame_id}.json"
        pc_path = pc_dir / f"{frame_id}.json"
        if yolo_path.exists():
            yolo = json.loads(yolo_path.read_text(encoding="utf-8"))
        if pc_path.exists():
            pc = json.loads(pc_path.read_text(encoding="utf-8"))
        for cls_id, cls_name in classes.items():
            yolo_entry = yolo.get(str(cls_id), {})
            pc_entry = pc.get(cls_name, {})
            rows.append(
                {
                    "frame_id": frame_id,
                    "class_name": cls_name,
                    "yolo_mean_conf": _safe_float(yolo_entry.get("mean_conf"), 0.1),
                    "yolo_count": int(_safe_float(yolo_entry.get("count"), 0)),
                    "pc_entropy": _safe_float(pc_entry.get("entropy"), 10.0),
                    "pc_count": int(_safe_float(pc_entry.get("count"), 0)),
                }
            )
    return pd.DataFrame(rows)


def _fusion_baseline(split: str) -> pd.DataFrame:
    out_dir = ALGORITHMS_DIR / "data_fusion" / "output" / "fusion" / split
    rows = []
    for path in sorted(out_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for cls_name, values in data.items():
            rows.append(
                {
                    "frame_id": path.stem,
                    "class_name": cls_name,
                    "prediction_fused_prob": _safe_float(values.get("fused_prob"), 0.0),
                }
            )
    return pd.DataFrame(rows)


def build_data_fusion_pack(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    train = _fusion_records("val")
    test = _fusion_records("test")
    baseline = _fusion_baseline("test")

    train.to_csv(output_dir / "train_features.csv", index=False, encoding="utf-8-sig")
    test.to_csv(output_dir / "test_features.csv", index=False, encoding="utf-8-sig")
    baseline.to_csv(output_dir / "baseline_predictions.csv", index=False, encoding="utf-8-sig")
    baseline.to_csv(output_dir / "reference_fusion.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        {
            "frame_id": test["frame_id"],
            "class_name": test["class_name"],
            "prediction_fused_prob": "",
        }
    ).to_csv(output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig")

    metadata = {
        "task_id": "data_fusion",
        "module_id": "data_fusion",
        "task_name": "多源感知结果融合自研算法",
        "input_files": ["train_features.csv", "test_features.csv"],
        "submission_columns": ["frame_id", "class_name", "prediction_fused_prob"],
        "baseline_file": "baseline_predictions.csv",
        "reference_note": "无人工标注真值时，以平台贝叶斯融合结果作为可重复参考基线。",
        "train_size": int(len(train)),
        "test_size": int(len(test)),
    }
    _write_json(output_dir / "metadata.json", metadata)
    (output_dir / "README.md").write_text(
        "# 多源数据融合学生算法包\n\n"
        "读取 `test_features.csv`，为每个 `frame_id + class_name` 输出融合概率。\n"
        "提交列为 `frame_id,class_name,prediction_fused_prob`。\n",
        encoding="utf-8",
    )
    return metadata


def evaluate_data_fusion(submission_path: Path, pack_dir: Path) -> dict:
    reference = _read_csv(pack_dir / "reference_fusion.csv")
    submission = _read_csv(submission_path)
    key_cols = ["frame_id", "class_name"]
    _require_columns(submission, key_cols + ["prediction_fused_prob"], "数据融合提交文件")
    submission["prediction_fused_prob"] = pd.to_numeric(
        submission["prediction_fused_prob"], errors="coerce"
    )
    if submission["prediction_fused_prob"].isna().any():
        raise ValueError("prediction_fused_prob 存在空值或非数值")
    merged = reference.merge(submission, on=key_cols, how="left", suffixes=("_reference", "_student"))
    if merged["prediction_fused_prob_student"].isna().any():
        raise ValueError("提交缺少部分测试样本")
    metrics = _metrics(merged["prediction_fused_prob_reference"], merged["prediction_fused_prob_student"])
    return {
        "task_id": "data_fusion",
        "sample_count": int(len(merged)),
        "reference_metrics": metrics,
        "comparison": {"mae_to_platform_baseline": metrics["mae"], "rmse_to_platform_baseline": metrics["rmse"]},
    }


def _webster_solution() -> pd.DataFrame:
    config = json.loads(
        (ALGORITHMS_DIR / "signal_optimization" / "config_files" / "Webster算法配置.json").read_text(
            encoding="utf-8"
        )
    )
    main = float(config["traffic_flow"]["main_road"])
    branch = float(config["traffic_flow"]["branch_road"])
    flows = [main / 2, main / 2, branch / 2, branch / 2]
    saturation = 1800.0
    y_values = [flow / saturation for flow in flows]
    y_sum = sum(y_values)
    lost_time = len(flows) * 4
    cycle = (1.5 * lost_time + 5) / (1 - y_sum)
    cycle = max(40, min(cycle, 180))
    greens = [max(10, round((y / y_sum) * (cycle - lost_time))) for y in y_values]
    return pd.DataFrame(
        {
            "cycle": [round(cycle)] * len(greens),
            "phase_id": list(range(len(greens))),
            "green_time": greens,
            "phase_flow": flows,
        }
    )


def build_signal_optimization_pack(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = ALGORITHMS_DIR / "signal_optimization" / "config_files" / "Webster算法配置.json"
    shutil.copy2(config_path, output_dir / "scenario_config.json")
    baseline = _webster_solution()
    baseline.to_csv(output_dir / "baseline_solution.csv", index=False, encoding="utf-8-sig")
    baseline[["cycle", "phase_id"]].assign(green_time="").to_csv(
        output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig"
    )
    metadata = {
        "task_id": "signal_optimization",
        "module_id": "signal_optimization",
        "task_name": "单点交叉口信号配时自研算法",
        "input_files": ["scenario_config.json"],
        "submission_columns": ["cycle", "phase_id", "green_time"],
        "baseline_file": "baseline_solution.csv",
        "primary_metric": "green_time_mae",
        "constraints": {"cycle_min": 40, "cycle_max": 180, "green_min": 10, "green_max": 80},
    }
    _write_json(output_dir / "metadata.json", metadata)
    return metadata


def evaluate_signal_optimization(submission_path: Path, pack_dir: Path) -> dict:
    baseline = _read_csv(pack_dir / "baseline_solution.csv")
    submission = _read_csv(submission_path)
    _require_columns(submission, ["cycle", "phase_id", "green_time"], "信号优化提交文件")
    submission["cycle"] = pd.to_numeric(submission["cycle"], errors="coerce")
    submission["green_time"] = pd.to_numeric(submission["green_time"], errors="coerce")
    if submission[["cycle", "green_time"]].isna().any().any():
        raise ValueError("cycle 或 green_time 存在空值或非数值")
    merged = baseline.merge(submission, on="phase_id", how="left", suffixes=("_baseline", "_student"))
    if merged["green_time_student"].isna().any():
        raise ValueError("提交缺少部分相位")
    green_mae = float(np.mean(np.abs(merged["green_time_baseline"] - merged["green_time_student"])))
    cycle_mae = float(np.mean(np.abs(merged["cycle_baseline"] - merged["cycle_student"])))
    feasible = bool(
        submission["cycle"].between(40, 180).all()
        and submission["green_time"].between(10, 80).all()
    )
    return {
        "task_id": "signal_optimization",
        "phase_count": int(len(merged)),
        "student_metrics": {
            "green_time_mae": round(green_mae, 4),
            "cycle_mae": round(cycle_mae, 4),
            "feasible": feasible,
        },
        "baseline_metrics": {"green_time_mae": 0.0, "cycle_mae": 0.0, "feasible": True},
    }


def _build_graph_from_sumo_net() -> dict[str, list[tuple[str, str, float]]]:
    net_file = ALGORITHMS_DIR / "signal_optimization" / "config" / "siouxfalls.net.xml"
    root = ET.parse(net_file).getroot()
    graph: dict[str, list[tuple[str, str, float]]] = {}
    for edge in root.findall("edge"):
        edge_id = edge.get("id", "")
        if edge_id.startswith(":") or "_" not in edge_id:
            continue
        from_node, to_node = edge_id.split("_", 1)
        lane = edge.find("lane")
        length = _safe_float(lane.get("length") if lane is not None else None, 1.0)
        graph.setdefault(from_node, []).append((to_node, edge_id, length))
    return graph


def _dijkstra(graph: dict[str, list[tuple[str, str, float]]], origin: str, dest: str) -> tuple[list[str], float]:
    import heapq

    heap = [(0.0, origin, [origin])]
    seen = set()
    while heap:
        cost, node, path = heapq.heappop(heap)
        if node == dest:
            return path, cost
        if node in seen:
            continue
        seen.add(node)
        for next_node, _, edge_cost in graph.get(node, []):
            if next_node not in seen:
                heapq.heappush(heap, (cost + edge_cost, next_node, path + [next_node]))
    return [], math.inf


def build_path_guidance_pack(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = _build_graph_from_sumo_net()
    od = pd.read_csv(ALGORITHMS_DIR / "signal_optimization" / "data" / "SiouxFalls_od.csv")
    od = od.sort_values("Ton", ascending=False).head(30).copy()
    od["origin"] = od["O"].astype(str)
    od["destination"] = od["D"].astype(str)
    od[["origin", "destination", "Ton"]].to_csv(output_dir / "od_pairs.csv", index=False, encoding="utf-8-sig")

    edge_rows = []
    for from_node, edges in sorted(graph.items(), key=lambda item: int(item[0])):
        for to_node, edge_id, length in edges:
            edge_rows.append({"from_node": from_node, "to_node": to_node, "edge_id": edge_id, "length": length})
    pd.DataFrame(edge_rows).to_csv(output_dir / "network_edges.csv", index=False, encoding="utf-8-sig")

    baseline_rows = []
    for row in od.itertuples(index=False):
        path, cost = _dijkstra(graph, str(row.O), str(row.D))
        if path:
            baseline_rows.append(
                {
                    "origin": str(row.O),
                    "destination": str(row.D),
                    "path": "|".join(path),
                    "total_cost": round(cost, 4),
                }
            )
    baseline = pd.DataFrame(baseline_rows)
    baseline.to_csv(output_dir / "baseline_paths.csv", index=False, encoding="utf-8-sig")
    baseline[["origin", "destination"]].assign(path="", total_cost="").to_csv(
        output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig"
    )
    metadata = {
        "task_id": "path_guidance",
        "module_id": "path_guidance",
        "task_name": "SiouxFalls路网路径诱导自研算法",
        "input_files": ["network_edges.csv", "od_pairs.csv"],
        "submission_columns": ["origin", "destination", "path", "total_cost"],
        "baseline_file": "baseline_paths.csv",
        "primary_metric": "cost_ratio_mean",
    }
    _write_json(output_dir / "metadata.json", metadata)
    return metadata


def evaluate_path_guidance(submission_path: Path, pack_dir: Path) -> dict:
    edges = _read_csv(pack_dir / "network_edges.csv")
    edge_cost = {(str(r.from_node), str(r.to_node)): float(r.length) for r in edges.itertuples(index=False)}
    baseline = _read_csv(pack_dir / "baseline_paths.csv")
    submission = _read_csv(submission_path)
    _require_columns(submission, ["origin", "destination", "path", "total_cost"], "路径诱导提交文件")
    merged = baseline.merge(submission, on=["origin", "destination"], how="left", suffixes=("_baseline", "_student"))
    if merged["path_student"].isna().any():
        raise ValueError("提交缺少部分OD对")
    ratios = []
    invalid = 0
    for row in merged.itertuples(index=False):
        nodes = str(row.path_student).split("|")
        if len(nodes) < 2 or nodes[0] != str(row.origin) or nodes[-1] != str(row.destination):
            invalid += 1
            continue
        cost = 0.0
        ok = True
        for a, b in zip(nodes, nodes[1:]):
            value = edge_cost.get((str(a), str(b)))
            if value is None:
                ok = False
                break
            cost += value
        if not ok:
            invalid += 1
            continue
        ratios.append(cost / float(row.total_cost_baseline))
    return {
        "task_id": "path_guidance",
        "sample_count": int(len(merged)),
        "valid_paths": int(len(ratios)),
        "invalid_paths": int(invalid),
        "student_metrics": {
            "cost_ratio_mean": round(float(np.mean(ratios)), 6) if ratios else math.inf,
            "valid_rate": round(len(ratios) / len(merged), 6) if len(merged) else 0,
        },
        "baseline_metrics": {"cost_ratio_mean": 1.0, "valid_rate": 1.0},
    }


def build_traffic_reconstruction_pack(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = ALGORITHMS_DIR / "traffic_reconstruction" / "dtalite"
    validation = pd.read_csv(base / "debug_validation_results.csv")
    columns = ["link_id", "time_interval", "observed_link_count", "simulated_link_count"]
    validation[columns].to_csv(output_dir / "validation_reference.csv", index=False, encoding="utf-8-sig")
    validation[["link_id", "time_interval", "observed_link_count"]].to_csv(
        output_dir / "test_observed_counts.csv", index=False, encoding="utf-8-sig"
    )
    validation[["link_id", "time_interval", "simulated_link_count"]].to_csv(
        output_dir / "baseline_reconstruction.csv", index=False, encoding="utf-8-sig"
    )
    validation[["link_id", "time_interval"]].assign(simulated_link_count="").to_csv(
        output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig"
    )
    for name in ["input_link.csv", "input_node.csv", "input_zone.csv"]:
        src = base / name
        if src.exists():
            shutil.copy2(src, output_dir / name)
    metadata = {
        "task_id": "traffic_reconstruction",
        "module_id": "traffic_reconstruction",
        "task_name": "交通流重构自研算法",
        "input_files": ["test_observed_counts.csv", "input_link.csv", "input_node.csv", "input_zone.csv"],
        "submission_columns": ["link_id", "time_interval", "simulated_link_count"],
        "baseline_file": "baseline_reconstruction.csv",
        "primary_metric": "rmse_to_observed",
    }
    _write_json(output_dir / "metadata.json", metadata)
    return metadata


def evaluate_traffic_reconstruction(submission_path: Path, pack_dir: Path) -> dict:
    reference = _read_csv(pack_dir / "validation_reference.csv")
    baseline = _read_csv(pack_dir / "baseline_reconstruction.csv")
    submission = _read_csv(submission_path)
    keys = ["link_id", "time_interval"]
    _require_columns(submission, keys + ["simulated_link_count"], "交通重构提交文件")
    submission["simulated_link_count"] = pd.to_numeric(submission["simulated_link_count"], errors="coerce")
    if submission["simulated_link_count"].isna().any():
        raise ValueError("simulated_link_count 存在空值或非数值")
    merged = reference[keys + ["observed_link_count"]].merge(submission, on=keys, how="left")
    if merged["simulated_link_count"].isna().any():
        raise ValueError("提交缺少部分观测样本")
    baseline_merged = reference[keys + ["observed_link_count"]].merge(baseline, on=keys, how="left")
    student_metrics = _metrics(merged["observed_link_count"], merged["simulated_link_count"])
    baseline_metrics = _metrics(baseline_merged["observed_link_count"], baseline_merged["simulated_link_count"])
    return {
        "task_id": "traffic_reconstruction",
        "sample_count": int(len(merged)),
        "student_metrics": student_metrics,
        "baseline_metrics": baseline_metrics,
        "comparison": {
            "rmse_delta": round(student_metrics["rmse"] - baseline_metrics["rmse"], 4),
            "beats_baseline_by_rmse": student_metrics["rmse"] < baseline_metrics["rmse"],
        },
    }


def build_vehicle_speed_control_pack(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = ALGORITHMS_DIR / "vehicle_speed_control" / "output" / "speed_pid_4_40" / "results.json"
    baseline = json.loads(result_path.read_text(encoding="utf-8"))
    _write_json(output_dir / "scenario.json", {"flow_level": 4, "cav_penetration": 40, "baseline_algorithm": "PID"})
    pd.DataFrame([baseline]).to_csv(output_dir / "baseline_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "algorithm": "",
                "average_delay": "",
                "avg_speed": "",
                "speed_std": "",
                "avg_accel": "",
                "throughput": "",
            }
        ]
    ).to_csv(output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig")
    metadata = {
        "task_id": "vehicle_speed_control",
        "module_id": "vehicle_speed_control",
        "task_name": "车速控制算法结果对比",
        "input_files": ["scenario.json"],
        "submission_columns": ["algorithm", "average_delay", "avg_speed", "speed_std", "avg_accel", "throughput"],
        "baseline_file": "baseline_metrics.csv",
        "primary_metric": "delay_delta",
        "note": "学生可在外部环境运行控制算法后提交同格式指标；平台侧统一比较指标。",
    }
    _write_json(output_dir / "metadata.json", metadata)
    return metadata


def evaluate_vehicle_speed_control(submission_path: Path, pack_dir: Path) -> dict:
    baseline = _read_csv(pack_dir / "baseline_metrics.csv").iloc[0]
    submission = _read_csv(submission_path).iloc[0]
    numeric = ["average_delay", "avg_speed", "speed_std", "avg_accel", "throughput"]
    for col in numeric:
        if col not in submission.index:
            raise ValueError(f"车速控制提交文件缺少列: {col}")
    values = {col: _safe_float(submission[col]) for col in numeric}
    baseline_values = {col: _safe_float(baseline[col]) for col in numeric}
    return {
        "task_id": "vehicle_speed_control",
        "student_metrics": values,
        "baseline_metrics": baseline_values,
        "comparison": {
            "delay_delta": round(values["average_delay"] - baseline_values["average_delay"], 4),
            "avg_speed_delta": round(values["avg_speed"] - baseline_values["avg_speed"], 4),
            "beats_baseline_by_delay": values["average_delay"] < baseline_values["average_delay"],
        },
    }


def _latest_metrics_file(mode: str) -> Path:
    output = ALGORITHMS_DIR / "multi_level_coordination" / "output"
    files = sorted(output.glob(f"metrics_{mode}_*.json"))
    if not files:
        raise FileNotFoundError(f"缺少多层级协调基准文件: metrics_{mode}_*.json")
    return files[-1]


def build_coordination_control_pack(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    mode_files = {}
    for mode in ["none", "local", "full"]:
        src = _latest_metrics_file(mode)
        dst = output_dir / f"baseline_{mode}.json"
        shutil.copy2(src, dst)
        mode_files[mode] = dst.name
    full = pd.DataFrame(json.loads((output_dir / "baseline_full.json").read_text(encoding="utf-8")))
    full[["step", "avg_speed", "waiting_count"]].to_csv(
        output_dir / "baseline_full_timeseries.csv", index=False, encoding="utf-8-sig"
    )
    full[["step"]].assign(avg_speed="", waiting_count="").to_csv(
        output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig"
    )
    metadata = {
        "task_id": "coordination_control",
        "module_id": "three_level_control,multi_level_coordination,hierarchical_control",
        "task_name": "三层级/多层级协调控制指标对比",
        "input_files": list(mode_files.values()),
        "submission_columns": ["step", "avg_speed", "waiting_count"],
        "baseline_file": "baseline_full_timeseries.csv",
        "primary_metric": "avg_speed_rmse_to_full_baseline",
    }
    _write_json(output_dir / "metadata.json", metadata)
    return metadata


def evaluate_coordination_control(submission_path: Path, pack_dir: Path) -> dict:
    reference = _read_csv(pack_dir / "baseline_full_timeseries.csv")
    submission = _read_csv(submission_path)
    _require_columns(submission, ["step", "avg_speed", "waiting_count"], "协调控制提交文件")
    submission["avg_speed"] = pd.to_numeric(submission["avg_speed"], errors="coerce")
    submission["waiting_count"] = pd.to_numeric(submission["waiting_count"], errors="coerce")
    if submission[["avg_speed", "waiting_count"]].isna().any().any():
        raise ValueError("avg_speed 或 waiting_count 存在空值或非数值")
    merged = reference.merge(submission, on="step", how="left", suffixes=("_baseline", "_student"))
    if merged["avg_speed_student"].isna().any():
        raise ValueError("提交缺少部分仿真步")
    speed_metrics = _metrics(merged["avg_speed_baseline"], merged["avg_speed_student"])
    waiting_metrics = _metrics(merged["waiting_count_baseline"], merged["waiting_count_student"])
    return {
        "task_id": "coordination_control",
        "sample_count": int(len(merged)),
        "student_metrics": {
            "avg_speed_rmse_to_full_baseline": speed_metrics["rmse"],
            "waiting_count_rmse_to_full_baseline": waiting_metrics["rmse"],
        },
        "baseline_metrics": {
            "avg_speed_rmse_to_full_baseline": 0.0,
            "waiting_count_rmse_to_full_baseline": 0.0,
        },
    }


TASKS: dict[str, TaskSpec] = {
    "traffic_prediction": TaskSpec(
        "traffic_prediction", "traffic_prediction", "交通流预测", build_traffic_prediction_pack, evaluate_traffic_prediction
    ),
    "data_fusion": TaskSpec("data_fusion", "data_fusion", "多源数据融合", build_data_fusion_pack, evaluate_data_fusion),
    "signal_optimization": TaskSpec(
        "signal_optimization", "signal_optimization", "交通信号优化", build_signal_optimization_pack, evaluate_signal_optimization
    ),
    "path_guidance": TaskSpec("path_guidance", "path_guidance", "路径诱导", build_path_guidance_pack, evaluate_path_guidance),
    "traffic_reconstruction": TaskSpec(
        "traffic_reconstruction", "traffic_reconstruction", "交通流重构", build_traffic_reconstruction_pack, evaluate_traffic_reconstruction
    ),
    "vehicle_speed_control": TaskSpec(
        "vehicle_speed_control", "vehicle_speed_control", "车速控制", build_vehicle_speed_control_pack, evaluate_vehicle_speed_control
    ),
    "coordination_control": TaskSpec(
        "coordination_control",
        "three_level_control,multi_level_coordination,hierarchical_control",
        "三层级/多层级协调控制",
        build_coordination_control_pack,
        evaluate_coordination_control,
    ),
}


MODULE_CATALOG = {
    "included_offline_tasks": list(TASKS.keys()),
    "format_only_or_external_dependency": {
        "data_collection": "依赖YOLO/视频输入，建议提交 detection_results.json 或 trajectories.csv 后由教师按检测指标评测。",
        "carla_simulation": "依赖CARLA服务与地图环境，建议提交 trajectory.csv、collision_count、completion_rate 等指标。",
        "vehicle_dev_control": "依赖车规级控制/硬件或CARLA环境，纳入CARLA同类指标规范。",
        "simulation": "作为仿真承载模块，不单独作为学生算法题目；由信号、路径、速度、协调任务复用。",
    },
}


def build_all_packs(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    all_metadata = {}
    for task_id, task in TASKS.items():
        metadata = task.builder(output_root / task_id)
        all_metadata[task_id] = metadata
    _write_json(output_root / "suite_metadata.json", {"tasks": all_metadata, "catalog": MODULE_CATALOG})
    return all_metadata


def evaluate(task_id: str, submission_path: Path, pack_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    if task_id not in TASKS:
        raise KeyError(f"未知任务: {task_id}")
    return TASKS[task_id].evaluator(submission_path, pack_root / task_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="学生自研算法统一数据包和评测器")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build", help="生成全部或指定学生算法包")
    build_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))

    list_parser = sub.add_parser("list", help="列出支持的任务")
    list_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))

    eval_parser = sub.add_parser("evaluate", help="评测学生提交")
    eval_parser.add_argument("task_id", choices=sorted(TASKS.keys()))
    eval_parser.add_argument("submission")
    eval_parser.add_argument("--pack-root", default=str(DEFAULT_OUTPUT_ROOT))
    eval_parser.add_argument("--output", default="")

    args = parser.parse_args()
    if args.command == "build":
        metadata = build_all_packs(Path(args.output_root))
        print(json.dumps({"generated": list(metadata.keys()), "output_root": str(Path(args.output_root).resolve())}, ensure_ascii=False, indent=2))
    elif args.command == "list":
        print(json.dumps({"tasks": list(TASKS.keys()), "catalog": MODULE_CATALOG}, ensure_ascii=False, indent=2))
    elif args.command == "evaluate":
        result = evaluate(args.task_id, Path(args.submission), Path(args.pack_root))
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(text)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
