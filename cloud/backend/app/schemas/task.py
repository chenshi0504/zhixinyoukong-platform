from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    module_id: str | None = None
    org_id: int | None = None
    class_id: int | None = None
    deadline: datetime | None = None
    max_score: int = 100


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    module_id: str | None = None
    class_id: int | None = None
    deadline: datetime | None = None
    max_score: int | None = None


class TaskRead(BaseModel):
    id: int
    title: str
    description: str | None
    module_id: str | None
    teacher_id: int | None
    org_id: int | None
    class_id: int | None
    deadline: datetime | None
    max_score: int
    status: str
    created_at: datetime
    updated_at: datetime
    class_name: str | None = None
    teacher_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
