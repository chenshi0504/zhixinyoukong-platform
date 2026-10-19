from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Text, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class SoftwareUpdate(Base):
    __tablename__ = "software_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    release_notes: Mapped[str | None] = mapped_column(Text)
    download_url: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
