"""
Report module tests.
"""
import pytest
import io
from fastapi import status
from datetime import datetime, timedelta, timezone

from app.models import Task, TaskStatus, Report, ReportStatus


class TestReportSubmission:
    """Tests for report submission."""
    
    def test_submit_report_success(self, client, student_token, db, test_teacher):
        """Test successful report submission."""
        # Create a published task
        task = Task(
            title="测试任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Create a test file
        file_content = b"Test report content"
        files = {"file": ("test_report.pdf", io.BytesIO(file_content), "application/pdf")}
        
        response = client.post(
            f"/api/v1/reports?task_id={task.id}",
            headers={"Authorization": f"Bearer {student_token}"},
            files=files
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["task_id"] == task.id
        assert data["file_name"] == "test_report.pdf"
        assert data["status"] == "submitted"
    
    def test_submit_report_to_closed_task(self, client, student_token, db, test_teacher):
        """Test that submission to closed task is rejected."""
        task = Task(
            title="已关闭任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.CLOSED.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        file_content = b"Test report content"
        files = {"file": ("test_report.pdf", io.BytesIO(file_content), "application/pdf")}
        
        response = client.post(
            f"/api/v1/reports?task_id={task.id}",
            headers={"Authorization": f"Bearer {student_token}"},
            files=files
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["detail"]["code"] == "BIZ_001"
    
    def test_submit_report_invalid_format(self, client, student_token, db, test_teacher):
        """Test that invalid file format is rejected."""
        task = Task(
            title="测试任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        file_content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
        
        response = client.post(
            f"/api/v1/reports?task_id={task.id}",
            headers={"Authorization": f"Bearer {student_token}"},
            files=files
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["detail"]["code"] == "BIZ_101"


class TestLateSubmission:
    """Tests for late submission detection."""
    
    def test_late_submission_detected(self, client, student_token, db, test_teacher):
        """Test that late submissions are marked correctly."""
        # Create a task with past deadline
        past_deadline = datetime.now(timezone.utc) - timedelta(days=1)
        task = Task(
            title="已过期任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value,
            deadline=past_deadline
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        file_content = b"Late report content"
        files = {"file": ("late_report.pdf", io.BytesIO(file_content), "application/pdf")}
        
        response = client.post(
            f"/api/v1/reports?task_id={task.id}",
            headers={"Authorization": f"Bearer {student_token}"},
            files=files
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["is_late"] == True


class TestReportGrading:
    """Tests for report grading."""
    
    def test_grade_report_success(self, client, teacher_token, db, test_teacher, test_student):
        """Test successful report grading."""
        task = Task(
            title="测试任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        report = Report(
            task_id=task.id,
            student_id=test_student.id,
            file_path="/fake/path.pdf",
            file_name="report.pdf",
            status=ReportStatus.SUBMITTED
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        
        response = client.put(
            f"/api/v1/reports/{report.id}/grade",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={"score": 85.5, "feedback": "做得不错"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["score"] == 85.5
        assert data["feedback"] == "做得不错"
        assert data["status"] == "graded"
    
    def test_get_pending_reports(self, client, teacher_token, db, test_teacher, test_student):
        """Test getting pending reports."""
        task = Task(
            title="测试任务",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Create submitted and graded reports
        submitted_report = Report(
            task_id=task.id,
            student_id=test_student.id,
            file_path="/fake/path1.pdf",
            file_name="report1.pdf",
            status=ReportStatus.SUBMITTED
        )
        graded_report = Report(
            task_id=task.id,
            student_id=test_student.id,
            file_path="/fake/path2.pdf",
            file_name="report2.pdf",
            status=ReportStatus.GRADED,
            score=90
        )
        db.add(submitted_report)
        db.add(graded_report)
        db.commit()
        
        response = client.get(
            "/api/v1/reports/pending",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        reports = response.json()
        
        # Only submitted reports should be returned
        for report in reports:
            assert report["status"] == "submitted"
