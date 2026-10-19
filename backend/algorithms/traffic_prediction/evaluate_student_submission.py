# -*- coding: utf-8 -*-
"""Evaluate a student traffic-flow prediction submission against the pack truth."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PACK_DIR = BASE_DIR / "student_pack"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return pd.read_csv(path, encoding="utf-8-sig")


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    mse = mean_squared_error(y_true, y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = math.sqrt(mse)
    non_zero = y_true != 0
    mape = float(np.mean(np.abs((y_true[non_zero] - y_pred[non_zero]) / y_true[non_zero])) * 100)
    r2 = r2_score(y_true, y_pred)
    return {
        "mae": round(float(mae), 4),
        "rmse": round(float(rmse), 4),
        "mape": round(mape, 4),
        "r2": round(float(r2), 6),
    }


def evaluate_submission(submission_path: Path, pack_dir: Path = DEFAULT_PACK_DIR) -> dict[str, object]:
    """Return metrics and baseline comparison for a student CSV submission."""
    metadata_path = pack_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"缺少 metadata.json，请先运行 student_algorithm_pack.py: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    id_column = metadata["id_column"]
    prediction_column = metadata["prediction_column"]

    truth = _read_csv(pack_dir / "test_ground_truth.csv")
    baseline = _read_csv(pack_dir / "baseline_predictions.csv")
    submission = _read_csv(submission_path)

    missing = [col for col in (id_column, prediction_column) if col not in submission.columns]
    if missing:
        raise ValueError(f"提交文件缺少列: {', '.join(missing)}")

    submission = submission[[id_column, prediction_column]].copy()
    submission[prediction_column] = pd.to_numeric(submission[prediction_column], errors="coerce")
    if submission[prediction_column].isna().any():
        bad_count = int(submission[prediction_column].isna().sum())
        raise ValueError(f"预测列存在非数值或空值: {bad_count} 行")
    if submission[id_column].duplicated().any():
        raise ValueError("sample_id 存在重复值")

    merged = truth.merge(submission, on=id_column, how="left", validate="one_to_one")
    if merged[prediction_column].isna().any():
        missing_ids = merged.loc[merged[prediction_column].isna(), id_column].head(10).tolist()
        raise ValueError(f"提交文件缺少测试样本预测，示例 sample_id: {missing_ids}")

    truth_ids = set(truth[id_column].tolist())
    extra_ids = sorted(set(submission[id_column].tolist()) - truth_ids)
    if extra_ids:
        raise ValueError(f"提交文件包含非测试集 sample_id，示例: {extra_ids[:10]}")

    y_true = merged["target_total_flow"].to_numpy(dtype=float)
    y_pred = merged[prediction_column].to_numpy(dtype=float)
    student_metrics = _metrics(y_true, y_pred)

    baseline_merged = truth.merge(baseline, on=id_column, how="inner", validate="one_to_one")
    baseline_metrics = _metrics(
        baseline_merged["target_total_flow"].to_numpy(dtype=float),
        baseline_merged[prediction_column].to_numpy(dtype=float),
    )
    rmse_delta = student_metrics["rmse"] - baseline_metrics["rmse"]
    rmse_improvement = (baseline_metrics["rmse"] - student_metrics["rmse"]) / baseline_metrics["rmse"] * 100

    result = {
        "submission": str(submission_path),
        "sample_count": int(len(merged)),
        "student_metrics": student_metrics,
        "baseline_metrics": baseline_metrics,
        "comparison": {
            "rmse_delta": round(float(rmse_delta), 4),
            "rmse_improvement_percent": round(float(rmse_improvement), 4),
            "beats_baseline_by_rmse": bool(student_metrics["rmse"] < baseline_metrics["rmse"]),
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("submission", help="学生提交 CSV，例如 student_pack/baseline_predictions.csv")
    parser.add_argument("--pack-dir", default=str(DEFAULT_PACK_DIR), help="学生算法数据包目录")
    parser.add_argument("--output", default="", help="可选：将评测结果保存为 JSON")
    args = parser.parse_args()

    result = evaluate_submission(Path(args.submission), Path(args.pack_dir))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
