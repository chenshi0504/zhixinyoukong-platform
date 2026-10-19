from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # super_admin/org_admin/teacher/student
    real_name: Mapped[str | None] = mapped_column(String(50))
    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="teacher", foreign_keys="Task.teacher_id")
    reports_submitted: Mapped[list["Report"]] = relationship("Report", back_populates="student", foreign_keys="Report.student_id")
    reports_graded: Mapped[list["Report"]] = relationship("Report", back_populates="grader", foreign_keys="Report.grader_id")

    @property
    def org_name(self) -> str | None:
        return self.organization.name if self.organization else None

    @property
    def class_name(self) -> str | None:
        if self.enrolled_classes:
            return self.enrolled_classes[0].name
        if self.managed_classes:
            return self.managed_classes[0].name
        return None


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
