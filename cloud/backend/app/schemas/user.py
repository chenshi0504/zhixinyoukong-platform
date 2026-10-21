from datetime import datetime
from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    password: str
    role: str  # super_admin / org_admin / teacher / student
    real_name: str | None = None
    org_id: int | None = None


class UserUpdate(BaseModel):
    real_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    id: int
    username: str
    role: str
    real_name: str | None
    org_id: int | None
    org_name: str | None = None
    class_name: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class TeacherRegisterRequest(BaseModel):
    real_name: str
    org_id: int
    password: str


class TeacherRegisterResponse(BaseModel):
    username: str
    real_name: str
    org_name: str
    message: str = "注册成功"


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str
    reason: str | None = None


class PasswordResetRequest(BaseModel):
    new_password: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StudentRegisterRequest(BaseModel):
    org_id: int
    class_id: int
    real_name: str
    password: str


class StudentRegisterResponse(BaseModel):
    username: str
    real_name: str
    role: str
    class_name: str | None = None
    student_id: str | None = None
    message: str = "注册成功"
