"""
数据同步路由：供 Local_Client 调用。
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.task import Task
from ..models.user import User
from ..models.report import Report
from ..schemas.task import TaskRead
from ..schemas.user import UserRead
from ..schemas.report import ReportRead

router = APIRouter(prefix="/api/cloud/sync", tags=["数据同步"])


@router.get("/tasks", response_model=list[TaskRead])
def sync_tasks(
    since: datetime = Query(...),
    org_id: int = Query(...),
    db: Session = Depends(get_db),
):
    tasks = (
        db.query(Task)
        .filter(Task.org_id == org_id, Task.status == "published", Task.updated_at > since)
        .order_by(Task.updated_at)
        .all()
    )
    return tasks


@router.get("/users", response_model=list[UserRead])
def sync_users(
    since: datetime = Query(...),
    org_id: int = Query(...),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .filter(User.org_id == org_id, User.updated_at > since)
        .order_by(User.updated_at)
        .all()
    )
    return users


@router.get("/grades", response_model=list[ReportRead])
def sync_grades(
    since: datetime = Query(...),
    student_id: int = Query(...),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(Report)
        .filter(
            Report.student_id == student_id,
            Report.status == "graded",
            Report.graded_at > since,
        )
        .order_by(Report.graded_at)
        .all()
    )
    return reports
