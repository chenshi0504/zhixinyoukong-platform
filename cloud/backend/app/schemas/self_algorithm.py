from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SelfAlgorithmPack(BaseModel):
    algorithm_type: str
    label: str
    description: str
    baseline_file: str | None = None
    primary_metric: str | None = None
    input_files: list[str] = []
    submission_columns: list[str] = []
    download_name: str


class SelfAlgorithmSubmissionRead(BaseModel):
    id: int
    algorithm_type: str
    org_id: int | None
    class_id: int | None
    task_id: int | None = None
    student_id: int
    org_name: str | None = None
    class_name: str | None = None
    task_title: str | None = None
    student_name: str | None = None
    code_original_filename: str | None
    code_file_size: int | None
    spec_original_filename: str | None
    spec_file_size: int | None
    process_original_filename: str | None = None
    process_file_size: int | None = None
    result_original_filename: str | None
    result_file_size: int | None
    analysis_status: str
    analysis_provider: str
    analysis_text: str | None
    analysis: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
