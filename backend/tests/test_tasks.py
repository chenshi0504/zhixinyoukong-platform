"""
Task management module tests.
"""
import pytest
from fastapi import status

from app.models import Task, TaskStatus
from app.services.auth import get_password_hash


class TestTaskCreation:
    """Tests for task creation."""
    
    def test_create_task_as_teacher(self, client, teacher_token):
        """Test creating a task as a teacher."""
        response = client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "title": "测试任务",
                "description": "这是一个测试任务",
                "module_id": "test_module"
            }
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title"] == "测试任务"
        assert data["status"] == "draft"
    
    def test_create_task_as_student_forbidden(self, client, student_token):
        """Test that students cannot create tasks."""
        response = client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"title": "学生任务", "description": "不应该成功"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestTaskUpdate:
    """Tests for task update."""
    
    def test_update_task(self, client, teacher_token, db, test_teacher):
        """Test updating a task."""
        # Create a task first
        task = Task(
            title="原始标题",
            description="原始描述",
            teacher_id=test_teacher.id,
            status=TaskStatus.DRAFT.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        response = client.put(
            f"/api/v1/tasks/{task.id}",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={"title": "更新后的标题"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "更新后的标题"


class TestTaskStatusTransition:
    """Tests for task status transitions."""
    
    def test_publish_task(self, client, teacher_token, db, test_teacher):
        """Test publishing a draft task."""
        task = Task(
            title="待发布任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.DRAFT.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        response = client.post(
            f"/api/v1/tasks/{task.id}/publish",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "published"
    
    def test_close_task(self, client, teacher_token, db, test_teacher):
        """Test closing a published task."""
        task = Task(
            title="待关闭任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        response = client.post(
            f"/api/v1/tasks/{task.id}/close",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "closed"


class TestStudentTaskVisibility:
    """Tests for student task visibility."""
    
    def test_student_sees_only_published_tasks(self, client, student_token, db, test_teacher):
        """Test that students only see published tasks."""
        # Create draft and published tasks
        draft_task = Task(
            title="草稿任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.DRAFT.value
        )
        published_task = Task(
            title="已发布任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value
        )
        db.add(draft_task)
        db.add(published_task)
        db.commit()
        
        response = client.get(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        tasks = response.json()
        
        # Student should only see published tasks
        for task in tasks:
            assert task["status"] == "published"
    
    def test_student_cannot_view_draft_task(self, client, student_token, db, test_teacher):
        """Test that students cannot view draft tasks directly."""
        task = Task(
            title="草稿任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.DRAFT.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        response = client.get(
            f"/api/v1/tasks/{task.id}",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_teacher_sees_all_tasks(self, client, teacher_token, db, test_teacher):
        """Test that teachers can see all tasks."""
        # Create tasks with different statuses
        for task_status in [TaskStatus.DRAFT.value, TaskStatus.PUBLISHED.value, TaskStatus.CLOSED.value]:
            task = Task(
                title=f"任务-{task_status}",
                teacher_id=test_teacher.id,
                status=task_status
            )
            db.add(task)
        db.commit()
        
        response = client.get(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        tasks = response.json()
        
        # Teacher should see tasks with all statuses
        statuses = {task["status"] for task in tasks}
        assert "draft" in statuses
        assert "published" in statuses
        assert "closed" in statuses
