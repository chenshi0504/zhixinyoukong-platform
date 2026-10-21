# -*- coding: utf-8 -*-
"""Build a lightweight student algorithm pack for traffic-flow prediction.

The pack contains raw data, train/test feature tables, hidden ground truth,
baseline predictions, and a metadata file. Students can develop algorithms
offline without calling the full simulation platform.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.tree import DecisionTreeRegressor


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "Traffic flow data.csv"
DEFAULT_OUTPUT_DIR = BASE_DIR / "student_pack"

TIME_STEP = 5
TRAIN_RATIO = 0.8
BASELINE_MODEL = "DecisionTreeRegressor(max_depth=10, random_state=42)"


def load_source_data(data_file: Path = DATA_FILE) -> pd.DataFrame:
    """Load and normalize the platform traffic-flow CSV."""
    source = pd.read_csv(data_file, encoding="utf-8")
    data = pd.DataFrame()
    data["datetime"] = pd.to_datetime(
        source["Local Date"].str.strip() + " " + source[" Local Time"].str.strip()
    )
    data["total_flow"] = source[" Total Carriageway Flow"].astype(float)
    data["speed"] = source[" Speed Value"].astype(float)
    data["quality_index"] = source[" Quality Index"].astype(int)
    data["day_type_id"] = source[" Day Type ID"].astype(int)
    data["hour"] = data["datetime"].dt.hour
    data["minute"] = data["datetime"].dt.minute
    data["day_of_week"] = data["datetime"].dt.dayofweek
    return data


def create_supervised_table(data: pd.DataFrame, time_step: int = TIME_STEP) -> pd.DataFrame:
    """Create lag features and target values for one-step-ahead prediction."""
    rows = []
    flow = data["total_flow"].to_numpy()
    for idx in range(time_step, len(data)):
        row = {
            "sample_id": idx - time_step,
            "datetime": data.iloc[idx]["datetime"].isoformat(),
            "hour": int(data.iloc[idx]["hour"]),
            "minute": int(data.iloc[idx]["minute"]),
            "day_of_week": int(data.iloc[idx]["day_of_week"]),
            "speed": float(data.iloc[idx]["speed"]),
            "quality_index": int(data.iloc[idx]["quality_index"]),
            "day_type_id": int(data.iloc[idx]["day_type_id"]),
            "target_total_flow": float(flow[idx]),
        }
        for lag in range(time_step, 0, -1):
            row[f"flow_lag_{lag}"] = float(flow[idx - lag])
        rows.append(row)
    return pd.DataFrame(rows)


def _lag_columns(time_step: int = TIME_STEP) -> list[str]:
    return [f"flow_lag_{lag}" for lag in range(time_step, 0, -1)]


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
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


def build_pack(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, object]:
    """Generate all files needed for student development and comparison."""
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_source_data()
    table = create_supervised_table(data)
    split = int(len(table) * TRAIN_RATIO)
    train = table.iloc[:split].copy()
    test = table.iloc[split:].copy()

    feature_columns = [
        "sample_id",
        "datetime",
        "hour",
        "minute",
        "day_of_week",
        "speed",
        "quality_index",
        "day_type_id",
        *_lag_columns(),
    ]
    prediction_columns = ["sample_id", "prediction_total_flow"]

    X_train = train[_lag_columns()].to_numpy()
    y_train = train["target_total_flow"].to_numpy()
    X_test = test[_lag_columns()].to_numpy()
    y_test = test["target_total_flow"].to_numpy()

    model = DecisionTreeRegressor(max_depth=10, random_state=42)
    model.fit(X_train, y_train)
    baseline_pred = model.predict(X_test)
    baseline_metrics = _regression_metrics(y_test, baseline_pred)

    data.to_csv(output_dir / "raw_traffic_flow.csv", index=False, encoding="utf-8-sig")
    train[feature_columns + ["target_total_flow"]].to_csv(
        output_dir / "train.csv", index=False, encoding="utf-8-sig"
    )
    test[feature_columns].to_csv(output_dir / "test_features.csv", index=False, encoding="utf-8-sig")
    test[["sample_id", "target_total_flow"]].to_csv(
        output_dir / "test_ground_truth.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(
        {
            "sample_id": test["sample_id"].to_numpy(),
            "prediction_total_flow": baseline_pred,
        }
    ).to_csv(output_dir / "baseline_predictions.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"sample_id": test["sample_id"].to_numpy(), "prediction_total_flow": ""}).to_csv(
        output_dir / "student_submission_template.csv", index=False, encoding="utf-8-sig"
    )

    metadata = {
        "task_id": "traffic_flow_prediction_lag5",
        "task_name": "交通流短时预测学生自研算法任务",
        "created_by": "student_algorithm_pack.py",
        "source_data": str(DATA_FILE.relative_to(BASE_DIR)),
        "target": "target_total_flow",
        "prediction_column": "prediction_total_flow",
        "id_column": "sample_id",
        "time_step": TIME_STEP,
        "train_ratio": TRAIN_RATIO,
        "train_size": int(len(train)),
        "test_size": int(len(test)),
        "feature_columns": feature_columns,
        "submission_columns": prediction_columns,
        "baseline": {
            "name": "decision_tree_lag5",
            "model": BASELINE_MODEL,
            "feature_columns": _lag_columns(),
            "metrics": baseline_metrics,
        },
        "evaluation": {
            "primary_metric": "rmse",
            "smaller_is_better": ["mae", "rmse", "mape"],
            "larger_is_better": ["r2"],
        },
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    readme = f"""# 交通流预测学生自研算法数据包

本数据包用于学生在平台外独立开发交通流短时预测算法，并与平台基准算法进行统一对比。

## 文件说明

- `raw_traffic_flow.csv`: 题目涉及的原始交通流数据整理版。
- `train.csv`: 训练集，包含特征列和 `target_total_flow` 标签。
- `test_features.csv`: 测试集特征，学生算法只读取这个文件生成预测。
- `student_submission_template.csv`: 学生提交格式模板，需填写 `prediction_total_flow`。
- `baseline_predictions.csv`: 平台基准算法在同一测试集上的预测结果。
- `test_ground_truth.csv`: 测试集标准答案，教师评测时使用。
- `metadata.json`: 数据划分、特征、指标和基准算法说明。

## 学生提交要求

提交 CSV 文件，至少包含两列：

```csv
sample_id,prediction_total_flow
2300,925.0
2301,918.0
```

`sample_id` 必须与 `test_features.csv` 一致，`prediction_total_flow` 为算法预测的总车流量。

## 当前基准算法

基准算法：`{BASELINE_MODEL}`

基准结果：MAE={baseline_metrics["mae"]}, RMSE={baseline_metrics["rmse"]}, MAPE={baseline_metrics["mape"]}%, R2={baseline_metrics["r2"]}
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="学生算法数据包输出目录")
    args = parser.parse_args()

    metadata = build_pack(Path(args.output_dir))
    baseline = metadata["baseline"]["metrics"]
    print("学生算法数据包已生成")
    print(f"输出目录: {Path(args.output_dir).resolve()}")
    print(
        "基准结果: "
        f"MAE={baseline['mae']}, RMSE={baseline['rmse']}, "
        f"MAPE={baseline['mape']}%, R2={baseline['r2']}"
    )


if __name__ == "__main__":
    main()
