"""
pytest fixtures：测试数据库、测试客户端、mock 用户。
"""
import os
import pytest

# 设置测试环境变量（必须在导入 app 之前）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests"

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models import *  # noqa: F401, F403
from app.services.auth import hash_password

# 共享测试引擎（SQLite in-memory 需要同一个连接才能看到表）
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)

# SQLite in-memory: 让所有 session 共享同一个底层连接
_connection = _test_engine.connect()


@pytest.fixture(autouse=True)
def _setup_tables():
    """每个测试前建表，测试后清表。"""
    Base.metadata.create_all(bind=_connection)
    yield
    Base.metadata.drop_all(bind=_connection)


@pytest.fixture()
def db():
    """返回绑定到共享连接的 Session。"""
    # 使用 nested transaction 以便测试后回滚
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_connection)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session):
    """FastAPI 测试客户端，注入测试数据库。"""
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_users(db: Session):
    """创建测试用户，返回 dict 方便查找。"""
    from app.models.user import User
    from app.models.organization import Organization

    org = Organization(name="测试大学", contact_name="张三")
    db.add(org)
    db.flush()

    users = {}
    for username, role in [
        ("super_admin", "super_admin"),
        ("org_admin", "org_admin"),
        ("teacher1", "teacher"),
        ("student1", "student"),
    ]:
        u = User(
            username=username,
            password_hash=hash_password("password123"),
            role=role,
            real_name=f"{username}_name",
            org_id=org.id,
        )
        db.add(u)
        db.flush()
        users[username] = u

    db.commit()
    return {"org": org, "users": users}


@pytest.fixture()
def admin_headers(client, seed_users) -> dict:
    """super_admin 的 Authorization headers。"""
    resp = client.post("/api/cloud/auth/login", json={
        "username": "super_admin",
        "password": "password123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def teacher_headers(client, seed_users) -> dict:
    """teacher 的 Authorization headers。"""
    resp = client.post("/api/cloud/auth/login", json={
        "username": "teacher1",
        "password": "password123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
