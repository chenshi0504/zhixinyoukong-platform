import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480   # 8 小时
    refresh_token_expire_days: int = 7
    rsa_private_key_path: str = ""
    upload_dir: str = "./uploads"
    self_algorithm_ai_api_url: str = "https://api.deepseek.com/v1/chat/completions"
    self_algorithm_ai_api_key: str = ""
    self_algorithm_ai_model: str = "deepseek-v4-pro"
    self_algorithm_ai_reasoning_effort: str = "max"
    self_algorithm_ai_timeout_seconds: int = 20

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
