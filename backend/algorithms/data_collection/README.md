# 数据采集模块

## 模块简介
基于YOLO11的实时目标检测和跟踪系统，用于采集交通场景中的车辆、行人等目标数据。

## 算法原理
- **目标检测**: 使用YOLO11深度学习模型进行实时目标检测
- **目标跟踪**: 采用ByteTrack算法进行多目标跟踪
- **数据融合**: 结合视频流和点云数据进行多源数据融合

## 主要功能
- 实时视频流目标检测
- 多目标跟踪和轨迹记录
- 检测结果可视化
- 数据导出（JSON/CSV格式）

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| video_source | str | 0 | 视频源（摄像头ID或视频文件路径） |
| model_path | str | yolo11n.pt | YOLO模型路径 |
| conf_threshold | float | 0.25 | 置信度阈值 |
| iou_threshold | float | 0.45 | NMS的IoU阈值 |
| track_buffer | int | 30 | 跟踪缓冲帧数 |

### 运行示例

**通过Web界面运行**:
1. 在实验平台选择"数据采集"模块
2. 配置视频源和检测参数
3. 点击"开始采集"按钮

**通过命令行运行**:
```bash
cd backend/algorithms/data_collection
python detector/yolo11_tracker.py --source 0 --conf 0.25
```

### API调用
```python
import requests

# 启动数据采集服务
response = requests.post('http://localhost:5000/start', json={
    'video_source': 0,
    'conf_threshold': 0.25
})

# 获取检测结果
results = requests.get('http://localhost:5000/results')
```

## 输出结果
- **检测结果JSON**: `output/detection_results_{timestamp}.json`
  - 包含每帧的检测框、类别、置信度、跟踪ID
- **轨迹数据CSV**: `output/trajectories_{timestamp}.csv`
  - 包含目标ID、时间戳、位置、速度等信息
- **可视化视频**: `output/detection_video_{timestamp}.mp4`
  - 带检测框和跟踪ID的可视化视频

## 依赖环境
- Python 3.10
- PyTorch 2.0+
- ultralytics (YOLO11)
- opencv-python
- numpy

## 常见问题

### 1. 摄像头无法打开
**问题**: 提示"无法打开视频源"
**解决方案**: 
- 检查摄像头是否被其他程序占用
- 尝试更换video_source参数（0, 1, 2等）
- 确认摄像头驱动已正确安装

### 2. 检测速度慢
**问题**: FPS低于10
**解决方案**:
- 使用更小的模型（yolo11n.pt而非yolo11x.pt）
- 降低输入分辨率
- 确保使用GPU加速（CUDA可用）

### 3. 检测精度不足
**问题**: 漏检或误检较多
**解决方案**:
- 降低conf_threshold阈值（如0.15）
- 使用更大的模型（yolo11m.pt或yolo11l.pt）
- 针对特定场景微调模型

## 技术细节

### YOLO11模型
- **输入**: 640×640 RGB图像
- **输出**: 检测框 [x, y, w, h, conf, class]
- **类别**: 支持80类COCO数据集目标

### ByteTrack跟踪算法
- 基于卡尔曼滤波的运动预测
- 两阶段数据关联（高分检测 + 低分检测）
- 自适应跟踪缓冲区

## 参考文献
1. YOLO11: https://github.com/ultralytics/ultralytics
2. ByteTrack: https://arxiv.org/abs/2110.06864
