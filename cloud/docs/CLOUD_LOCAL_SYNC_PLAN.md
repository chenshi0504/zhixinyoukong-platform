# 云端平台（Cloud）与本地安装包（Local Installer）沟通开发计划方案

## 1. 目标与边界

### 1.1 总目标
实现“教师端发布任务 → 学生端/本地端获知并接收任务 → 本地端提交报告/结果 → 云端可批阅与统计”的闭环。

### 1.2 当前阶段边界（先做什么）
- **先确保本地安装包可安装、可启动、无权限错误（WinError 5 / PermissionError）**。
- 在本地可稳定运行后，再进行 Cloud ↔ Local 的联调。

### 1.3 关键角色
- **Cloud 管理平台**：组织/账号/License 管理、云端任务/报告/统计、版本更新。
- **Local Installer 平台**：实验执行环境（算法/仿真/数据采集等）、本地学生/教师使用入口、离线可用。
- **Local_Client 同步模块**：负责将本地事件/数据上报云端，并从云端拉取任务/指令。


## 2. 业务场景拆解（教师发布任务、学生获知）

### 2.1 组织/班级/用户归属原则
为实现“同一个班级内发布指令”，需要最小可行的数据归属：
- **机构（Organization）**：如“大连理工大学”。
- **机构内用户（User.org_id）**：教师、学生必须归属同一 `org_id`。

> 说明：Cloud 现有模型有 `Organization`、`User`、`Task.org_id`、`Report.task_id/student_id`，**但没有“班级/课程/班级成员关系”**。

### 2.2 MVP 方案（先跑通）
先以“**机构 org_id**”代替班级范围：
- 教师发布任务时，任务带 `org_id = teacher.org_id`
- 学生端拉取任务时，按 `org_id = student.org_id` 过滤

后续迭代再引入班级维度：
- 新增 `Class` 表（学院/专业/年级/班级编码）
- 新增 `User.class_id` 或 `Enrollment(user_id, class_id)`
- `Task.class_id`（可选）实现“按班级发布”


## 3. 通信架构选型

### 3.1 推荐：HTTP 拉取 + 增量同步（现有基础上扩展）
Cloud 后端已经存在：
- `/api/cloud/sync/tasks`：按 `org_id` + `since` 拉取任务
- `/api/cloud/sync/users`：按 `org_id` + `since` 拉取用户
- `/api/cloud/sync/grades`：按 `student_id` + `since` 拉取成绩

优点：
- 与现有接口一致（成本最低）
- 断网可重试，适合本地安装包环境

补充能力：
- 引入“指令/通知”概念（例如强制更新、任务变更、紧急通知）

### 3.2 可选：WebSocket/消息队列（后续）
用于即时推送，但对本地环境复杂度更高，建议第二阶段再做。


## 4. 数据模型对齐与映射（Cloud ↔ Local）

### 4.1 关键实体
- **Organization**：云端权威
- **User**：云端权威；本地可缓存
- **Task**：教师发布（云端权威）；本地拉取执行
- **Report**：学生提交（本地生成，云端存档/批阅）
- **License / Activation Token**：本地合法性凭证

### 4.2 建议新增字段（为同步做准备）
为避免 ID 冲突、支持多端同步：
- `Task.cloud_id`（uuid）
- `Report.cloud_id`（uuid）
- `User.cloud_id`（uuid）

> 注：如果本地安装包项目已经实现了 `cloud_id` 兼容（曾出现 `no such column: users.cloud_id`），需要与 Cloud 项目统一策略。

### 4.3 同步游标
- `since` 使用 `updated_at`（或单调递增的 `sync_seq`）
- 建议统一为 **UTC ISO8601** 字符串


## 5. API 设计计划（在现有 sync 基础上补齐）

### 5.1 拉取任务（Local 拉取 Cloud）
- **GET** `/api/cloud/sync/tasks?org_id=...&since=...`
- 返回：任务列表（包含 `cloud_id`、`updated_at`、`status`）

补齐：
- 支持按 `status=published` 过滤
- 支持按 `class_id`（未来）过滤

### 5.2 任务变更通知/指令（Local 拉取 Cloud）
新增：
- **GET** `/api/cloud/sync/commands?org_id=...&since=...`
- command 类型示例：
  - `TASK_PUBLISHED`
  - `TASK_UPDATED`
  - `FORCE_UPDATE`
  - `NOTICE`

### 5.3 上报报告（Local 推送 Cloud）
Cloud 已有：
- **POST** `/api/cloud/reports/upload`（multipart：file + task_id + student_id）

补齐建议：
- 支持 `task_cloud_id` / `student_cloud_id`（避免纯 int id 绑定）
- 支持断点续传/重复提交幂等（`report.cloud_id` 唯一）

### 5.4 上报统计（Local 推送 Cloud）
Cloud 已有：
- **POST** `/api/cloud/analytics/report`

补齐：
- 标准化 module_id 枚举
- 限制频率/签名验证（依赖 activation_token）


## 6. 权限与安全

### 6.1 本地端鉴权方式
推荐：
- 本地端请求 Cloud Sync API 时携带 `activation_token`（License 激活后获得）
- Cloud 端验证 token 与 License 状态（已存在 `/licenses/verify`）

替代：
- 使用 JWT（需要本地端有云端账号/密码，不适合学生端批量）

### 6.2 数据隔离
- `org_id` 是最小隔离边界
- 未来引入 `class_id` 作为更细粒度隔离


## 7. 联调步骤（建议执行顺序）

### 7.1 第 0 步：本地安装包安装与启动验证（当前优先）
- 安装包安装到 `Program Files` 后启动
- 验证：
  - 无 WinError 5（写目录权限问题）
  - 算法/数据采集模块输出目录均落到可写 runtime dir（如 `%APPDATA%\智信优控\...`）

### 7.2 第 1 步：Cloud 侧准备试验数据
- 创建机构：大连理工大学
- 创建 org_admin/teacher/student（或导入 CSV）
- 为该机构生成 License 并激活

> 备注：目前 Cloud 数据模型没有学院/专业/班级字段，先通过 org_name/备注字段记录。

### 7.3 第 2 步：Local_Client 拉取任务
- 本地输入 activation_token
- 调用 `/sync/tasks` 拉取 `published` 任务
- 本地 UI 展示“任务列表/详情”

### 7.4 第 3 步：本地提交报告到云端
- 上传文件到 `/reports/upload`
- 云端教师端可在“报告管理”看到并评分

### 7.5 第 4 步：补齐“班级”维度
- 引入 Class/Enrollment
- 任务发布支持 class_id
- 学生端拉取按 class_id


## 8. 里程碑与交付物

### M1（稳定性）
- 本地安装包可安装可启动
- 所有运行时写目录归一到 runtime

### M2（任务同步 MVP）
- Cloud 教师发布任务（published）
- Local 拉取任务并展示

### M3（报告闭环）
- Local 提交报告
- Cloud 批阅 + 统计

### M4（班级/课程体系）
- Class/Enrollment 模型
- 按班级发布/接收


## 9. 风险与注意事项
- **ID 冲突风险**：Cloud 与 Local 若各自自增 int，需要 `cloud_id` 统一。
- **权限与隔离风险**：仅靠 org_id 会导致同机构不同班级无法隔离；但可作为 MVP。
- **网络环境**：校园网/离线环境必须支持重试与断点续传。
- **部署差异**：Cloud 前端 base path 与反向代理路径要一致（目前 `/api/cloud` 代理到 8000）。
