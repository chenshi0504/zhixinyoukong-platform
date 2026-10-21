# 智信优控 · 面向车路云一体化的综合交通实验平台

> Zhixin Youkong — Integrated Traffic Experiment Platform for Vehicle-Road-Cloud Integration

面向交通工程、智慧交通、管理科学与工程专业的**教学科研一体化实验平台**：把「数据采集 → 融合 → 重构 → 预测 → 信号优化 → 路径诱导 → 车速控制 → 三层级协同 → 虚实结合仿真」整条链路装进一套可在普通机房运行的软件里。

- 本地桌面端：Windows 一键安装，离线可用（FastAPI + PyWebView + SQLite）
- 云端管理端：教师远程发布任务、评阅报告、查看统计（Vue 3 + FastAPI + PostgreSQL）
- 硬件在环：MQTT/ROS 接入真实智能小车与校园点云地图，仿真算法可上车验证

---

## 一、功能模块

| # | 模块 | 核心算法 / 工具 | 教学用途 |
|---|------|------------------|----------|
| 1 | 多源数据采集 | YOLO11 目标检测与跟踪 | 视频车辆检测、分车型流量统计、精度比对 |
| 2 | 多源数据融合 | 贝叶斯决策级融合 | 视频置信度与点云熵融合，量化融合增益 |
| 3 | 交通流重构 | DTALite 动态分配、转向流量 OD 反推 | 由有限观测重建路网 OD 与流量分布 |
| 4 | 交通流预测 | 线性回归、随机森林、决策树、LSTM、GRU | 短时流量预测与多模型对比 |
| 5 | 交通信号优化 | Webster、HCM、BO、TuRBO、MPC-TuRBO、GA、PSO、DQN、PPO | 配时方案优化与延误对比 |
| 6 | 路径诱导 | Dijkstra、A*、Floyd、SSP | 动态路阻下的路径规划与诱导 |
| 7 | 车速控制 | PID、MPC、ACC、CACC、IDM | 跟踪误差与舒适性权衡 |
| 8 | 三层级协同优化 | 信号 + 路径 + 速度联合优化 | 单层 / 双层 / 三层效果定量对比 |
| 9 | 虚实结合仿真 | SUMO、CARLA、MQTT/ROS | 场景构建、算法测试、实车回环 |
| 10 | 教学管理 | 任务发布、报告评阅、学生管理 | 教学过程留痕与过程性评价 |

## 二、目录结构

```
.
├── backend/                 # FastAPI 主后端（端口 8000）
│   ├── app/                 # 路由、模型、服务
│   ├── algorithms/          # 各算法模块（不含权重与样本数据）
│   ├── data/                # 初始化数据
│   ├── knowledge_base/      # 实验助手知识库素材
│   ├── tests/               # 自动化测试
│   ├── requirements.txt
│   └── run.py               # 一键启动（含算法子服务）
├── frontend/                # 本地前端（原生 HTML/CSS/JS）
│   ├── index.html / student.html / teacher.html / admin.html
│   └── src/pages/           # 各功能页面
├── cloud/                   # 云端管理平台（端口 9000）
│   ├── backend/  frontend/  nginx/  docker-compose.yml
├── docker/                  # 打包与容器构建脚本
├── docs/                    # 安装/教师/学生手册、API、架构、教材
├── scripts/                  # 启动脚本
├── site/                    # GitHub Pages 静态站点
└── 启动平台前后端.bat        # Windows 一键启动
```

## 三、快速开始

### 3.1 Windows（推荐）

1. 安装 Python 3.10+（勾选 Add to PATH）
2. 双击 `启动平台前后端.bat`
3. 浏览器访问 <http://localhost:8000>

### 3.2 手动启动

```bash
cd backend
pip install -r requirements.txt
python run.py
```

启动后自动初始化数据库、拉起算法子服务（数据融合 5000、交通流重构 5001、交通流预测 5002、数据采集 5003），主平台监听 8000。

### 3.3 云端管理端

```bash
cd cloud
cp .env.example .env          # 修改 DATABASE_URL / SECRET_KEY
docker compose up -d          # Nginx:80 → API:9000 → PostgreSQL
```

### 3.4 外部依赖

| 依赖 | 版本 | 必需性 | 说明 |
|------|------|--------|------|
| Python | 3.10+ | 必需 | 后端与算法 |
| SUMO | 1.21+ | 信号/路径/车速/协同实验必需 | 设置 `SUMO_HOME` |
| CARLA | 0.9.15 | 虚实结合仿真必需 | 需 NVIDIA 显卡（显存 ≥ 4 GB） |
| DTALite | 随包提供 | 交通流重构 | 见 `backend/algorithms/traffic_reconstruction` |

> 本仓库不含模型权重（`*.pt`、`*.weights`）、点云样本（`*.pcd`）与大体量结果数据，首次运行检测类实验时请按 `docs/install` 中的说明自行下载权重并放入对应目录。

## 四、默认账号与安全

| 角色 | 账号 | 初始密码 |
|------|------|----------|
| 管理员 | admin | 123456 |
| 教师 | teacher | 123456 |
| 学生 | student | 123456 |

**部署到公网前必须修改默认口令，并设置强 `SECRET_KEY`**；`backend/.env`、`config.local.env` 等含密钥的文件已在 `.gitignore` 中排除，请不要提交。

## 五、文档

| 文档 | 路径 |
|------|------|
| 安装手册 | `docs/user-guide/安装手册.md` |
| 教师使用手册 | `docs/user-guide/教师使用手册.md` |
| 学生使用手册 | `docs/user-guide/学生使用手册.md` |
| API 接口说明 | `docs/api/API接口说明文档.md` |
| 平台架构与云端定位 | `docs/development/平台定位与架构设计.md` |
| 学生自研算法题包 | `docs/development/学生自研算法能力设计.md` |
| 硬件在环平台说明 | `docs/hil.md` |
| 配套教材（7 章 + 附录） | `docs/textbook/` |

在线文档站：`https://<你的用户名>.github.io/<仓库名>/`（部署 Pages 后生效，见 `PUBLISH.md`）。

## 六、部署到公网

GitHub 只能托管**代码与静态站点**，无法运行 FastAPI / SUMO / CARLA。若要在公网「打开即用」，需要一台服务器或容器平台：

- 云端管理端（轻量，可公网运行）：见 `deploy/README.md`，支持 Docker Compose、Render、Railway、VPS
- 本地仿真平台（重，依赖 SUMO/CARLA/GPU）：建议部署在校内服务器或 GPU 工作站，通过内网/VPN 访问

## 七、许可与引用

源码版权归大连理工大学智慧交通团队所有。教学、科研使用请注明出处；商业使用需书面授权，详见 `LICENSE`。

若在论文或报告中引用本平台，建议注明：

> 智信优控：面向车路云一体化的综合交通实验平台，大连理工大学经济管理学院智慧交通研究院。

## 八、联系

- 维护：大连理工大学智慧交通团队
- 邮箱：chenshi_edu@gmail.com
- 问题反馈：GitHub Issues
