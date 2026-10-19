from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class ReportRead(BaseModel):
    id: int
    task_id: int | None
    student_id: int | None
    original_filename: str | None
    file_size: int | None
    file_type: str | None
    description: str | None
    is_independent: bool
    score: int | None
    feedback: str | None
    grader_id: int | None
    status: str
    submitted_at: datetime
    graded_at: datetime | None
    updated_at: datetime
    task_title: str | None = None
    student_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        model = super().model_validate(obj, *args, **kwargs)
        if getattr(obj, "task", None):
            model.task_title = obj.task.title
        if getattr(obj, "student", None):
            model.student_name = obj.student.real_name or obj.student.username
        return model


class GradeRequest(BaseModel):
    score: int
    feedback: str | None = None

    @field_validator("score")
    @classmethod
    def score_range(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError("score must be between 0 and 100")
        return v
