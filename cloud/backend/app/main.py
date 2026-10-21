import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import engine, Base, SessionLocal
# 导入所有模型，确保 Base.metadata 包含所有表
from .models import *  # noqa: F401, F403
from .seed import seed_default_users

# CORS 允许的来源（环境变量配置，逗号分隔；默认允许所有）
_allowed_origins_str = os.environ.get(
    "ALLOWED_ORIGINS",
    "*"
)
ALLOWED_ORIGINS = (
    ["*"] if _allowed_origins_str == "*"
    else [o.strip() for o in _allowed_origins_str.split(",") if o.strip()]
)


def _ensure_sqlite_columns() -> None:
    """Keep existing SQLite deployments compatible with newer models."""
    db_url = str(engine.url)
    if not db_url.startswith("sqlite"):
        return

    required_columns = {
        "reports": {
            "file_type": "VARCHAR(20)",
            "description": "TEXT",
            "is_independent": "BOOLEAN DEFAULT 0",
        },
        "tasks": {
            "class_id": "INTEGER",
        },
        "self_algorithm_submissions": {
            "task_id": "INTEGER",
            "process_file_path": "VARCHAR(500)",
            "process_original_filename": "VARCHAR(255)",
            "process_file_size": "BIGINT",
        },
        "messages": {},
        "message_reads": {},
    }

    with engine.begin() as conn:
        for table, columns in required_columns.items():
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _repair_class_org_links() -> None:
    """Repair legacy classes so registration can find them by organization."""
    db_url = str(engine.url)
    if not db_url.startswith("sqlite"):
        return

    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "classes" not in tables or "users" not in tables:
            return
        conn.execute(
            text(
                """
                UPDATE classes
                SET org_id = (
                    SELECT users.org_id
                    FROM users
                    WHERE users.id = classes.teacher_id
                )
                WHERE org_id IS NULL
                  AND teacher_id IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM users
                    WHERE users.id = classes.teacher_id
                      AND users.org_id IS NOT NULL
                  )
                """
            )
        )


def _ensure_global_usernames() -> None:
    """Make login usernames globally unique for existing SQLite databases."""
    db_url = str(engine.url)
    if not db_url.startswith("sqlite"):
        return

    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "users" not in tables:
            return

        duplicates = conn.execute(
            text(
                """
                SELECT username
                FROM users
                GROUP BY username
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()
        for (username,) in duplicates:
            rows = conn.execute(
                text(
                    """
                    SELECT id
                    FROM users
                    WHERE username = :username
                    ORDER BY id ASC
                    """
                ),
                {"username": username},
            ).fetchall()
            for (user_id,) in rows[1:]:
                conn.execute(
                    text("UPDATE users SET username = username || '_' || id WHERE id = :id"),
                    {"id": user_id},
                )

        indexes = {
            row[1]
            for row in conn.execute(text("PRAGMA index_list(users)")).fetchall()
        }
        if "uq_users_username" not in indexes:
            conn.execute(text("CREATE UNIQUE INDEX uq_users_username ON users(username)"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发环境：直接建表；生产环境改为 alembic upgrade head
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    _repair_class_org_links()
    _ensure_global_usernames()
    db = SessionLocal()
    try:
        seed_default_users(db)
    except Exception as e:
        print(f"[警告] 数据库初始化失败: {e}")
    finally:
        db.close()
    yield


app = FastAPI(
    title="智信优控云端管理平台 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from .routers import auth as auth_router
from .routers import organizations as org_router
from .routers import licenses as license_router
from .routers import users as users_router
from .routers import tasks as tasks_router
from .routers import reports as reports_router
from .routers import analytics as analytics_router
from .routers import updates as updates_router
from .routers import sync as sync_router
from .routers import admin as admin_router
from .routers import public as public_router
from .routers import classes as classes_router
from .routers import messages as messages_router
from .routers import password_requests as password_requests_router
from .routers import self_algorithms as self_algorithms_router

app.include_router(auth_router.router)
app.include_router(org_router.router)
app.include_router(license_router.router)
app.include_router(users_router.router)
app.include_router(tasks_router.router)
app.include_router(reports_router.router)
app.include_router(analytics_router.router)
app.include_router(updates_router.router)
app.include_router(sync_router.router)
app.include_router(admin_router.router)
app.include_router(public_router.router)
app.include_router(classes_router.router)
app.include_router(messages_router.router)
app.include_router(password_requests_router.router)
app.include_router(self_algorithms_router.router)


@app.get("/api/cloud/health")
def health():
    return {"status": "ok"}


# ---------- 静态前端文件 ----------
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    # 处理 /zhixinyoukong-cloud/ 前缀（前端构建配置的 base 路径）
    @app.get("/zhixinyoukong-cloud/{full_path:path}")
    async def serve_cloud_assets(full_path: str):
        file_path = os.path.join(_frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = os.path.join(_frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))

