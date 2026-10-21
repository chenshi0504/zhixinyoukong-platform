"""
Task service for managing experiment assignments.
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..models import Task, TaskStatus, User, UserRole
from ..schemas import TaskCreate, TaskUpdate


def create_task(db: Session, task_data: TaskCreate, teacher_id: int) -> Task:
    """Create a new task."""
    task = Task(
        title=task_data.title,
        description=task_data.description,
        module_id=task_data.module_id,
        deadline=task_data.deadline,
        scoring_criteria=task_data.scoring_criteria,
        teacher_id=teacher_id,
        status=TaskStatus.DRAFT.value
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task_by_id(db: Session, task_id: int) -> Optional[Task]:
    """Get a task by ID."""
    return db.query(Task).filter(Task.id == task_id).first()


def get_tasks_for_teacher(db: Session, teacher_id: int) -> List[Task]:
    """Get all tasks created by a teacher."""
    return db.query(Task).filter(Task.teacher_id == teacher_id).order_by(Task.created_at.desc()).all()


def get_all_tasks(db: Session) -> List[Task]:
    """Get all tasks (for admin)."""
    return db.query(Task).order_by(Task.created_at.desc()).all()


def get_published_tasks(db: Session) -> List[Task]:
    """Get all published tasks (for students)."""
    return db.query(Task).filter(Task.status == TaskStatus.PUBLISHED.value).order_by(Task.created_at.desc()).all()


def get_tasks_by_user_role(db: Session, user: User) -> List[Task]:
    """Get tasks based on user role."""
    if user.role == UserRole.ADMIN.value:
        return get_all_tasks(db)
    elif user.role == UserRole.TEACHER.value:
        return get_all_tasks(db)  # Teachers can see all tasks
    else:  # Student
        return get_published_tasks(db)


def update_task(db: Session, task_id: int, task_data: TaskUpdate, user: User) -> Task:
    """Update a task."""
    task = get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_002",
                "message": "任务不存在",
                "suggestion": "请检查任务ID是否正确"
            }
        )
    
    # Check permission: only the creator or admin can update
    if user.role != UserRole.ADMIN.value and task.teacher_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权修改此任务",
                "suggestion": "只有任务创建者或管理员可以修改任务"
            }
        )
    
    # Update fields if provided
    update_data = task_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: int, user: User) -> bool:
    """Delete a task."""
    task = get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_002",
                "message": "任务不存在",
                "suggestion": "请检查任务ID是否正确"
            }
        )
    
    # Check permission
    if user.role != UserRole.ADMIN.value and task.teacher_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权删除此任务",
                "suggestion": "只有任务创建者或管理员可以删除任务"
            }
        )
    
    db.delete(task)
    db.commit()
    return True


def publish_task(db: Session, task_id: int, user: User) -> Task:
    """Publish a task to make it visible to students."""
    task = get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_002",
                "message": "任务不存在",
                "suggestion": "请检查任务ID是否正确"
            }
        )
    
    # Check permission
    if user.role != UserRole.ADMIN.value and task.teacher_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权发布此任务",
                "suggestion": "只有任务创建者或管理员可以发布任务"
            }
        )
    
    if task.status == TaskStatus.CLOSED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BIZ_003",
                "message": "已关闭的任务无法重新发布",
                "suggestion": "请创建新任务"
            }
        )
    
    task.status = TaskStatus.PUBLISHED.value
    db.commit()
    db.refresh(task)
    return task


def close_task(db: Session, task_id: int, user: User) -> Task:
    """Close a task to prevent further submissions."""
    task = get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_002",
                "message": "任务不存在",
                "suggestion": "请检查任务ID是否正确"
            }
        )
    
    # Check permission
    if user.role != UserRole.ADMIN.value and task.teacher_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权关闭此任务",
                "suggestion": "只有任务创建者或管理员可以关闭任务"
            }
        )
    
    task.status = TaskStatus.CLOSED.value
    db.commit()
    db.refresh(task)
    return task
