from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"))
    license_type: Mapped[str] = mapped_column(String(20), nullable=False)  # trial/education/permanent
    machine_id: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship("Organization", back_populates="licenses")
    sync_logs: Mapped[list["SyncLog"]] = relationship("SyncLog", back_populates="license")
    analytics: Mapped[list["Analytics"]] = relationship("Analytics", back_populates="license")
