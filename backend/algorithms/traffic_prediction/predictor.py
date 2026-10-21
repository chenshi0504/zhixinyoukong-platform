# -*- coding: utf-8 -*-
"""
交通流预测 - 模型训练与预测脚本
支持4种算法: 线性回归、随机森林、SVR、决策树回归
通过命令行参数 --model 选择算法，支持 all/lr/rf/svr/dtr
在cmd窗口中展示完整训练过程
"""
import os
import sys
import math
import time
import argparse
import traceback


def pause_if_interactive(prompt='按回车键退出...'):
    """Only wait for input when launched from an interactive console."""
    if sys.stdin is not None and sys.stdin.isatty():
        input(prompt)


try:
    import pandas as pd
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.tree import DecisionTreeRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.svm import SVR
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
except ImportError as e:
    print(f'缺少依赖包: {e}')
    print('请运行: pip install pandas numpy matplotlib scikit-learn')
    pause_if_interactive()
    sys.exit(1)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

MODEL_NAMES = {
    'lr': '线性回归',
    'rf': '随机森林',
    'svr': '支持向量回归',
    'dtr': '决策树回归',
}
MODEL_COLORS = {
    'lr': 'blue',
    'rf': 'green',
    'svr': 'orange',
    'dtr': 'purple',
}


def create_features(df, time_step=5):
    """创建滞后特征"""
    flow = df['total_flow'].values
    X, y = [], []
    for i in range(time_step, len(flow)):
        X.append(flow[i - time_step:i])
        y.append(flow[i])
    return np.array(X), np.array(y)


