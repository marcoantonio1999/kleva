from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stream_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_sid: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ClaimCase(Base):
    __tablename__ = "claim_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_sid: Mapped[str] = mapped_column(String(64), index=True)
    caller_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    incident_summary: Mapped[str] = mapped_column(Text)
    incident_severity: Mapped[str] = mapped_column(String(24), default="media")
    claim_status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ComplaintCase(Base):
    __tablename__ = "complaint_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_sid: Mapped[str] = mapped_column(String(64), index=True)
    caller_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    complaint_summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(24), default="media")
    resolution_status: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EmergencyEscalation(Base):
    __tablename__ = "emergency_escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_sid: Mapped[str] = mapped_column(String(64), index=True)
    caller_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_channel: Mapped[str] = mapped_column(String(64), default="adjuster_and_emergency")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
