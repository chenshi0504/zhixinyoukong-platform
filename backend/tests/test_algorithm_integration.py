"""
Integration test: full flow from template creation to student code execution
and teacher review.

Validates: Requirements 1.1, 2.1, 3.1, 4.1, 5.1
"""
import pytest
from app.models import User, UserRole, Task
from app.services.auth import get_password_hash, create_access_token


@pytest.fixture
def teacher_and_token(db):
    """Create teacher + JWT token."""
    user = User(
        username="int_teacher", password_hash=get_password_hash("pass"),
        role=UserRole.TEACHER.value, real_name="集成教师", is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "role": user.role}
    )
    return user, token


@pytest.fixture
def student_and_token(db):
    """Create student + JWT token."""
    user = User(
        username="int_student", password_hash=get_password_hash("pass"),
        role=UserRole.STUDENT.value, real_name="集成学生",
        student_id="INT001", class_name="集成班", is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "role": user.role}
    )
    return user, token


@pytest.fixture
def task(db, teacher_and_token):
    """Create a published task."""
    teacher, _ = teacher_and_token
    t = Task(
        title="集成测试任务", description="测试",
        teacher_id=teacher.id, status="published",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_full_algorithm_workflow(client, teacher_and_token, student_and_token, task):
    """
    Complete flow:
    1. Teacher creates algorithm template
    2. Student views templates
    3. Student submits code
    4. Student executes code
    5. Student views result
    6. Teacher reviews student submission
    """
    _, t_token = teacher_and_token
    student, s_token = student_and_token

    # 1. Teacher creates template
    resp = client.post(
        "/api/v1/algorithm-templates",
        json={
            "module_id": "signal_optimization",
            "name": "Webster配时模板",
            "description": "基于Webster公式的信号配时",
            "code": "def run():\n    return 60\n",
        },
        headers=_auth(t_token),
    )
    assert resp.status_code == 201
    template = resp.json()
    assert template["module_id"] == "signal_optimization"
    template_id = template["id"]

    # 2. Student views templates for the module
    resp = client.get(
        "/api/v1/algorithm-templates",
        params={"module_id": "signal_optimization"},
        headers=_auth(s_token),
    )
    assert resp.status_code == 200
    templates = resp.json()
    assert any(t["id"] == template_id for t in templates)

    # 3. Student submits their own code
    resp = client.post(
        "/api/v1/algorithm-scripts",
        json={
            "task_id": task.id,
            "module_id": "signal_optimization",
            "code": "print('hello from student')\n",
        },
        headers=_auth(s_token),
    )
    assert resp.status_code == 201
    script = resp.json()
    script_id = script["id"]
    assert script["execution_status"] == "pending"

    # 4. Student executes the script
    resp = client.post(
        f"/api/v1/algorithm-scripts/{script_id}/execute",
        json={"timeout": 10},
        headers=_auth(s_token),
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["execution_status"] in ("completed", "error")
    assert result["stdout"] is not None
    assert result["exit_code"] is not None
    assert result["execution_duration"] is not None

    # 5. Student views the result
    resp = client.get(
        f"/api/v1/algorithm-scripts/{script_id}",
        headers=_auth(s_token),
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["stdout"] is not None
    assert "hello from student" in detail["stdout"]

    # 6. Teacher reviews student submissions for the task
    resp = client.get(
        "/api/v1/algorithm-scripts",
        params={"task_id": task.id, "student_id": student.id},
        headers=_auth(t_token),
    )
    assert resp.status_code == 200
    submissions = resp.json()
    assert len(submissions) >= 1
    assert submissions[0]["code"]  # teacher can see the code
    assert submissions[0]["stdout"] is not None