def train_single_model(key, X_train, y_train, X_test, y_test, scaler=None):
    """训练单个模型，返回 (predictions, metrics, elapsed)"""
    name = MODEL_NAMES[key]
    print(f'\n  --- {name} ---')
    t0 = time.time()

    if key == 'lr':
        model = LinearRegression()
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
    elif key == 'rf':
        model = RandomForestRegressor(
            n_estimators=100, max_depth=15,
            random_state=42, n_jobs=-1, verbose=0
        )
        print('  正在训练100棵决策树...')
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
    elif key == 'svr':
        # SVR需要标准化
        if scaler is None:
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_train)
        else:
            X_tr_s = scaler.transform(X_train)
        X_te_s = scaler.transform(X_test)
        model = SVR(kernel='rbf', C=100, gamma='scale', epsilon=0.1)
        print('  正在训练SVR（RBF核）...')
        model.fit(X_tr_s, y_train)
        pred = model.predict(X_te_s)
    elif key == 'dtr':
        model = DecisionTreeRegressor(
            max_depth=10, random_state=42
        )
        print('  正在训练决策树...')
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
    else:
        raise ValueError(f'未知模型: {key}')

    elapsed = time.time() - t0
    mse = mean_squared_error(y_test, pred)
    rmse = math.sqrt(mse)
    mae = mean_absolute_error(y_test, pred)
    r2 = r2_score(y_test, pred)

    print(f'  训练耗时: {elapsed:.2f}s')
    print(f'  MSE:  {mse:.2f}')
    print(f'  RMSE: {rmse:.2f}')
    print(f'  MAE:  {mae:.2f}')
    print(f'  R2:   {r2:.4f}')

    metrics = {'mse': mse, 'rmse': rmse, 'mae': mae, 'r2': r2, 'time': elapsed}
    return pred, metrics, scaler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='all',
                        help='选择模型: all, lr, rf, svr, dtr')
    args = parser.parse_args()

    selected = args.model.lower().strip()
    if selected == 'all':
        model_keys = ['lr', 'rf', 'svr', 'dtr']
    elif selected in MODEL_NAMES:
        model_keys = [selected]
    else:
        print(f'未知模型: {selected}，使用全部模型')
        model_keys = ['lr', 'rf', 'svr', 'dtr']

    model_labels = '、'.join([MODEL_NAMES[k] for k in model_keys])
    print('=' * 60)
    print('  交通流预测 - 模型训练与预测分析')
    print(f'  算法: {model_labels}')
    print('=' * 60)

    # ---- 1. 加载数据 ----
    print('\n[1/5] 加载交通流数据...')
    inputfile = os.path.join(BASE_DIR, 'Traffic flow data.csv')
    if not os.path.exists(inputfile):
        print('  错误: 数据文件不存在!')
        pause_if_interactive()
        return

    f = pd.read_csv(inputfile, encoding='utf-8')
    print(f'  成功加载: {len(f)} 行')

    # ---- 2. 数据预处理 ----
    print('\n[2/5] 数据预处理...')
    data = pd.DataFrame()
    data['datetime'] = f['Local Date'] + ' ' + f[' Local Time']
    data['total_flow'] = f[' Total Carriageway Flow']
    data['datetime'] = pd.to_datetime(data['datetime'])
    data['hour'] = data['datetime'].dt.hour
    data['total_flow'] = data['total_flow'].astype(np.float64)

    flow_values = data['total_flow'].values
    print(f'  平均流量: {flow_values.mean():.2f}')
    print(f'  最大流量: {flow_values.max():.0f}')
    print(f'  最小流量: {flow_values.min():.0f}')
    print(f'  标准差:   {flow_values.std():.2f}')

    split_idx = int(len(data) * 0.8)
    train_data = data.iloc[:split_idx]
    test_data = data.iloc[split_idx:]
    print(f'  训练集: {len(train_data)} 条')
    print(f'  测试集: {len(test_data)} 条')

    # ---- 3. 特征工程 ----
    print('\n[3/5] 特征工程...')
    time_step = 5
    X_train, y_train = create_features(train_data, time_step)
    X_test, y_test = create_features(test_data, time_step)
    print(f'  滞后窗口: {time_step}')
    print(f'  训练样本: {len(X_train)}')
    print(f'  测试样本: {len(X_test)}')

    # ---- 4. 模型训练 ----
    print(f'\n[4/5] 模型训练（共{len(model_keys)}个模型）...')
    all_preds = {}
    all_metrics = {}
    scaler = None

    for key in model_keys:
        pred, metrics, scaler = train_single_model(
            key, X_train, y_train, X_test, y_test, scaler
        )
        all_preds[key] = pred
        all_metrics[key] = metrics

    # ---- 5. 保存结果 ----
    print('\n[5/5] 保存结果...')
    n_models = len(model_keys)

    # 5a. 预测对比图（每个模型一个子图 + 总对比图）
    print('  生成预测对比图...')
    n_plots = n_models + 1  # 各模型 + 总对比
    cols = 2
    rows = math.ceil(n_plots / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
    if rows == 1:
        axes = axes.reshape(1, -1)

    for idx, key in enumerate(model_keys):
        r, c = divmod(idx, cols)
        ax = axes[r][c]
        ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
        ax.plot(all_preds[key], color=MODEL_COLORS[key], linewidth=1.5,
                label=f'{MODEL_NAMES[key]}预测')
        ax.set_title(f'{MODEL_NAMES[key]} (R2={all_metrics[key]["r2"]:.4f})', fontsize=14)
        ax.set_xlabel('测试序列')
        ax.set_ylabel('流量/辆')
        ax.legend()
        ax.grid(True, alpha=0.3)

    # 总对比子图
    r_last, c_last = divmod(n_models, cols)
    ax_all = axes[r_last][c_last]
    ax_all.plot(y_test, color='red', linewidth=1.5, label='实际流量')
    for key in model_keys:
        ax_all.plot(all_preds[key], color=MODEL_COLORS[key], linewidth=1, alpha=0.7,
                    label=MODEL_NAMES[key])
    ax_all.set_title('所有模型预测对比', fontsize=14)
    ax_all.set_xlabel('测试序列')
    ax_all.set_ylabel('流量/辆')
    ax_all.legend()
    ax_all.grid(True, alpha=0.3)

    # 隐藏多余子图
    for idx in range(n_plots, rows * cols):
        r, c = divmod(idx, cols)
        axes[r][c].set_visible(False)

    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'simple_traffic_analysis_result.jpg'),
                dpi=200, bbox_inches='tight')
    plt.close()
    print('  已保存: simple_traffic_analysis_result.jpg')

    # 5b. 最佳模型单独对比图（pre.jpg）
    best_key = max(all_metrics, key=lambda k: all_metrics[k]['r2'])
    fig2, ax2 = plt.subplots(figsize=(15, 10))
    ax2.plot(y_test, label='实际流量 (Real_Flow)', color='r', linewidth=2)
    ax2.plot(all_preds[best_key], label=f'预测流量 ({MODEL_NAMES[best_key]})',
             color='b', linewidth=2)
    ax2.set_xlabel('测试序列', fontsize=15)
    ax2.set_ylabel('交通流量/辆', fontsize=15)
    ax2.set_title(f'{MODEL_NAMES[best_key]}交通流预测结果 (R2={all_metrics[best_key]["r2"]:.4f})',
                  fontsize=18)
    ax2.legend(fontsize=12)
    ax2.grid(True, alpha=0.3)

    import shutil
    pre_path = os.path.join(BASE_DIR, 'pre.jpg')
    plt.savefig(pre_path, dpi=300, bbox_inches='tight')
    plt.close()
    shutil.copy2(pre_path, os.path.join(CHARTS_DIR, 'pre.jpg'))
    print('  已保存: pre.jpg')

    # 5c. 24小时交通模式图
    print('  生成24小时交通模式图...')
    hourly = data.groupby('hour')['total_flow'].agg(['mean', 'std', 'max', 'min'])
    fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(12, 8))
    ax3a.plot(hourly.index, hourly['mean'], 'b-o', linewidth=2, markersize=6, label='平均流量')
    ax3a.fill_between(hourly.index, hourly['mean'] - hourly['std'],
                       hourly['mean'] + hourly['std'], alpha=0.2, color='blue', label='±1标准差')
    ax3a.set_title('24小时交通流量模式', fontsize=14)
    ax3a.set_xlabel('小时')
    ax3a.set_ylabel('流量/辆')
    ax3a.legend()
    ax3a.grid(True, alpha=0.3)
    ax3a.set_xticks(range(24))
    ax3b.bar(hourly.index, hourly['max'] - hourly['min'], color='steelblue', alpha=0.7)
    ax3b.set_title('各小时流量变化幅度', fontsize=14)
    ax3b.set_xlabel('小时')
    ax3b.set_ylabel('变化幅度')
    ax3b.grid(True, alpha=0.3)
    ax3b.set_xticks(range(24))
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'hourly_traffic_pattern.jpg'), dpi=200, bbox_inches='tight')
    plt.close()
    print('  已保存: hourly_traffic_pattern.jpg')

    # 5d. 保存结果数据
    results = {
        'avg_flow': f'{flow_values.mean():.2f}',
        'max_flow': f'{flow_values.max():.0f}',
        'min_flow': f'{flow_values.min():.0f}',
        'std_flow': f'{flow_values.std():.2f}',
        'train_size': str(len(X_train)),
        'test_size': str(len(X_test)),
        'models': ','.join(model_keys),
    }
    for key in model_keys:
        m = all_metrics[key]
        results[f'{key}_r2'] = f'{m["r2"]:.4f}'
        results[f'{key}_rmse'] = f'{m["rmse"]:.2f}'
        results[f'{key}_mae'] = f'{m["mae"]:.2f}'
    results['best_model'] = best_key

    results_file = os.path.join(CHARTS_DIR, 'results.txt')
    with open(results_file, 'w', encoding='utf-8') as fout:
        for k, v in results.items():
            fout.write(f'{k}={v}\n')
    print('  已保存: results.txt')

    # 5e. 生成实验报告
    report_file = os.path.join(CHARTS_DIR, '实验报告.txt')
    with open(report_file, 'w', encoding='utf-8') as fout:
        fout.write('交通流预测实验报告\n')
        fout.write('=' * 50 + '\n\n')
        fout.write('一、数据概况\n')
        fout.write(f'  数据记录数: {len(data)}\n')
        fout.write(f'  平均流量: {flow_values.mean():.2f} 辆/时段\n')
        fout.write(f'  最大流量: {flow_values.max():.0f} 辆/时段\n')
        fout.write(f'  最小流量: {flow_values.min():.0f} 辆/时段\n')
        fout.write(f'  标准差: {flow_values.std():.2f}\n\n')
        fout.write('二、模型训练\n')
        fout.write(f'  算法框架: scikit-learn\n')
        fout.write(f'  滞后窗口: {time_step}\n')
        fout.write(f'  训练集大小: {len(X_train)}\n')
        fout.write(f'  测试集大小: {len(X_test)}\n')
        fout.write(f'  训练模型: {model_labels}\n\n')
        fout.write('三、预测结果\n')
        for key in model_keys:
            m = all_metrics[key]
            fout.write(f'  {MODEL_NAMES[key]}:\n')
            fout.write(f'    R2 = {m["r2"]:.4f}\n')
            fout.write(f'    RMSE = {m["rmse"]:.2f}\n')
            fout.write(f'    MAE = {m["mae"]:.2f}\n')
            fout.write(f'    训练耗时: {m["time"]:.2f}s\n')
        fout.write(f'\n四、结论\n')
        fout.write(f'  {MODEL_NAMES[best_key]}模型表现最优，R2={all_metrics[best_key]["r2"]:.4f}。\n')
    print('  已保存: 实验报告.txt')

    print('\n' + '=' * 60)
    print('  预测分析完成！')
    for key in model_keys:
        print(f'  {MODEL_NAMES[key]} R2: {all_metrics[key]["r2"]:.4f}')
    print(f'  最佳模型: {MODEL_NAMES[best_key]}')
    print('=' * 60)
    print('\n完成，可以关闭此窗口。')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('\n' + '=' * 60)
        print(f'  运行出错: {e}')
        print('=' * 60)
        traceback.print_exc()
        pause_if_interactive('\n按回车键退出...')
