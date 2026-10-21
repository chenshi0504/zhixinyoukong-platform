# -*- coding: utf-8 -*-
import importlib.util
import sys
from pathlib import Path

import pandas as pd


SUITE_PATH = Path(__file__).resolve().parents[1] / "student_algorithm_suite.py"


def _load_suite():
    spec = importlib.util.spec_from_file_location("student_algorithm_suite", SUITE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_all_backend_student_algorithm_packs(tmp_path):
    suite = _load_suite()

    metadata = suite.build_all_packs(tmp_path)

    expected_tasks = {
        "traffic_prediction",
        "data_fusion",
        "signal_optimization",
        "path_guidance",
        "traffic_reconstruction",
        "vehicle_speed_control",
        "coordination_control",
    }
    assert expected_tasks == set(metadata)
    assert (tmp_path / "suite_metadata.json").exists()

    for task_id in expected_tasks:
        task_dir = tmp_path / task_id
        assert task_dir.exists()
        assert (task_dir / "metadata.json").exists()
        assert (task_dir / "student_submission_template.csv").exists()


def test_baseline_submissions_evaluate_for_all_packs(tmp_path):
    suite = _load_suite()
    suite.build_all_packs(tmp_path)

    submissions = {
        "traffic_prediction": "baseline_predictions.csv",
        "data_fusion": "baseline_predictions.csv",
        "signal_optimization": "baseline_solution.csv",
        "path_guidance": "baseline_paths.csv",
        "traffic_reconstruction": "baseline_reconstruction.csv",
        "vehicle_speed_control": "baseline_metrics.csv",
        "coordination_control": "baseline_full_timeseries.csv",
    }

    for task_id, file_name in submissions.items():
        result = suite.evaluate(task_id, tmp_path / task_id / file_name, tmp_path)
        assert result["task_id"] == task_id

    traffic_prediction = suite.evaluate(
        "traffic_prediction",
        tmp_path / "traffic_prediction" / "baseline_predictions.csv",
        tmp_path,
    )
    assert traffic_prediction["comparison"]["rmse_delta"] == 0

    path_guidance = suite.evaluate(
        "path_guidance",
        tmp_path / "path_guidance" / "baseline_paths.csv",
        tmp_path,
    )
    assert path_guidance["student_metrics"]["cost_ratio_mean"] == 1.0

    signal = suite.evaluate(
        "signal_optimization",
        tmp_path / "signal_optimization" / "baseline_solution.csv",
        tmp_path,
    )
    assert signal["student_metrics"]["feasible"] is True


def test_submission_templates_match_metadata_columns(tmp_path):
    suite = _load_suite()
    metadata = suite.build_all_packs(tmp_path)

    for task_id, task_meta in metadata.items():
        template = pd.read_csv(
            tmp_path / task_id / "student_submission_template.csv",
            encoding="utf-8-sig",
        )
        assert list(template.columns) == task_meta["submission_columns"]
