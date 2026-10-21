# 交通流预测学生自研算法数据包

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

基准算法：`DecisionTreeRegressor(max_depth=10, random_state=42)`

基准结果：MAE=79.6619, RMSE=118.4984, MAPE=10.7515%, R2=0.937576
