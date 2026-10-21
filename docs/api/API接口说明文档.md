# 智信优控综合交通实验平台 API接口规范文档

## 文档信息

文档标题：API接口规范文档

平台名称：面向车路云一体化的综合交通实验平台

版本号：v1.0.0

文档版本：1.0

发布日期：2024年11月18日

维护部门：智信优控实验平台开发组

---

## 1. 概述

### 1.1 文档目的

本文档规定了智信优控综合交通实验平台前后端通信的API接口规范，包括接口设计原则、通信协议、数据格式、错误处理等内容。本文档适用于前端开发人员、后端开发人员和系统集成人员。

### 1.2 适用范围

本规范适用于平台所有API接口的设计、开发和维护。

### 1.3 核心设计原则

RESTful架构：遵循REST设计原则，使用标准HTTP方法进行资源操作。

统一接口：所有接口采用统一的请求响应格式，便于客户端统一处理。

版本管理：通过URL路径进行版本控制，支持多版本并存。

安全认证：采用JWT Token认证机制，确保接口安全。

可扩展性：预留扩展空间，支持未来功能增加。

---

## 2. 技术规范

### 2.1 基础配置

基础URL：http://localhost:8000

API版本：v1

协议：HTTP/HTTPS

数据格式：JSON

字符编码：UTF-8

### 2.2 认证方式

认证类型：JWT Token

Token位置：HTTP Authorization请求头

Token格式：Bearer {token}

Token有效期：3600秒（1小时）

刷新Token有效期：7天

### 2.3 请求规范

#### 2.3.1 HTTP方法

GET：用于查询资源，不修改服务器状态。

POST：用于创建新资源或执行操作。

PUT：用于完整更新现有资源。

PATCH：用于部分更新资源。

DELETE：用于删除资源。

#### 2.3.2 请求头

Content-Type：application/json

Authorization：Bearer {access_token}（需要认证的请求）

Accept：application/json

#### 2.3.3 请求参数

路径参数：在URL路径中指定，如/api/v1/users/{user_id}

查询参数：在URL查询字符串中指定，如?page=1&size=10

请求体：使用JSON格式，仅用于POST、PUT、PATCH请求

### 2.4 响应规范

#### 2.4.1 响应格式

所有响应均为JSON格式，包含以下字段：

code：整数，表示响应状态码

message：字符串，表示响应消息

data：对象或数组，表示响应数据

#### 2.4.2 成功响应示例

```
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "name": "示例数据"
  }
}
```

#### 2.4.3 列表响应示例

```
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "size": 10,
    "pages": 10
  }
}
```

#### 2.4.4 错误响应示例

```
{
  "code": 400,
  "message": "参数错误",
  "detail": "用户名不能为空"
}
```

### 2.5 HTTP状态码

200 OK：请求成功

201 Created：资源创建成功

204 No Content：删除成功，无返回内容

400 Bad Request：请求参数错误

401 Unauthorized：未授权，需要登录

403 Forbidden：禁止访问，权限不足

404 Not Found：资源不存在

500 Internal Server Error：服务器内部错误

### 2.6 分页规范

分页参数：page（页码，从1开始）、size（每页数据数，默认10，最大100）

分页响应字段：total（总数）、page（当前页）、size（每页数）、pages（总页数）

示例：GET /api/v1/tasks?page=1&size=10

---

## 3. 认证与授权

### 3.1 登录流程

请求：

```
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "123456"
}
```

响应：

```
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "id": 1,
      "username": "admin",
      "role": "teacher"
    }
  }
}
```

### 3.2 Token使用

在后续请求中添加Authorization请求头：

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 3.3 Token刷新

当access_token过期时，使用refresh_token获取新token：

```
POST /api/v1/auth/refresh
Authorization: Bearer {refresh_token}
```

---

## 4. 接口定义

### 4.1 认证接口

#### 4.1.1 用户登录

接口地址：POST /api/v1/auth/login

