# 智信优控 云端管理平台 — 现状分析与修复计划

## 一、项目概述

| 项 | 值 |
|---|---|
| 前端 | Vue 3 + Element Plus + ECharts + Pinia + Vue Router (Hash) |
| 后端 | FastAPI + SQLAlchemy 2.0 (SQLite dev / PostgreSQL prod) |
| 认证 | JWT (access + refresh token)，bcrypt 密码哈希 |
| 部署 | GitHub Pages (前端) + IPv6 HTTPS (后端) + Docker Compose |

## 二、已完成功能

### 管理员模块 (Admin)
- [x] 登录 / 登出 / Token 刷新
- [x] Dashboard 概览 (机构数、License 数、活跃 License)
- [x] 机构管理 CRUD + 详情页
- [x] License 管理 (生成 / 吊销 / 列表)
- [x] 用户管理 (创建 / 重置密码 / CSV 导入)
- [x] 统计分析 (概览 / 趋势图 / 模块排名)
- [x] 版本更新管理 (发布 / 列表)

### 教师模块 (Teacher)
- [x] 教师自助注册 (自动分配账号)
- [x] 教学任务管理 (创建 / 列表)
- [x] 实验报告管理 (列表 / 批阅)
- [x] 学生列表查看
- [x] 教学统计 (统计卡片 + 图表)
- [x] 修改密码

### 后端 API
- [x] License 激活 / 验证 (HMAC-SHA256 签名)
- [x] 数据同步 API (供 Local_Client 调用)
- [x] 使用数据上报 API
- [x] 版本更新检查 API

### 基础设施
- [x] GitHub Actions 自动部署前端
- [x] Docker Compose 配置
- [x] 后端测试 (auth / orgs / licenses / properties)

## 三、存在的 BUG（需立即修复）

### BUG-1: 前端-后端 API 数据格式不匹配 [严重]
后端所有列表接口统一返回 `PagedResponse { items, total, page, page_size, pages }`，
但教师模块多个页面直接将 `response.data` 当作数组使用，导致页面无数据。

| 文件 | 问题 |
|---|---|
| `TeacherTasks.vue` | `tasks.value = data` 应为 `data.items` |
| `TeacherReports.vue` | `reports.value = data` 应为 `data.items` |
| `TeacherStudents.vue` | `students.value = data` 应为 `data.items` |
| `TeacherAnalytics.vue` | 同上，从 tasks/reports 取数据格式错 |

### BUG-2: 统计分析页 API 调用错误 [严重]
- `AnalyticsView.vue` 调用 `/api/cloud/analytics/trends` 不带 `start`/`end` 参数，后端要求这两个参数为必填 → 422 错误
- `AnalyticsView.vue` 将响应 `data` 直接 `.map()`，但后端返回 `{ data: [...] }` 格式
- `AnalyticsView.vue` 映射字段 `d.date` / `d.active_users` / `d.experiments` 与后端 `report_date` / `active_users` / `experiment_count` 不匹配
- `/api/cloud/analytics/modules` 响应中用 `module_id` / `total_count`，前端用 `module_id` / `count`

### BUG-3: 无初始管理员账号 [严重]
数据库首次创建后为空，没有 seed 脚本创建 `super_admin` 账号，导致无法登录。

### BUG-4: Dashboard 缺少 total_users [轻微]
前端 Dashboard 显示"总用户数"，但后端 `/api/cloud/admin/dashboard` 未返回 `total_users` 字段。

### BUG-5: TeacherReports 批阅字段不匹配 [轻微]
`TeacherReports.vue` 发送 `{ score, comment }` 批阅，但后端 `GradeRequest` schema 字段是 `{ score, feedback }`。

## 四、缺失功能

### 缺失-1: 管理员任务/报告管理路由未注册
`views/Tasks/TaskList.vue` 和 `views/Reports/ReportList.vue` 已实现但**未注册到路由**，
管理员侧边栏也没有对应菜单项。

### 缺失-2: 角色路由守卫
当前仅在登录页做简单角色判断，无全局路由守卫阻止管理员访问教师页面或反之。

### 缺失-3: TeacherAnalytics 图表用硬编码数据
近期任务完成情况图表使用 `[3,5,8,12,7,2,1]` 硬编码数据，未对接后端真实数据。

### 缺失-4: 无 README.md
项目缺少 README 文档。

### 缺失-5: pydantic-settings 缺失
`requirements.txt` 中没有 `pydantic-settings`，但 `config.py` 使用了 `from pydantic_settings import BaseSettings`。

## 五、修复计划（按优先级）

| # | 优先级 | 任务 | 涉及文件 |
|---|--------|------|----------|
| 1 | P0 | 添加 DB seed 脚本创建 super_admin | `backend/app/seed.py` + `backend/app/main.py` |
| 2 | P0 | 修复教师模块 PagedResponse 解析 | `TeacherTasks.vue`, `TeacherReports.vue`, `TeacherStudents.vue`, `TeacherAnalytics.vue` |
| 3 | P0 | 修复统计分析页 API 调用 | `AnalyticsView.vue` |
| 4 | P1 | 修复 TeacherReports 批阅字段 | `TeacherReports.vue` |
| 5 | P1 | Dashboard 补充 total_users | `backend/app/routers/admin.py` |
| 6 | P1 | 注册管理员任务/报告路由 + 侧边栏 | `router/index.js`, `AdminLayout.vue` |
| 7 | P2 | 添加角色路由守卫 | `router/index.js` |
| 8 | P2 | TeacherAnalytics 对接真实数据 | `TeacherAnalytics.vue` |
| 9 | P2 | 补充 pydantic-settings 到 requirements.txt | `requirements.txt` |
