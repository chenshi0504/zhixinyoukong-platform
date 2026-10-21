from datetime import datetime, date
from sqlalchemy import String, Integer, DateTime, Date, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from ..database import Base


class Analytics(Base):
    __tablename__ = "analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("licenses.id"), index=True)
    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"), index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    active_user_count: Mapped[int] = mapped_column(Integer, default=0)
    experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    # 使用 JSON 兼容 SQLite 和 PostgreSQL
    module_usage: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    license: Mapped["License"] = relationship("License", back_populates="analytics")
    organization: Mapped["Organization"] = relationship("Organization", back_populates="analytics")
