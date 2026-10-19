# CARLA仿真模块

## 模块简介
基于CARLA的高保真自动驾驶仿真系统，提供真实的3D环境、物理引擎和传感器模拟。

## 算法原理

### CARLA仿真器
- 基于虚幻引擎4
- 高精度物理仿真
- 多种传感器模拟（相机、激光雷达、雷达）
- 支持多车协同仿真

### 场景配置
- 自定义地图和路网
- 天气和光照条件
- 交通流生成
- 行人和障碍物

## 主要功能
- 自动驾驶算法测试
- 传感器数据采集
- 场景回放和分析
- 多车协同仿真
- 车路协同测试

## 使用方法

### 参数说明
| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| map_name | str | Town01 | 地图名称 |
| num_vehicles | int | 50 | 车辆数量 |
| weather | str | ClearNoon | 天气条件 |
| sensors | list | [camera] | 传感器列表 |
| sync_mode | bool | true | 同步模式 |

### 运行示例
```bash
# 启动CARLA服务器
./CarlaUE4.sh -quality-level=Low

# 运行仿真场景
cd backend/algorithms/carla_simulation
python run_carla_scene.py --map Town01 --vehicles 50
```

### API调用
```python
import carla

# 连接CARLA服务器
client = carla.Client('localhost', 2000)
world = client.get_world()

# 生成车辆
blueprint = world.get_blueprint_library().find('vehicle.tesla.model3')
spawn_point = world.get_map().get_spawn_points()[0]
vehicle = world.spawn_actor(blueprint, spawn_point)
```

## 输出结果
- **传感器数据**: `output/sensor_data_{timestamp}/`
  - 相机图像、点云数据、雷达数据
- **轨迹记录**: `output/trajectory_{timestamp}.csv`
- **仿真视频**: `output/simulation_{timestamp}.mp4`

## 性能指标
- **碰撞次数**: 仿真过程中的碰撞事件
- **平均速度**: 车辆平均行驶速度
- **任务完成率**: 成功完成任务的比例

## 依赖环境
- CARLA 0.9.13+
- Python 3.7+
- pygame (可视化)
- numpy, opencv-python

## 常见问题

### 1. 无法连接CARLA服务器
**问题**: 提示"Connection refused"
**解决方案**:
- 确认CARLA服务器已启动
- 检查端口2000是否开放
- 尝试使用`client.set_timeout(10.0)`增加超时时间

### 2. 帧率过低
**问题**: 仿真运行卡顿
**解决方案**:
- 降低画质设置（-quality-level=Low）
- 减少车辆数量
- 关闭不必要的传感器
- 使用异步模式

### 3. 车辆生成失败
**问题**: 提示"Spawn failed"
**解决方案**:
- 检查生成点是否被占用
- 尝试其他生成点
- 增加生成重试次数

## 技术细节

### 同步模式设置
```python
# 启用同步模式
settings = world.get_settings()
settings.synchronous_mode = True
settings.fixed_delta_seconds = 0.05  # 20 FPS
world.apply_settings(settings)
```

### 传感器配置
```python
# 添加RGB相机
camera_bp = world.get_blueprint_library().find('sensor.camera.rgb')
camera_bp.set_attribute('image_size_x', '1920')
camera_bp.set_attribute('image_size_y', '1080')
camera_bp.set_attribute('fov', '110')

camera = world.spawn_actor(camera_bp, 
                          carla.Transform(carla.Location(x=1.5, z=2.4)),
                          attach_to=vehicle)
```

### 自动驾驶控制
```python
# 启用自动驾驶
vehicle.set_autopilot(True)

# 手动控制
control = carla.VehicleControl()
control.throttle = 0.5
control.steer = 0.0
vehicle.apply_control(control)
```

## 实验建议

### 基础实验
1. 熟悉CARLA基本操作和API
2. 生成车辆并控制移动
3. 配置传感器并采集数据
4. 测试不同天气和光照条件

### 进阶实验
1. 实现自动驾驶算法（车道保持、跟车）
2. 多车协同仿真
3. 传感器融合算法测试
4. 车路协同场景搭建

## 参考文献
1. CARLA官方文档: https://carla.readthedocs.io/
2. Dosovitskiy, A., et al., "CARLA: An Open Urban Driving Simulator", 2017
3. 虚幻引擎: https://www.unrealengine.com/
