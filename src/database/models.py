"""Database models for the application."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class GuildInfo(Base):
    """Model for storing guild information."""
    __tablename__ = "guild_info"

    id = Column(Integer, primary_key=True)
    role_id = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    clan_memberships = relationship("ClanMembership", back_populates="user")

class AFKEntry(Base):
    """AFK status entry model."""
    __tablename__ = "afk_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    reason = Column(Text)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
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

class ClanMembership(Base):
    """Clan membership tracking model."""
    __tablename__ = "clan_memberships"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    clan_role_id = Column(String(20), nullable=False)
    joined_at = Column(DateTime, nullable=False)
    left_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="clan_memberships")

class GuildWelcomeMessage(Base):
    """Welcome message model for guilds."""
    __tablename__ = "guild_welcome_messages"

    id = Column(Integer, primary_key=True)
    guild_role_id = Column(String(20), nullable=False, unique=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProcessedEvent(Base):
    """Model for tracking processed events."""
    __tablename__ = "processed_events"

    event_id = Column(String(20), primary_key=True)
    processed_at = Column(DateTime, default=datetime.utcnow)

class RaidHelperEvent(Base):
    """Model for storing RaidHelper events."""
    __tablename__ = "raidhelper_events"

    id = Column(String(20), primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    leader_id = Column(String(20))
    leader_name = Column(String(100))
    channel_id = Column(String(20))
    channel_name = Column(String(100))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    close_time = Column(DateTime)
    last_updated = Column(DateTime)
    template_id = Column(String(20))
    signup_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    signups = relationship("RaidHelperSignup", back_populates="event")

class RaidHelperSignup(Base):
    """Model for storing RaidHelper event signups."""
    __tablename__ = "raidhelper_signups"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(20), ForeignKey("raidhelper_events.id"), nullable=False)
    user_id = Column(String(20), nullable=False)
    user_name = Column(String(100), nullable=False)
    entry_time = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False)  # primary, bench, tentative, etc.
    class_name = Column(String(50))
    spec_name = Column(String(50))
    position = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    event = relationship("RaidHelperEvent", back_populates="signups")

    class Meta:
        """Meta class for RaidHelperSignup."""
        unique_together = (("event_id", "user_id"),)  # Ein User kann nur einmal pro Event angemeldet sein 