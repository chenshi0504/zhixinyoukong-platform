"""
Application configuration settings.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional

# 确保数据库文件始终在 backend/ 目录下
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BACKEND_DIR, "data.db")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = f"sqlite:///{_DB_PATH}"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # File Upload
    UPLOAD_DIR: str = os.path.join(_BACKEND_DIR, "uploads")
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: set = {"pdf", "docx", "doc"}
    
    # Application
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    APP_NAME: str = "综合交通实验教学平台"
    APP_VERSION: str = "3.4.3"

    CLOUD_API_URL: str = "http://127.0.0.1:9100"
    CLOUD_API_VERIFY_SSL: bool = False
    LOCAL_APP_HOST: str = "0.0.0.0"
    LOCAL_APP_PORT: int = 8000

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "debug", "dev", "development"}:
            return True
        if text in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
