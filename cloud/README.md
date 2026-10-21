# ZhiXinYouKong Cloud Platform

> Centralized cloud management platform for the **Vehicle–Road–Cloud Integrated Transportation Experiment System** (车路云一体化综合交通实验平台).

[![GitHub Pages](https://img.shields.io/badge/demo-GitHub%20Pages-blue)](https://chenshi0504.github.io/zhixinyoukong-cloud/)

**在线访问地址：<https://chenshi0504.github.io/zhixinyoukong-cloud/>**

## What Is This Repo?

This repository contains **only the cloud management platform** — a standalone web application for administrators and teachers to manage teaching organizations, classes, experiment tasks, student reports, licenses, and analytics.

> **Note:** The local desktop experiment platform (student‑facing, port 8000) is maintained in a separate codebase. This cloud platform (port 9000) communicates with local clients via a well‑defined Sync API.

### Scope Boundary

| | This Repo (Cloud) | Separate Repo (Local) |
|---|---|---|
| **Port** | 9000 | 8000 |
| **Users** | Admin, Teacher | Student |
| **Interface** | Web browser (SPA) | Desktop app (PyInstaller) |
| **API prefix** | `/api/cloud/*` | `/api/v1/*` |
| **Database** | `cloud_prod.db` / PostgreSQL | `data.db` (SQLite) |
| **Deployment** | GitHub Pages + Server | Installer `.exe` |

### Platform Roles

| Role | Entry Point | Capabilities |
|------|-------------|--------------|
| **Admin** | Web browser → Cloud URL | Organizations, licenses, users, version updates |
| **Teacher** | Web browser → Cloud URL | Classes, tasks, report grading, analytics |
| **Student** | *(uses local app, not this platform)* | Experiments, report submission (auto‑sync) |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 · Element Plus · ECharts · Vite |
| Backend | FastAPI · SQLAlchemy · Pydantic v2 · Uvicorn |
| Database | SQLite (dev) · PostgreSQL (prod / Docker) |
| Auth | JWT (HS256) with refresh‑token rotation |
| Deployment | GitHub Pages · Cloudflare Tunnel / cpolar / frp |
| CI/CD | GitHub Actions (frontend auto‑deploy) |

## Quick Start

### Prerequisites

- Python ≥ 3.10
- Node.js ≥ 18

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env          # edit as needed
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
```

Health check: `GET http://localhost:9000/api/cloud/health`

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

### Production Build

```bash
cd frontend
VITE_API_BASE_URL=https://your-api.example.com npm run build
# Output → frontend/dist/
```

## Deployment

See [`docs/部署指南.md`](docs/部署指南.md) for full deployment instructions.

### Quick Deploy (3 steps)

1. **Start backend** on a server (`python -m uvicorn ...`)
2. **Expose via tunnel** — e.g. `cloudflared tunnel --url http://localhost:9000`
3. **Build & push frontend** to GitHub Pages with the tunnel URL

### Docker Compose

```bash
cp .env.example .env             # configure secrets
docker compose up -d             # Nginx :80 → API :9000 → PostgreSQL
```

## Project Structure

```
├── backend/                 # Cloud API server (FastAPI)
│   ├── app/
│   │   ├── main.py          # App entry, middleware, router registration
│   │   ├── config.py        # Settings via pydantic-settings + .env
│   │   ├── database.py      # SQLAlchemy engine & session factory
│   │   ├── deps.py          # Dependency injection (auth, db session)
│   │   ├── seed.py          # Default account seeding on first run
│   │   ├── models/          # ORM models (User, Task, Report, Org, …)
│   │   ├── schemas/         # Pydantic request / response schemas
│   │   ├── routers/         # API route handlers (12 modules)
│   │   └── services/        # Business logic (auth, license)
│   ├── tests/               # Pytest test suite
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Container image definition
├── frontend/                # Cloud web portal (Vue 3 SPA)
│   ├── src/
│   │   ├── api/client.js    # Axios instance with token‑refresh interceptor
│   │   ├── views/           # Page components (Login, Dashboard, Teacher/*, …)
│   │   ├── layouts/         # AdminLayout, TeacherLayout
│   │   ├── router/          # Vue Router config (hash history for GitHub Pages)
│   │   └── stores/          # Pinia auth store
│   ├── .env.production      # Production API base URL
│   └── vite.config.js       # Build config (GitHub Pages base path)
├── nginx/                   # Nginx reverse‑proxy config (Docker / self‑hosted)
├── deploy/                  # Deployment scripts & tools
│   └── start_cloud.bat      # Windows one‑click start (HTTP/HTTPS + tunnel)
├── docs/                    # Design docs & deployment guide
├── docker-compose.yml       # Full‑stack: Nginx + API + PostgreSQL
├── .env.example             # Environment variable template
├── DEVLOG.md                # Development & test changelog
└── README.md                # This file
```

> **CI/CD note:** The GitHub Actions workflow lives at `/.github/workflows/deploy-cloud-frontend.yml`
> (required by GitHub). It auto‑deploys `frontend/dist/` to GitHub Pages on push to `main`.

## API Endpoints

All cloud endpoints are prefixed with `/api/cloud/`.

| Group | Prefix | Description |
|-------|--------|-------------|
| Auth | `/auth` | Login, register, token refresh |
| Public | `/public` | Org & class lists (no auth) |
| Sync | `/sync` | Local ↔ cloud data sync |
| Tasks | `/tasks` | Task CRUD |
| Reports | `/reports` | Report management & grading |
| Organizations | `/orgs` | Org management |
| Classes | `/classes` | Class management |
| Users | `/users` | User management |
| Licenses | `/licenses` | License key management |
| Analytics | `/analytics` | Usage statistics |
| Updates | `/updates` | Version update management |
| Admin | `/admin` | Dashboard & system stats |

Interactive docs: `http://localhost:9000/docs`

## Default Accounts

| Username | Password | Role |
|----------|----------|------|
| `admin` | `123456` | Super Admin |
| `teacher` | `123456` | Teacher |

## Integration with Local Platform

The local desktop app (separate codebase) connects to this cloud platform via `CLOUD_API_URL` environment variable. The cloud exposes three sync endpoints consumed by local clients:

| Endpoint | Direction | Purpose |
|----------|-----------|----------|
| `GET  /api/cloud/sync/tasks` | Cloud → Local | Pull published tasks |
| `POST /api/cloud/sync/reports` | Local → Cloud | Push student reports |
| `GET  /api/cloud/sync/grades` | Cloud → Local | Pull teacher grades |

For integration details, see [`docs/CLOUD_LOCAL_SYNC_PLAN.md`](docs/CLOUD_LOCAL_SYNC_PLAN.md).

## License

Proprietary — Internal use only.
