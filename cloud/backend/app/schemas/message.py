from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MessageCreate(BaseModel):
    title: str
    content: str
    class_id: int


class MessageRead(BaseModel):
    id: int
    title: str
    content: str
    org_id: int | None
    class_id: int
    sender_id: int
    created_at: datetime
    class_name: str | None = None
    sender_name: str | None = None
    read: bool = False

    model_config = ConfigDict(from_attributes=True)
