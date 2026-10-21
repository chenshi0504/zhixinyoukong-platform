# -*- coding: utf-8 -*-
"""
自定义算法实验 - 岭回归 (Ridge Regression)
========================================
岭回归是带L2正则化的线性回归，alpha越大正则化越强。
学生可修改 alpha 参数观察对预测效果的影响。
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 可修改区域 ============
# 修改 alpha 值观察正则化强度对预测的影响
# alpha 越大，模型越简单（防止过拟合）
ALPHA = 1.0          # 正则化强度，试试 0.01, 0.1, 1.0, 10, 100
TIME_STEP = 5        # 滞后窗口大小，试试 3, 5, 10, 15
TRAIN_RATIO = 0.8    # 训练集比例
# ====================================

print('=' * 60)
print('  自定义算法实验 - 岭回归 (Ridge)')
print(f'  alpha={ALPHA}, 滞后窗口={TIME_STEP}')
print('=' * 60)

# 加载数据
print('\n[1/4] 加载数据...')
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
data = pd.DataFrame()
data['total_flow'] = df[' Total Carriageway Flow'].astype(np.float64)
print(f'  数据量: {len(data)} 条')

# 构建特征
print('\n[2/4] 构建特征...')
flow = data['total_flow'].values
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]
print(f'  训练集: {len(X_train)}, 测试集: {len(X_test)}')

# 训练模型
print('\n[3/4] 训练岭回归模型...')
t0 = time.time()
model = Ridge(alpha=ALPHA)
model.fit(X_train, y_train)
pred = model.predict(X_test)
elapsed = time.time() - t0

rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)
print(f'  训练耗时: {elapsed:.2f}s')
print(f'  RMSE: {rmse:.2f}')
print(f'  MAE:  {mae:.2f}')
print(f'  R²:   {r2:.4f}')

# 保存结果
print('\n[4/4] 保存结果...')
fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='blue', linewidth=1.5, label=f'岭回归预测 (alpha={ALPHA})')
ax.set_title(f'岭回归预测结果 (R²={r2:.4f}, alpha={ALPHA})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=岭回归 (Ridge)\n')
    f.write(f'params=alpha={ALPHA}, time_step={TIME_STEP}\n')
    f.write(f'r2={r2:.4f}\n')
    f.write(f'rmse={rmse:.2f}\n')
    f.write(f'mae={mae:.2f}\n')
    f.write(f'time={elapsed:.2f}\n')

print('\n' + '=' * 60)
print(f'  实验完成！R² = {r2:.4f}')
print('=' * 60)
print('\n完成，可以关闭此窗口。')
