"""
班级消息路由：教师按班级发布，教师和班级学生可见。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models.classroom import Class, student_classes
from ..models.message import Message, MessageRead as MessageReadModel
from ..models.user import User
from ..schemas.common import PagedResponse
from ..schemas.message import MessageCreate, MessageRead

router = APIRouter(prefix="/api/cloud/messages", tags=["班级消息"])


def _student_class_ids(db: Session, user_id: int) -> list[int]:
    rows = db.execute(
        student_classes.select().where(student_classes.c.student_id == user_id)
    ).fetchall()
    return [row.class_id for row in rows]


def _message_to_read(db: Session, msg: Message, current_user: User) -> MessageRead:
    data = MessageRead.model_validate(msg)
    if current_user.role == "student":
        data.read = db.query(MessageReadModel).filter(
            MessageReadModel.message_id == msg.id,
            MessageReadModel.user_id == current_user.id,
        ).first() is not None
    else:
        data.read = True
    return data


@router.get("", response_model=PagedResponse[MessageRead])
def list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    class_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Message)
    if current_user.role == "teacher":
        q = q.join(Class, Message.class_id == Class.id).filter(Class.teacher_id == current_user.id)
    elif current_user.role == "student":
        class_ids = _student_class_ids(db, current_user.id)
        if not class_ids:
            return PagedResponse(items=[], total=0, page=page, page_size=page_size, pages=1)
        q = q.filter(Message.class_id.in_(class_ids))
    elif current_user.role == "org_admin":
        q = q.filter(Message.org_id == current_user.org_id)
    elif current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")

    if class_id:
        q = q.filter(Message.class_id == class_id)

    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    rows = q.order_by(Message.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [_message_to_read(db, row, current_user) for row in rows]
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message(
    body: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("teacher", "org_admin", "super_admin")),
):
    cls = db.query(Class).filter(Class.id == body.class_id).first()
    if cls is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    if current_user.role == "teacher" and cls.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能向自己管理的班级发布消息")
    if current_user.role == "org_admin" and cls.org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="只能向本机构班级发布消息")

    title = body.title.strip()
    content = body.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="标题和内容不能为空")

    msg = Message(
        title=title,
        content=content,
        org_id=cls.org_id,
        class_id=cls.id,
        sender_id=current_user.id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _message_to_read(db, msg, current_user)


@router.post("/{message_id}/read", response_model=MessageRead)
def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("student")),
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if msg.class_id not in _student_class_ids(db, current_user.id):
        raise HTTPException(status_code=403, detail="无权查看该消息")

    existing = db.query(MessageReadModel).filter(
        MessageReadModel.message_id == message_id,
        MessageReadModel.user_id == current_user.id,
    ).first()
    if existing is None:
        db.add(MessageReadModel(message_id=message_id, user_id=current_user.id))
        db.commit()
    db.refresh(msg)
    return _message_to_read(db, msg, current_user)
