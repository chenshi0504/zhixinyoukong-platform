"""
Class model for local experiment platform.
Mirrors the cloud Class model for offline sync.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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
    """班级模型（本地端，从云端同步）"""

    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    description = Column(String(500), nullable=True)
    cloud_id = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    teacher = relationship("User", backref="managed_classes", foreign_keys=[teacher_id])
    students = relationship("User", secondary=student_classes, backref="enrolled_classes")
    tasks = relationship("Task", back_populates="assigned_class")

    def __repr__(self):
        return f"<Class(id={self.id}, name='{self.name}')>"
