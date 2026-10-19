from datetime import datetime
from pydantic import BaseModel, ConfigDict


class LicenseCreate(BaseModel):
    org_id: int
    license_type: str  # trial / education / permanent


class LicenseRead(BaseModel):
    id: int
    license_key: str
    org_id: int | None
    license_type: str
    machine_id: str | None
    is_active: bool
    activated_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LicenseActivateRequest(BaseModel):
    machine_id: str
    license_key: str


class LicenseActivateResponse(BaseModel):
    activation_token: str
    expires_at: datetime | None
    license_type: str


class LicenseVerifyRequest(BaseModel):
    activation_token: str


class LicenseVerifyResponse(BaseModel):
    is_active: bool
    license_type: str | None = None
    expires_at: datetime | None = None
    machine_id: str | None = None