请求参数：username（用户名）、password（密码）

响应数据：access_token、token_type、expires_in、user

#### 4.1.2 Token刷新

接口地址：POST /api/v1/auth/refresh

请求头：Authorization: Bearer {refresh_token}

响应数据：access_token、expires_in

### 4.2 数据采集接口

#### 4.2.1 启动数据采集

接口地址：POST /api/v1/data-collection/start

请求参数：data_source（数据源）、collection_type（采集类型）、duration（采集时长）

响应数据：task_id、status、start_time

#### 4.2.2 获取采集数据

接口地址：GET /api/v1/data-collection/data/{task_id}

路径参数：task_id（采集任务ID）

响应数据：task_id、data_points（数据点数组）

### 4.3 交通流接口

#### 4.3.1 交通流重构

接口地址：POST /api/v1/traffic/reconstruction

请求参数：algorithm（算法）、data_source（数据源）、time_range（时间范围）

响应数据：task_id、od_matrix（OD矩阵）、accuracy（精度）

#### 4.3.2 交通流预测

接口地址：POST /api/v1/traffic/prediction

请求参数：model（模型）、prediction_horizon（预测时长）、historical_data（历史数据）

响应数据：predictions（预测结果）、confidence（置信度）

### 4.4 控制策略接口

#### 4.4.1 信号优化

接口地址：POST /api/v1/strategies/signal-optimization

请求参数：algorithm（算法）、intersection_id（路口ID）、optimization_objective（优化目标）

响应数据：optimized_timing（优化信号时长）、expected_improvement（预期改进）

#### 4.4.2 路径诱导

接口地址：POST /api/v1/strategies/path-guidance

请求参数：algorithm（算法）、origin（起点）、destination（终点）、optimization_goal（优化目标）

响应数据：path（路径）、distance（距离）、estimated_time（预计时间）

#### 4.4.3 车速控制

接口地址：POST /api/v1/strategies/speed-control

请求参数：vehicle_id（车辆ID）、target_speed（目标速度）、control_mode（控制模式）

响应数据：status（状态）、current_speed（当前速度）

### 4.5 仿真接口

#### 4.5.1 启动SUMO仿真

接口地址：POST /api/v1/simulations/sumo/start

请求参数：scenario（场景）、flow_rate（流量）、simulation_time（仿真时长）

响应数据：session_id、status、start_time

#### 4.5.2 获取仿真状态

接口地址：GET /api/v1/simulations/sumo/status/{session_id}

路径参数：session_id（仿真会话ID）

响应数据：session_id、status、progress、vehicles_completed

#### 4.5.3 分析仿真结果

接口地址：POST /api/v1/simulations/sumo/analyze

请求参数：session_id、analysis_type

响应数据：time_series_svg、trip_analysis_svg、statistics

#### 4.5.4 下载仿真报告

接口地址：GET /api/v1/simulations/sumo/report/{session_id}

路径参数：session_id

响应：DOCX文件流

### 4.6 任务管理接口

#### 4.6.1 创建任务

接口地址：POST /api/v1/tasks

请求参数：title（标题）、module（模块）、description（描述）、deadline（截止时间）

响应数据：id、title、status、created_at

#### 4.6.2 获取任务列表

接口地址：GET /api/v1/tasks?page=1&size=10

查询参数：page、size

响应数据：items、total、page、size、pages

#### 4.6.3 提交任务结果

接口地址：POST /api/v1/tasks/{task_id}/submit

路径参数：task_id

请求参数：results（结果数据）

响应数据：id、status、submitted_at

### 4.7 报告管理接口

#### 4.7.1 生成报告

接口地址：POST /api/v1/reports/generate

请求参数：task_id、report_type、include_charts

响应数据：report_id、status、created_at

#### 4.7.2 获取报告列表

接口地址：GET /api/v1/reports?user_id=1

查询参数：user_id、page、size

响应数据：items、total、page、size、pages

