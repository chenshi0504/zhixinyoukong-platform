"""
Task model for experiment assignments.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from ..database import Base


class TaskStatus(str, enum.Enum):
    """Task status enumeration."""
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class Task(Base):
    """Task model for storing experiment assignments."""
    
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    module_id = Column(String(50), nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default=TaskStatus.DRAFT.value)
    scoring_criteria = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    teacher = relationship("User", back_populates="tasks", foreign_keys=[teacher_id])
    reports = relationship("Report", back_populates="task")
    experiment_records = relationship("ExperimentRecord", back_populates="task")
    
    def __repr__(self):
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"
