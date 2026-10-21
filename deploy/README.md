# 公网部署说明

## 0. 先理解边界：GitHub 能托管什么

| 内容 | 能否放在 GitHub | 说明 |
|------|-----------------|------|
| 源码、文档、静态页面 | ✅ 可以 | 仓库 + GitHub Pages |
| 云端管理端（FastAPI + PostgreSQL） | ❌ 不能 | GitHub 不提供常驻后端进程，需 PaaS 或服务器 |
| 本地仿真平台（SUMO / CARLA / GPU） | ❌ 不能 | 需要图形界面、GPU 与本地仿真引擎 |

结论：
- **公网「能看」** → 仓库 + Pages 文档站（本仓库已带 `site/` 与自动部署 workflow）
- **公网「能用」教学管理** → 把 `cloud/` 部署到 Render / Railway / VPS（本文方案 A、B）
- **公网「能用」仿真算法** → 部署在校内 GPU 服务器，通过内网/VPN 或端口映射访问（方案 C）

---

## 方案 A：Render 一键部署云端管理端（推荐，免费额度可试）

1. 把本仓库推到 GitHub（见 `PUBLISH.md`）
2. 打开 <https://dashboard.render.com> → New → **Blueprint** → 选择本仓库
3. Render 读取 `deploy/render.yaml`，创建：
   - `zhixinyoukong-api`（Docker，FastAPI）
   - `zhixinyoukong-web`（静态站，Vue 3）
   - `zhixinyoukong-db`（PostgreSQL）
4. 填写两个变量：
   - `ALLOWED_ORIGINS`：前端域名，如 `https://zhixinyoukong-web.onrender.com`
   - `VITE_API_BASE`：后端域名，如 `https://zhixinyoukong-api.onrender.com`
5. 首次部署后，进入 API 服务执行一次建表/种子数据：
   ```bash
   python -m app.init_db      # 若项目提供该入口
   ```
   或按 `cloud/backend/部署指南.md` 操作。
6. 打开前端域名，用管理员账号登录，**立即修改默认口令**。

> 免费实例会休眠，首次访问约 30 秒冷启动；学生集中实验建议至少 Starter 规格。

## 方案 B：VPS / 校内服务器（Docker Compose，最稳）

```bash
git clone https://github.com/<你的账号>/<仓库名>.git
cd <仓库名>
cp deploy/.env.example .env          # 修改 POSTGRES_PASSWORD、SECRET_KEY、ALLOWED_ORIGINS

cd cloud/frontend && npm install && npm run build && cd ../..
mkdir -p deploy/site-dist && cp -r cloud/frontend/dist/* deploy/site-dist/

docker compose -f deploy/docker-compose.public.yml up -d --build
```

- 前端：`http://<服务器IP>/`
- 后端：`http://<服务器IP>:8000`
- 建议前置 Nginx/Caddy 配 HTTPS，并把 8000 只对内网开放

## 方案 C：本地仿真平台（重型）部署在校内服务器

本地平台依赖 SUMO（GUI）、CARLA（GPU）、DTALite 与桌面壳，不适合公网直连。可行做法：

1. **远程桌面/虚拟应用**：Windows Server + RDP，或 Guacamole 网页化
2. **只暴露 Web 前端 + API**：`python backend/run.py` 监听 0.0.0.0，前置 Nginx 认证
3. **JupyterHub / 容器化实验环境**：为每个学生分配容器 + 挂载算法数据

> CARLA 需要独显；无 GPU 的机房请改用 SUMO 轻量场景，或在课程中把 CARLA 实验设为选做。

## 环境变量清单

| 变量 | 必需 | 说明 |
|------|------|------|
| `DATABASE_URL` | ✅ | PostgreSQL 连接串 |
| `SECRET_KEY` | ✅ | JWT 签名密钥，随机 48 字节 |
| `ALLOWED_ORIGINS` | ✅ | 前端域名，逗号分隔 |
| `UPLOAD_DIR` | ⬜ | 上传目录，默认 `/data/uploads` |
| `VITE_API_BASE` | ✅（前端构建） | 后端公网地址 |

## 上线前检查表

- [ ] 修改 admin / teacher / student 默认口令
- [ ] `SECRET_KEY` 为随机值，未提交到仓库
- [ ] `ALLOWED_ORIGINS` 精确到域名（不要用 `*`）
- [ ] 数据库已初始化并改掉示例密码
- [ ] 关闭 `/docs` 或加访问控制（FastAPI 默认暴露 OpenAPI）
- [ ] 配置 HTTPS 与访问日志
- [ ] 学生个人信息、上传文件按学校要求脱敏与备份
