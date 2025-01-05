"""Database operations for the application."""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from src.database.models import AFKEntry, RaidSignup, User

def get_or_create_user(
    db: Session,
    discord_id: str,
    username: str,
    display_name: Optional[str] = None,
    clan_role_id: Optional[str] = None
) -> User:
    """Get or create a user in the database."""
    user = db.query(User).filter(User.discord_id == discord_id).first()
    
    if not user:
        user = User(
            discord_id=discord_id,
            username=username,
            display_name=display_name,
            clan_role_id=clan_role_id
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update user information if it has changed
        update_needed = False
        if user.username != username:
            user.username = username
            update_needed = True
        if user.display_name != display_name:
            user.display_name = display_name
            update_needed = True
        if user.clan_role_id != clan_role_id:
            user.clan_role_id = clan_role_id
            update_needed = True
            
        if update_needed:
            db.commit()
            db.refresh(user)
    
    return user

def set_afk(
    db: Session,
    user: User,
    start_date: datetime,
    end_date: datetime,
    reason: str
) -> AFKEntry:
    """Set a user as AFK.
    
    When setting a new AFK:
    1. Deactivate any existing active AFK entries that overlap with the new period
    2. Create the new AFK entry with is_active based on current time:
       - True if current time is between start_date and end_date
       - False if start_date is in the future
    """
    current_time = datetime.utcnow()
    
    # Deactivate any existing active AFK entries that overlap with the new period
    overlapping_entries = db.query(AFKEntry).filter(
        and_(
            AFKEntry.user_id == user.id,
            AFKEntry.is_active == True,
            or_(
                # New period starts during existing period
                and_(
                    AFKEntry.start_date <= start_date,
                    AFKEntry.end_date >= start_date
                ),
                # New period ends during existing period
                and_(
                    AFKEntry.start_date <= end_date,
                    AFKEntry.end_date >= end_date
                ),
                # New period completely contains existing period
                and_(
                    AFKEntry.start_date >= start_date,
                    AFKEntry.end_date <= end_date
                )
            )
        )
    )
    
    for entry in overlapping_entries:
        entry.is_active = False
        entry.ended_at = current_time
    
    # Create new AFK entry
    # Set is_active based on current time and start_date
    is_active = current_time >= start_date
    
    afk_entry = AFKEntry(
        user_id=user.id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        is_active=is_active
    )
    
    db.add(afk_entry)
    db.commit()
    db.refresh(afk_entry)
    return afk_entry

def get_active_afk(
    db: Session,
    clan_role_id: Optional[str] = None,
    discord_id: Optional[str] = None
) -> List[Tuple[User, AFKEntry]]:
    """Get all active AFK users, optionally filtered by clan or discord_id.
    
    An AFK entry is considered active if:
    1. is_active is True
    2. Current time is between start_date and end_date
    3. ended_at is either NULL or after the current time
    """
    current_time = datetime.utcnow()
    
    query = (
        db.query(User, AFKEntry)
        .join(AFKEntry, User.id == AFKEntry.user_id)
        .filter(
            and_(
                AFKEntry.is_active == True,
                AFKEntry.start_date <= current_time,
                AFKEntry.end_date >= current_time,
                or_(
                    AFKEntry.ended_at == None,
                    AFKEntry.ended_at >= current_time
                )
            )
        )
    )
    
    if clan_role_id:
        query = query.filter(User.clan_role_id == clan_role_id)
    
    if discord_id:
        query = query.filter(User.discord_id == discord_id)
    
    return query.all()

def get_user_afk_history(
    db: Session,
    user: User,
    limit: int = 5
) -> List[AFKEntry]:
    """Get AFK history for a specific user."""
    return db.query(AFKEntry).filter(
        AFKEntry.user_id == user.id
    ).order_by(AFKEntry.created_at.desc()).limit(limit).all()

def get_afk_statistics(
    db: Session,
    clan_role_id: Optional[str] = None
) -> Tuple[int, int, int, int, float]:
    """Get AFK statistics."""
    base_query = db.query(AFKEntry).join(User)
    if clan_role_id:
        base_query = base_query.filter(User.clan_role_id == clan_role_id)
    
    current_time = datetime.utcnow()
    
    # Total AFK entries
    total_afk = base_query.count()
    
    # Unique users
    unique_users = base_query.with_entities(func.count(func.distinct(AFKEntry.user_id))).scalar()
    
    # Currently active
    active_now = base_query.filter(
        and_(
            AFKEntry.is_active == True,
            AFKEntry.start_date <= current_time,
            AFKEntry.end_date > current_time
        )
    ).count()
    
    # Scheduled for future
    scheduled_future = base_query.filter(
        and_(
            AFKEntry.is_active == True,
            AFKEntry.start_date > current_time
        )
    ).count()
    
    # Average duration in days
    avg_duration = db.query(
        func.avg(
            func.julianday(
                func.coalesce(AFKEntry.ended_at, AFKEntry.end_date)
            ) - func.julianday(AFKEntry.start_date)
        )
    ).scalar()
    
    return total_afk, unique_users, active_now, scheduled_future, avg_duration or 0.0

def delete_afk_entries(
    db: Session,
    user: User,
    all_entries: bool = False
) -> int:
    """Delete AFK entries for a user."""
    query = db.query(AFKEntry).filter(AFKEntry.user_id == user.id)
    
    if not all_entries:
        query = query.filter(AFKEntry.is_active == True)
    
    deleted_count = query.delete()
    db.commit()
    return deleted_count

def track_raid_signup(
    db: Session,
    user: User,
    event_id: str,
    status: str
) -> RaidSignup:
    """Track a raid signup."""
    signup = RaidSignup(
        user_id=user.id,
        event_id=event_id,
        status=status
    )
    
    db.add(signup)
    db.commit()
    db.refresh(signup)
    return signup

def get_clan_members(
    db: Session,
    clan_role_id: str
) -> List[User]:
    """Get all members of a specific clan."""
    return db.query(User).filter(User.clan_role_id == clan_role_id).all()

def update_afk_status(
    db: Session,
    user: User,
    all_entries: bool = False
) -> int:
    """Update AFK entries to inactive for a user."""
    query = db.query(AFKEntry).filter(AFKEntry.user_id == user.id)
    
    if not all_entries:
        query = query.filter(AFKEntry.is_active == True)
    
    current_time = datetime.utcnow()
    updated_count = query.update({
        "is_active": False,
        "ended_at": current_time
    })
    
    db.commit()
    return updated_count 

def update_afk_active_status(db: Session) -> int:
    """Update is_active status for all AFK entries based on current time."""
    current_time = datetime.utcnow()
    
    # Update future entries
    future_count = db.query(AFKEntry).filter(
        and_(
            AFKEntry.is_active == True,
            AFKEntry.start_date > current_time
        )
    ).update({
        "is_active": False
    })
    
    # Update expired entries
    expired_count = db.query(AFKEntry).filter(
        and_(
            AFKEntry.is_active == True,
            AFKEntry.end_date < current_time
        )
    ).update({
        "is_active": False,
        "ended_at": current_time
    })
    
    db.commit()
    return future_count + expired_count 