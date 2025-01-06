"""Database operations for the application."""
import logging
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
    1. Check for any existing active or future AFK entries that overlap with the new period
    2. If there are overlapping entries, raise an error
    3. Create the new AFK entry with is_active based on current time:
       - True if current time is between start_date and end_date
       - False if start_date is in the future
    """
    current_time = datetime.utcnow()
    
    # Check for overlapping entries
    overlapping_entries = db.query(AFKEntry).filter(
        and_(
            AFKEntry.user_id == user.id,
            AFKEntry.ended_at == None,  # Only check entries that haven't been ended early
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
    ).all()
    
    if overlapping_entries:
        # Get the first overlapping entry for the error message
        overlap = overlapping_entries[0]
        raise ValueError(
            f"You already have an AFK entry during this time period!\n"
            f"From: <t:{int(overlap.start_date.timestamp())}:f>\n"
            f"Until: <t:{int(overlap.end_date.timestamp())}:f>\n"
            f"Reason: {overlap.reason}"
        )
    
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
    user_id: Optional[int] = None,
    clan_role_id: Optional[str] = None,
    discord_id: Optional[str] = None
) -> List[Tuple[User, AFKEntry]]:
    """Get all active AFK users, optionally filtered by clan, user_id, or discord_id.
    
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
    
    if user_id:
        query = query.filter(User.id == user_id)
    
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
) -> dict:
    """Get AFK statistics."""
    try:
        base_query = db.query(AFKEntry).join(User)
        if clan_role_id:
            base_query = base_query.filter(User.clan_role_id == clan_role_id)
        
        current_time = datetime.utcnow()
        
        # Total AFK entries
        total_entries = base_query.count()
        
        # Currently active entries
        active_entries = base_query.filter(
            and_(
                AFKEntry.is_active == True,
                AFKEntry.start_date <= current_time,
                AFKEntry.end_date >= current_time,
                or_(
                    AFKEntry.ended_at == None,
                    AFKEntry.ended_at >= current_time
                )
            )
        ).count()
        
        # Total unique users
        total_users = db.query(func.count(func.distinct(AFKEntry.user_id))).scalar()
        
        # Calculate average duration only for completed entries
        avg_duration_query = db.query(
            func.avg(
                AFKEntry.end_date - AFKEntry.start_date
            )
        ).filter(
            AFKEntry.end_date != None,
            AFKEntry.start_date != None
        )
        
        average_duration = avg_duration_query.scalar()
        
        return {
            "total_entries": total_entries,
            "active_entries": active_entries,
            "total_users": total_users,
            "average_duration": average_duration
        }
        
    except Exception as e:
        logging.error(f"Error getting AFK statistics: {e}")
        return {
            "total_entries": 0,
            "active_entries": 0,
            "total_users": 0,
            "average_duration": None
        }

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
    """Get all members of a specific clan.
    
    Args:
        db: Database session
        clan_role_id: Role ID of the clan
        
    Returns:
        List of User objects
    """
    logging.info(f"Fetching members for clan role ID: {clan_role_id}")
    members = db.query(User).filter(User.clan_role_id == clan_role_id).all()
    logging.info(f"Found {len(members)} members")
    return members

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

def update_afk_active_status(db: Session) -> None:
    """Update the is_active status of all AFK entries based on current time."""
    current_time = datetime.utcnow()
    
    # Get all AFK entries
    afk_entries = db.query(AFKEntry).all()
    
    for entry in afk_entries:
        try:
            # Skip entries with None values for required fields
            if not entry.start_date or not entry.end_date:
                entry.is_active = False
                continue

            # Check if entry has been manually ended
            if entry.ended_at:
                entry.is_active = False
                continue

            # Entry is active if current time is between start and end date
            is_active = entry.start_date <= current_time <= entry.end_date
            
            # Update if status changed
            if entry.is_active != is_active:
                entry.is_active = is_active
                
        except Exception as e:
            logging.error(f"Error updating AFK entry {entry.id}: {e}")
            # Set to inactive on error
            entry.is_active = False
            
    db.commit()

def remove_future_afk(db: Session, user: User, afk_id: int) -> None:
    """Remove a future AFK entry for a user.
    
    Args:
        db: Database session
        user: User object
        afk_id: ID of the AFK entry to remove
        
    Raises:
        ValueError: If the AFK entry doesn't exist, belongs to another user,
                  or is not a future entry
    """
    # Get the AFK entry
    afk_entry = db.query(AFKEntry).filter(AFKEntry.id == afk_id).first()
    
    if not afk_entry:
        raise ValueError("AFK entry not found")
        
    if str(afk_entry.user_id) != str(user.id):
        raise ValueError("This AFK entry belongs to another user")
        
    # Check if this is a future entry
    current_time = datetime.utcnow()
    if afk_entry.start_date <= current_time:
        raise ValueError("You can only remove future AFK entries")
        
    # Delete the entry
    db.delete(afk_entry)
    db.commit()

def get_user_active_and_future_afk(
    db: Session,
    user_id: int
) -> List[AFKEntry]:
    """Get all active and future AFK entries for a user.
    
    Returns entries where:
    1. ended_at is NULL AND
    2. Either:
       - is_active is True (current active entries) OR
       - is_active is False (future entries)
    """
    current_time = datetime.utcnow()
    
    return (
        db.query(AFKEntry)
        .filter(
            and_(
                AFKEntry.user_id == user_id,
                AFKEntry.ended_at == None,
                or_(
                    # Active entries
                    and_(
                        AFKEntry.is_active == True,
                        AFKEntry.start_date <= current_time,
                        AFKEntry.end_date >= current_time
                    ),
                    # Future entries
                    and_(
                        AFKEntry.start_date > current_time
                    )
                )
            )
        )
        .order_by(AFKEntry.start_date.asc())
        .all()
    ) 

def get_clan_active_and_future_afk(
    db: Session,
    clan_role_id: Optional[str] = None
) -> List[Tuple[User, AFKEntry]]:
    """Get all active and future AFK entries for a clan.
    
    Returns entries where:
    1. ended_at is NULL AND
    2. Either:
       - is_active is True (current active entries) OR
       - start_date is in the future
    
    Args:
        db: Database session
        clan_role_id: Optional clan role ID to filter by
        
    Returns:
        List of (User, AFKEntry) tuples
    """
    current_time = datetime.utcnow()
    
    query = (
        db.query(User, AFKEntry)
        .join(AFKEntry, User.id == AFKEntry.user_id)
        .filter(
            and_(
                AFKEntry.ended_at == None,
                or_(
                    # Active entries
                    and_(
                        AFKEntry.is_active == True,
                        AFKEntry.start_date <= current_time,
                        AFKEntry.end_date >= current_time
                    ),
                    # Future entries
                    AFKEntry.start_date > current_time
                )
            )
        )
    )
    
    if clan_role_id:
        query = query.filter(User.clan_role_id == clan_role_id)
    
    return query.order_by(AFKEntry.start_date.asc()).all() 