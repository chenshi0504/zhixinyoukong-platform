# 算法模块

专业化的交通算法模块，采用统一的架构和接口设计。

## 模块结构

```
algorithms/
├── common/                          # 公共组件
│   ├── base_service.py              # 基础服务类
│   ├── config.py                    # 配置管理
│   ├── utils.py                     # 工具函数
│   ├── exceptions.py                # 异常定义
│   └── logger.py                    # 日志配置
│
├── data_collection/                 # 多源数据采集
├── data_fusion/                     # 多源数据融合
├── traffic_reconstruction/          # 交通流重构
├── traffic_prediction/              # 交通流预测
├── signal_optimization/             # 交通信号优化
├── path_guidance/                   # 路径诱导
├── speed_control/                   # 车速控制
├── hierarchical_control/            # 三层级协同控制
└── simulation/                      # 虚实结合仿真
```

## 模块说明

### 1. data_collection - 多源数据采集
- **功能**：基于机器视觉的交通流数据采集
- **核心文件**：
  - `collector.py` - 数据采集主程序
  - `detector/` - YOLOv4 车辆检测模块
  - `report_generator.py` - 报告生成

### 2. data_fusion - 多源数据融合
- **功能**：基于贝叶斯方法的多源数据融合
- **核心文件**：
  - `service.py` - 融合服务
  - `bayesian_fusion.py` - 贝叶斯融合算法

### 3. traffic_reconstruction - 交通流重构
- **功能**：基于多源数据的 OD 矩阵估计
- **核心文件**：
  - `service.py` - 重构服务
  - `visualizer.py` - OD 可视化
  - `report_generator.py` - 报告生成

### 4. traffic_prediction - 交通流预测
- **功能**：基于机器学习的交通流预测
- **核心文件**：
  - `service.py` - 预测服务
  - `predictor.py` - 预测模型
  - `report_generator.py` - 报告生成

### 5. signal_optimization - 交通信号优化
- **功能**：交通信号配时优化
- **支持算法**：Webster, HCM, TuRBO, MPC-TuRBO
- **核心文件**：
  - `config_generator.py` - 配置生成
  - `visualizer.py` - 结果可视化

### 6. path_guidance - 路径诱导
- **功能**：最优路径规划
- **支持算法**：Dijkstra, A*, Floyd
- **核心文件**：
  - `config_generator.py` - 配置生成
  - `visualizer.py` - 路径可视化

### 7. speed_control - 车速控制
- **功能**：智能车速控制
- **支持算法**：PID, MPC, ACC
- **核心文件**：
  - `config_generator.py` - 配置生成
  - `visualizer.py` - 控制效果可视化

### 8. hierarchical_control - 三层级协同控制
- **功能**：信号-路径-速度三层级协同优化
- **核心文件**：
  - `service.py` - 协同控制服务
  - `turbo/` - TuRBO 优化算法
  - `config_generator.py` - 配置生成

### 9. simulation - 虚实结合仿真
- **功能**：基于 SUMO 的交通仿真
- **核心文件**：
  - `service.py` - 仿真服务
  - `sumo_simulation/` - SUMO 接口

## 统一接口

所有算法模块都继承自 `BaseAlgorithmService`，提供统一的接口：

```python
from algorithms.common import BaseAlgorithmService

class MyAlgorithmService(BaseAlgorithmService):
    def __init__(self, config):
        super().__init__("my_algorithm", config)
    
    def process(self, data):
        # 实现算法逻辑
        return result

# 启动服务
service = MyAlgorithmService(config)
service.start(host='0.0.0.0', port=8001)
```

## API 端点

每个服务都提供以下标准端点：

- `GET /health` - 健康检查
- `POST /process` - 处理数据
- `GET /config` - 获取配置

## 配置管理

使用 `ConfigManager` 统一管理配置：

```python
from algorithms.common import ConfigManager

config = ConfigManager('config/service.yaml')
host = config.get('service.host', '0.0.0.0')
port = config.get('service.port', 8000)
```

## 日志管理

使用 `setup_logger` 配置日志：

```python
from algorithms.common import setup_logger

logger = setup_logger(
    name='my_service',
    level='INFO',
    log_file='logs/service.log'
)
```

## 开发规范

### 目录结构
每个模块应包含：
- `__init__.py` - 模块初始化
- `service.py` - 服务入口
- `config/` - 配置文件
- `data/` - 数据文件
- `tests/` - 测试文件

### 命名规范
- 模块名：小写+下划线（如 `data_collection`）
- 类名：大驼峰（如 `DataCollector`）
- 函数名：小写+下划线（如 `process_data`）
- 常量：大写+下划线（如 `MAX_SIZE`）

### 代码风格
- 遵循 PEP 8 规范
- 使用类型注解
- 编写文档字符串
- 添加单元测试

## 测试

运行所有测试：
```bash
pytest algorithms/
```

运行特定模块测试：
```bash
pytest algorithms/data_collection/tests/
```

## 部署

每个模块可以独立部署为微服务：

```bash
# 启动数据采集服务
python -m algorithms.data_collection.service

# 启动交通流预测服务
python -m algorithms.traffic_prediction.service
```

## 依赖

核心依赖：
- Flask - Web 服务框架
- NumPy - 数值计算
- Pandas - 数据处理
- PyYAML - 配置文件解析

各模块特定依赖见各自的 `requirements.txt`。
