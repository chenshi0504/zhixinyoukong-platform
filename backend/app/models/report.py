"""
Report model for student submissions.
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class ReportStatus(str):
    """Report status constants."""
    SUBMITTED = "submitted"
    GRADED = "graded"


class Report(Base):
    """Report model for storing student submissions."""
    
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    score = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    status = Column(String(20), default=ReportStatus.SUBMITTED)
    is_late = Column(Boolean, default=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    graded_at = Column(DateTime(timezone=True), nullable=True)
    graded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    task = relationship("Task", back_populates="reports")
    student = relationship("User", back_populates="reports", foreign_keys=[student_id])
    grader = relationship("User", back_populates="graded_reports", foreign_keys=[graded_by])
    
    def __repr__(self):
        return f"<Report(id={self.id}, task_id={self.task_id}, student_id={self.student_id}, status='{self.status}')>"