#### 4.7.3 下载报告

接口地址：GET /api/v1/reports/{report_id}/download

路径参数：report_id

响应：DOCX文件流

---

## 5. 错误处理

### 5.1 错误响应格式

```
{
  "code": 400,
  "message": "参数错误",
  "detail": "用户名不能为空"
}
```

### 5.2 错误码定义

1000系列：参数错误（1000参数错误、1001参数缺失、1002参数类型错误、1003参数值超出范围）

2000系列：认证错误（2000未登录、2001Token无效、2002Token过期、2003权限不足）

3000系列：业务错误（3000资源不存在、3001资源已存在、3002操作失败、3003状态不允许）

5000系列：系统错误（5000服务器错误、5001数据库错误、5002第三方服务错误、5003文件操作错误）

### 5.3 错误处理建议

客户端应根据HTTP状态码和错误code进行相应处理。

对于4xx错误，应检查请求参数和认证信息。

对于5xx错误，应重试请求或联系技术支持。

---

## 6. 调用示例

### 6.1 JavaScript示例

登录请求：

```javascript
const response = await fetch('http://localhost:8000/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'admin',
    password: '123456'
  })
});
const result = await response.json();
if (result.code === 200) {
  localStorage.setItem('token', result.data.access_token);
}
```

认证请求：

```javascript
const token = localStorage.getItem('token');
const response = await fetch('http://localhost:8000/api/v1/tasks', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
const result = await response.json();
```

### 6.2 Python示例

登录请求：

```python
import requests

response = requests.post('http://localhost:8000/api/v1/auth/login', json={
  'username': 'admin',
  'password': '123456'
})
token = response.json()['data']['access_token']
```

认证请求：

```python
headers = {'Authorization': f'Bearer {token}'}
response = requests.get('http://localhost:8000/api/v1/tasks', headers=headers)
result = response.json()
```

### 6.3 cURL示例

登录请求：

```
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}'
```

认证请求：

```
curl -X GET http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 7. 开发指南

### 7.1 新接口开发规范

路径格式：/api/v1/{module}/{action}

响应格式：统一的JSON格式

参数验证：所有参数必须进行验证

错误处理：所有错误必须返回标准错误响应

文档注册：所有接口必须在Swagger文档中注册

### 7.2 版本升级策略

不兼容修改：创建新版本/api/v2/

版本维护：旧版本API保持可用至少6个月

版本通知：版本升级前提前通知所有客户端

### 7.3 性能优化

大数据查询：使用分页机制

频繁查询：使用缓存机制

长时间操作：使用异步任务队列

大文件上传：支持分块上传

### 7.4 安全性要求

权限验证：所有敏感操作进行权限验证

输入验证：所有用户输入进行验证和清理

日志记录：所有API调用记录日志

安全审计：定期进行安全审计和漏洞扫描

---

## 8. 接口清单

认证模块：POST /api/v1/auth/login、POST /api/v1/auth/refresh

数据采集模块：POST /api/v1/data-collection/start、GET /api/v1/data-collection/data/{task_id}

交通流模块：POST /api/v1/traffic/reconstruction、POST /api/v1/traffic/prediction

控制策略模块：POST /api/v1/strategies/signal-optimization、POST /api/v1/strategies/path-guidance、POST /api/v1/strategies/speed-control

仿真模块：POST /api/v1/simulations/sumo/start、GET /api/v1/simulations/sumo/status/{session_id}、POST /api/v1/simulations/sumo/analyze、GET /api/v1/simulations/sumo/report/{session_id}

任务管理模块：POST /api/v1/tasks、GET /api/v1/tasks、POST /api/v1/tasks/{task_id}/submit

报告管理模块：POST /api/v1/reports/generate、GET /api/v1/reports、GET /api/v1/reports/{report_id}/download

---

## 附录：文档修订记录

版本1.0：2024年11月18日，初始版本发布

---

文档结束
