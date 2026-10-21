from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    module_id: Mapped[str | None] = mapped_column(String(50))
    teacher_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"), index=True)
    class_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classes.id"), index=True, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/published
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    teacher: Mapped["User"] = relationship("User", back_populates="tasks", foreign_keys=[teacher_id])
    assigned_class: Mapped["Class"] = relationship("Class", back_populates="tasks")
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="task")

    @property
    def class_name(self) -> str | None:
        return self.assigned_class.name if self.assigned_class else None

    @property
    def teacher_name(self) -> str | None:
        if not self.teacher:
            return None
        return self.teacher.real_name or self.teacher.username
