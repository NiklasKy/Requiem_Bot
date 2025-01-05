"""Database models for the application."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    """Discord user model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    discord_id = Column(String(20), unique=True, nullable=False)
    username = Column(String(100), nullable=False)
    display_name = Column(String(100))
    clan_role_id = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    afk_entries = relationship("AFKEntry", back_populates="user")

class AFKEntry(Base):
    """AFK status entry model."""
    __tablename__ = "afk_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    reason = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="afk_entries")

class RaidSignup(Base):
    """Raid signup tracking model."""
    __tablename__ = "raid_signups"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(String(50), nullable=False)
    signup_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), nullable=False)  # e.g., "confirmed", "tentative", "declined"

    # Relationships
    user = relationship("User") 