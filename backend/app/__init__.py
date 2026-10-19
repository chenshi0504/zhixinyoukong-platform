"""
综合交通实验教学平台后端应用
"""
from .config import settings
from .database import Base, get_db, init_db

__all__ = ["settings", "Base", "get_db", "init_db"]
