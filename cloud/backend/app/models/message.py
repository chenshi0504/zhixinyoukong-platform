from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"), index=True)
    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"), index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped["Organization"] = relationship("Organization")
    classroom: Mapped["Class"] = relationship("Class")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    reads: Mapped[list["MessageRead"]] = relationship(
        "MessageRead", back_populates="message", cascade="all, delete-orphan"
    )

    @property
    def class_name(self) -> str | None:
        return self.classroom.name if self.classroom else None

    @property
    def sender_name(self) -> str | None:
        if not self.sender:
            return None
        return self.sender.real_name or self.sender.username


class MessageRead(Base):
    __tablename__ = "message_reads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    message: Mapped["Message"] = relationship("Message", back_populates="reads")
    user: Mapped["User"] = relationship("User")
