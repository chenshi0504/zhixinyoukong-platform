# 交通流预测模块

## 模块简介
基于深度学习的交通流预测系统，支持LSTM、GRU、Transformer等多种时序预测模型。

## 算法原理

### LSTM (Long Short-Term Memory)
- 长短期记忆网络
- 处理长序列依赖
- 适合交通流时序预测

### GRU (Gated Recurrent Unit)
- 门控循环单元
- 参数更少，训练更快
- 性能接近LSTM

### Transformer
- 自注意力机制
- 并行计算能力强
- 捕捉长距离依赖

## 主要功能
- 短期流量预测（5-30分钟）
- 中期流量预测（1-3小时）
- 多步预测
- 模型对比评估

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| model | str | LSTM | 预测模型（LSTM/GRU/Transformer） |
| sequence_length | int | 12 | 输入序列长度（时间步） |
| prediction_horizon | int | 6 | 预测时长（时间步） |
| hidden_size | int | 64 | 隐藏层大小 |
| num_layers | int | 2 | 网络层数 |
| epochs | int | 100 | 训练轮数 |

### 运行示例
```bash
cd backend/algorithms/traffic_prediction
python train_model.py --model LSTM --epochs 100
```

## 输出结果
- **预测结果**: `output/prediction_{timestamp}.csv`
- **训练曲线**: `output/training_curve_{timestamp}.png`
- **模型文件**: `output/model_{timestamp}.pth`

## 性能指标
- **MAE (Mean Absolute Error)**: 平均绝对误差
- **RMSE (Root Mean Square Error)**: 均方根误差
- **MAPE (Mean Absolute Percentage Error)**: 平均绝对百分比误差

## 常见问题

### 1. 预测精度不高
**解决方案**: 增加训练数据量，调整sequence_length，尝试不同模型

### 2. 训练过拟合
**解决方案**: 添加Dropout层，减少模型复杂度，使用早停策略

## 参考文献
1. LSTM: Hochreiter, S., & Schmidhuber, J., "Long short-term memory", 1997
2. GRU: Cho, K., et al., "Learning Phrase Representations using RNN Encoder-Decoder", 2014
3. Transformer: Vaswani, A., et al., "Attention is All You Need", 2017
