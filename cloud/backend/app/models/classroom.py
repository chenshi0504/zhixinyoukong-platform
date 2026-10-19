"""
班级模型：机构 → 班级 → 学生 的管理层级。
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Table, Column, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


# 学生-班级 多对多关联表
student_classes = Table(
    "student_classes",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", Integer, ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True),
    Column("joined_at", DateTime, server_default=func.now()),
)


class Class(Base):
    """班级"""
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"), index=True)
    teacher_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship("Organization", backref="classes")
    teacher: Mapped["User"] = relationship("User", backref="managed_classes", foreign_keys=[teacher_id])
    students: Mapped[list["User"]] = relationship(
        "User", secondary=student_classes, backref="enrolled_classes"
    )
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="assigned_class")
