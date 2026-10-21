from datetime import datetime
import json

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class SelfAlgorithmSubmission(Base):
    """学生自研算法提交记录。"""

    __tablename__ = "self_algorithm_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    algorithm_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"), index=True)
    class_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classes.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tasks.id"), index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    code_file_path: Mapped[str | None] = mapped_column(String(500))
    code_original_filename: Mapped[str | None] = mapped_column(String(255))
    code_file_size: Mapped[int | None] = mapped_column(BigInteger)

    spec_file_path: Mapped[str | None] = mapped_column(String(500))
    spec_original_filename: Mapped[str | None] = mapped_column(String(255))
    spec_file_size: Mapped[int | None] = mapped_column(BigInteger)

    process_file_path: Mapped[str | None] = mapped_column(String(500))
    process_original_filename: Mapped[str | None] = mapped_column(String(255))
    process_file_size: Mapped[int | None] = mapped_column(BigInteger)

    result_file_path: Mapped[str | None] = mapped_column(String(500))
    result_original_filename: Mapped[str | None] = mapped_column(String(255))
    result_file_size: Mapped[int | None] = mapped_column(BigInteger)

    analysis_status: Mapped[str] = mapped_column(String(20), default="done")
    analysis_provider: Mapped[str] = mapped_column(String(30), default="builtin")
    analysis_text: Mapped[str | None] = mapped_column(Text)
    analysis_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship("Organization")
    classroom: Mapped["Class"] = relationship("Class")
    task: Mapped["Task"] = relationship("Task")
    student: Mapped["User"] = relationship("User")

    @property
    def org_name(self) -> str | None:
        return self.organization.name if self.organization else None

    @property
    def class_name(self) -> str | None:
        return self.classroom.name if self.classroom else None

    @property
    def student_name(self) -> str | None:
        if not self.student:
            return None
        return self.student.real_name or self.student.username

    @property
    def task_title(self) -> str | None:
        return self.task.title if self.task else None

    @property
    def analysis(self) -> dict | None:
        if not self.analysis_json:
            return None
        try:
            data = json.loads(self.analysis_json)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
