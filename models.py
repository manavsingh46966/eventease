from datetime import datetime, timezone

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String,
                        UniqueConstraint)
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String(300), nullable=False, default="")
    date = Column(String(10), nullable=False)       # YYYY-MM-DD
    venue = Column(String(100), nullable=False)
    total_seats = Column(Integer, nullable=False)
    registrations = relationship("Registration", back_populates="event",
                                 cascade="all, delete-orphan")


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("event_id", "roll_no", name="uq_event_roll"),)
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    roll_no = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    event = relationship("Event", back_populates="registrations")
