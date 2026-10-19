"""
Experiment record service for tracking student experiment progress.
"""
import json
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..models import ExperimentRecord, ExperimentStatus, Task


def start_experiment(
    db: Session,
    student_id: int,
    module_id: str,
    task_id: Optional[int] = None
) -> ExperimentRecord:
    """Start a new experiment and create a record."""
    # Validate task if provided
    if task_id:
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

    record = ExperimentRecord(
        task_id=task_id,
        student_id=student_id,
        module_id=module_id,
        operation_log=json.dumps([], ensure_ascii=False),
        result_data=None,
        status=ExperimentStatus.IN_PROGRESS
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def log_operation(
    db: Session,
    record_id: int,
    student_id: int,
    operation: dict
) -> ExperimentRecord:
    """Log an operation to an experiment record."""
    record = db.query(ExperimentRecord).filter(
        ExperimentRecord.id == record_id
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_004",
                "message": "实验记录不存在",
                "suggestion": "请检查实验记录ID是否正确"
            }
        )

    if record.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权操作此实验记录",
                "suggestion": "您只能操作自己的实验记录"
            }
        )

    if record.status == ExperimentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BIZ_004",
                "message": "实验已完成，无法继续记录",
                "suggestion": "请开始新的实验"
            }
        )

    # Append operation to log
    logs = json.loads(record.operation_log) if record.operation_log else []
    operation["timestamp"] = datetime.now(timezone.utc).isoformat()
    logs.append(operation)
    record.operation_log = json.dumps(logs, ensure_ascii=False)

    db.commit()
    db.refresh(record)
    return record


def complete_experiment(
    db: Session,
    record_id: int,
    student_id: int,
    result_data: Optional[dict] = None
) -> ExperimentRecord:
    """Complete an experiment and save final results."""
    record = db.query(ExperimentRecord).filter(
        ExperimentRecord.id == record_id
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_004",
                "message": "实验记录不存在",
                "suggestion": "请检查实验记录ID是否正确"
            }
        )

    if record.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权操作此实验记录",
                "suggestion": "您只能操作自己的实验记录"
            }
        )

    record.status = ExperimentStatus.COMPLETED
    record.completed_at = datetime.now(timezone.utc)
    if result_data:
        record.result_data = json.dumps(result_data, ensure_ascii=False)

    db.commit()
    db.refresh(record)
    return record


def get_experiment_by_id(db: Session, record_id: int) -> Optional[ExperimentRecord]:
    """Get an experiment record by ID."""
    return db.query(ExperimentRecord).filter(ExperimentRecord.id == record_id).first()


def get_experiments_by_student(db: Session, student_id: int) -> List[ExperimentRecord]:
    """Get all experiment records for a student."""
    return db.query(ExperimentRecord).filter(
        ExperimentRecord.student_id == student_id
    ).order_by(ExperimentRecord.started_at.desc()).all()


def get_experiments_by_task(db: Session, task_id: int) -> List[ExperimentRecord]:
    """Get all experiment records for a task."""
    return db.query(ExperimentRecord).filter(
        ExperimentRecord.task_id == task_id
    ).order_by(ExperimentRecord.started_at.desc()).all()
