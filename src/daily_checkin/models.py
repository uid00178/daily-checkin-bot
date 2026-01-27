from __future__ import annotations

import enum
from datetime import datetime, date, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class ContactStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"


class DailyStateEnum(str, enum.Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    MISSED = "MISSED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    tg_chat_id: Mapped[int] = mapped_column(Integer, index=True)
    timezone: Mapped[str] = mapped_column(String(64))
    checkin_time_local: Mapped[time] = mapped_column(Time)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.ACTIVE)
    pause_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unreachable_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    contacts: Mapped[list[TrustedContact]] = relationship(
        "TrustedContact", back_populates="user", cascade="all, delete-orphan"
    )


class TrustedContact(Base):
    __tablename__ = "trusted_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    contact_tg_user_id: Mapped[int] = mapped_column(Integer, index=True)
    contact_chat_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[ContactStatus] = mapped_column(Enum(ContactStatus), default=ContactStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="contacts")

    __table_args__ = (UniqueConstraint("user_id", "contact_tg_user_id"),)


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date_local: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    photo_file_id: Mapped[str] = mapped_column(String(512))
    photo_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    geo_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyState(Base):
    __tablename__ = "daily_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    date_local: Mapped[date] = mapped_column(Date, primary_key=True)
    due_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[DailyStateEnum] = mapped_column(Enum(DailyStateEnum))
    reminders_sent_count: Mapped[int] = mapped_column(Integer, default=0)
    escalation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_prompt_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_prompt_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_notify_contacts: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    target_chat_id: Mapped[int] = mapped_column(Integer, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
