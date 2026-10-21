from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrgCreate(BaseModel):
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    license_quota: int = 10


class OrgUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    license_quota: int | None = None


class OrgRead(BaseModel):
    id: int
    name: str
    contact_name: str | None
    contact_phone: str | None
    address: str | None
    license_quota: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrgDetail(OrgRead):
    license_count: int = 0
    active_license_count: int = 0
    user_count: int = 0
