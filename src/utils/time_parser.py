"""Time parsing utilities."""
from datetime import datetime, timedelta
from typing import Tuple

def parse_time(time_str: str) -> Tuple[int, int]:
    """Parse time string in various formats (HH:MM or HHMM).
    
    Args:
        time_str: Time string in format HH:MM or HHMM
        
    Returns:
        Tuple of (hour, minute)
        
    Raises:
        ValueError: If time format is invalid
    """
    clean_time = time_str.replace(':', '')
    
    if len(clean_time) != 4:
        raise ValueError("Time must be in format: HHMM or HH:MM")
    
    try:
        hour = int(clean_time[:2])
        minute = int(clean_time[2:])
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid hour or minute")
            
        return hour, minute
    except ValueError as e:
        raise ValueError(f"Invalid time format: {str(e)}")

def parse_date(date_str: str, time_str: str) -> datetime:
    """Parse date string and time string into datetime object.
    
    Args:
        date_str: Date string in format DD.MM, DD/MM or DDMM
        time_str: Time string in format HH:MM or HHMM
        
    Returns:
        datetime object
        
    Raises:
        ValueError: If date or time format is invalid
    """
    current_date = datetime.utcnow()
    
    clean_date = date_str.replace('.', '').replace('/', '')
    if len(clean_date) != 4:
        raise ValueError("Date must be in format: DDMM, DD/MM or DD.MM")
    
    try:
        day = int(clean_date[:2])
        month = int(clean_date[2:])
        
        if not (1 <= month <= 12 and 1 <= day <= 31):
            raise ValueError("Invalid day or month")
            
        hour, minute = parse_time(time_str)
        
        # Start with current year
        year = current_date.year
        
        # Create datetime object
        date_time = datetime(year, month, day, hour, minute)
        
        # If date is in the past, add a year
        if date_time < current_date:
            date_time = datetime(year + 1, month, day, hour, minute)
            
        return date_time
        
    except ValueError as e:
        raise ValueError(f"Invalid date or time format: {str(e)}")

def format_duration(duration: timedelta) -> str:
    """Format a timedelta into a human-readable string.
    
    Args:
        duration: timedelta object
        
    Returns:
        Formatted duration string
    """
    days = duration.days
    hours = duration.seconds // 3600
    minutes = (duration.seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} {'day' if days == 1 else 'days'}")
    if hours > 0:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    
    if not parts:
        return "less than a minute"
    
    if len(parts) == 1:
        return parts[0]
    
    return f"{', '.join(parts[:-1])} and {parts[-1]}" 