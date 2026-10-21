from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class UpdateCreate(BaseModel):
    version: str
    release_date: date
    release_notes: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    is_mandatory: bool = False


class UpdateRead(BaseModel):
    id: int
    version: str
    release_date: date
    release_notes: str | None
    download_url: str | None
    file_size: int | None
    is_mandatory: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateCheckResponse(BaseModel):
    up_to_date: bool
    latest: UpdateRead | None = None
