"""
班级管理路由：CRUD、学生管理。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models.classroom import Class, student_classes
from ..models.user import User
from ..schemas.classroom import (
    ClassCreate, ClassUpdate, ClassRead, ClassDetail, ClassStudentOp, StudentBrief,
)
from ..schemas.common import PagedResponse

router = APIRouter(prefix="/api/cloud/classes", tags=["班级管理"])


def _get_accessible_class(db: Session, class_id: int, current_user: User) -> Class:
    q = db.query(Class).filter(Class.id == class_id)
    if current_user.role == "org_admin":
        q = q.filter(Class.org_id == current_user.org_id)
    elif current_user.role == "teacher":
        q = q.filter(Class.teacher_id == current_user.id)
    cls = q.first()
    if cls is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    return cls


# ---------- CRUD ----------

@router.get("", response_model=PagedResponse[ClassRead])
def list_classes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    q = db.query(Class)
    if current_user.role == "org_admin":
        q = q.filter(Class.org_id == current_user.org_id)
    elif current_user.role == "teacher":
        q = q.filter(Class.teacher_id == current_user.id)
    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(Class.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
def create_class(
    body: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    org_id = body.org_id
    if current_user.role in ("org_admin", "teacher"):
        org_id = current_user.org_id
    if org_id is None:
        raise HTTPException(status_code=400, detail="请选择所属机构")
    cls = Class(
        name=body.name,
        description=body.description,
        org_id=org_id,
        teacher_id=current_user.id,
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)
    return cls


@router.get("/{class_id}", response_model=ClassDetail)
def get_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    cls = _get_accessible_class(db, class_id, current_user)
    students = [StudentBrief.model_validate(s) for s in cls.students]
    return ClassDetail(
        id=cls.id, name=cls.name, org_id=cls.org_id, teacher_id=cls.teacher_id,
        description=cls.description, created_at=cls.created_at, updated_at=cls.updated_at,
        students=students,
    )


@router.put("/{class_id}", response_model=ClassRead)
def update_class(
    class_id: int,
    body: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    cls = _get_accessible_class(db, class_id, current_user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cls, k, v)
    db.commit()
    db.refresh(cls)
    return cls


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    cls = _get_accessible_class(db, class_id, current_user)
    db.delete(cls)
    db.commit()


# ---------- 学生管理 ----------

@router.post("/{class_id}/students", response_model=ClassDetail)
def add_students(
    class_id: int,
    body: ClassStudentOp,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    """向班级批量添加学生"""
    cls = _get_accessible_class(db, class_id, current_user)

    existing_ids = {s.id for s in cls.students}
    users = db.query(User).filter(
        User.id.in_(body.student_ids),
        User.role == "student",
        User.org_id == cls.org_id,
    ).all()
    for u in users:
        if u.id not in existing_ids:
            cls.students.append(u)
    db.commit()
    db.refresh(cls)

    students = [StudentBrief.model_validate(s) for s in cls.students]
    return ClassDetail(
        id=cls.id, name=cls.name, org_id=cls.org_id, teacher_id=cls.teacher_id,
        description=cls.description, created_at=cls.created_at, updated_at=cls.updated_at,
        students=students,
    )


@router.delete("/{class_id}/students", response_model=ClassDetail)
def remove_students(
    class_id: int,
    body: ClassStudentOp,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    """从班级批量移除学生"""
    cls = _get_accessible_class(db, class_id, current_user)

    remove_set = set(body.student_ids)
    cls.students = [s for s in cls.students if s.id not in remove_set]
    db.commit()
    db.refresh(cls)

    students = [StudentBrief.model_validate(s) for s in cls.students]
    return ClassDetail(
        id=cls.id, name=cls.name, org_id=cls.org_id, teacher_id=cls.teacher_id,
        description=cls.description, created_at=cls.created_at, updated_at=cls.updated_at,
        students=students,
    )


@router.get("/{class_id}/students", response_model=list[StudentBrief])
def list_class_students(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    """获取班级的学生列表"""
    cls = _get_accessible_class(db, class_id, current_user)
    return [StudentBrief.model_validate(s) for s in cls.students]
