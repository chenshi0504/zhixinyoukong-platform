# ZhiXinYouKong Cloud Platform — Development Log

> **Repository**: [chenshi0504/zhixinyoukong-cloud](https://github.com/chenshi0504/zhixinyoukong-cloud)  
> **Live Frontend**: https://chenshi0504.github.io/zhixinyoukong-cloud/  
> **Tech Stack**: FastAPI (Python) · Vue 3 + Element Plus · SQLite/PostgreSQL · Cloudflare Tunnel

---

## Architecture Overview

```
┌─── GitHub Pages ───────────────────────┐    ┌─── Campus Server ────────────────┐
│  Vue 3 SPA (Element Plus + ECharts)    │    │  FastAPI :9000                   │
│  Hash-based routing                    │───→│  SQLite / PostgreSQL             │
│  Axios API client                      │    │  JWT auth (HS256)                │
│  Vite build, manual chunk splitting    │    │  File uploads                    │
└────────────────────────────────────────┘    │  Cloudflare Tunnel → public URL  │
                                              └──────────────────────────────────┘
┌─── Local Installer ───────────────────┐
│  智信优控.exe (PyInstaller)            │
│  FastAPI :8000 (local backend)        │───→  Cloud API via CLOUD_API_URL
│  Sync: tasks / reports / grades       │
└────────────────────────────────────────┘
```

### API Prefix Convention

- **Cloud endpoints**: `/api/cloud/*` (auth, sync, tasks, reports, orgs, licenses, analytics, etc.)
- **Local endpoints** (separate repo): `/api/v1/*`

### Roles

| Role | Access | Platform |
|------|--------|----------|
| `super_admin` | Full cloud management | Cloud (browser) |
| `teacher` | Classes, tasks, grading | Cloud (browser) |
| `student` | Experiments, reports | Local installer |

---

## Changelog

### 2026-04-12 — v3.4.0 Login 改版 & GitHub Pages 修复

**Milestone**: 登录页增加角色选择 + 后端状态检测；彻底修复 GitHub Pages 缓存问题。

#### Login 页改版

- 登录页新增**角色选择屏**（管理员 / 教师），选择后进入对应登录表单
- **后端连接状态检测**移到全局可见位置（角色选择页即显示绿色/红色状态条）
- 登录前检查后端是否在线，未连接时拦截并提示「请先启动云端后端服务」
- 教师模式支持注册入口

#### GitHub Pages 部署修复

- **根本原因**：GitHub Pages Source 被设为 "GitHub Actions" 而非 "Deploy from branch: gh-pages"，导致推送 gh-pages 无效
- **修复**：Settings → Pages → Source 改为 `Deploy from a branch: gh-pages / root`
- **防缓存**：`index.html` 模板添加 `Cache-Control: no-cache` meta 标签
- **SW 清除**：`index.html` 注入内联脚本，自动注销旧 Service Worker 并清除 CacheStorage
- **干净部署**：每次用 `--orphan` 新建 gh-pages 分支，避免旧构建文件累积

#### Cloudflare Tunnel 穿透

- 重新建立 Cloudflare quick tunnel，当前公网地址：`https://cad-containing-filters-call.trycloudflare.com`
- `.env.production` 中 `VITE_API_BASE_URL` 指向该地址
- CORS 已配置允许 `https://chenshi0504.github.io`
- 后端 health check 公网验证通过

#### 配置修复

- `vite.config.js`：开发代理 target 从 `localhost:8000` → `localhost:9000`（匹配云端后端端口）
- `.env.production`：清空过期 Cloudflare tunnel URL，按需填入最新地址
- `cloudflared.exe` 从 git 仓库移除，加入 `.gitignore`

---

### 2026-04-08 — v3.3.1 Public Deployment

**Milestone**: Cloud platform deployed to public internet for the first time.

#### Infrastructure
- Downloaded `cloudflared.exe` (Cloudflare Tunnel) for zero-config public HTTPS
- Tunnel established: `https://fancy-qui-patients-isaac.trycloudflare.com`
- Backend health check verified over public internet
- Admin login verified over public tunnel (JWT issued successfully)

#### Frontend Deployment
- Built production frontend with `GITHUB_PAGES=true` and `VITE_API_BASE_URL` pointing to tunnel
- Pushed `dist/` to `gh-pages` branch on GitHub
- GitHub Pages deployment active (3 deployments total)

#### Configuration Files Created
- `backend/.env` — Production config (SQLite, strong SECRET_KEY, CORS for GitHub Pages + tunnel)
- `frontend/.env.production` — `VITE_API_BASE_URL` for production builds
- `docs/部署指南.md` — Deployment guide (Chinese)

#### Scripts Updated
- `deploy/start_cloud.bat` — Added dependency check, HTTP/HTTPS mode selection, optional tunnel integration
- `nginx/nginx.conf` — Added frontend SPA serving, `client_max_body_size 50m`, `proxy_read_timeout 120s`
- GitHub Actions workflow — Added `VITE_API_BASE_URL` from repo variables

---

### 2026-04-05 — Cloud Backend v1.0

**Milestone**: Cloud backend API fully functional.

#### Features Implemented
- **Authentication**: JWT login/register with access + refresh tokens
- **Organizations**: CRUD for educational institutions
- **Licenses**: Generation, activation, expiry management
- **Users**: Role-based management (super_admin, org_admin, teacher, student)
- **Classes**: Classroom management under organizations
- **Tasks**: Teacher creates tasks, synced to local installers
- **Reports**: Student submissions, teacher grading
- **Analytics**: Usage statistics, module tracking
- **Updates**: Version update management
- **Sync API**: Bi-directional sync between local platform and cloud
  - `GET /api/cloud/sync/tasks` — Pull tasks to local
  - `POST /api/cloud/sync/reports` — Push reports to cloud
  - `GET /api/cloud/sync/grades` — Pull grades to local

#### Cloud Sync Bug Fixes
- Added `_parse_dt()` helper for ISO datetime → Python datetime conversion
- Fixed `cloud_id` type mismatch (int vs string)
- Fixed `ReportStatus.GRADED` — string constant, not enum
- Added `db.rollback()` in error handlers to prevent session corruption

---

### 2026-03-30 — Cloud Frontend v1.0

**Milestone**: Vue 3 cloud frontend completed.

#### Pages
- **Login**: Supports admin and teacher roles
- **Dashboard**: Overview statistics
- **Organizations**: List + detail views
- **Licenses**: License management table
- **Users**: User management with role filtering
- **Analytics**: ECharts-based visualizations
- **Updates**: Version update management
- **Teacher Portal**: Classes, tasks, reports, students, analytics (auto-redirect for teacher role)

#### Technical
- Vue 3 + Vue Router (hash history) + Pinia stores
- Element Plus UI components
- ECharts for data visualization
- Axios with automatic token refresh interceptor
- Vite build with manual chunks (echarts, element-plus)
- `base: '/zhixinyoukong-cloud/'` for GitHub Pages deployment

---

## Test Records

### 2026-04-08 — Public Access Verification

| Test | Method | Result |
|------|--------|--------|
| Health check (local) | `GET http://localhost:9000/api/cloud/health` | ✅ `{"status":"ok"}` |
| Health check (tunnel) | `GET https://...trycloudflare.com/api/cloud/health` | ✅ `{"status":"ok"}` |
| Admin login (tunnel) | `POST /api/cloud/auth/login` with admin/123456 | ✅ JWT token received |
| Frontend build | `npm run build` with `GITHUB_PAGES=true` | ✅ 2.72MB, 28 files |
| API URL in build | grep `trycloudflare` in `client-*.js` | ✅ `baseURL` correctly set |
| gh-pages push | `git push -f origin gh-pages` | ✅ 47 files, 974KB |

---

## Default Credentials

| Username | Password | Role |
|----------|----------|------|
| admin | 123456 | super_admin |
| teacher | 123456 | teacher |

---

## Known Limitations

1. **Tunnel address is ephemeral**: Free Cloudflare quick tunnels change URL on restart. Need to rebuild frontend and update configs each time. Solution: register a Cloudflare account + bind a domain for permanent tunnel.
2. **SQLite concurrency**: Current production uses SQLite. Fine for small-scale teaching (<50 concurrent users). Switch to PostgreSQL via `docker-compose.yml` for larger deployments.
3. **No HTTPS on backend directly**: Backend runs HTTP; HTTPS is terminated by the tunnel proxy. If deploying without a tunnel, use the self-signed `cert.pem`/`key.pem` or set up Nginx + Let's Encrypt.
4. **Frontend double-build artifacts**: `dist/` contains both `GITHUB_PAGES` and non-`GITHUB_PAGES` build outputs. Only the latest build is used.

---

## File Structure

```
├── backend/                 # Cloud API server (FastAPI :9000)
│   ├── app/
│   │   ├── main.py          # App entry + router registration
│   │   ├── config.py        # pydantic-settings + .env loading
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── routers/         # 12 API route modules
│   │   └── services/        # Business logic (auth, license)
│   ├── tests/               # Pytest test suite
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # Cloud web portal (Vue 3 SPA)
│   ├── src/
│   ├── .env.production      # Production API base URL
│   └── vite.config.js       # GitHub Pages base path config
├── nginx/                   # Nginx reverse proxy
├── deploy/                  # Deployment scripts & tunnel tools
├── docs/                    # Documentation
├── docker-compose.yml       # Nginx + API + PostgreSQL
├── .env.example
├── DEVLOG.md                # This file
└── README.md
```
