from datetime import datetime
from sqlalchemy import BigInteger, String, Integer, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import Optional


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    # WhatsApp (Botcorp) поля
    whatsapp_phone: Mapped[Optional[str]] = mapped_column(String(32), unique=True, index=True, nullable=True)
    whatsapp_contact_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    channel: Mapped[str] = mapped_column(String(16), default="telegram")  # "telegram" | "whatsapp"

    source: Mapped[str] = mapped_column(String(32), default="unknown")
    ab_group: Mapped[str] = mapped_column(String(8), default="A")

    current_step: Mapped[int] = mapped_column(Integer, default=0)
    max_step_reached: Mapped[int] = mapped_column(Integer, default=0)

    purchased: Mapped[bool] = mapped_column(Boolean, default=False)
    purchase_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    human_takeover: Mapped[bool] = mapped_column(Boolean, default=False)
    takeover_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    takeover_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    first_ai_reply_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    incoming_messages_count: Mapped[int] = mapped_column(Integer, default=0)
    mentioned_no_money: Mapped[bool] = mapped_column(Boolean, default=False)
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    last_push_sent_index: Mapped[int] = mapped_column(Integer, default=-1)
    last_push_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    events: Mapped[list["Event"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="events")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    content: Mapped[str] = mapped_column(Text)
    step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="messages")


class MediaCache(Base):
    __tablename__ = "media_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    file_id: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Index("ix_events_user_created", Event.user_id, Event.created_at)
Index("ix_messages_user_created", Message.user_id, Message.created_at)
