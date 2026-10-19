from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("licenses.id"))
    sync_type: Mapped[str | None] = mapped_column(String(50))   # tasks/users/reports/analytics
    direction: Mapped[str | None] = mapped_column(String(10))   # upload/download
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str | None] = mapped_column(String(20))      # success/error
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    license: Mapped["License"] = relationship("License", back_populates="sync_logs")
