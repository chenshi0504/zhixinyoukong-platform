"""
Algorithm template and student script models.
"""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class AlgorithmTemplate(Base):
    """教师创建的算法模板。"""

    __tablename__ = "algorithm_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(Text, nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    teacher = relationship("User", foreign_keys=[teacher_id])

    def __repr__(self):
        return f"<AlgorithmTemplate(id={self.id}, module='{self.module_id}', name='{self.name}')>"


class ExecutionStatus:
    """脚本执行状态常量。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"


class AlgorithmScript(Base):
    """学生提交的算法脚本及执行结果。"""

    __tablename__ = "algorithm_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    module_id = Column(String(50), nullable=False)
    code = Column(Text, nullable=False)
    # 执行结果
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)
    execution_duration = Column(Float, nullable=True)
    execution_status = Column(String(20), default=ExecutionStatus.PENDING)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)

    student = relationship("User", foreign_keys=[student_id])
    task = relationship("Task", foreign_keys=[task_id])

    def __repr__(self):
        return f"<AlgorithmScript(id={self.id}, student={self.student_id}, status='{self.execution_status}')>"
