"""
Report service for managing student submissions and grading.
"""
import os
import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, UploadFile

from ..config import settings
from ..models import Report, ReportStatus, Task, TaskStatus, User, UserRole
from ..schemas import ReportGrade


def get_report_by_id(db: Session, report_id: int) -> Optional[Report]:
    """Get a report by ID."""
    return db.query(Report).filter(Report.id == report_id).first()


def get_reports_by_task(db: Session, task_id: int) -> List[Report]:
    """Get all reports for a task."""
    return db.query(Report).filter(Report.task_id == task_id).order_by(Report.submitted_at.desc()).all()


def get_reports_by_student(db: Session, student_id: int) -> List[Report]:
    """Get all reports submitted by a student."""
    return db.query(Report).filter(Report.student_id == student_id).order_by(Report.submitted_at.desc()).all()


def get_pending_reports(db: Session) -> List[Report]:
    """Get all ungraded reports."""
    return db.query(Report).filter(Report.status == ReportStatus.SUBMITTED).order_by(Report.submitted_at.asc()).all()


def get_reports_by_user_role(db: Session, user: User, task_id: Optional[int] = None) -> List[Report]:
    """Get reports based on user role."""
    query = db.query(Report)
    
    if task_id:
        query = query.filter(Report.task_id == task_id)
    
    if user.role == UserRole.STUDENT.value:
        query = query.filter(Report.student_id == user.id)
    
    return query.order_by(Report.submitted_at.desc()).all()


async def submit_report(
    db: Session,
    task_id: int,
    student_id: int,
    file: UploadFile
) -> Report:
    """Submit a report for a task."""
    # Check if task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_002",
                "message": "任务不存在",
                "suggestion": "请检查任务ID是否正确"
            }
        )
    
    # Check if task is closed
    if task.status == TaskStatus.CLOSED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BIZ_001",
                "message": "任务已关闭，无法提交",
                "suggestion": "请联系教师了解情况"
            }
        )
    
    # Check if task is published
    if task.status != TaskStatus.PUBLISHED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BIZ_003",
                "message": "任务尚未发布",
                "suggestion": "请等待教师发布任务"
            }
        )
    
    # Validate file extension
    file_ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BIZ_101",
                "message": "不支持的文件格式",
                "suggestion": f"请上传以下格式的文件: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            }
        )
    
    # Check file size
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BIZ_102",
                "message": "文件大小超出限制",
                "suggestion": f"文件大小不能超过 {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB"
            }
        )
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)
    
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Check if late submission
    is_late = False
    if task.deadline:
        is_late = datetime.now(timezone.utc) > task.deadline.replace(tzinfo=timezone.utc)
    
    # Check for existing report (resubmission)
    existing_report = db.query(Report).filter(
        Report.task_id == task_id,
        Report.student_id == student_id
    ).first()
    
    if existing_report:
        # Update existing report (resubmission)
        # Delete old file if exists
        if os.path.exists(existing_report.file_path):
            os.remove(existing_report.file_path)
        
        existing_report.file_path = file_path
        existing_report.file_name = file.filename
        existing_report.submitted_at = datetime.now(timezone.utc)
        existing_report.is_late = is_late
        existing_report.status = ReportStatus.SUBMITTED
        existing_report.score = None
        existing_report.feedback = None
        existing_report.graded_at = None
        existing_report.graded_by = None
        
        db.commit()
        db.refresh(existing_report)
        return existing_report
    
    # Create new report
    report = Report(
        task_id=task_id,
        student_id=student_id,
        file_path=file_path,
        file_name=file.filename,
        is_late=is_late,
        status=ReportStatus.SUBMITTED
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def grade_report(
    db: Session,
    report_id: int,
    grade_data: ReportGrade,
    grader: User
) -> Report:
    """Grade a report."""
    report = get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_003",
                "message": "报告不存在",
                "suggestion": "请检查报告ID是否正确"
            }
        )
    
    # Update grading info
    report.score = grade_data.score
    report.feedback = grade_data.feedback
    report.status = ReportStatus.GRADED
    report.graded_at = datetime.now(timezone.utc)
    report.graded_by = grader.id
    
    db.commit()
    db.refresh(report)
    return report
