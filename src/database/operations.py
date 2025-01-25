"""Database operations for the application."""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session

from src.database.models import AFKEntry, RaidSignup, User, ClanMembership, GuildWelcomeMessage, RaidHelperEvent, RaidHelperSignup, GuildInfo, ProcessedEvent

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
    """Get all active AFK users, optionally filtered by clan, user_id, or discord_id."""
    current_time = datetime.utcnow()
    
    query = (
        db.query(User, AFKEntry)
        .join(AFKEntry, User.id == AFKEntry.user_id)
        .filter(
            and_(
                AFKEntry.is_active == True,
                AFKEntry.is_deleted == False,
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
    return (
        db.query(AFKEntry)
        .filter(
            AFKEntry.user_id == user.id,
            AFKEntry.is_deleted == False
        )
        .distinct(
            AFKEntry.start_date,
            AFKEntry.end_date,
            AFKEntry.reason
        )
        .order_by(
            AFKEntry.start_date,
            AFKEntry.end_date,
            AFKEntry.reason,
            AFKEntry.created_at.desc()
        )
        .limit(limit)
        .all()
    )

def get_afk_statistics(
    db: Session,
    clan_role_id: Optional[str] = None
) -> dict:
    """Get AFK statistics."""
    try:
        base_query = db.query(AFKEntry).join(User).filter(AFKEntry.is_deleted == False)
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
        total_users = db.query(
            func.count(
                func.distinct(AFKEntry.user_id)
            )
        ).filter(AFKEntry.is_deleted == False).scalar()
        
        # Calculate average duration only for completed entries
        avg_duration_query = db.query(
            func.avg(
                AFKEntry.end_date - AFKEntry.start_date
            )
        ).filter(
            AFKEntry.end_date != None,
            AFKEntry.start_date != None,
            AFKEntry.is_deleted == False
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
    all_entries: bool = False,
    afk_id: Optional[int] = None
) -> int:
    """Mark AFK entries as deleted.
    
    Args:
        db: Database session
        user: User object
        all_entries: Whether to mark all entries or only active ones as deleted
        afk_id: Optional specific AFK entry ID to mark as deleted
        
    Returns:
        Number of marked entries
    """
    current_time = datetime.utcnow()
    
    if afk_id is not None:
        # Mark specific AFK entry as deleted
        entry = db.query(AFKEntry).filter(
            AFKEntry.id == afk_id,
            AFKEntry.user_id == user.id,
            AFKEntry.is_deleted == False
        ).first()
        
        if not entry:
            raise ValueError(f"No AFK entry found with ID {afk_id} for this user")
            
        entry.is_deleted = True
        entry.is_active = False
        entry.ended_at = current_time
        db.commit()
        return 1
    
    # Mark multiple entries as deleted
    query = db.query(AFKEntry).filter(
        AFKEntry.user_id == user.id,
        AFKEntry.is_deleted == False
    )
    
    if not all_entries:
        query = query.filter(AFKEntry.is_active == True)
    
    marked_count = query.update({
        "is_deleted": True,
        "is_active": False,
        "ended_at": current_time
    })
    
    db.commit()
    return marked_count

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
    """Get all active and future AFK entries for a user."""
    current_time = datetime.utcnow()
    
    return (
        db.query(AFKEntry)
        .filter(
            and_(
                AFKEntry.user_id == user_id,
                AFKEntry.is_deleted == False,
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

def sync_clan_memberships(
    db: Session,
    clan_role_id: str,
    current_member_ids: list[str]
) -> tuple[list[str], list[str]]:
    """Synchronize clan memberships with current Discord role members.
    
    Args:
        db: Database session
        clan_role_id: Discord role ID of the clan
        current_member_ids: List of Discord user IDs currently in the role
        
    Returns:
        Tuple of (joined_members, left_members) Discord IDs
    """
    current_time = datetime.utcnow()
    joined_members = []
    left_members = []
    
    # Get all active memberships for this clan
    active_memberships = (
        db.query(ClanMembership)
        .join(User)
        .filter(
            ClanMembership.clan_role_id == clan_role_id,
            ClanMembership.is_active == True
        )
        .all()
    )
    
    # Create a map of active memberships by discord_id
    active_members = {
        m.user.discord_id: m for m in active_memberships
    }
    
    # Process current members
    for discord_id in current_member_ids:
        if discord_id not in active_members:
            # New member joined
            user = get_or_create_user(db, discord_id, str(discord_id))
            membership = ClanMembership(
                user_id=user.id,
                clan_role_id=clan_role_id,
                joined_at=current_time,
                is_active=True
            )
            db.add(membership)
            joined_members.append(discord_id)
    
    # Process members who left
    for discord_id, membership in active_members.items():
        if discord_id not in current_member_ids:
            # Member left
            membership.is_active = False
            membership.left_at = current_time
            left_members.append(discord_id)
    
    db.commit()
    return joined_members, left_members

def get_clan_membership_history(
    db: Session,
    discord_id: Optional[str] = None,
    clan_role_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_inactive: bool = False
) -> List[Tuple[User, ClanMembership]]:
    """Get clan membership history.
    
    Args:
        db: Database session
        discord_id: Optional Discord ID to filter by specific user
        clan_role_id: Optional clan role ID to filter by specific clan
        start_date: Optional start date to filter changes
        end_date: Optional end date to filter changes
        include_inactive: Whether to include inactive memberships
        
    Returns:
        List of tuples containing (User, ClanMembership)
    """
    query = (
        db.query(User, ClanMembership)
        .join(ClanMembership, User.id == ClanMembership.user_id)
    )
    
    # Apply filters
    if discord_id:
        query = query.filter(User.discord_id == discord_id)
        
    if clan_role_id:
        query = query.filter(ClanMembership.clan_role_id == clan_role_id)
        
    if not include_inactive:
        query = query.filter(ClanMembership.is_active == True)
        
    if start_date:
        query = query.filter(
            or_(
                ClanMembership.joined_at >= start_date,
                and_(
                    ClanMembership.left_at != None,
                    ClanMembership.left_at >= start_date
                )
            )
        )
        
    if end_date:
        query = query.filter(ClanMembership.joined_at <= end_date)
    
    # Order by joined_at date, most recent first
    query = query.order_by(ClanMembership.joined_at.desc())
    
    return query.all()

def get_clan_membership_changes(
    db: Session,
    clan_role_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Tuple[User, ClanMembership]]:
    """Get clan membership changes within a time period.
    
    Args:
        db: Database session
        clan_role_id: Optional clan role ID to filter by
        start_date: Optional start date for the period
        end_date: Optional end date for the period
        
    Returns:
        List of (User, ClanMembership) tuples
    """
    query = (
        db.query(User, ClanMembership)
        .join(ClanMembership)
    )
    
    if clan_role_id:
        query = query.filter(ClanMembership.clan_role_id == clan_role_id)
    
    if start_date:
        query = query.filter(
            or_(
                ClanMembership.joined_at >= start_date,
                ClanMembership.left_at >= start_date
            )
        )
    
    if end_date:
        query = query.filter(
            or_(
                ClanMembership.joined_at <= end_date,
                and_(
                    ClanMembership.left_at != None,
                    ClanMembership.left_at <= end_date
                )
            )
        )
    
    return query.order_by(ClanMembership.joined_at.desc()).all() 

def extend_afk(
    db: Session,
    user: User,
    afk_id: int,
    hours: int
) -> AFKEntry:
    """Extend an existing AFK entry by a number of hours.
    
    Args:
        db: Database session
        user: User object
        afk_id: ID of the AFK entry to extend
        hours: Number of hours to extend by
        
    Returns:
        Updated AFKEntry
        
    Raises:
        ValueError: If the AFK entry doesn't exist, belongs to another user,
                  or is already ended
    """
    # Get the AFK entry
    afk_entry = db.query(AFKEntry).filter(AFKEntry.id == afk_id).first()
    
    if not afk_entry:
        raise ValueError("AFK entry not found")
        
    if afk_entry.user_id != user.id:
        raise ValueError("This AFK entry belongs to another user")
        
    if not afk_entry.is_active:
        raise ValueError("Cannot extend an inactive AFK entry")
        
    if afk_entry.ended_at:
        raise ValueError("Cannot extend an AFK entry that has been ended early")
        
    # Calculate new end date
    afk_entry.end_date = afk_entry.end_date + timedelta(hours=hours)
    
    db.commit()
    db.refresh(afk_entry)
    return afk_entry 

def set_guild_welcome_message(
    db: Session,
    guild_role_id: str,
    message: str
) -> GuildWelcomeMessage:
    """Set or update welcome message for a guild."""
    welcome_msg = db.query(GuildWelcomeMessage).filter(
        GuildWelcomeMessage.guild_role_id == guild_role_id
    ).first()
    
    if welcome_msg:
        welcome_msg.message = message
        welcome_msg.updated_at = datetime.utcnow()
    else:
        welcome_msg = GuildWelcomeMessage(
            guild_role_id=guild_role_id,
            message=message
        )
        db.add(welcome_msg)
    
    db.commit()
    db.refresh(welcome_msg)
    return welcome_msg

def get_guild_welcome_message(
    db: Session,
    guild_role_id: str
) -> Optional[str]:
    """Get welcome message for a guild."""
    welcome_msg = db.query(GuildWelcomeMessage).filter(
        GuildWelcomeMessage.guild_role_id == guild_role_id
    ).first()
    
    return welcome_msg.message if welcome_msg else None

def get_all_welcome_messages(
    db: Session
) -> List[GuildWelcomeMessage]:
    """Get all welcome messages."""
    return db.query(GuildWelcomeMessage).all()

def add_user_to_guild(
    db: Session,
    user: User,
    guild_role_id: str
) -> ClanMembership:
    """Add a user to a guild (clan).
    
    Args:
        db: Database session
        user: User object
        guild_role_id: Discord role ID of the guild/clan
        
    Returns:
        Created ClanMembership object
        
    Raises:
        ValueError: If user is already in the guild
    """
    # Check if user is already in this guild
    existing = db.query(ClanMembership).filter(
        and_(
            ClanMembership.user_id == user.id,
            ClanMembership.clan_role_id == guild_role_id,
            ClanMembership.is_active == True
        )
    ).first()
    
    if existing:
        raise ValueError("User is already a member of this guild")
    
    # Create new membership
    membership = ClanMembership(
        user_id=user.id,
        clan_role_id=guild_role_id,
        joined_at=datetime.utcnow(),
        is_active=True
    )
    
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership

def remove_user_from_guild(
    db: Session,
    user: User,
    guild_role_id: str
) -> ClanMembership:
    """Remove a user from a guild (clan).
    
    Args:
        db: Database session
        user: User object
        guild_role_id: Discord role ID of the guild/clan
        
    Returns:
        Updated ClanMembership object
        
    Raises:
        ValueError: If user is not in the guild
    """
    # Check if user is in this guild
    membership = db.query(ClanMembership).filter(
        and_(
            ClanMembership.user_id == user.id,
            ClanMembership.clan_role_id == guild_role_id,
            ClanMembership.is_active == True
        )
    ).first()
    
    if not membership:
        raise ValueError("User is not a member of this guild")
    
    # Update membership
    membership.is_active = False
    membership.left_at = datetime.utcnow()
    
    db.commit()
    db.refresh(membership)
    return membership 

def create_or_update_raidhelper_event(db: Session, event_data: Dict[str, Any]) -> RaidHelperEvent:
    """Create or update a RaidHelper event."""
    event = db.query(RaidHelperEvent).filter(RaidHelperEvent.id == event_data["id"]).first()
    
    if not event:
        event = RaidHelperEvent(
            id=event_data["id"],
            title=event_data["title"],
            description=event_data.get("description"),
            leader_id=event_data["leaderId"],
            leader_name=event_data["leaderName"],
            channel_id=event_data["channelId"],
            channel_name=event_data.get("channelName"),
            start_time=datetime.fromtimestamp(int(event_data["startTime"])),
            end_time=datetime.fromtimestamp(int(event_data["endTime"])) if event_data.get("endTime") else None,
            close_time=datetime.fromtimestamp(int(event_data["closeTime"])) if event_data.get("closeTime") else None,
            last_updated=datetime.fromtimestamp(int(event_data["lastUpdated"])) if event_data.get("lastUpdated") else None,
            template_id=event_data.get("templateId"),
            signup_count=int(event_data.get("signUpCount", 0))
        )
        db.add(event)
    else:
        # Update existing event
        event.title = event_data["title"]
        event.description = event_data.get("description")
        event.leader_id = event_data["leaderId"]
        event.leader_name = event_data["leaderName"]
        event.channel_id = event_data["channelId"]
        event.channel_name = event_data.get("channelName")
        event.start_time = datetime.fromtimestamp(int(event_data["startTime"]))
        event.end_time = datetime.fromtimestamp(int(event_data["endTime"])) if event_data.get("endTime") else None
        event.close_time = datetime.fromtimestamp(int(event_data["closeTime"])) if event_data.get("closeTime") else None
        event.last_updated = datetime.fromtimestamp(int(event_data["lastUpdated"])) if event_data.get("lastUpdated") else None
        event.template_id = event_data.get("templateId")
        event.signup_count = int(event_data.get("signUpCount", 0))
    
    db.commit()
    return event

def update_raidhelper_signups(db: Session, event_id: str, signups_data: List[Dict[str, Any]]) -> List[RaidHelperSignup]:
    """Update signups for a RaidHelper event."""
    # Get existing signups for this event
    existing_signups = {
        signup.user_id: signup 
        for signup in db.query(RaidHelperSignup).filter(RaidHelperSignup.event_id == event_id).all()
    }
    
    # Track processed user IDs
    processed_user_ids = set()
    
    # Update or create signups
    signups = []
    for signup_data in signups_data:
        user_id = signup_data["userId"]
        processed_user_ids.add(user_id)
        
        if user_id in existing_signups:
            # Update existing signup if values have changed
            signup = existing_signups[user_id]
            has_changes = False
            
            # Check each field for changes
            if signup.user_name != signup_data["name"]:
                signup.user_name = signup_data["name"]
                has_changes = True
            if signup.status != signup_data["status"]:
                signup.status = signup_data["status"]
                has_changes = True
            if signup.class_name != signup_data.get("className"):
                signup.class_name = signup_data.get("className")
                has_changes = True
            if signup.spec_name != signup_data.get("specName"):
                signup.spec_name = signup_data.get("specName")
                has_changes = True
            if signup.position != signup_data.get("position"):
                signup.position = signup_data.get("position")
                has_changes = True
            
            # Update entry_time only if other changes were made
            if has_changes:
                signup.entry_time = datetime.fromtimestamp(int(signup_data["entryTime"]))
                signup.updated_at = datetime.utcnow()
                logging.info(f"Updated signup for user {user_id} in event {event_id}")
        else:
            # Create new signup
            signup = RaidHelperSignup(
                event_id=event_id,
                user_id=user_id,
                user_name=signup_data["name"],
                entry_time=datetime.fromtimestamp(int(signup_data["entryTime"])),
                status=signup_data["status"],
                class_name=signup_data.get("className"),
                spec_name=signup_data.get("specName"),
                position=signup_data.get("position")
            )
            db.add(signup)
            logging.info(f"Created new signup for user {user_id} in event {event_id}")
        
        signups.append(signup)
    
    # Remove signups that no longer exist in RaidHelper
    for user_id, signup in existing_signups.items():
        if user_id not in processed_user_ids and signup.class_name != "No Info":
            db.delete(signup)
            logging.info(f"Removed signup for user {user_id} from event {event_id}")
    
    db.commit()
    return signups

def get_active_raidhelper_events(db: Session) -> List[RaidHelperEvent]:
    """Get all active RaidHelper events (where close_time is in the future)."""
    current_time = datetime.utcnow()
    return db.query(RaidHelperEvent)\
        .filter(RaidHelperEvent.close_time > current_time)\
        .order_by(RaidHelperEvent.start_time)\
        .all()

def get_user_event_history(db: Session, user_id: str, limit: int = 10) -> List[RaidHelperSignup]:
    """Get event history for a specific user."""
    return db.query(RaidHelperSignup)\
        .filter(RaidHelperSignup.user_id == user_id)\
        .order_by(desc(RaidHelperSignup.entry_time))\
        .limit(limit)\
        .all()

def add_guild_info(db: Session, role_id: str, name: str) -> GuildInfo:
    """Add or update guild information in the database."""
    guild_info = db.query(GuildInfo).filter(GuildInfo.role_id == role_id).first()
    
    if guild_info:
        guild_info.name = name
    else:
        guild_info = GuildInfo(role_id=role_id, name=name)
        db.add(guild_info)
    
    db.commit()
    db.refresh(guild_info)
    return guild_info 

def mark_event_as_processed(db: Session, event_id: str) -> ProcessedEvent:
    """Mark an event as processed."""
    processed_event = ProcessedEvent(event_id=event_id)
    db.add(processed_event)
    db.commit()
    return processed_event

def is_event_processed(db: Session, event_id: str) -> bool:
    """Check if an event has been processed."""
    return db.query(ProcessedEvent).filter(ProcessedEvent.event_id == event_id).first() is not None 