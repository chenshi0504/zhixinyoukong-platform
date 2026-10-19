# 综合交通实验教学平台 - 后端服务

基于 FastAPI + SQLite 的教学管理后端，提供用户认证、任务管理、报告提交批阅、实验记录等功能。

## 快速启动

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 可选：复制配置模板
copy .env.example .env

# 启动服务（自动初始化数据库）
python run.py
```

服务启动后访问:
- API文档: http://localhost:8000/api/docs
- 健康检查: http://localhost:8000/api/v1/health

## 默认账户

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | 123456 | 管理员 |
| teacher | 123456 | 教师 |
| student | 123456 | 学生 |

## API 概览

| 模块 | 路径前缀 | 说明 |
|------|---------|------|
| 认证 | `/api/v1/auth` | 登录、登出、获取当前用户 |
| 用户 | `/api/v1/users` | 用户CRUD、批量导入、密码重置 |
| 任务 | `/api/v1/tasks` | 任务创建、发布、关闭 |
| 报告 | `/api/v1/reports` | 报告提交、批阅、下载 |
| 实验 | `/api/v1/experiments` | 实验开始、操作记录、完成 |
| 健康 | `/api/v1/health` | 服务状态检查 |

## 运行测试

```bash
cd backend
python -m pytest tests/ -v
```

## 项目结构

```
backend/
├── app/
│   ├── main.py          # FastAPI 应用入口
│   ├── config.py        # 配置管理
│   ├── database.py      # 数据库连接
│   ├── dependencies.py  # 权限依赖
│   ├── init_db.py       # 数据库初始化
│   ├── models/          # SQLAlchemy 模型
│   ├── schemas/         # Pydantic 模式
│   ├── routers/         # API 路由
│   └── services/        # 业务逻辑
├── tests/               # 测试文件
├── run.py               # 启动脚本
└── requirements.txt     # 依赖列表
```
