# -*- coding: utf-8 -*-
import importlib.util
import json
from pathlib import Path

import pandas as pd


MODULE_DIR = Path(__file__).resolve().parents[1]


def _load_module(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / file_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_student_pack_generation_and_baseline_evaluation(tmp_path):
    packer = _load_module("student_algorithm_pack", "student_algorithm_pack.py")
    evaluator = _load_module("evaluate_student_submission", "evaluate_student_submission.py")

    metadata = packer.build_pack(tmp_path)

    expected_files = {
        "raw_traffic_flow.csv",
        "train.csv",
        "test_features.csv",
        "test_ground_truth.csv",
        "baseline_predictions.csv",
        "student_submission_template.csv",
        "metadata.json",
        "README.md",
    }
    assert expected_files.issubset({path.name for path in tmp_path.iterdir()})

    train = pd.read_csv(tmp_path / "train.csv", encoding="utf-8-sig")
    test_features = pd.read_csv(tmp_path / "test_features.csv", encoding="utf-8-sig")
    truth = pd.read_csv(tmp_path / "test_ground_truth.csv", encoding="utf-8-sig")
    baseline = pd.read_csv(tmp_path / "baseline_predictions.csv", encoding="utf-8-sig")

    assert len(train) == metadata["train_size"]
    assert len(test_features) == metadata["test_size"]
    assert len(truth) == metadata["test_size"]
    assert len(baseline) == metadata["test_size"]
    assert "target_total_flow" not in test_features.columns
    assert list(baseline.columns) == ["sample_id", "prediction_total_flow"]

    result = evaluator.evaluate_submission(tmp_path / "baseline_predictions.csv", tmp_path)
    assert result["sample_count"] == metadata["test_size"]
    assert result["student_metrics"] == metadata["baseline"]["metrics"]
    assert result["comparison"]["rmse_delta"] == 0

    persisted_metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert persisted_metadata["task_id"] == "traffic_flow_prediction_lag5"
