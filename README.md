# 智信优控 - 面向车路云一体化的综合交通实验平台

## 核心目标

**能用。** 平台的首要目标是每个功能模块都能实际运行，结果导向，用最简单的方法达到目的。

## 快速启动

### 方法一：一键启动（推荐）

双击项目根目录的 `启动平台前后端.bat`

### 方法二：手动启动

```bash
cd backend
python run.py
```

如需自定义端口、云端地址等配置，可先复制：

```bash
copy backend\.env.example backend\.env
copy cloud\.env.example cloud\.env
```

启动后自动：
- 初始化数据库
- 启动算法子服务（数据融合5000、交通流重构5001、交通流预测5002、数据采集5003）
- 启动主平台后端 http://localhost:8000
- 自动打开浏览器登录页

## 环境配置

| 项目 | 默认值 | 说明 |
|------|--------|------|
| 本地平台端口 | `8000` | 由 `backend/.env` 中的 `LOCAL_APP_PORT` 控制 |
| 云端平台端口 | `9000` | 由 `cloud/.env` 中的 `CLOUD_APP_PORT` 控制 |
| 本地连接云端 | `http://localhost:9000` | 由 `backend/.env` 中的 `CLOUD_API_URL` 控制 |
| Python 解释器 | `python` | 批处理脚本默认读取 `ZXK_PYTHON_EXE`，未设置时回退到系统 `python` |

本地平台配置模板：`backend/.env.example`

云端平台配置模板：`cloud/.env.example`

## 功能模块状态

| 模块 | 页面 | 后端API | 仿真运行 |
|------|------|---------|----------|
| 多源数据采集 (YOLOv8/YOLO11) | ✅ | ✅ /api/collection/ | ✅ cmd窗口 |
| 多源数据融合 (贝叶斯) | ✅ | ✅ 端口5000 | ✅ |
| 交通流重构 (DTALite) | ✅ | ✅ /api/reconstruction/ | ✅ cmd窗口 |
| 交通流预测 | ✅ | ✅ 端口5002 | ✅ |
| 交通信号优化 (TuRBO/BO/DQN/PPO/GA/PSO) | ✅ | ✅ /api/signal-opt/ | ✅ sumo-gui |
| 路径诱导 (Dijkstra/SSP/A*) | ✅ | ✅ /api/path-guidance/ | ✅ sumo-gui |
| 车速控制 (IDM/ACC/CACC/PID) | ✅ | ✅ /api/vehicle-speed/ | ✅ sumo-gui |
| 三层级协同优化控制 | ✅ | ✅ /api/three-level/ | ✅ sumo-gui |
| 虚实结合仿真场景构建 (CARLA) | ✅ | ✅ /api/carla-sim/ | ✅ CARLA+SUMO |
| 车规级智能车辆开发与控制 | ✅ | ✅ /api/vehicle-dev/ | 待接入 |

## 默认账户

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | 123456 | 管理员 |
| teacher | 123456 | 教师 |
| student | 123456 | 学生 |

> 本地平台默认账号统一为 `admin / teacher / student`，默认密码统一为 `123456`。

## 开发约定

- 所有蓝色统一使用 `#2C5AA0`，hover `#1e3d72`
- 仿真通过 `start "Title" cmd /k` 在独立窗口运行，标题用英文
- SUMO 仿真统一使用 `sumo-gui`，加 `--no-warnings`
- 流量等级：界面显示 1/2/3（低/中/高），内部值 2/4/6
- DQN/PPO 算法标注 `[需预热]`
- CAV 渗透率可选 20%/40%/60%/80%，采纳率 80%-100%
- 自定义算法在独立 cmd 窗口运行

## 目录结构

```
├── frontend/                    # 前端页面
│   ├── src/pages/               # 各功能模块页面
│   ├── student.html             # 学生实验中心
│   ├── teacher.html             # 教师管理页
│   └── admin.html               # 管理员页
├── backend/
│   ├── app/                     # FastAPI 主后端 (端口8000)
│   │   ├── main.py              # 应用入口 + 路由注册
│   │   └── routers/             # API 路由模块
│   ├── algorithms/              # 算法实现
│   │   ├── signal_optimization/ # 信号优化 (SUMO)
│   │   ├── path_guidance/       # 路径诱导 (SUMO)
│   │   ├── vehicle_speed_control/ # 车速控制 (SUMO+TraCI)
│   │   ├── three_level_control/ # 三层级协同
│   │   ├── data_collection/     # 数据采集 (YOLO)
│   │   ├── carla_simulation/    # CARLA仿真
│   │   └── ...
│   ├── run.py                   # 一键启动脚本
│   └── requirements.txt
└── 启动平台前后端.bat            # 双击启动
```

## 许可证

Copyright © 2024 大连理工大学
