"""
Experiment record model for tracking student experiment progress.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class ExperimentStatus(str):
    """Experiment status constants."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ExperimentRecord(Base):
    """Experiment record model for tracking student experiment progress."""
    
    __tablename__ = "experiment_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    module_id = Column(String(50), nullable=False)
    operation_log = Column(Text, nullable=True)  # JSON string
    result_data = Column(Text, nullable=True)    # JSON string
    status = Column(String(20), default=ExperimentStatus.IN_PROGRESS)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    task = relationship("Task", back_populates="experiment_records")
    student = relationship("User", back_populates="experiment_records")
    
    def __repr__(self):
        return f"<ExperimentRecord(id={self.id}, student_id={self.student_id}, module_id='{self.module_id}', status='{self.status}')>"
