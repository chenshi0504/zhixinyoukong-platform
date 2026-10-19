from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, BigInteger, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tasks.id"), index=True)
    student_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    file_path: Mapped[str | None] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_type: Mapped[str | None] = mapped_column(String(20))  # data/report/config
    description: Mapped[str | None] = mapped_column(Text)
    is_independent: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否独立文件（不关联任务）
    score: Mapped[int | None] = mapped_column(Integer)          # 0-100
    feedback: Mapped[str | None] = mapped_column(Text)
    grader_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted/graded
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    graded_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="reports")
    student: Mapped["User"] = relationship("User", back_populates="reports_submitted", foreign_keys=[student_id])
    grader: Mapped["User"] = relationship("User", back_populates="reports_graded", foreign_keys=[grader_id])

    @property
    def task_title(self) -> str | None:
        return self.task.title if self.task else None

    @property
    def student_name(self) -> str | None:
        if not self.student:
            return None
        return self.student.real_name or self.student.username
