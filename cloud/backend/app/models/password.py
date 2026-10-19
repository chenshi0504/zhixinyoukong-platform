from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class PasswordChangeRequest(Base):
    __tablename__ = "password_change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    reviewer: Mapped["User"] = relationship("User", foreign_keys=[reviewed_by_id])


class PasswordHistory(Base):
    __tablename__ = "password_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="unknown")
    changed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    request_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("password_change_requests.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    changed_by: Mapped["User"] = relationship("User", foreign_keys=[changed_by_id])
    request: Mapped["PasswordChangeRequest"] = relationship("PasswordChangeRequest")
