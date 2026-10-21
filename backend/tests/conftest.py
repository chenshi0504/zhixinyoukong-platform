"""
Pytest configuration and fixtures.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole
from app.services.auth import get_password_hash, create_access_token


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Create a test client with database override."""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    
    with TestClient(app) as test_client:
        yield test_client
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def test_admin(db):
    """Create a test admin user."""
    user = User(
        username="admin",
        password_hash=get_password_hash("admin123"),
        role=UserRole.ADMIN.value,
        real_name="测试管理员",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_teacher(db):
    """Create a test teacher user."""
    user = User(
        username="teacher1",
        password_hash=get_password_hash("teacher123"),
        role=UserRole.TEACHER.value,
        real_name="测试教师",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_student(db):
    """Create a test student user."""
    user = User(
        username="student1",
        password_hash=get_password_hash("student123"),
        role=UserRole.STUDENT.value,
        real_name="测试学生",
        student_id="2024001",
        class_name="测试班级",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(test_admin):
    """Create an admin JWT token."""
    return create_access_token(
        data={
            "sub": test_admin.username,
            "user_id": test_admin.id,
            "role": test_admin.role
        }
    )


@pytest.fixture
def teacher_token(test_teacher):
    """Create a teacher JWT token."""
    return create_access_token(
        data={
            "sub": test_teacher.username,
            "user_id": test_teacher.id,
            "role": test_teacher.role
        }
    )


@pytest.fixture
def student_token(test_student):
    """Create a student JWT token."""
    return create_access_token(
        data={
            "sub": test_student.username,
            "user_id": test_student.id,
            "role": test_student.role
        }
    )
